# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The configuration loader: the engine side that MAKES a run context (stage 124).

:func:`read_config_and_transform` reads the tree under ``<root>/cfg``,
renders and structures it, builds and registers every builder, constructs
the :class:`~.run_context.RunContext`, binds the context to each builder
and to the process (:func:`~.run_context.bind_current`), makes the run's
:class:`~.finalizer.Finalizer`, and reads the domain-item kinds
(:class:`ItemKind`) into the registry. The context it returns knows
everything and loads nothing; the loading lives here.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import is_dataclass
from .models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
import logging
import os
from pathlib import Path
from datetime import datetime
from pprint import pformat
from typing import Any
import typer
import yaml

from cs_image_system.base.models.base_image import BaseImage

from .orchestrator import Orchestrator, TemplateResolver

from .models.user import User
from .models.ia_config import IAConfig
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .basic.builder_base_image import ImageBuilderBase
    from .basic.builder_base_instance import InstanceBuilderBase
    from .basic.builder_base_mod import ModBuilderBase
    from .basic.builder_base_runtime import RuntimeBuilderBase
from . import registry
from .loader import load_plugins
from .template_utils import cycle_main_yaml, read_and_preprocess_yaml_files
from .encryption import decrypt_tree, decrypted_plaintexts, refuse_markers_at
from .reserved_names import refuse_invalid_config_keys, refuse_reserved_names
from .run_context import RunContext, bind_current
from .finalizer import Finalizer
from .orchestrator import reset_unresolved_fks
from .models.ia_config import DEFAULT_DATEFORMAT
from .image_sources import ImageSourceCatalog, default_os_type

log = logging.getLogger(__name__)

from .constants import (
    BASE_IMAGES,
    GROUPS,
    IMAGES,
    INSTANCES,
    OOPS_DEFAULTS,
    PLUGIN_TYPES,
    STORAGES,
    VCT,
)

from .models.group import Group
from .models.image import Image
from .models.instance import Instance
from .models.storage import Storage
from .models.group_builder import GroupBuilderModel
from .models.image_builder_model import ImageBuilderModel
from .models.instance_builder import InstanceBuilderModel
from .models.mod_builder import ModBuilderModel
from .models.os_builder_model import OsBuilderModel
from .models.runtime import RuntimeBuilderModel
from .models.state_builder import StateBuilderModel
from .models.storage_builder import StorageBuilderModel
from .models.user_builder import UserBuilderModel

from .models.executable import ExecutableModel

from .basic.builder_base import BuilderBase
from .models.builder_model import BuilderModel, NameTyped
from cs_image_system.contract.core import BuilderModelProtocol

PLUGIN_TYPEMAP: dict[str, type] = {
    "base" : dict,
    "runtime": RuntimeBuilderModel,
    "state": StateBuilderModel,
    "modification": ModBuilderModel,
    "storage": StorageBuilderModel,
    "group": GroupBuilderModel,
    "user": UserBuilderModel,
    "os": OsBuilderModel,
    "image": ImageBuilderModel,
    "instance": InstanceBuilderModel,
    "other": dict,
    "executables": ExecutableModel,
}


@dataclass(frozen=True, config=CSIS_MODEL_CONFIG)
class ItemKind:
    """Declarative spec for reading one domain-item collection from YAML.

    The generic reader :func:`read_item_kind` turns each spec
    into the read -> structure -> resolve -> register -> attach-to-builder flow that
    used to be copy-pasted as ``read_*_from_files``. Register additional kinds via
    :func:`register_item_kind` -- this is the extension seam for a plugin that
    manages a new kind of domain item.

    ``model_cls`` must be a :class:`~.models.builder_model.NameTyped` subclass:
    the reader relies on its ``name``/``type`` fields (``type`` is the FK naming
    the owning builder) and its registrability.
    """
    name: str                                   # collection name (the registry holds the items)
    source_dir: str                             # subdir under working_path (constants.IMAGES, ...)
    model_cls: type[NameTyped]                  # dataclass the YAML items structure into
    builder_vct: VCT                            # classification of the builder that owns each item
    attach: Callable[[Any, Any], None]          # (builder, item) -> None, e.g. b.add_image(item)
    default_missing_type_to: VCT | None = None  # if item.type_ is a DEFAULT sentinel, fill from this VCT's default
    validate: Callable[[RunContext, list[Any]], None] | None = None
    base_only: bool = False                     # read in base-only mode instead of the normal flow


_ITEM_KINDS: list[ItemKind] = []


def item_model_class(reg: "registry.Registry", spec: ItemKind) -> type:
    """The class a kind's items structure into: the plugin-injected default
    model of the kind's classification when one is registered and extends
    the kind's own model (an identity plugin's user subclass carrying its
    directory's profile fields), else the kind's model. The YAML key and
    the ``isinstance`` check stay the kind's: a subclass only adds fields."""
    classify = getattr(spec.model_cls, "csis_classifier", None)
    if not callable(classify):
        return spec.model_cls
    try:
        classifier = classify()
    except Exception:  # noqa: BLE001 - a model that classifies nothing has no injected default
        return spec.model_cls
    if not isinstance(classifier, VCT):
        return spec.model_cls
    name = reg.defaults_registry.get(classifier)
    injected = reg.get_model(classifier, name) if name else None
    if isinstance(injected, type) and issubclass(injected, spec.model_cls) and injected is not spec.model_cls:
        return injected
    return spec.model_cls


