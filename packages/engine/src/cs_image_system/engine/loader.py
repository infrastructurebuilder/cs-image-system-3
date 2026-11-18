# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import functools
import logging
from collections.abc import Callable, Mapping
from functools import cache
from importlib.metadata import entry_points
from typing import Any, NamedTuple, cast

from cs_image_system.base import registry
from cs_image_system.contract import enrollment, field_kinds
from cs_image_system.contract.constants import PLUGIN_TYPES, VCT
from cs_image_system.contract.core import PluginArtifactProtocol, PluginMetadataProtocol
from cs_image_system.contract.testing import conformance_problems, protocol_for

log = logging.getLogger(__name__)


#: What every workspace distribution's name starts with, and what a plugin's
#: ends with; both are dropped from a distribution name to make a namespace.
DISTRIBUTION_PREFIX = "cs-image-system-"
PLUGIN_SUFFIX = "-plugin"


def namespace_of_distribution(dist_name: str) -> str:
    """The namespace a plugin's registrations carry, from the name of the
    distribution that declares its entry point: the ``cs-image-system-``
    prefix and the ``-plugin`` suffix dropped, so the workspace's
    ``cs-image-system-<kind>-plugin`` becomes ``<kind>`` and the core's own
    distribution becomes ``base``; a distribution named otherwise keeps its
    name whole."""
    name = dist_name.strip().lower()
    if name.startswith(DISTRIBUTION_PREFIX) and len(name) > len(DISTRIBUTION_PREFIX):
        name = name[len(DISTRIBUTION_PREFIX):]
    if name.endswith(PLUGIN_SUFFIX) and len(name) > len(PLUGIN_SUFFIX):
        name = name[:-len(PLUGIN_SUFFIX)]
    return name


class PluginNamespaceError(ValueError):
    """A plugin whose registrations would carry no namespace: its entry
    point has no distribution to derive one from and its metadata names
    none. Refused when the plugin is discovered, with the field named."""


def namespace_for(pname: str, md: PluginMetadataProtocol, derived: str | None) -> str:
    """The namespace one plugin metadata record registers under: the
    ``namespace`` the record names (an override), else the one derived
    from the plugin's distribution, else the refusal."""
    chosen = md.namespace or derived
    if not chosen:
        raise PluginNamespaceError(
            f"Plugin {pname} is refused: its entry point has no distribution to derive a namespace from, "
            f"and its metadata names none; set PluginMetadata.namespace")
    if registry.NAMESPACE_SEPARATOR in chosen:
        raise PluginNamespaceError(
            f"Plugin {pname} is refused: PluginMetadata.namespace {chosen!r} may not contain "
            f"{registry.NAMESPACE_SEPARATOR!r}")
    return chosen


class PluginConformanceError(ValueError):
    """A plugin registered a class that does not satisfy the contract's
    protocol for its classification: refused when the plugin is
    discovered, with the plugin, the class, the protocol and every missing
    or mis-signed member named, instead of an ``AttributeError`` later in
    the run."""


def check_conformance(pname: str, md: PluginMetadataProtocol) -> None:
    """Hold every class ``md`` registers to the protocol of its
    classification (:func:`~cs_image_system.contract.testing.protocol_for`):
    a service under a builder or builder-model classification, and every
    builder in ``builders_for_models`` under its model's. A class under a
    classification the contract declares no protocol for (an injected item
    model, a version checker) is held only to ``PluginArtifactProtocol``."""
    checks: list[tuple[type, type | None]] = []
    for services in md.services.values():
        for service in services:
            if not isinstance(service, PluginArtifactProtocol):
                raise PluginConformanceError(
                    f"Plugin {pname}: {service!r} names no csis_name/csis_classifier (PluginArtifactProtocol)")
            checks.append((service, protocol_for(service.csis_classifier())))
    for model_cls, builder_cls in md.builders_for_models.items():
        if isinstance(model_cls, PluginArtifactProtocol):
            model_protocol = protocol_for(model_cls.csis_classifier())
            checks.append((model_cls, model_protocol))
            builder_protocol = protocol_for(builder_cls.csis_classifier()) \
                if isinstance(builder_cls, PluginArtifactProtocol) else None
            checks.append((builder_cls, builder_protocol))
    problems: list[str] = []
    seen: set[type] = set()
    for cls, protocol in checks:
        if protocol is None or cls in seen:       # a class listed as a service and as a builder: one check
            continue
        seen.add(cls)
        shortfalls = conformance_problems(cls, protocol)
        if shortfalls:
            problems.append(f"{cls.__module__}.{cls.__qualname__} does not conform to {protocol.__qualname__}: "
                            + "; ".join(shortfalls))
    if problems:
        raise PluginConformanceError(f"Plugin {pname} is refused: " + "; ".join(problems))


