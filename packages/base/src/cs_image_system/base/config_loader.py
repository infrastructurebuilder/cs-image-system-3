# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The configuration loader: the engine side that MAKES a run context.

:func:`read_config_and_transform` reads the tree under ``<root>/cfg``,
renders and structures it, builds and registers every builder, constructs
the :class:`~.run_context.RunContext`, binds the context to each builder,
makes the run's :class:`~.finalizer.Finalizer`, and reads the domain-item
kinds (:class:`ItemKind`) into the registry. The context it returns knows
everything and loads nothing; the loading lives here.

Every load makes its own registry, image-source catalog and template
resolver and hands them to the context it returns; nothing of a load is
kept by the process, so a second load in the same process (another tree,
or the same tree under other overlays) shares nothing with the first.
"""

from __future__ import annotations

import copy
import logging
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import is_dataclass
from datetime import datetime
from pathlib import Path
from pprint import pformat
from typing import TYPE_CHECKING, Any

import typer
import yaml
from pydantic.dataclasses import dataclass  # validation at construction

from cs_image_system.base.models.base_image import BaseImage
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG

from .models.ia_config import IAConfig
from .models.user import User
from .orchestrator import PydanticConverter, TemplateResolver, parent_by_default_type, parent_by_written_type

if TYPE_CHECKING:
    from .basic.builder_base_image import ImageBuilderBase
    from .basic.builder_base_instance import InstanceBuilderBase
    from .basic.builder_base_mod import ModBuilderBase
    from .basic.builder_base_runtime import RuntimeBuilderBase
from cs_image_system.contract.context import (
    CliServiceProtocol,
    CommandsServiceProtocol,
    FilesServiceProtocol,
    IdentityServiceProtocol,
    ImagesServiceProtocol,
    LaunchServiceProtocol,
    LifecyclesServiceProtocol,
    LineageServiceProtocol,
    MetaStateProtocol,
    ScopeServiceProtocol,
    SecretsServiceProtocol,
    ServicesProtocol,
    StorageServiceProtocol,
    WorkspacesServiceProtocol,
)
from cs_image_system.contract.executables import ExecutableProtocol
from cs_image_system.contract.group import GroupBuilderProtocol
from cs_image_system.contract.image import ImageQuery
from cs_image_system.contract.lifecycles import LifecycleLike
from cs_image_system.contract.storage import StorageBuilderProtocol

# the registry and the services behind the context: the modules the
# adapters at the end of this file delegate to, imported here because the loader is
# where the run is assembled and the one place already inside the import
# web every one of them belongs to
from . import (
    bake_steps,
    bake_user,
    capabilities,
    ephemeral_policy,
    identity_attributes,
    image_tests,
    launch_params,
    lineage,
    materialize,
    os_types,
    registry,
    standing,
    state_backup,
    storage_state,
    utils,
)
from . import encryption as _encryption
from . import image_sources as _image_sources
from . import lifecycles as _lifecycles
from .encryption import decrypt_tree, refuse_markers_at
from .finalizer import Finalizer
from .image_sources import ImageSourceCatalog, default_os_type
from .loader import load_plugins
from .models.ia_config import DEFAULT_DATEFORMAT
from .network_facts import adopt as adopt_network_facts
from .reserved_names import refuse_invalid_config_keys, refuse_reserved_names
from .run_context import RunContext
from .template_utils import read_and_preprocess_yaml_files, string_stage

log = logging.getLogger(__name__)

from cs_image_system.contract.constants import (
    BASE_IMAGES,
    GROUPS,
    IMAGES,
    INSTANCES,
    OOPS_DEFAULTS,
    PLUGIN_TYPES,
    STORAGES,
    VCT,
)
from cs_image_system.contract.core import (
    BuilderModelProtocol,
    PluginArtifactProtocol,
    RuntimeEnabledBuilderModelProtocol,
)

from .basic.builder_base import BuilderBase
from .models.builder_model import BuilderModel, NameTyped
from .models.executable import ExecutableModel
from .models.group import Group
from .models.group_builder import GroupBuilderModel
from .models.image import Image
from .models.image_builder_model import ImageBuilderModel
from .models.instance import Instance
from .models.instance_builder import InstanceBuilderModel
from .models.mod_builder import ModBuilderModel
from .models.os_builder_model import OsBuilderModel
from .models.runtime import RuntimeBuilderModel
from .models.state_builder import StateBuilderModel
from .models.storage import Storage
from .models.storage_builder import StorageBuilderModel
from .models.user_builder import UserBuilderModel

#: the file a verbose load writes the rendered document to, in the
#: configuration root's private directory (``_private/``)
VERBOSE_DUMP = "YAML_DUMP.yaml"

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


# shared by every run in the process: specs registered by code at import; a run reads its items INTO its own context
_ITEM_KINDS: list[ItemKind] = []


def item_model_class(reg: "registry.Registry", spec: ItemKind) -> type:
    """The class a kind's items structure into: the plugin-injected default
    model of the kind's classification when one is registered and extends
    the kind's own model (an identity plugin's user subclass carrying its
    directory's profile fields), else the kind's model. The YAML key and
    the ``isinstance`` check stay the kind's: a subclass only adds fields."""
    if not isinstance(spec.model_cls, PluginArtifactProtocol):
        return spec.model_cls
    try:
        classifier = spec.model_cls.csis_classifier()
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
    items are read INTO (its working path, registry and overlays); it used
    to be the context's own ``_read_item_kind`` method.
    """
    yaml_files = get_files_by_extensions(ctx.working_path / spec.source_dir)
    template_resolver = ctx.template_resolver
    cvt = template_resolver.converter
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
                    # every builder model and its default is registered by
                    # now: an item whose `type` names its parent holds that
                    # builder's model (the default's, for a type left at
                    # `default`) before it is entered in the flat map, so
                    # the key it is entered under names its parent
                    parent_by_written_type(reg, ri)
                    parent_by_default_type(reg, ri)
                    items.append(ri)
                    template_resolver.flatten_dataclass(ri)
                    reg.register_built_instance(ri)
    except Exception as e:
        log.error(f"Error parsing {yaml_files}: {e}")
        raise
    # the object stage returns the foreign keys that named nothing,
    # for the whole load so far (the builder stage's included); the context
    # carries them and `validate` refuses them
    ctx.unresolved_foreign_keys = template_resolver.resolve_all()
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
    on disk is never touched -- that is the point. A context
    without overlays (unit-test stand-ins included) is a no-op."""
    overlays = getattr(ctx, "overlays", None) or []
    data_list = getattr(ctx, "_overlay_data", None) or []
    key = spec.model_cls.klazz_yaml_key() if hasattr(spec.model_cls, "klazz_yaml_key") else spec.name
    for path, data in zip(overlays, data_list, strict=False):
        for item in data.get(key) or []:
            name = item.get("name")
            if item.get("undeclare"):
                # an overlay can also UNDECLARE a tree entry for one
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
                # transient: declared by an overlay, not by the tree
                getattr(ctx, "overlay_declared", set()).add((key, name))
                log.info(f"Overlay {path.name}: {spec.name} '{name}' declared (transient)")
    # the same undeclare, from `--undeclare <kind>:<name>` (no file)
    for kind_key, name in getattr(ctx, "undeclared", None) or []:
        if kind_key != key:
            continue
        if read_dict.pop(name, None) is not None:
            log.info(f"--undeclare: {spec.name} '{name}' undeclared for this invocation")
        else:
            log.warning(f"--undeclare: {spec.name} '{name}' is not declared; nothing to undeclare")