def register_item_kind(spec: ItemKind) -> None:
    """Register a domain-item kind to be read by the loader once the context exists."""
    _ITEM_KINDS.append(spec)


def item_kinds() -> list[ItemKind]:
    """The registered domain-item kinds, in read order."""
    return list(_ITEM_KINDS)



def read_item_kind(ctx: RunContext, spec: ItemKind) -> list[Any]:
    """Generic reader replacing the per-type ``read_*_from_files`` methods.

    Reads the YAML for a domain-item collection, structures each item into
    ``spec.model_cls``, resolves templates, registers the item, resolves its
    owning builder from the registry (alias-aware) and attaches it, then runs
    the kind's optional cross-item validation. ``ctx`` is the context the
    items are read INTO (its working path, registry and overlays); until
    stage 124 this was the context's own ``_read_item_kind`` method.
    """
    yaml_files = get_files_by_extensions(ctx.working_path / spec.source_dir)
    cvt = Orchestrator().get_converter()
    template_resolver = TemplateResolver()
    reset_unresolved_fks()          # stage 48.3: a fresh load starts with no unresolved foreign keys
    reg = ctx.reg
    items: list[NameTyped] = []
    model_cls = item_model_class(reg, spec)
    try:
        read_dict = read_and_preprocess_yaml_files(spec.model_cls, yaml_files)[0]
        apply_overlays(ctx, spec, read_dict)
        for _key, raw in read_dict.items():
            structured = cvt.structure(raw, model_cls)
            for ri in (structured if isinstance(structured, list) else [structured]):
                if isinstance(ri, spec.model_cls):
                    items.append(ri)
                    template_resolver.flatten_dataclass(ri)
                    reg.register_built_instance(ri)
    except Exception as e:
        log.error(f"Error parsing {yaml_files}: {e}")
        raise
    template_resolver.resolve_all()
    for it in items:
        if spec.default_missing_type_to is not None and it.type_ in OOPS_DEFAULTS:
            log.debug(f"{spec.name} item '{it.get_name()}' using default builder")
            dflt = reg.get_default_for(spec.default_missing_type_to)
            if not dflt:
                raise ValueError(
                    f"{spec.name} item '{it.get_name()}' has no builder type and no "
                    f"default is registered for {spec.default_missing_type_to}"
                )
            it.type_ = dflt
        builder = reg.get_instance_by_name_or_alias(spec.builder_vct, it.type_)
        if builder is None:
            raise ValueError(
                f"{spec.name} builder '{it.type_}' specified for '{it.get_name()}' not configured"
            )
        spec.attach(builder, it)
    if spec.validate is not None:
        spec.validate(ctx, items)
    log.info(f"Total {spec.name} read: {len(items)}")
    return items


def get_files_by_extensions(
    path: Path,
    extensions: list[str] | None = None,
    recursive: bool = True,
) -> list[Path]:
    """Read all files from a directory path and return files with specified extensions.

    Args:
        path: Directory path to search for files
        extensions: List of file extensions to filter by (default: ['.yaml', '.yml'])
        recursive: Whether to search subdirectories recursively (default: True)

    Returns:
        List of Path objects for files matching the specified extensions

    Raises:
        ValueError: If path is not a directory or doesn't exist
    """
    if extensions is None:
        extensions = [".yaml", ".yml"]

    if not path.exists():
        raise ValueError(f"Path does not exist: {path}")

    if not path.is_dir():
        raise ValueError(f"Path is not a directory: {path}")

    # Normalize extensions to lowercase and ensure they start with a dot
    normalized_extensions = []
    for ext in extensions:
        if not ext.startswith("."):
            ext = "." + ext
        normalized_extensions.append(ext)

    files = []

    if recursive:
        # Use recursive glob pattern
        for file_path in path.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in normalized_extensions:
                files.append(file_path)
    else:
        # Only search immediate directory
        for file_path in path.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in normalized_extensions:
                files.append(file_path)

    return sorted(files)