#: What a plugin discovered under an entry-point group registers: at least
#: one class of the group's classifications, or the group it chose is not
#: the one it is. ``base`` (the core's own) and ``other`` (anything the
#: named groups do not cover: a checker, an injected model) name no kind
#: and are not held to one.
GROUP_CLASSIFICATIONS: dict[str, frozenset[VCT]] = {
    "runtime": frozenset({VCT.RUNTIME_BUILDER_MODEL, VCT.RUNTIME_BUILDER, VCT.CLOUD_BUILDER_MODEL, VCT.CLOUD_BUILDER,
                          VCT.CONTAINER_BUILDER_MODEL, VCT.CONTAINER_BUILDER}),
    "state": frozenset({VCT.STATE_BACKEND_MODEL, VCT.STATE_BACKEND}),
    "modification": frozenset({VCT.MOD_BUILDER_MODEL, VCT.MOD_BUILDER}),
    "storage": frozenset({VCT.STORAGE_BUILDER_MODEL, VCT.STORAGE_BUILDER}),
    "group": frozenset({VCT.GROUP_BUILDER_MODEL, VCT.GROUP_BUILDER}),
    "user": frozenset({VCT.USER_BUILDER_MODEL, VCT.USER_BUILDER}),
    "image": frozenset({VCT.IMAGE_BUILDER_MODEL, VCT.IMAGE_BUILDER}),
    "os": frozenset({VCT.OS_BUILDER_MODEL, VCT.OS_BUILDER}),
    "instance": frozenset({VCT.INSTANCE_BUILDER_MODEL, VCT.INSTANCE_BUILDER}),
}


class PluginGroupError(ValueError):
    """A plugin declared under an entry-point group whose kind it does not
    register (a group builder under ``cs_image_system.plugins.runtime``):
    refused when the plugin is discovered, with the group it chose, what it
    registers and the groups that fit named."""


def registered_classifications(metadata: list[Any]) -> set[VCT]:
    """Every classification the classes of ``metadata`` (one plugin's
    records) register under: the services', the builders' and their
    models', the injected models' keys."""
    out: set[VCT] = set()
    for md in metadata:
        if not isinstance(md, PluginMetadataProtocol):
            continue
        for services in md.services.values():
            out.update(s.csis_classifier() for s in services if isinstance(s, PluginArtifactProtocol))
        for model_cls, builder_cls in md.builders_for_models.items():
            out.update(c.csis_classifier() for c in (model_cls, builder_cls) if isinstance(c, PluginArtifactProtocol))
        out.update(md.injected_models.keys())
    return out


def check_group(pname: str, plugin_type: str, metadata: list[Any]) -> None:
    """Hold the entry-point group ``plugin_type`` the plugin was found under
    to what its classes register: a group in :data:`GROUP_CLASSIFICATIONS`
    needs at least one class of its kind, else :class:`PluginGroupError`.
    A plugin may register more than its group's kind (an instance plugin's
    storage roots, an identity plugin's users beside its groups); the group
    names the kind it is, not every kind it has."""
    expected = GROUP_CLASSIFICATIONS.get(plugin_type)
    if expected is None:
        return
    registered = registered_classifications(metadata)
    if registered & expected:
        return
    fitting = sorted(g for g, kinds in GROUP_CLASSIFICATIONS.items() if kinds & registered)
    raise PluginGroupError(
        f"Plugin {pname} is refused: declared under cs_image_system.plugins.{plugin_type}, it registers no "
        f"{plugin_type} class, only {', '.join(sorted(c.value for c in registered)) or 'nothing'}; "
        + (f"the group that fits what it registers: {', '.join(fitting)}" if fitting else
           "a plugin of no named kind declares cs_image_system.plugins.other"))


class DiscoveredPlugin(NamedTuple):
    """One installed plugin as discovery leaves it: its type and entry-point
    name, the namespace derived from its distribution (``None`` when the
    entry point has none, which only a metadata ``namespace`` cures) and
    its ``initialize``."""

    plugin_type: str
    name: str
    derived_namespace: str | None
    initializer: Callable[[], Any]


#: why a plugin could not be used
FAILED_TO_IMPORT = "failed to import"
REFUSED = "refused"
COLLIDES = "collides"