def parse_undeclare(specs: list[str] | None) -> list[tuple[str, str]]:
    """``--undeclare <kind>:<name>`` -> ``[(yaml key, name)]``.
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
    """Read one overlay file: a mapping whose keys are ``config``
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
    refuse_reserved_names(data, str(path))          # an overlay names items too
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
        The root directory containing the configuration files, and the
        run's working directory. Required: a load without one is refused
        before anything is loaded or changed.
    reg : Registry, optional
        A prepared registry to load this run into (a test's); by default
        the run gets a registry of its own with the installed plugins
        loaded into it.

    Returns
    -------
        The global configuration instance.
    """
    # refused first: no plugin is loaded, no catalog made and the typer
    # context's object is left as the caller had it
    if not root_dir:
        raise ValueError("Root directory must be provided")
    run_start_time = datetime.now()
    typer_cntx.obj = {"run_start_time": run_start_time}   # the CLI sets "base_only" itself
    env = os.environ.copy()
    # the run's registry: one per run, the plugins loaded into it
    if reg is None:
        reg = registry.Registry()
    load_plugins(reg)
    # the run's image-source catalog over its registry: the release layer
    # read from this registry's runtimes, the tree's layer set below once
    # the configuration is parsed
    catalog = ImageSourceCatalog(reg)
    _config_dir = root_dir / "cfg"
    orig = read_and_process(_config_dir)
    if not orig:
        raise ValueError(f"Failed to read configuration from {_config_dir}")
    # Here, we know that none of the "name" elements collide
    dtfmt = orig.get("dateformat", DEFAULT_DATEFORMAT)     # the model's one default
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


    # The string stage walks the ONE parsed tree (read_and_process parsed each
    # cfg/*.yml exactly once): the registered passes render its string leaves
    # in place and nothing is dumped back to text or parsed again. A mapping
    # keeps the key order its file gave it, so a free-form mapping an emission
    # writes as it is (an image's tags) comes out in the file's order.
    generic_yaml: Any = string_stage(orig, addl=addl)
    log.debug("string stage result:\n%s", pformat(generic_yaml, indent=2, width=163))

    # the run's object stage and its converter: every model the converter
    # structures is bound to this run's registry and catalog, and the
    # resolver's map starts with this run's own scopes. It collects the
    # foreign keys that name nothing for THIS load (the context receives
    # them when the item kinds are read; `validate` refuses them)
    cvt = PydanticConverter(reg, catalog)
    template_resolver = TemplateResolver(reg, addl=addl, converter=cvt)
    if verbose:
        # the rendered document, the one time it is written out (and before
        # decryption, so no plaintext lands in it), under the root's private
        # directory, which is never committed; the invoking directory is left
        # alone (the root is not yet the current directory, so a relative
        # root still resolves against the invoking one here)
        dump_dir = materialize.private_root(root_dir)
        dump_dir.mkdir(parents=True, exist_ok=True)
        with open(dump_dir / VERBOSE_DUMP, "w+") as f:
            yaml.safe_dump(generic_yaml, f, sort_keys=False)

    # any value in the base document may be an ENC[age:...] marker.
    # HERE, after the string stage, not in read_and_process: the passes render
    # every string leaf as template SOURCE, and a Decrypted leaf rendered that
    # way would feed its plaintext to Jinja; kept as its marker through the
    # passes (a marker carries no tag, so it renders to itself), every
    # ciphertext survives for the emission to write back. This one call covers
    # IAConfig and the plugin builder models, whose dicts are popped out of
    # generic_yaml below and structured from these objects.
    generic_yaml = decrypt_tree(generic_yaml, source=str(_config_dir))
    generic_yaml = _single_mapping(generic_yaml)

    original_yaml_dictionary_lists = _take_builder_lists(generic_yaml)

    # generic_yaml no longer contains the plugin-typed builder models
    config_data = _structure_configuration(cvt, generic_yaml)

    # the tree's image sources land on the release's before any OS
    # builder structures, so a missing `type` can be defaulted from what the
    # family IS and every family reader sees the catalog
    catalog.set_tree(list(config_data.image_sources or []))


    _structure_builder_models(original_yaml_dictionary_lists, cvt, catalog, reg, template_resolver)

    template_resolver.resolve_all()

    # template_resolver holds everything in it's map at the moment
    _collect_builder_models(config_data, reg)
    if not config_data.runtime_builders:
        raise ValueError("No runtime providers configured.")

    _ = reg.get_default_for(VCT.RUNTIME_BUILDER_MODEL)   # the first ask fills the registry's defaults

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


    log.debug(f"Original runtime builders config: {config_data.runtime_builders}")

    # config_data.runtime_builders = reprocess_a(config_data.runtime_builders, addl_config)  # type: ignore
    # config_data.state_backends = reprocess_a(config_data.state_backends, addl_config) if config_data.state_backends else []  # type: ignore

    # # for q in config_data.os_builders or []:
    # #     log.debug(f"OS builder {q.name} runtime provider before reprocessing")
    # #     scan_for_trouble(q)
    # config_data.os_builders = reprocess_a(config_data.os_builders, addl_config) if config_data.os_builders else []  # type: ignore
    # config_data.group_builders = reprocess_a(config_data.group_builders, addl_config) if config_data.group_builders else []  # type: ignore
    # config_data.user_builders = reprocess_a(config_data.user_builders, addl_config) if config_data.user_builders else []  # type: ignore
    # config_data.storage_builders = reprocess_a(config_data.storage_builders, addl_config) if config_data.storage_builders else []  # type: ignore
    # config_data.image_builders = reprocess_a(config_data.image_builders, addl_config) if config_data.image_builders else []  # type: ignore
    # config_data.instance_builders = reprocess_a(config_data.instance_builders, addl_config) if config_data.instance_builders else []  # type: ignore

    builders = _build_builders(config_data, addl_config, reg)

    wpath, gen_path = _enter_working_directory(root_dir, config_data)
    overlay_paths, overlay_data = _read_overlays(overlays, config_data)
    ctx = RunContext(
        verbose,
        root_dir,
        config_data,
        wpath,
        gen_path,
        builders,
        reg=reg,
        image_sources=catalog,
        template_resolver=template_resolver,
        dry_run=dry_run,
        overlays=overlay_paths,
        overlay_data=overlay_data,
        undeclared=parse_undeclare(undeclare),
        run_start_time=run_start_time,
    )
    ctx.bind_finalizer(Finalizer(ctx))
    ctx.bind_services(RunServices(ctx))
    _bind_builders(builders, ctx)
    # the network facts a real run or `validate --online` recorded
    # are adopted OFFLINE here (a `default` network becomes the recorded one);
    # what the record leaves unanswered waits on the context for `validate`.
    # The load itself reaches no cloud.
    adopt_network_facts(ctx)
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


def _single_mapping(generic_yaml: Any) -> dict[str, Any]:
    """The one mapping the configuration document is: a list holding exactly
    one entry is unwrapped to that entry, and anything that is not a mapping
    at the top level is refused."""
    if isinstance(generic_yaml, list):
        if len(generic_yaml) != 1:
            raise ValueError(f"Expected single config, got {len(generic_yaml)}")
        generic_yaml = generic_yaml[0]
    if not isinstance(generic_yaml, dict):
        raise ValueError(
            f"Expected config to be a dictionary at the top level, got {type(generic_yaml)}"
        )
    return generic_yaml


def _take_builder_lists(generic_yaml: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Take every builder list (one per key of ``PLUGIN_TYPES``) OUT of the
    document, keyed as the document keyed it, so what is left structures as
    the configuration proper. A key that holds no list, an entry that is no
    mapping and an entry without a ``name`` are each refused."""
    original_yaml_dictionary_lists: dict[str, list[dict[str, Any]]] = {}
    for _plugin_name, plugin_key in PLUGIN_TYPES:
        if plugin_key in generic_yaml:
            items = generic_yaml.pop(plugin_key)
            if not isinstance(items, list):
                raise ValueError(
                    f"Expected a list for key '{plugin_key}', got {type(items)}"
                )
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
            original_yaml_dictionary_lists[plugin_key] = items
    return original_yaml_dictionary_lists


def _structure_configuration(cvt: PydanticConverter, generic_yaml: dict[str, Any]) -> IAConfig:
    """The document, its builder lists taken out, structured as the
    configuration (:class:`IAConfig`): the document is one mapping
    (:func:`_single_mapping`), so the configuration is one object. A
    document that does not structure is logged as an error and the failure
    raised as it came."""
    try:
        # cattrs.resolve_types(IAConfig)
        return cvt.structure(generic_yaml, IAConfig)
    except Exception as e:
        log.error(f"Failed to parse configuration: {e}")
        raise


def _structure_builder_models(
    original_yaml_dictionary_lists: dict[str, list[dict[str, Any]]],
    cvt: PydanticConverter,
    catalog: ImageSourceCatalog,
    reg: "registry.Registry",
    template_resolver: TemplateResolver,
) -> None:
    """Structure every declared builder into its model, kind by kind in the
    order of ``PLUGIN_TYPES`` and entry by entry in the document's order. A
    kind without a class in ``PLUGIN_TYPEMAP`` fails the load."""
    for plugin_name, plugin_key in PLUGIN_TYPES:
        typemap_type: type = PLUGIN_TYPEMAP.get(plugin_name, None)  # type: ignore
        assert (
            typemap_type
        ), f"No class found for plugin key '{plugin_key}' in PLUGIN_TYPEMAP. Please add an entry for this plugin type."
        if plugin_key in original_yaml_dictionary_lists:
            for item in original_yaml_dictionary_lists[plugin_key]:
                _structure_builder_model(item, plugin_key, typemap_type, cvt, catalog, reg, template_resolver)


def _structure_builder_model(
    item: dict[str, Any],
    plugin_key: str,
    typemap_type: type,
    cvt: PydanticConverter,
    catalog: ImageSourceCatalog,
    reg: "registry.Registry",
    template_resolver: TemplateResolver,
) -> None:
    """One declared builder, structured into its model and entered in the
    resolver's map. An entry needs a ``name`` and a ``type``; an OS builder
    that leaves ``type`` out takes the one registered type that serves its
    family, when there is exactly one. A model that says it is the default
    of its classification becomes the registry's default (replacing one
    already there, with a warning). A failure to structure is logged as an
    error and raised as it came."""
    name = item.get("name", None)
    _type = item.get("type", None)
    if name and not _type and plugin_key == "os_builders":
        # an OS builder may leave `type` out when exactly
        # one registered type serves what its family IS
        _type = default_os_type(catalog, str(item.get("family", "")), item.get("family_version"),
                                reg.models_under(VCT.OS_BUILDER_MODEL))
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
                registered = reg.get_default_for(vct)
                if registered is not None:
                    log.warning(
                        f"Default {vct.value} builder already registered: {registered}. Overwriting with {bmpname} from config."
                    )
                reg.set_default_for(vct, bmpname)
        template_resolver.flatten_dataclass(named_obj)
    except Exception as e:
        log.error(
            f"Failed to structure item {item} for plugin key '{plugin_key}': {e}"
        )
        raise
    # The structure call registers the object into the registry


def _collect_builder_models(config_data: IAConfig, reg: "registry.Registry") -> None:
    """Put on the configuration, family by family, every builder model the
    registry holds: what the structuring of the builder lists registered."""
    config_data.runtime_builders = reg.get_all_instances_by_classification(VCT.RUNTIME_BUILDER_MODEL)  # type: ignore
    config_data.state_backends = reg.get_all_instances_by_classification(VCT.STATE_BACKEND_MODEL)  # type: ignore
    config_data.os_builders = reg.get_all_instances_by_classification(VCT.OS_BUILDER_MODEL)  # type: ignore
    config_data.group_builders = reg.get_all_instances_by_classification(VCT.GROUP_BUILDER_MODEL)  # type: ignore
    config_data.user_builders = reg.get_all_instances_by_classification(VCT.USER_BUILDER_MODEL)  # type: ignore
    config_data.mod_builders = reg.get_all_instances_by_classification(VCT.MOD_BUILDER_MODEL)  # type: ignore
    config_data.storage_builders = reg.get_all_instances_by_classification(VCT.STORAGE_BUILDER_MODEL)  # type: ignore
    config_data.image_builders = reg.get_all_instances_by_classification(VCT.IMAGE_BUILDER_MODEL)  # type: ignore
    config_data.instance_builders = reg.get_all_instances_by_classification(VCT.INSTANCE_BUILDER_MODEL)  # type: ignore


def _build_builders(
    config_data: IAConfig,
    addl_config: dict[str, Any],
    reg: "registry.Registry",
) -> list[BuilderBase]:
    """Build and register the builders of every family the configuration
    declares (the runtimes always; another family only when it has entries)
    and return them as one list. The families are built in one order and
    listed in another, and each order is kept for what depends on it:

    * BUILT: runtimes, state backends, OS, group, user, image, instance,
      modification, storage. The runtimes must come first: every model
      that names a runtime resolves the name (or ``default``) against the
      runtime builders' names, aliases and default, which the runtimes'
      own build registers.
    * LISTED (by name within a family): runtimes, state backends, group,
      user, OS, modification, storage, image, instance. The list is the
      run's ``all_sorted_builders``, and its order is the run's: every
      phase hook walks the builders in it (the generation before and after
      a phase and the deferred commands it collects, the executor's pre-,
      post- and failed-phase hooks), and the state-location check walks
      the terraform roots in it, so its refusals come out in this order.
      Listing in the build order changes no file the installed plugins
      emit (each family acts in a phase of its own), but it would reorder
      those refusals (an instance root's ahead of a storage root's) and
      the hooks of any builder that acts in another family's phase, so
      the listing keeps its own order."""
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
    return builders


def _enter_working_directory(root_dir: Path, config_data: IAConfig) -> tuple[Path, Path]:
    """The root is the working path: resolved, refused when it does not
    exist, made the process's current directory, and returned with the
    generation path under it. The configuration's ``working_directory`` is
    accepted and not read: every load is handed its root, and the root is
    where the run works."""
    wpath = Path(root_dir).resolve()
    if not wpath.exists():
        raise FileNotFoundError(f"Working directory {wpath} does not exist.")
    # Deliberately NOT a scoped change: the loaded configuration is used from
    # its root for the rest of the command (relative paths in it resolve
    # against the root), so the process stays there. The CLI's main callback
    # restores the invoking directory when its context closes.
    os.chdir(wpath)
    gen_path = (
        wpath / config_data.generation_directory
        if config_data.generation_directory
        else wpath / "generated"
    )
    return wpath, gen_path


def _read_overlays(
    overlays: list[Path] | None,
    config_data: IAConfig,
) -> tuple[list[Path], list[dict[str, Any]]]:
    """Read the overlay files (paths resolved against the current
    directory) and merge each one's ``config`` keys over the
    configuration's; the resolved paths and what each file held."""
    # Transient declarations: overlay files merged over the tree for THIS
    # invocation only -- their `config:` keys land on the merged config here,
    # after the builders were built against the tree's own (as they always were);
    # their items are merged kind by kind as each kind is read (apply_overlays).
    overlay_paths = [Path(p).resolve() for p in (overlays or [])]
    overlay_data = [load_overlay(p) for p in overlay_paths]
    for data in overlay_data:
        if data.get("config"):
            if config_data.config is None:
                config_data.config = {}
            config_data.config.update(data["config"])
    return overlay_paths, overlay_data


def _bind_builders(builders: list[BuilderBase], ctx: RunContext) -> None:
    """Hand the run context to every builder that takes one."""
    # the context is passed (DESIGN's phrase): every builder holds the one it
    # was registered into, bound BEFORE the kinds are read, since attaching
    # an item to its builder may ask the builder for its run
    for b in builders:
        # a builder that satisfies the contract structurally (the contract
        # example's) carries no bind; it reads nothing from the context
        bind = getattr(b, "bind", None)
        if callable(bind):
            bind(ctx)


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
        # the contract's protocol, not the core's base class --
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
        aliases = model.aliases                  # every builder model carries them (BuilderModelProtocol)
        if model.name in aliases:
            aliases.remove(model.name)
        reg.register_aliases(classification, model.name, list(aliases))  # Keeps aliases from colliding
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
        if isinstance(model, RuntimeEnabledBuilderModelProtocol):   # the protocol check is the dispatch
            rt = reg.get_registered_name_by_name_or_alias(VCT.RUNTIME_BUILDER, model.runtime)
            assert rt, f"Runtime provider '{rt}' not found for builder '{model.name}'"
            model.runtime = rt
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
                if callable(prov.__post_init__):
                    prov.__post_init__()  # type: ignore
        prov.finalize()
        # the registry gates on the instance (NameTypedProtocol) and
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
                # (unsafe_load once stood here alone; every other reader of
                # the tree is safe_load, and no tree carries a tag)
                data = yaml.safe_load(stream)
                if isinstance(data, dict):
                    # needs NO identity -- a structural check, so it
                    # still runs where nothing could be decrypted
                    refuse_markers_at(data, str(file))
                    # nothing may be named after a word that means "not
                    # set"; refused here so the message names the file and entry
                    refuse_reserved_names(data, str(file))
                    # the `config:` key guard, switched on as written
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
    reg = builder._run_context().reg
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


# ------------------------------------------------------------------------- the services
# The engine's run-bound knowledge as a plugin reaches it: ``ctx.services.<name>``
# answers with one of these, each delegating to the module the functions
# live in (the modules do not move; the functions keep their signatures,
# minus the context they are bound to). Each lists its contract protocol as
# a base so pyright compares the signatures; ``assert_conforms`` checks them
# at the bar. The modules annotate the context as the kit's ``RunContext``.

class _Service:
    def __init__(self, ctx: RunContext) -> None:
        self._ctx: RunContext = ctx


class LineageService(_Service, LineageServiceProtocol):
    def owner_of(self, tags: dict[str, Any] | None) -> str:
        return lineage.owner_of(tags)

    def belongs_to_another_configuration(self, tags: dict[str, Any]) -> bool:
        return lineage.belongs_to_another_configuration(self._ctx, tags)

    def ours_or_unlabelled(self, tags: dict[str, Any] | None) -> bool:
        return lineage.ours_or_unlabelled(self._ctx, tags)

    def config_tags(self) -> dict[str, str]:
        return lineage.config_tags(self._ctx)

    def configuration_tag(self) -> str:
        return lineage.configuration_tag(self._ctx)

    def lineage_tags(self, image: Any, runtime: str | None = None) -> dict[str, str]:
        return lineage.lineage_tags(self._ctx, image, runtime)

    def series_of(self, image: Any) -> str:
        return lineage.series_of(image)

    def mod_records(self, image: Any) -> list[dict[str, Any]]:
        return lineage.mod_records(self._ctx, image)

    def bake_disk_size(self, image: Any, runtime: str | None) -> int | str | None:
        return lineage.bake_disk_size(self._ctx, image, runtime)

    def pinned_parent_build(self, image: Any, runtime: str | None = None) -> str | None:
        return lineage.pinned_parent_build(self._ctx, image, runtime)

    def record_build(self, image: Any, runtime: str, build_id: str, name: str | None,
                     resolve_parent: Callable[[str], str | None]) -> dict[str, Any]:
        return lineage.record_build(self._ctx, image, runtime, build_id, name, resolve_parent)

    def pinned_instance_build(self, instance: Any) -> str | None:
        return lineage.pinned_instance_build(self._ctx, instance)

    def instance_follow_target(self, instance: Any) -> tuple[str, str] | None:
        return lineage.instance_follow_target(self._ctx, instance)

    def pending_instance_replacements(self, instances: list[Any]) -> set[str]:
        return lineage.pending_instance_replacements(self._ctx, instances)


class LaunchService(_Service, LaunchServiceProtocol):
    def compute_launch_params(self, instance: Any) -> dict[str, Any]:
        return launch_params.compute_launch_params(self._ctx, instance)

    def user_data_template(self, params: dict[str, Any]) -> str:
        return launch_params.user_data_template(params, self._ctx)

    def detachments(self, instance: Any) -> list[dict[str, Any]]:
        return launch_params.detachments(self._ctx, instance)

    def group_builder_of(self, group: str) -> GroupBuilderProtocol | None:
        return capabilities.group_builder_of(self._ctx, group)

    def failure_policy(self, instance: Any) -> tuple[str, int | None]:
        return ephemeral_policy.failure_policy(self._ctx, instance)

    def teardown_due(self, instance: Any, now: datetime | None = None) -> bool:
        return ephemeral_policy.teardown_due(self._ctx, instance, now)


class SecretsService(_Service, SecretsServiceProtocol):
    def is_marker(self, value: Any) -> bool:
        return _encryption.is_marker(value)

    def decrypt_marker(self, marker: str, identities: Iterable[Any] | None = None) -> str:
        return _encryption.decrypt_marker(marker, identities)

    def emit(self, value: Any) -> Any:
        return _encryption.emit(value)


class FilesService(_Service, FilesServiceProtocol):
    def mirror_path(self, config_root: Path, path: Path) -> Path:
        return materialize.mirror_path(config_root, path)


class CommandsService(_Service, CommandsServiceProtocol):
    def execute_command_line(self, indent: str = "    ") -> str:
        return bake_steps.execute_command_line(indent)

    def settle_commands(self, runtime_commands: list[str] | None = None) -> list[str]:
        return bake_steps.settle_commands(runtime_commands)


class ImagesService(_Service, ImagesServiceProtocol):
    def image_chain(self, image: Any) -> tuple[list[str], str | None]:
        return capabilities.image_chain(self._ctx, image)

    def resolve_bake_user(self, image: Any, runtime: str) -> str:
        return bake_user.resolve_bake_user(self._ctx, image, runtime)

    def os_type_for_family(self, family: str | None) -> type:
        return os_types.os_type_for_family(family, self._ctx.reg)

    def packaged_entries_of(self, package: str) -> list[Mapping[str, Any]]:
        return _image_sources.packaged_entries_of(package)

    def container_reference(self, query: ImageQuery) -> str | None:
        return _image_sources.container_reference(query)

    def base_image_verify_commands(self, base: Any, runtime_name: str) -> list[str]:
        return image_tests.base_image_verify_commands(self._ctx, base, runtime_name)

    def instance_image_verify_commands(self, image: Any, runtime_name: str | None = None) -> list[str]:
        return image_tests.instance_image_verify_commands(self._ctx, image, runtime_name)

    def finalize_provisioner(self, source_label: str, runtime_name: str, os_family: str | None) -> list[str]:
        return image_tests.finalize_provisioner(self._ctx, source_label, runtime_name, os_family)

    def verify_provisioner(self, source_label: str, cmds: list[str], what: str) -> list[str]:
        return image_tests.verify_provisioner(source_label, cmds, what)

    def admin_user(self, os_builder_name: str) -> str:
        return capabilities.admin_user(self._ctx, os_builder_name)

    def admin_public_keys(self, base: Any = None, os_builder_name: str | None = None) -> list[str]:
        return capabilities.admin_public_keys(self._ctx, base, os_builder_name)


class IdentityService(_Service, IdentityServiceProtocol):
    def declared_attributes(self) -> dict[str, dict[str, dict[str, Any]]]:
        return identity_attributes.declared_attributes(self._ctx)

    def standing_instances(self, *, runtime: str | None = None, names: list[str] | None = None) -> list[Any]:
        return standing.standing_instances(self._ctx, runtime=runtime, names=names)

    def group_builders_by_identity_type(self) -> Mapping[str, Sequence[GroupBuilderProtocol]]:
        return capabilities.group_builders_by_identity_type(self._ctx)


class StorageService(_Service, StorageServiceProtocol):
    def undeclared_transitions(self) -> list[Any]:
        return list(storage_state.undeclared_transitions(self._ctx))

    def storage_builders_by_type(self) -> Mapping[str, Sequence[StorageBuilderProtocol]]:
        return capabilities.storage_builders_by_type(self._ctx)


class WorkspacesService(_Service, WorkspacesServiceProtocol):
    def terraform_workspaces(self) -> dict[str, tuple[str | None, str | None]]:
        return standing.terraform_workspaces(self._ctx)

    def deployed_in_workspace(self, workspace: str) -> list[str]:
        return standing.deployed_in_workspace(self._ctx, workspace)

    def backup_state(self, workspace: str, tofu: str, run_id: str, cwd: Path) -> int:
        return state_backup.backup(self._ctx, workspace, tofu, run_id, cwd)


class ScopeService(_Service, ScopeServiceProtocol):
    def apply_enabled(self, lifecycle_key: str, root: str | None = None, aliases: Iterable[str] = ()) -> bool:
        return utils.apply_enabled(self._ctx, lifecycle_key, root, aliases)

    def root_in_runtime_scope(self, runtime: str | None) -> bool:
        return utils.root_in_runtime_scope(self._ctx, runtime)

    def module_source(self, module_dirname: str, workspace_dir: Path | None = None) -> str:
        return utils.module_source(self._ctx, module_dirname, workspace_dir)


class CliService(_Service, CliServiceProtocol):
    def system_cli_executable(self, args: list[str], working_directory: Path | None = None) -> ExecutableProtocol:
        return utils.system_cli_executable(args, working_directory)

    def system_cli_executable_with_config(self, args: list[str],
                                          working_directory: Path | None = None) -> ExecutableProtocol:
        return utils.system_cli_executable_with_config(self._ctx, args, working_directory)


class LifecyclesService(_Service, LifecyclesServiceProtocol):
    def all_lifecycles(self) -> list[LifecycleLike]:
        return _lifecycles.all_lifecycles()

    def builder_vcts_of(self, lifecycle: LifecycleLike) -> set[VCT]:
        return _lifecycles.builder_vcts_of(lifecycle)


class RunServices(ServicesProtocol):
    """The services of one run, bound to its context by the loader."""

    def __init__(self, ctx: RunContext) -> None:
        self._lineage = LineageService(ctx)
        self._launch = LaunchService(ctx)
        self._secrets = SecretsService(ctx)
        self._files = FilesService(ctx)
        self._commands = CommandsService(ctx)
        self._images = ImagesService(ctx)
        self._identity = IdentityService(ctx)
        self._storage = StorageService(ctx)
        self._workspaces = WorkspacesService(ctx)
        self._scope = ScopeService(ctx)
        self._cli = CliService(ctx)
        self._lifecycles = LifecyclesService(ctx)
        self._meta_state: MetaStateProtocol = ctx.meta_state

    @property
    def lineage(self) -> LineageServiceProtocol:
        return self._lineage

    @property
    def launch(self) -> LaunchServiceProtocol:
        return self._launch

    @property
    def secrets(self) -> SecretsServiceProtocol:
        return self._secrets

    @property
    def files(self) -> FilesServiceProtocol:
        return self._files

    @property
    def commands(self) -> CommandsServiceProtocol:
        return self._commands

    @property
    def images(self) -> ImagesServiceProtocol:
        return self._images

    @property
    def identity(self) -> IdentityServiceProtocol:
        return self._identity

    @property
    def storage(self) -> StorageServiceProtocol:
        return self._storage

    @property
    def workspaces(self) -> WorkspacesServiceProtocol:
        return self._workspaces

    @property
    def scope(self) -> ScopeServiceProtocol:
        return self._scope

    @property
    def cli(self) -> CliServiceProtocol:
        return self._cli

    @property
    def lifecycles(self) -> LifecyclesServiceProtocol:
        return self._lifecycles

    @property
    def meta_state(self) -> MetaStateProtocol:
        return self._meta_state


#: the adapters, each with the protocol it implements (the bar's conformance check)
SERVICE_PAIRS: tuple[tuple[type, type], ...] = (
    (LineageService, LineageServiceProtocol), (LaunchService, LaunchServiceProtocol),
    (SecretsService, SecretsServiceProtocol), (FilesService, FilesServiceProtocol),
    (CommandsService, CommandsServiceProtocol), (ImagesService, ImagesServiceProtocol),
    (IdentityService, IdentityServiceProtocol), (StorageService, StorageServiceProtocol),
    (WorkspacesService, WorkspacesServiceProtocol), (ScopeService, ScopeServiceProtocol),
    (CliService, CliServiceProtocol), (LifecyclesService, LifecyclesServiceProtocol),
    (RunServices, ServicesProtocol),
)