def apply_overlays(ctx: Any, spec: ItemKind, read_dict: dict[str, Any]) -> None:
    """Merge every overlay's entries for this kind over the tree's: a named
    entry that exists is updated key by key (``state: destroyed`` on a
    declared storage), a new one is appended (a cycle's instance). The tree
    on disk is never touched -- that is the point (stage 8). A context
    without overlays (unit-test stand-ins included) is a no-op."""
    overlays = getattr(ctx, "overlays", None) or []
    data_list = getattr(ctx, "_overlay_data", None) or []
    key = spec.model_cls.klazz_yaml_key() if hasattr(spec.model_cls, "klazz_yaml_key") else spec.name
    for path, data in zip(overlays, data_list):
        for item in data.get(key) or []:
            name = item.get("name")
            if item.get("undeclare"):
                # ledger 68: an overlay can also UNDECLARE a tree entry for one
                # invocation -- the instance decommissions / the storage is
                # destroyed exactly as if its entry had left the YAML
                if read_dict.pop(name, None) is not None:
                    log.info(f"Overlay {path.name}: {spec.name} '{name}' undeclared for this invocation")
                else:
                    log.warning(f"Overlay {path.name}: {spec.name} '{name}' is not declared; nothing to undeclare")
                continue
            if name in read_dict:
                read_dict[name] = {**read_dict[name], **item}
                log.info(f"Overlay {path.name}: {spec.name} '{name}' updated ({', '.join(k for k in item if k != 'name')})")
            else:
                read_dict[name] = dict(item)
                # transient: declared by an overlay, not by the tree (stage 10.15)
                getattr(ctx, "overlay_declared", set()).add((key, name))
                log.info(f"Overlay {path.name}: {spec.name} '{name}' declared (transient)")
    # stage 28: the same undeclare, from `--undeclare <kind>:<name>` (no file)
    for kind_key, name in getattr(ctx, "undeclared", None) or []:
        if kind_key != key:
            continue
        if read_dict.pop(name, None) is not None:
            log.info(f"--undeclare: {spec.name} '{name}' undeclared for this invocation")
        else:
            log.warning(f"--undeclare: {spec.name} '{name}' is not declared; nothing to undeclare")


def parse_undeclare(specs: list[str] | None) -> list[tuple[str, str]]:
    """``--undeclare <kind>:<name>`` (stage 28) -> ``[(yaml key, name)]``.
    The kind is an overlay collection key (``instances``, ``storages``, ...);
    the singular is accepted. Refused up front, like a malformed overlay."""
    allowed = {
        (k.model_cls.klazz_yaml_key() if hasattr(k.model_cls, "klazz_yaml_key") else k.name)
        for k in item_kinds()}
    out: list[tuple[str, str]] = []
    for spec in specs or []:
        kind, sep, name = spec.partition(":")
        if not sep or not kind or not name:
            raise ValueError(f"--undeclare {spec!r}: expected <kind>:<name> (e.g. instance:<name>)")
        key = kind if kind in allowed else kind + "s"
        if key not in allowed:
            raise ValueError(f"--undeclare {spec!r}: unknown kind {kind!r}; allowed: {sorted(allowed)}")
        out.append((key, name))
    return out


def load_overlay(path: Path) -> dict[str, Any]:
    """Read one overlay file (stage 8): a mapping whose keys are ``config``
    and/or the domain-item collections (``instances``, ``storages``, ...),
    each a list of named entries. Anything else is refused up front."""
    allowed = {"config"} | {
        (k.model_cls.klazz_yaml_key() if hasattr(k.model_cls, "klazz_yaml_key") else k.name)
        for k in item_kinds()}
    if not path.is_file():
        raise ValueError(f"Overlay {path} does not exist")
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Overlay {path} must be a mapping at the top level")
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(f"Overlay {path}: unknown top-level key(s) {unknown}; allowed: {sorted(allowed)}")
    for key, value in data.items():
        if key == "config":
            if not isinstance(value, dict):
                raise ValueError(f"Overlay {path}: 'config' must be a mapping")
            continue
        if not isinstance(value, list) or any(not isinstance(i, dict) or not i.get("name") for i in value):
            raise ValueError(f"Overlay {path}: '{key}' must be a list of named entries")
    refuse_reserved_names(data, str(path))          # stage 76: an overlay names items too
    refuse_invalid_config_keys(data, str(path))     # and carries a `config:` mapping
    return data