class Unusable(NamedTuple):
    """One installed plugin that discovery could not use. It is skipped:
    nothing of it loads, one ERROR line names it and the cause, and every
    command on a configuration that does not use it works. ``words`` are
    the ``classification:name`` pairs it would have registered, when its
    metadata could be read; ``other`` is, for a collision, the plugin it
    collides with and ``claim`` the thing both claim."""

    plugin: str
    distribution: str
    plugin_type: str
    cause: str
    detail: str
    words: tuple[str, ...] = ()
    other: str = ""
    claim: str = ""

    def named(self) -> str:
        return f"{self.plugin} ({self.distribution})" if self.distribution else self.plugin

    def said(self) -> str:
        """The plugin and why it could not be used, as a sentence's end:
        ``thing (cs-image-system-thing-plugin): failed to import: ...``."""
        if self.cause == COLLIDES:
            return f"{self.named()}: it and {self.other} both register {self.claim}"
        return f"{self.named()}: {self.cause}: {self.detail}"


def _words_of(metadata: list[Any]) -> tuple[str, ...]:
    out: list[str] = []
    for md in metadata:
        if isinstance(md, PluginMetadataProtocol):
            for services in md.services.values():
                out += [f"{s.csis_classifier().value}:{s.csis_name()}" for s in services
                        if isinstance(s, PluginArtifactProtocol)]
    return tuple(sorted(set(out)))


def _registrations(pname: str, derived: str | None, metadata: list[Any]) -> dict[tuple[str, str, str], type]:
    """What one plugin would put in a registry, by key: (classification,
    namespace, name) -> class. Every key a load writes: each service under
    its own classification, a cloud's or a container's model a second time
    as a runtime's, and each injected model under the classification it is
    injected at."""
    out: dict[tuple[str, str, str], type] = {}
    for md in metadata:
        if not isinstance(md, PluginMetadataProtocol):
            continue
        namespace = namespace_for(pname, md, derived)
        for services in md.services.values():
            for service in services:
                classifier = service.csis_classifier()
                out[(classifier.value, namespace, service.csis_name())] = service
                if classifier in (VCT.CLOUD_BUILDER_MODEL, VCT.CONTAINER_BUILDER_MODEL):
                    out[(VCT.RUNTIME_BUILDER_MODEL.value, namespace, service.csis_name())] = service
        for classifier, injected in md.injected_models.items():
            injected_any: Any = injected
            name = injected_any.csis_name() if isinstance(injected_any, PluginArtifactProtocol) else injected.__name__
            out[(classifier.value, namespace, str(name))] = injected
    return out


#: the classifications a runtime type is registered under
RUNTIME_CLASSIFICATIONS = frozenset({VCT.RUNTIME_BUILDER, VCT.CLOUD_BUILDER, VCT.CONTAINER_BUILDER})
#: who else may own something a plugin replaced
THE_SYSTEM = "the system itself"


def _shared_kinds() -> dict[str, dict[str, Any]]:
    """The two registries of the contract that a plugin fills by a call of
    its own, not through its metadata, and that every run in the process
    shares: the enrollment kinds and the field kinds, by what a collision
    over one is called."""
    return {"enrollment kind": cast(dict[str, Any], enrollment._KINDS),
            "field kind": cast(dict[str, Any], field_kinds._HANDLERS)}


