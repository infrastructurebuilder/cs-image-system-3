# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from collections.abc import Callable
from functools import cache
from importlib.metadata import entry_points
from typing import Any, NamedTuple

from cs_image_system.contract.constants import VCT, PLUGIN_TYPES
from cs_image_system.contract.core import PluginArtifactProtocol, PluginMetadataProtocol
from cs_image_system.contract.testing import conformance_problems, protocol_for
from cs_image_system.base import registry


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
        raise PluginConformanceError(f"Plugin {pname} is refused:\n  " + "\n  ".join(problems))


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


@cache
def _discovered_plugins() -> tuple[DiscoveredPlugin, ...]:
    """Every installed plugin's ``initialize`` by plugin type and name, in
    name order: discovered (entry points read, modules imported) ONCE per
    process; what each one registers is replayed into every registry a run
    makes. Discovery is where the installed plugin is held to the
    contract: every class its metadata registers is checked
    against the protocol of its classification, once, as shipped -- a
    shortfall is a :class:`PluginConformanceError` here, with the member
    named, and nothing of that plugin loads -- and the entry-point group
    it was found under is held to what it registers (:func:`check_group`). The plugin's namespace is
    settled here too (:func:`namespace_of_distribution`,
    :func:`namespace_for`): a plugin with none is refused the same way. A
    plugin whose entry point fails to import (or whose ``initialize``
    raises) is not a refusal but an absence: one ERROR line names the
    plugin and the error, and the rest load."""
    found: list[DiscoveredPlugin] = []
    for plugin_type, plugin_key in PLUGIN_TYPES:
        log.debug(f"Loading plugins of type: {plugin_type}")
        plugins = entry_points(group=f'cs_image_system.plugins.{plugin_type}')
        if not plugins:
            log.debug(f"No '{plugin_type}' plugins found.")
        plugin_names = sorted([plugin.name for plugin in plugins])
        log.info(f"Found {len(plugins)} {plugin_type} plugins.")
        for pname in plugin_names:
            entry = plugins[pname]
            dist = getattr(entry, "dist", None)
            derived = namespace_of_distribution(dist.name) if dist is not None else None
            # an entry point whose module does not import, or whose
            # ``initialize`` raises, is reported once and skipped, as a hook
            # plugin is: the other plugins load and every command keeps
            # working without it (a traceback here would end them all)
            try:
                initializer = entry.load()
                metadata = _metadata_of(initializer)
            except Exception as e:
                log.error(f"Plugin {pname} ({plugin_type}) failed to import and is skipped: {type(e).__name__}: {e}")
                continue
            for md in metadata:
                if isinstance(md, PluginMetadataProtocol):
                    namespace_for(pname, md, derived)
                    check_conformance(pname, md)
            check_group(pname, plugin_type, metadata)
            found.append(DiscoveredPlugin(plugin_type, pname, derived, initializer))
    return tuple(found)


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


def load_plugins(reg: "registry.Registry | None" = None) -> None:
    """Register every installed plugin's models, builders and checkers into
    ``reg`` -- the registry of the run being loaded (the loader
    makes one per run and loads the plugins into it) -- or, with no
    registry given, into the process's current one
    (:func:`~.registry.current_registry`): a pre-load command (the
    preflight, the catalog, the scan) and the CLI callback load that way."""
    # Discovery via entry_points
    if reg is None:
        reg = registry.current_registry()
    if reg.vct_type_registry:
        # Idempotent: plugins register exactly once per registry lifetime.
        # A second call on the same registry within one process -- the CLI
        # callback after a library caller already loaded, or a test
        # harness -- must not raise type collisions.
        log.debug("Plugins already loaded; skipping discovery")
        return
    registered_by_namespace: dict[str, list[str]] = {}
    for plugin_type, pname, derived, initialized in _discovered_plugins():
        log.debug(f"Loading plugin: {pname}")
        # In our case, this can return a single PluginMetadataProtocol instance or a list of them
        for md in _metadata_of(initialized):
            if not isinstance(md, PluginMetadataProtocol):
                log.error(f"Plugin {pname} did not return a valid PluginMetadataProtocol instance.")
                continue
            namespace = namespace_for(pname, md, derived)
            reg.register_plugin_metadata(md, namespace=namespace)
            words = registered_by_namespace.setdefault(namespace, [])
            for service_name, services in md.services.items():
                for service in services:
                    reg.register_service(service, namespace=namespace)
                    words.append(f"{service.csis_classifier().value}:{service.csis_name()}")
                    if service.csis_classifier() in [VCT.CLOUD_BUILDER_MODEL, VCT.CONTAINER_BUILDER_MODEL]:
                        log.debug(f"Registering service: {service.csis_name()} {service.csis_classifier()} as RUNTIME")
                        # the second registration carries the namespace with it
                        reg.register_service(service, override_classifier=VCT.RUNTIME_BUILDER_MODEL, namespace=namespace)
                        log.debug(f"Registered service: {service.csis_name()} {service.csis_classifier()}")
            for classifier, injected in md.injected_models.items():
                injected_any: Any = injected
                name = injected_any.csis_name() if isinstance(injected_any, PluginArtifactProtocol) else injected.__name__
                words.append(f"{classifier.value}:{name}")
    # one line per load at INFO; the per-namespace detail at DEBUG, where a
    # `--verbose` run reads it (at INFO it was a hundred lines on every command)
    for namespace, words in sorted(registered_by_namespace.items()):
        log.debug(f"namespace {namespace}: registered {', '.join(words) or 'nothing'}")
    log.info(f"registered {sum(len(w) for w in registered_by_namespace.values())} classes "
             f"under {len(registered_by_namespace)} namespaces")

    # All plugin model/builder classes are now registered; drop any cached cattrs
    # Converter so it rebuilds against the full plugin set on next use.
    from cs_image_system.base.orchestrator import Orchestrator
    Orchestrator().invalidate_converter()