def read_config_and_transform(
    typer_cntx: typer.Context,
    root_dir: Path,
            # config_file: str,
    verbose: bool = False,  # We eventually set verbose in the typer_cntx.obj
    *,
    dry_run: bool = True,
    overlays: list[Path] | None = None,
    undeclare: list[str] | None = None,
    reg: "registry.Registry | None" = None,
) -> RunContext:
    """Read the global configuration from a file.

    Parameters
    ----------
    root_dir : Path
        The root directory containing the configuration files.
    reg : Registry, optional
        A prepared registry to load this run into (a test's); by default
        the run gets a registry of its own with the installed plugins
        loaded into it (stage 124).

    Returns
    -------
        The global configuration instance.
    """
    run_start_time = datetime.now()
    typer_cntx.obj = {"run_start_time": run_start_time}   # the CLI sets "base_only" itself
    env = os.environ.copy()
    # the run's registry (stage 124): one per run, the plugins loaded into
    # it, and the process's current one from here on -- bound BEFORE any
    # model of this run is parsed, since a model holds no context and reads
    # the registry through the shim (current_registry)
    if reg is None:
        reg = registry.Registry()
    load_plugins(reg)
    registry.bind_current_registry(reg)
    if not root_dir:
        raise ValueError("Root directory must be provided")
    _config_dir = root_dir / "cfg"
    orig = read_and_process(_config_dir)
    if not orig:
        raise ValueError(f"Failed to read configuration from {_config_dir}")
    # Here, we know that none of the "name" elements collide
    original_str = yaml.dump(orig)
    dtfmt = orig.get("dateformat", DEFAULT_DATEFORMAT)     # stage 63: the model's one default
    run_start_date = run_start_time.date()
    timestamp = run_start_time.strftime(dtfmt)
    # TODO: figure out some more runtime values to inject here, like git commit hash, branch, etc
    addl: dict[str, Any] = {
        "execution": {
            "timestamp": timestamp,
            "dateformat": dtfmt,
            "date": run_start_date.isoformat(),
        },
        "ENV": env,
    }


    processed_str = cycle_main_yaml(original_str, addl=addl)
    orig = yaml.safe_load(processed_str)
    log.debug("cycle_main_yaml result:\n%s", pformat(orig, indent=2,width=163))

    template_resolver = TemplateResolver(addl=addl)
    # cycled = cycle_main_yaml(processed_str, addl=addl)
    cycled = processed_str  # skip the cycling for now, as it is causing some issues and we want to get the basic flow working.  We can re-enable it once we have a better handle on the process and have added some more safeguards around it.
    if verbose:
        with open("./YAML_DUMP.yaml", "w+") as f:
            f.write(cycled)

    # generic_yaml = template_utils.process_keys( yaml.unsafe_load(config_str))
    # _ddd: dict = {}
    # _ddd = template_utils.extend_with_envdata({},include_ENV=True)
    # config_str = template_utils.render_j2_template_string(config_str, **_ddd)
    generic_yaml = yaml.safe_load(cycled)
    # stage 49: any value in the base document may be an ENC[age:...] marker.
    # HERE, after the dump/render/re-parse above, not in read_and_process: a
    # Decrypted dumps as its plain text, so decrypting before that round-trip
    # would lose every ciphertext the emission has to write back, feed the
    # plaintext to Jinja as template SOURCE, and put it in YAML_DUMP.yaml.
    # This one call covers IAConfig and the plugin builder models, whose dicts
    # are popped out of generic_yaml below and structured from these objects.
    generic_yaml = decrypt_tree(generic_yaml, source=str(_config_dir),
                                collect=decrypted_plaintexts())
    if isinstance(generic_yaml, list):
        if len(generic_yaml) != 1:
            raise ValueError(f"Expected single config, got {len(generic_yaml)}")
        generic_yaml = generic_yaml[0]
    if not isinstance(generic_yaml, dict):
        raise ValueError(
            f"Expected config to be a dictionary at the top level, got {type(generic_yaml)}"
        )

    cycled_generic_yaml = copy.deepcopy(generic_yaml)
    original_yaml_strings: dict[str, str] = {}
    original_yaml_dictionary_lists: dict[str, list[dict[str, Any]]] = {}
    original_yaml_strings_by_plugin_type: dict[str, dict[str, str]] = {}
    for plugin_name, plugin_key in PLUGIN_TYPES:
        if plugin_key in generic_yaml:
            items = generic_yaml.pop(plugin_key)
            if not isinstance(items, list):
                raise ValueError(
                    f"Expected a list for key '{plugin_key}', got {type(items)}"
                )
            original_yaml_strings[plugin_key] = yaml.dump(items)
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    raise ValueError(
                        f"Expected each item in '{plugin_key}' to be a dictionary, got {type(item)}"
                    )
                name = item.get("name", None)
                if not name:
                    raise ValueError(
                        f"Each item in '{plugin_key}' must have a 'name' field. "
                        f"Item at index {idx} is missing a name."
                    )
                original_yaml_strings_by_plugin_type.setdefault(plugin_key, {})[
                    name
                ] = yaml.dump(item)
            original_yaml_dictionary_lists[plugin_key] = items

    # generic_yaml no longer contains the plugin-typed builder models
    try:
        # cattrs.resolve_types(IAConfig)
        config_data = Orchestrator().get_converter().structure(generic_yaml, IAConfig)
    except Exception as e:
        log.error(f"Failed to parse configuration: {e}")
        raise
    assert (
        config_data.working_directory is not None
    ), "working_directory is required in config"
    if isinstance(config_data, list):
        if len(config_data) != 1:
            raise ValueError(f"Expected single config, got {len(config_data)}")
        config_data = config_data[0]

    # stage 106: the tree's image sources land on the release's before any OS
    # builder structures, so a missing `type` can be defaulted from what the
    # family IS and every family reader sees the catalog
    ImageSourceCatalog().set_tree(list(config_data.image_sources or []))

    cvt = Orchestrator().get_converter()


    for plugin_name, plugin_key in PLUGIN_TYPES:
        typemap_type: type = PLUGIN_TYPEMAP.get(plugin_name, None)  # type: ignore
        assert (
            typemap_type
        ), f"No class found for plugin key '{plugin_key}' in PLUGIN_TYPEMAP. Please add an entry for this plugin type."
        if plugin_key in original_yaml_dictionary_lists:
            for item in original_yaml_dictionary_lists[plugin_key]:
                name = item.get("name", None)
                _type = item.get("type", None)
                if name and not _type and plugin_key == "os_builders":
                    # stage 106: an OS builder may leave `type` out when exactly
                    # one registered type serves what its family IS
                    _type = default_os_type(str(item.get("family", "")), item.get("family_version"),
                                            dict(reg.models.get(VCT.OS_BUILDER_MODEL, {})))
                    if _type:
                        item["type"] = _type
                        log.info(f"os_builders: {name}: type {_type} from family {item.get('family')}")
                if not name or not _type:
                    raise ValueError(
                        f"Each item in '{plugin_key}' must have a 'name' and 'type' field. "
                        f"Item {item} is missing a name or type."
                        + (" An OS builder's type is defaulted only when exactly one registered type serves "
                           "its family (what the image-source catalog says it is); declare `type`."
                           if plugin_key == "os_builders" else "")
                    )
                try:
                    named_obj = cvt.structure(item, typemap_type)
                    if named_obj and isinstance(named_obj, BuilderModelProtocol):
                        bmp: BuilderModelProtocol = named_obj
                        bmpname = bmp.get_name()
                        vct = registry.sanitize_classifier(bmp.get_classification())
                        if bmpname and vct and bmp.get_is_default():
                            if reg.get_default_for(vct) != None:
                                log.warning(
                                    f"Default {vct.value} builder already registered: {reg.get_default_for(vct)}. Overwriting with {bmpname} from config."
                                )
                            reg.set_default_for(vct, bmpname)
                    template_resolver.flatten_dataclass(named_obj)
                except Exception as e:
                    log.error(
                        f"Failed to structure item {item} for plugin key '{plugin_key}': {e}"
                    )
                    raise
                # The structure call registers the object into the registry

    template_resolver.resolve_all()

    # template_resolver holds everything in it's map at the moment
    config_data.runtime_builders = reg.get_all_instances_by_classification(VCT.RUNTIME_BUILDER_MODEL)  # type: ignore
    config_data.state_backends = reg.get_all_instances_by_classification(VCT.STATE_BACKEND_MODEL)  # type: ignore
    config_data.os_builders = reg.get_all_instances_by_classification(VCT.OS_BUILDER_MODEL)  # type: ignore
    config_data.group_builders = reg.get_all_instances_by_classification(VCT.GROUP_BUILDER_MODEL)  # type: ignore
    config_data.user_builders = reg.get_all_instances_by_classification(VCT.USER_BUILDER_MODEL)  # type: ignore
    config_data.mod_builders = reg.get_all_instances_by_classification(VCT.MOD_BUILDER_MODEL)  # type: ignore
    config_data.storage_builders = reg.get_all_instances_by_classification(VCT.STORAGE_BUILDER_MODEL)  # type: ignore
    config_data.image_builders = reg.get_all_instances_by_classification(VCT.IMAGE_BUILDER_MODEL)  # type: ignore
    config_data.instance_builders = reg.get_all_instances_by_classification(VCT.INSTANCE_BUILDER_MODEL)  # type: ignore
    configured_runtime_builders: dict[str, RuntimeBuilderBase] = {}
    if not config_data.runtime_builders:
        raise ValueError("No runtime providers configured.")

    default_runtime_builder = reg.get_default_for(VCT.RUNTIME_BUILDER_MODEL)

    # TODO:
    #  1. cycle_yaml using the local value of "runtime" including a timestamp and
    #     date to allow for dynamic values in the config file based on the current run.
    #     This produces a finalized yaml
    #  2. Load the finalized yaml into a dict
    #  3. Use RuntimeModel.from_dict to produce final runtime models for all types
    #  4. Fill in any defaults that are possible to fill
    #  5. Use the registry to lookup the actual type and instantiate the list
    #     of runtimes, returning that list.  Keep the original yaml in the runtime_builder's
    #     config for reference and debugging.
    # NOTE that this process is RELOADING THE YAML FOR EACH BUILDER TYPE INDIVIDUALLY
    if not config_data.config:
        log.warning("No configuration data found in config file.")
        config_data.config = {}
    addl_config = copy.deepcopy(addl)
    addl_config.update(config_data.config)


    if not config_data.runtime_builders:
        log.error("No runtime builders found in config file.")
        raise ValueError("No runtime builders found in config file.")

    log.debug(f"Original runtime builders config: {config_data.runtime_builders}")

    # config_data.runtime_builders = reprocess_a(config_data.runtime_builders, addl_config)  # type: ignore
    # config_data.state_backends = reprocess_a(config_data.state_backends, addl_config) if config_data.state_backends else []  # type: ignore

    # # for q in config_data.os_builders or []:
    # #     log.debug(f"OS builder {q.name} runtime provider before reprocessing")
    # #     scan_for_trouble(q)
    # #     # d = Orchestrator().get_converter().unstructure(q)
    # config_data.os_builders = reprocess_a(config_data.os_builders, addl_config) if config_data.os_builders else []  # type: ignore
    # config_data.group_builders = reprocess_a(config_data.group_builders, addl_config) if config_data.group_builders else []  # type: ignore
    # config_data.user_builders = reprocess_a(config_data.user_builders, addl_config) if config_data.user_builders else []  # type: ignore
    # config_data.storage_builders = reprocess_a(config_data.storage_builders, addl_config) if config_data.storage_builders else []  # type: ignore
    # config_data.image_builders = reprocess_a(config_data.image_builders, addl_config) if config_data.image_builders else []  # type: ignore
    # config_data.instance_builders = reprocess_a(config_data.instance_builders, addl_config) if config_data.instance_builders else []  # type: ignore

    configured_runtime_builders: dict[str, RuntimeBuilderBase] = process_and_register_builders(
        config_data, VCT.RUNTIME_BUILDER, "runtime_builders", addl_config, reg
    )  # type: ignore
    configured_state_builders = {}
    if config_data.state_backends:
        configured_state_builders = process_and_register_builders(
            config_data, VCT.STATE_BACKEND, "state_backends", addl_config, reg
        )
    configured_os_builders = {}
    if config_data.os_builders:
        configured_os_builders = process_and_register_builders(
            config_data, VCT.OS_BUILDER, "os_builders", addl_config, reg
        )
    configured_group_builders = {}
    if config_data.group_builders:
        configured_group_builders = process_and_register_builders(
            config_data, VCT.GROUP_BUILDER, "group_builders", addl_config, reg
        )
    configured_user_builders = {}
    if config_data.user_builders:
        configured_user_builders = process_and_register_builders(
            config_data, VCT.USER_BUILDER, "user_builders", addl_config, reg
        )
    configured_image_builders: dict[str, ImageBuilderBase] = {}
    if config_data.image_builders:
        configured_image_builders = process_and_register_builders(
            config_data, VCT.IMAGE_BUILDER, "image_builders", addl_config, reg
        )  # type: ignore
    configured_instance_builders: dict[str, InstanceBuilderBase] = {}
    if config_data.instance_builders:
        configured_instance_builders = process_and_register_builders(
            config_data, VCT.INSTANCE_BUILDER, "instance_builders", addl_config, reg
        )  # type: ignore
        # for instb_name, instancebuilder in configured_instance_builders.items():

    configured_mod_builders: dict[str, ModBuilderBase] = {}
    if config_data.mod_builders:
        configured_mod_builders = process_and_register_builders(
            config_data, VCT.MOD_BUILDER, "mod_builders", addl_config, reg
        )  # type: ignore
    configured_storage_builders = {}
    if config_data.storage_builders:
        configured_storage_builders = process_and_register_builders(
            config_data, VCT.STORAGE_BUILDER, "storage_builders", addl_config, reg
        )


    builders: list[BuilderBase] = []

    for d in [
        configured_runtime_builders,
        configured_state_builders,
        configured_group_builders,
        configured_user_builders,
        configured_os_builders,
        configured_mod_builders,
        configured_storage_builders,
        configured_image_builders,
        configured_instance_builders,

    ]:
        for k in sorted(d.keys()):
            builders.append(d[k])

    # If a root_dir is supplied
    if root_dir:
        # Use the supplied root_dir
        working_dir = root_dir
    else:
        # Use the root_dir from the config file, or default to "."
        working_dir = (
            config_data.working_directory if config_data.working_directory else "."
        )
    wpath = Path(working_dir).resolve()
    if not wpath.exists():
        raise FileNotFoundError(f"Working directory {wpath} does not exist.")
    os.chdir(wpath)
    gen_path = (
        wpath / config_data.generation_directory
        if config_data.generation_directory
        else wpath / "generated"
    )
    # Transient declarations (stage 8): overlay files merged over the tree for
    # THIS invocation only -- their `config:` keys land on the merged config here,
    # after the builders were built against the tree's own (as before stage 124);
    # their items are merged kind by kind as each kind is read (apply_overlays).
    overlay_paths = [Path(p).resolve() for p in (overlays or [])]
    overlay_data = [load_overlay(p) for p in overlay_paths]
    for data in overlay_data:
        if data.get("config"):
            if config_data.config is None:
                config_data.config = {}
            config_data.config.update(data["config"])
    ctx = RunContext(
        verbose,
        root_dir,
        config_data,
        wpath,
        gen_path,
        builders,
        dry_run=dry_run,
        overlays=overlay_paths,
        overlay_data=overlay_data,
        undeclared=parse_undeclare(undeclare),
        run_start_time=run_start_time,
        reg=reg,
    )
    ctx.bind_finalizer(Finalizer(ctx))
    # the context is passed (DESIGN's phrase): every builder holds the one it
    # was registered into, and the process holds it for the one-release shim
    # (current_context) -- bound BEFORE the kinds are read, as the singleton
    # was reachable then and a model may still fetch it during the read
    for b in builders:
        # a builder that satisfies the contract structurally (the contract
        # example's) carries no bind; it reads nothing from the context
        bind = getattr(b, "bind", None)
        if callable(bind):
            bind(ctx)
    bind_current(ctx)
    # Read the normal-flow domain-item kinds in registration order. Each reader
    # registers its items into the registry (from which the collection properties
    # read) and attaches them to their builders; the group kind's validator sets
    # the root group.
    #
    # base_only kinds (e.g. base_images) are registered but intentionally NOT
    # auto-read yet: that read path is incomplete on the current models
    # (base_image.type_ is an OS family, not an image-builder reference), exactly
    # as it was when read_base_images_from_files existed but was never called.
    for spec in item_kinds():
        if not spec.base_only:
            read_item_kind(ctx, spec)
    return ctx