def _replaced(before: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    """Every (registry, key) that held something in ``before`` and holds
    something else now: what the plugin that just loaded replaced. The
    same value registered again (a module loaded twice) is no replacement."""
    out: list[tuple[str, str]] = []
    for what, now in _shared_kinds().items():
        for key, was in before[what].items():
            if key in now and now[key] is not was and now[key] != was:
                out.append((what, key))
    return sorted(out)


def _restore(before: dict[str, dict[str, Any]], package: str) -> None:
    """Put the two shared registries back as ``before`` has them, for what
    the plugin whose own package is ``package`` did: a kind it replaced
    gets its earlier value back, and a kind it added is removed when its
    code is the plugin's own (:func:`_defined_in`). A kind added by a
    module outside the plugin's package -- a library the plugin imports,
    which another plugin may import too and which will not run again -- is
    the library's, and stays."""
    for what, now in _shared_kinds().items():
        added = {key: value for key, value in now.items()
                 if key not in before[what] and _a_librarys(_defined_in(what, value), package)}
        now.clear()
        now.update(before[what])
        now.update(added)


def _defined_in(what: str, value: Any) -> str:
    """The module that defines a kind's code: an enrollment kind's
    renderer (the function a ``functools.partial`` wraps, for one), a field
    kind's handler class.

    The rule stops here, by decision (research R13): a kind a plugin builds
    from a library's code -- a renderer a library's factory returns, an
    instance of a library's handler class -- reads as the library's, and
    is kept when the plugin is skipped. A library's module runs once per
    process, so what it registered cannot be told apart from what another
    plugin that imports it relies on; keeping it is the side that cannot
    break a usable plugin."""
    if what == "enrollment kind":
        renderer: Any = getattr(value, "script_lines", None)
        while isinstance(renderer, functools.partial):
            renderer = renderer.func
        return str(getattr(renderer, "__module__", "") or "")
    return str(type(value).__module__ or "")


def _own_package(entry: Any) -> str:
    """The package a plugin's entry point lives in, which holds its own
    code: under this system's root the package below it
    (``cs_image_system.<name>_plugin``), else the top-level package. For
    an entry point a test builds in process, with no value to read, the
    module its ``load`` is defined in."""
    value = str(getattr(entry, "value", "") or "")
    if value:
        parts = value.split(":", 1)[0].split(".")
        return ".".join(parts[:2]) if parts[0] == "cs_image_system" and len(parts) > 1 else parts[0]
    return str(getattr(getattr(entry, "load", None), "__module__", "") or "")


def _inside(module: str, package: str) -> bool:
    return bool(package) and (module == package or module.startswith(package + "."))


#: what defines the base classes a kind may be an instance of: a kind whose code is only these is the
#: registering plugin's, not a library's
_CONTRACT = "cs_image_system.contract"


def _a_librarys(module: str, package: str) -> bool:
    """Whether a kind whose code is in ``module`` belongs to a library
    rather than to the plugin whose own package is ``package``: it is
    defined outside the plugin's package, and not merely by the contract's
    base classes (a handler that is an instance of the contract's own
    class is the plugin's that registered it)."""
    return bool(module) and not _inside(module, package) and not _inside(module, _CONTRACT)


def _runtime_types(metadata: list[Any]) -> set[str]:
    """The runtime types one plugin registers."""
    return {s.csis_name() for md in metadata if isinstance(md, PluginMetadataProtocol)
            for services in md.services.values() for s in services
            if isinstance(s, PluginArtifactProtocol) and s.csis_classifier() in RUNTIME_CLASSIFICATIONS}


def _image_source_blocks(metadata: list[Any]) -> set[str]:
    """The runtime types the image-source catalog one plugin ships carries
    a block for (each runtime class's ``image_source_entries()``)."""
    out: set[str] = set()
    for md in metadata:
        if not isinstance(md, PluginMetadataProtocol):
            continue
        for services in md.services.values():
            for service in services:
                hook: Any = getattr(service, "image_source_entries", None)
                if not callable(hook) or not isinstance(service, PluginArtifactProtocol) \
                        or service.csis_classifier() not in RUNTIME_CLASSIFICATIONS:
                    continue
                answered: Any = cast(Any, hook)()
                for entry in answered or []:
                    if not isinstance(entry, Mapping):
                        raise TypeError(f"{service.__qualname__}.image_source_entries() answered {entry!r}, "
                                        "not a mapping")
                    out.update(str(k) for k in (entry.get("sources") or {}))
    return out


def _register(reg: "registry.Registry", pname: str, derived: str | None, metadata: list[Any]) -> dict[str, list[str]]:
    """Register one plugin's metadata records into ``reg``; the
    ``classification:name`` words it registered, by namespace."""
    registered: dict[str, list[str]] = {}
    for md in metadata:
        if not isinstance(md, PluginMetadataProtocol):
            log.error(f"Plugin {pname} did not return a valid PluginMetadataProtocol instance.")
            continue
        namespace = namespace_for(pname, md, derived)
        reg.register_plugin_metadata(md, namespace=namespace)
        words = registered.setdefault(namespace, [])
        for _service_name, services in md.services.items():
            for service in services:
                reg.register_service(service, namespace=namespace)
                words.append(f"{service.csis_classifier().value}:{service.csis_name()}")
                if service.csis_classifier() in [VCT.CLOUD_BUILDER_MODEL, VCT.CONTAINER_BUILDER_MODEL]:
                    # a cloud's or a container's model is a runtime's too; the second registration carries
                    # the namespace with it
                    reg.register_service(service, override_classifier=VCT.RUNTIME_BUILDER_MODEL, namespace=namespace)
        for classifier, injected in md.injected_models.items():
            injected_any: Any = injected
            name = injected_any.csis_name() if isinstance(injected_any, PluginArtifactProtocol) else injected.__name__
            words.append(f"{classifier.value}:{name}")
    return registered


class _Discovering:
    """One reading of the installed plugins, as it goes: the plugins that
    loaded and passed the checks (``candidates``), those that could not be
    used, and the collisions among the candidates."""

    def __init__(self) -> None:
        self.candidates: list[tuple[DiscoveredPlugin, list[Any], str]] = []
        self.unusable: list[Unusable] = []
        # collisions among the candidates, by the candidate's index: the other party and the claim
        self.colliding: dict[int, tuple[str, str]] = {}
        # who registered each enrollment kind and field kind in this reading, by candidate index: the CLAIMANT,
        # whatever defines the kind's code, is who a collision over it names; the OWNER, recorded only when the
        # code is the plugin's own, is who loses it when skipped (a library's kind stays for its other users)
        self.kind_claimant: dict[tuple[str, str], int] = {}
        self.kind_owner: dict[tuple[str, str], int] = {}
        # the kinds two plugins already collided over, with everyone who claimed them: nobody's from then on
        self.collided_kinds: dict[tuple[str, str], list[str]] = {}
        # the runtime types each candidate's image-source catalog carries a block for, by candidate index
        self.blocks: dict[int, set[str]] = {}

    def named(self, index: int) -> str:
        found, _metadata, dist_name = self.candidates[index]
        return f"{found.name} ({dist_name})" if dist_name else found.name

    def skip(self, u: Unusable) -> None:
        # one line, whatever the cause's message holds (a validation error's report runs over several)
        u = u._replace(detail=" ".join(u.detail.split()))
        self.unusable.append(u)
        log.error(f"Plugin {u.named()} is skipped: {u.cause}: {u.detail}")

    def one_name_twice(self, plugin_type: str, pname: str, dists: list[str]) -> None:
        """One entry-point name in one group, from several distributions:
        none is loaded, all are named."""
        claim = f"entry point {pname!r} (cs_image_system.plugins.{plugin_type})"
        both = " and ".join(f"{pname} ({d or 'a distribution without a name'})" for d in sorted(dists))
        log.error(f"Plugins {both} are both skipped: both register {claim}")
        for n, dist_name in enumerate(dists):
            others = ", ".join(sorted(d for m, d in enumerate(dists) if m != n))
            self.unusable.append(Unusable(pname, dist_name, plugin_type, COLLIDES, claim, (), others, claim))

    def load(self, plugin_type: str, pname: str, entry: Any, dist_name: str) -> None:
        """Load one plugin and hold it to the contract; a candidate when
        it passes, else skipped with whatever it registered on the way
        taken back."""
        derived = namespace_of_distribution(dist_name) if dist_name else None
        before = {what: dict(held) for what, held in _shared_kinds().items()}
        package = _own_package(entry)
        try:
            initializer = entry.load()
            metadata = _metadata_of(initializer)
        except Exception as e:
            _restore(before, package)
            self.skip(Unusable(pname, dist_name, plugin_type, FAILED_TO_IMPORT, f"{type(e).__name__}: {e}"))
            return
        try:
            for md in metadata:
                if isinstance(md, PluginMetadataProtocol):
                    namespace_for(pname, md, derived)
                    check_conformance(pname, md)
            check_group(pname, plugin_type, metadata)
        except (PluginNamespaceError, PluginConformanceError, PluginGroupError) as e:
            _restore(before, package)
            self.skip(Unusable(pname, dist_name, plugin_type, REFUSED, str(e), _words_of(metadata)))
            return
        try:
            # what the plugin answers and registers must be readable by itself: the image-source hook the core
            # asks of every runtime class, and its registrations, which every load replays into a registry
            blocks = _image_source_blocks(metadata)
            _register(registry.Registry(), pname, derived, metadata)
        except Exception as e:
            _restore(before, package)
            self.skip(Unusable(pname, dist_name, plugin_type, REFUSED,
                               f"Plugin {pname} is refused: what it registers cannot be loaded: "
                               f"{type(e).__name__}: {e}", _words_of(metadata)))
            return
        me = Unusable(pname, dist_name, plugin_type, COLLIDES, "", _words_of(metadata))
        replaced = _replaced(before)
        if replaced:
            self.replaced_a_kind(me, replaced[0], before, package)
            return
        added = [(what, key) for what, held in _shared_kinds().items() for key in held if key not in before[what]]
        contested = [kind for kind in added if kind in self.collided_kinds]
        if contested:
            # a kind two plugins already collided over is nobody's: a later claimant is skipped too, so the
            # outcome is the same whichever of them was found first
            what, key = contested[0]
            claim = f"{what} {key!r}"
            others = self.collided_kinds[(what, key)]
            _restore(before, package)
            self.unusable.append(me._replace(detail=claim, claim=claim, other=" and ".join(others)))
            log.error(f"Plugin {me.named()} is skipped: {COLLIDES}: {claim} is also registered by "
                      f"{' and '.join(others)}, and is nobody's")
            others.append(me.named())
            return
        # a kind is this plugin's when its code is: one a shared library registered is the library's, and
        # skipping this plugin later must not take it from another plugin that imports the same library
        held = _shared_kinds()
        for kind in added:
            self.kind_claimant[kind] = len(self.candidates)
            if not _a_librarys(_defined_in(kind[0], held[kind[0]][kind[1]]), package):
                self.kind_owner[kind] = len(self.candidates)
        self.blocks[len(self.candidates)] = blocks
        self.candidates.append((DiscoveredPlugin(plugin_type, pname, derived, initializer), metadata, dist_name))

    def replaced_a_kind(self, plugin: Unusable, kind: tuple[str, str], before: dict[str, dict[str, Any]],
                        package: str) -> None:
        """An enrollment kind or a field kind that was already registered
        now holds this plugin's: this one is skipped and the registries are
        put back; when another plugin of this reading owned the kind that
        one is skipped too, and the kind is neither's."""
        what, key = kind
        claim = f"{what} {key!r}"
        _restore(before, package)
        owner = self.kind_claimant.get((what, key))
        me = plugin._replace(detail=claim, claim=claim, other=THE_SYSTEM if owner is None else self.named(owner))
        self.unusable.append(me)
        if owner is None:
            log.error(f"Plugin {me.named()} is skipped: it registers {claim}, which is {THE_SYSTEM}'s")
            return
        del _shared_kinds()[what][key]
        self.collided_kinds[(what, key)] = [self.named(owner), me.named()]
        self.colliding.setdefault(owner, (me.named(), claim))
        log.error(f"Plugins {self.named(owner)} and {me.named()} are both skipped: both register {claim}")

    def _one_key_two_classes(self) -> dict[frozenset[int], str]:
        """Two candidates that would register DIFFERENT classes under one
        key (the same class from several plugins is one registration and
        is allowed), by pair, with the key."""
        registered = [_registrations(found.name, found.derived_namespace, metadata)
                      for found, metadata, _dist in self.candidates]
        owners: dict[tuple[str, str, str], list[int]] = {}
        for index, mine in enumerate(registered):
            for key in mine:
                owners.setdefault(key, []).append(index)
        pairs: dict[frozenset[int], str] = {}
        for key, indexes in sorted(owners.items()):
            if len({id(registered[i][key]) for i in indexes}) > 1:
                claim = f"{key[0]} {key[1]}{registry.NAMESPACE_SEPARATOR}{key[2]}"
                # each claimant beside one that registers a DIFFERENT class: a line never names two that agree
                for i in indexes:
                    other = next(j for j in indexes if registered[j][key] is not registered[i][key])
                    pairs.setdefault(frozenset((i, other)), claim)
        return pairs

    def _a_block_for_anothers_runtime(self) -> dict[frozenset[int], str]:
        """A candidate whose image-source catalog carries a block for a
        runtime type ANOTHER candidate registers (the block is the
        registering plugin's to ship), by pair, with the block."""
        runtime_owner: dict[str, int] = {}
        for index, (_found, metadata, _dist) in enumerate(self.candidates):
            for runtime_type in _runtime_types(metadata):
                runtime_owner.setdefault(runtime_type, index)
        pairs: dict[frozenset[int], str] = {}
        for index, (_found, metadata, _dist) in enumerate(self.candidates):
            for runtime_type in sorted(self.blocks.get(index, set()) - _runtime_types(metadata)):
                owner = runtime_owner.get(runtime_type)
                if owner is not None and owner != index:
                    pairs.setdefault(frozenset((index, owner)), f"image-source block {runtime_type!r}")
        return pairs

    def _one_model_two_builders(self) -> dict[frozenset[int], str]:
        """Two candidates that name DIFFERENT builders for one model class
        (the same builder from several plugins is one registration), by
        pair, with the model."""
        named: dict[type, list[tuple[int, type]]] = {}
        for index, (_found, metadata, _dist) in enumerate(self.candidates):
            for md in metadata:
                if isinstance(md, PluginMetadataProtocol):
                    for model, builder in md.builders_for_models.items():
                        named.setdefault(model, []).append((index, builder))
        pairs: dict[frozenset[int], str] = {}
        for model, claims in sorted(named.items(), key=lambda item: f"{item[0].__module__}.{item[0].__qualname__}"):
            if len({id(builder) for _index, builder in claims}) > 1:
                # everyone who names a builder for a disputed model is in the collision, each beside one that
                # names another
                for i, mine in claims:
                    other = next((j for j, theirs in claims if j != i and theirs is not mine), None)
                    if other is not None:
                        pairs.setdefault(frozenset((i, other)), f"the builder for {model.__module__}.{model.__qualname__}")
        return pairs

    def _one_classification_two_defaults(self) -> dict[frozenset[int], str]:
        """Two candidates that each mark a DIFFERENT injected model the
        default of one classification, by pair, with the classification."""
        marked: dict[VCT, list[tuple[int, str]]] = {}
        for index, (_found, metadata, _dist) in enumerate(self.candidates):
            for md in metadata:
                if isinstance(md, PluginMetadataProtocol) and md.is_injected_models_default:
                    for classifier, model in md.injected_models.items():
                        injected: Any = model
                        name = injected.csis_name() if isinstance(injected, PluginArtifactProtocol) else model.__name__
                        marked.setdefault(classifier, []).append((index, str(name)))
        pairs: dict[frozenset[int], str] = {}
        for classifier, claims in sorted(marked.items(), key=lambda item: item[0].value):
            if len({name for _index, name in claims}) > 1:
                for i, mine in claims:
                    other = next((j for j, theirs in claims if j != i and theirs != mine), None)
                    if other is not None:
                        pairs.setdefault(frozenset((i, other)), f"the default {classifier.value}")
        return pairs

    def _loadable_together(self, indexes: list[int]) -> list[int]:
        """The candidates of ``indexes`` whose registrations load into one
        registry together, as every run replays them. The collisions this
        reading knows by kind are found before this and skip both sides;
        this is the net under them: whatever else a registry refuses skips
        the plugin it refused, named with the registry's own words, so that
        no registration can stop a load."""
        remaining = list(indexes)
        while True:
            reg = registry.Registry()
            refused: tuple[int, Exception] | None = None
            for index in remaining:
                found, metadata, _dist = self.candidates[index]
                try:
                    _register(reg, found.name, found.derived_namespace, metadata)
                except Exception as e:
                    refused = (index, e)
                    break
            if refused is None:
                return remaining
            index, error = refused
            found, metadata, dist_name = self.candidates[index]
            self.skip(Unusable(found.name, dist_name, found.plugin_type, REFUSED,
                               f"Plugin {found.name} is refused: what it registers cannot be loaded beside the "
                               f"plugins found before it: {type(error).__name__}: {error}", _words_of(metadata)))
            remaining.remove(index)

    def settled(self) -> tuple[tuple[DiscoveredPlugin, ...], tuple[Unusable, ...]]:
        """The usable plugins and the unusable ones, once the collisions
        among the candidates are found: both sides of each are skipped."""
        pairs = self._one_key_two_classes()
        for more in (self._one_model_two_builders(), self._one_classification_two_defaults(),
                     self._a_block_for_anothers_runtime()):
            for pair, claim in more.items():
                pairs.setdefault(pair, claim)
        for pair, claim in sorted(pairs.items(), key=lambda item: sorted(item[0])):
            i, j = sorted(pair)
            log.error(f"Plugins {self.named(i)} and {self.named(j)} are both skipped: both register {claim}")
            self.colliding.setdefault(i, (self.named(j), claim))
            self.colliding.setdefault(j, (self.named(i), claim))
        for i, (other, claim) in sorted(self.colliding.items()):
            found, metadata, dist_name = self.candidates[i]
            self.unusable.append(Unusable(found.name, dist_name, found.plugin_type, COLLIDES, claim,
                                          _words_of(metadata), other, claim))
        together = self._loadable_together([i for i in range(len(self.candidates)) if i not in self.colliding])
        self._take_back_kinds(set(range(len(self.candidates))) - set(together))
        return tuple(self.candidates[i][0] for i in together), tuple(self.unusable)

    def _take_back_kinds(self, skipped: set[int]) -> None:
        """Remove from the contract's two shared registries every enrollment
        kind and field kind that a candidate skipped at settling registered
        when it was imported: nothing of a skipped plugin stays registered.
        (A plugin skipped while it loads was put back then.)"""
        shared = _shared_kinds()
        for (what, key), owner in self.kind_owner.items():
            if owner in skipped:
                shared[what].pop(key, None)


def discover() -> tuple[tuple[DiscoveredPlugin, ...], tuple[Unusable, ...]]:
    """Read the installed plugins once, from their entry points: the ones
    that can be used, by plugin type and name, in name order, and the ones
    that cannot, each with its cause.

    Discovery is where an installed plugin is held to the contract: every
    class its metadata registers is checked against the protocol of its
    classification, as shipped (:func:`check_conformance`); the entry-point
    group it was found under is held to what it registers
    (:func:`check_group`); and its namespace is settled
    (:func:`namespace_of_distribution`, :func:`namespace_for`).

    A plugin that cannot be used is never a reason to stop: it is an
    absence. That is so whether its entry point fails to import, its
    ``initialize`` raises, it is refused by one of the three checks above,
    or it collides with another plugin: two entry points of one name in
    one group; two plugins registering different classes under one key;
    one plugin replacing an enrollment kind or a field kind another
    registered; or one plugin shipping an image-source block for a runtime
    type another registers. One ERROR line names the plugin and the cause
    -- for a collision both plugins, and neither is used, so the outcome
    never depends on the order they were found in -- and the rest load. A
    configuration that needs such a plugin fails validation, which says so
    (``commands/load_failures``)."""
    found = _Discovering()
    for plugin_type, _plugin_key in PLUGIN_TYPES:
        log.debug(f"Loading plugins of type: {plugin_type}")
        plugins = list(entry_points(group=f'cs_image_system.plugins.{plugin_type}'))
        if not plugins:
            log.debug(f"No '{plugin_type}' plugins found.")
        log.info(f"Found {len(plugins)} {plugin_type} plugins.")
        by_name: dict[str, list[Any]] = {}
        for entry in plugins:
            by_name.setdefault(entry.name, []).append(entry)
        for pname in sorted(by_name):
            entries = by_name[pname]
            dists = [str(getattr(getattr(e, "dist", None), "name", "") or "") for e in entries]
            if len(entries) > 1:
                found.one_name_twice(plugin_type, pname, dists)
            else:
                found.load(plugin_type, pname, entries[0], dists[0])
    return found.settled()


# shared by every run in the process: the installed plugins, which each run replays into a registry of its own
@cache
def _discovery() -> tuple[tuple[DiscoveredPlugin, ...], tuple[Unusable, ...]]:
    return discover()


def _discovered_plugins() -> tuple[DiscoveredPlugin, ...]:
    """Every usable installed plugin's ``initialize`` by plugin type and
    name, in name order: discovered ONCE per process (:func:`discover`);
    what each one registers is replayed into every registry a run makes."""
    return _discovery()[0]


def unusable_plugins() -> tuple[Unusable, ...]:
    """The installed plugins this process could not use, with their causes
    (:func:`discover`): what a command names when a configuration needs one."""
    return _discovery()[1]


def _metadata_of(initializer: Callable[[], Any]) -> list[Any]:
    """What an entry point's ``initialize`` returns, as a list: one
    ``PluginMetadata`` or several."""
    md = initializer()
    return md if isinstance(md, list) else [md]


def discover_plugins() -> None:
    """Discover (and check) the installed plugins without loading them into
    a registry: a test session calls it first, so the plugins are held to
    the contract as shipped, before any test stubs a hook."""
    _discovered_plugins()


def installed_registry() -> "registry.Registry":
    """A registry of its own with every installed plugin loaded into it and
    nothing of any run: what a command reads the installed classes from
    before, or without, a load (the public-safe scan, the standalone gid
    lookup, the classification of a failed load). A new one on every call:
    no caller shares it, so nothing one registers reaches another. A
    loaded run reads its own, ``ctx.reg``. The replay is not announced at
    INFO: that line is the run's own load's."""
    reg = registry.Registry()
    load_plugins(reg, announce=False)
    return reg


def load_plugins(reg: "registry.Registry", *, announce: bool = True) -> None:
    """Register every installed plugin's models, builders and checkers into
    ``reg``: the registry of the run being loaded (the loader makes one per
    run and loads the plugins into it), or one a pre-load command made for
    itself (:func:`installed_registry`). ``announce`` says whether the one
    line counting what registered is logged at INFO (a run's load) or at
    DEBUG."""
    if reg.vct_type_registry:
        # Idempotent: plugins register exactly once per registry lifetime.
        # A second call on the same registry -- a caller that prepared one
        # and handed it to the loader -- must not raise type collisions.
        log.debug("Plugins already loaded; skipping discovery")
        return
    registered_by_namespace: dict[str, list[str]] = {}
    for _plugin_type, pname, derived, initialized in _discovered_plugins():
        log.debug(f"Loading plugin: {pname}")
        # an entry point answers one PluginMetadata or a list of them
        for namespace, words in _register(reg, pname, derived, _metadata_of(initialized)).items():
            registered_by_namespace.setdefault(namespace, []).extend(words)
    # one line per load at INFO; the per-namespace detail at DEBUG, where a
    # `--verbose` run reads it (at INFO it was a hundred lines on every command)
    for namespace, words in sorted(registered_by_namespace.items()):
        log.debug(f"namespace {namespace}: registered {', '.join(words) or 'nothing'}")
    log.log(logging.INFO if announce else logging.DEBUG,
            f"registered {sum(len(w) for w in registered_by_namespace.values())} classes "
            f"under {len(registered_by_namespace)} namespaces")
