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
    named, and nothing of that plugin loads. The plugin's namespace is
    settled here too (:func:`namespace_of_distribution`,
    :func:`namespace_for`): a plugin with none is refused the same way."""
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
            initializer = entry.load()
            for md in _metadata_of(initializer):
                if isinstance(md, PluginMetadataProtocol):
                    namespace_for(pname, md, derived)
                    check_conformance(pname, md)
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