def process_and_register_builders(
    config_data: IAConfig,
    classification: VCT,
    property: str,
    addl_config: dict[str, Any],
    reg: "registry.Registry",
) -> dict[str, BuilderBase]:
    """
    Reprocess a list of builders of a given classification to resolve references and defaults.
    This function MIGHT ALSO mutate the builder model objects.
    The builders are registered into ``reg``, the run's registry.
    """
    ret: dict[str, BuilderBase] = {}
    builder_models: dict[str,BuilderModel] = getattr(config_data, property, {})

    default: str | None = None
    default_classifier: VCT | None = None
    names: set[str] = set()
    for name, model in builder_models.items():
        # stage 30, branch 2: the contract's protocol, not the core's base class --
        # a plugin's model that satisfies BuilderModelProtocol structurally (the
        # proof plugin's does) is a builder model
        if not isinstance(model, BuilderModelProtocol):
            raise ValueError(
                f"Expected builder model for {name} in {property} to satisfy BuilderModelProtocol, got {type(model)}"
            )

        if model.name in OOPS_DEFAULTS:
            raise ValueError(
                f"Builder with default name found:{model.name}"
            )
        else:
            model.name = name.strip()
        if hasattr(model,"aliases"):
            aliases = getattr(model, "aliases", [])
            if model.name in aliases:
                aliases.remove(model.name)
            reg.register_aliases(classification, model.name,aliases) # Keeps aliases from colliding
        if model.name in names:
            raise ValueError(f"Duplicate builder name found: {model.name}")

        names.add(model.name)
        if model.is_default:
            if default is not None:
                raise ValueError(
                    f"Multiple default builders found: {default} and {model.name}"
                )
            default = model.name
            default_classifier = model.csis_classifier()
        if hasattr(model,"runtime"):
            rt = reg.get_registered_name_by_name_or_alias(VCT.RUNTIME_BUILDER, model.runtime) # type: ignore
            assert rt, f"Runtime provider '{rt}' not found for builder '{model.name}'"
            model.runtime = rt  # type: ignore
        try:
            model.finalize()  # This didn't happen in reprocess_a
        except Exception as e:
            log.error(
                f"Failed to finalize builder model {model.name} of type {classification}: {e}"
            )
            raise
        builder_models[name] = model

        model_type = type(model)
        model_name_type = model_type.csis_name()
        bc: type[BuilderBase] = reg.get_builder_for_model(model_name_type, classification) # type: ignore
        assert (
            bc is not None
        ), f"No builder class registered for model class {model.__class__}"
        prov = bc(model=model)  # type: ignore
        if not is_dataclass(prov):
            # We don't call __post_init__ for dataclasses
            # the system does that for us when we instantiate them,
            # but for non-dataclass builders we need to call it manually
            if hasattr(prov, "__post_init__"):
                if callable(getattr(prov, "__post_init__")):
                    prov.__post_init__()  # type: ignore
        prov.finalize()
        # stage 30: the registry gates on the instance (NameTypedProtocol) and
        # skips anything else. The class-level test here was
        # `issubclass(bc, PluginArtifactProtocol) or issubclass(bc, NameTypedProtocol)`,
        # whose second half would raise TypeError (a protocol with a property
        # member supports isinstance, not issubclass) and never ran: every
        # builder class satisfied the first half.
        reg.register_built_instance(prov)
        if model.name in ret:
            raise ValueError(
                f"Duplicate builder name '{model.name}' found for classification {classification} after reprocessing. Builder names must be unique."
            )
        ret[model.name] = prov # type: ignore
    if default is None:
        raise ValueError(f"No default builder found in {classification} list.")

    reg.set_default_for(classification, default)
    # Also register the default under the default builder's own model-level
    # classification (e.g. RUNTIME_BUILDER *and* RUNTIME_BUILDER_MODEL), taken from
    # the default model itself rather than whichever model happened to iterate last.
    if default_classifier is not None:
        reg.set_default_for(default_classifier, default)

    return ret



def read_and_process(dir: Path) -> dict[str, Any] | None:
    """Read and process YAML files in the given directory."""
    if not dir.exists() or not dir.is_dir():
        return None
    f:list[Path] = get_files_by_extensions(dir, recursive=False)
    ret: dict[str, Any] = {}
    for file in f:
        try:
            with open(file, "r") as stream:
                # safe_load: a PUBLIC configuration tree constructs no Python object
                # (stage 63 item 13; unsafe_load stood here alone, every other
                # reader of the tree is safe_load, and no tree carries a tag)
                data = yaml.safe_load(stream)
                if isinstance(data, dict):
                    # stage 49: needs NO identity -- a structural check, so it
                    # still runs where nothing could be decrypted
                    refuse_markers_at(data, str(file))
                    # stage 76: nothing may be named after a word that means "not
                    # set"; refused here so the message names the file and entry
                    refuse_reserved_names(data, str(file))
                    # stage 76 step 6: the `config:` key guard, switched on as written
                    refuse_invalid_config_keys(data, str(file))
                    ret = _extend_lists(ret, data)
        except Exception as e:
            log.error(f"Error reading or processing file {file}: {e}")
            raise
    if not ret:
        log.warning(f"No valid YAML files found in directory {dir}")
        return None
    # Check for name collisions on lists of dicts
    for key, value in ret.items():
        if isinstance(value, list):
            names_seen: set[str] = set()
            for item in value:
                if isinstance(item, dict):
                    if "name" in item:
                        name = item["name"]
                        if "{{" in name or "}}" in name:
                            errstr = (f"Name '{name}' in list for key '{key}' contains template markers. ")
                            log.error(errstr)
                            raise ValueError(errstr)
                        if name in names_seen:
                            raise ValueError(
                                f"Duplicate name '{name}' found in list for key '{key}'"
                            )
                        names_seen.add(name)
                    if "type" in item:
                        type_value = item["type"]
                        if "{{" in type_value or "}}" in type_value:
                            errstr = (f"Type '{type_value}' in list for key '{key}' contains template markers. ")
                            log.error(errstr)
                            raise ValueError(errstr)

    log.debug("read_and_process result:\n%s", pformat(ret))
    return ret

def _extend_lists(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Extend lists in the old dictionary with lists from the new dictionary by name."""
    for key, value in new.items():
        if isinstance(value, list):
            if key in old and isinstance(old[key], list):
                old[key].extend(value)
            else:
                old[key] = value
        else:
            old[key] = value
    return old


def _validate_groups(ctx: RunContext, groups: list[Group]) -> None:
    """Post-read validation for the ``groups`` kind: exactly one root group
    (marked ``is_root: true``), and every group member must be a defined user."""
    rgrp = [g for g in groups if g.is_root]
    if len(rgrp) != 1:
        raise ValueError(f"Expected exactly one root group (is_root: true), found {len(rgrp)}")
    ctx._root_group = rgrp[0]
    user_names = {u.get_name() for u in ctx.users}
    for g in groups:
        for u in g.members:
            if u not in user_names:
                raise ValueError(
                    f"Group {g.get_name()} has member {u} which is not in the list of "
                    "defined users"
                )


# --- Built-in domain-item kinds (read in this order by the loader).
# Users are read before groups so group-member validation can see them.
register_item_kind(ItemKind(
    "users", GROUPS, User, VCT.USER_BUILDER,
    attach=lambda b, it: b.add_user_to_builder(it),
))
register_item_kind(ItemKind(
    "groups", GROUPS, Group, VCT.GROUP_BUILDER,
    attach=lambda b, it: b.add_group_to_builder(it),
    validate=_validate_groups,
))
register_item_kind(ItemKind(
    "storages", STORAGES, Storage, VCT.STORAGE_BUILDER,
    attach=lambda b, it: b.add_storage(it),
))
def _attach_image(builder: Any, image: Any) -> None:
    """An image attaches to its ``type`` builder (the primary) and, since the
    second-cloud exploration, to every other image builder its ``runtimes`` name -- one bake per
    runtime of the same logical image."""
    builder.add_image(image)
    reg = builder._get_context().reg
    primary_runtime = builder.model.get_runtime_provider()
    for sub in getattr(image, "runtimes", None) or []:
        name = getattr(sub, "image_builder", None)
        if not name or name in OOPS_DEFAULTS:
            continue
        other = reg.get_instance_by_name_or_alias(VCT.IMAGE_BUILDER, name)
        if other is None or other is builder:
            continue
        if other.model.get_runtime_provider() == primary_runtime:
            continue  # same runtime: the primary builder's bake is the bake
        other.add_image(image)


register_item_kind(ItemKind(
    "images", IMAGES, Image, VCT.IMAGE_BUILDER,
    attach=_attach_image,
    default_missing_type_to=VCT.IMAGE_BUILDER_MODEL,
))
register_item_kind(ItemKind(
    "instances", INSTANCES, Instance, VCT.INSTANCE_BUILDER,
    attach=lambda b, it: b.add_instance(it),
))
# Base images are read in base-only mode (the normal-flow kinds are skipped then).
register_item_kind(ItemKind(
    "base_images", BASE_IMAGES, BaseImage, VCT.IMAGE_BUILDER,
    attach=lambda b, it: b.add_image(it),
    default_missing_type_to=VCT.IMAGE_BUILDER_MODEL,
    base_only=True,
))
