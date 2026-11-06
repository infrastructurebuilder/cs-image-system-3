# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from collections.abc import Callable
from functools import cache
from importlib.metadata import entry_points
from typing import Any

from cs_image_system.contract.constants import VCT, PLUGIN_TYPES
from cs_image_system.contract.core import PluginArtifactProtocol, PluginMetadataProtocol
from cs_image_system.contract.testing import conformance_problems, protocol_for
from cs_image_system.base import registry


log = logging.getLogger(__name__)


class PluginConformanceError(ValueError):
    """A plugin registered a class that does not satisfy the contract's
    protocol for its classification (stage 125): refused when the plugin is
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


@cache
def _discovered_plugins() -> tuple[tuple[str, str, Callable[[], Any]], ...]:
    """Every installed plugin's ``initialize`` by plugin type and name, in
    name order: discovered (entry points read, modules imported) ONCE per
    process; what each one registers is replayed into every registry a run
    makes (stage 124). Discovery is where the installed plugin is held to
    the contract (stage 125): every class its metadata registers is checked
    against the protocol of its classification, once, as shipped -- a
    shortfall is a :class:`PluginConformanceError` here, with the member
    named, and nothing of that plugin loads."""
    found: list[tuple[str, str, Callable[[], Any]]] = []
    for plugin_type, plugin_key in PLUGIN_TYPES:
        log.debug(f"Loading plugins of type: {plugin_type}")
        plugins = entry_points(group=f'cs_image_system.plugins.{plugin_type}')
        if not plugins:
            log.debug(f"No '{plugin_type}' plugins found.")
        plugin_names = sorted([plugin.name for plugin in plugins])
        log.info(f"Found {len(plugins)} {plugin_type} plugins.")
        for pname in plugin_names:
            initializer = plugins[pname].load()
            for md in _metadata_of(initializer):
                if isinstance(md, PluginMetadataProtocol):
                    check_conformance(pname, md)
            found.append((plugin_type, pname, initializer))
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
    ``reg`` -- the registry of the run being loaded (stage 124: the loader
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
    for plugin_type, pname, initialized in _discovered_plugins():
        log.debug(f"Loading plugin: {pname}")
        # In our case, this can return a single PluginMetadataProtocol instance or a list of them
        for md in _metadata_of(initialized):
            if not isinstance(md, PluginMetadataProtocol):
                log.error(f"Plugin {pname} did not return a valid PluginMetadataProtocol instance.")
                continue
            reg.register_plugin_metadata(md)
            for service_name, services in md.services.items():
                for service in services:
                    reg.register_service(service)
                    if service.csis_classifier() in [VCT.CLOUD_BUILDER_MODEL, VCT.CONTAINER_BUILDER_MODEL]:
                        log.debug(f"Registering service: {service.csis_name()} {service.csis_classifier()} as RUNTIME")
                        reg.register_service(service, override_classifier=VCT.RUNTIME_BUILDER_MODEL)
                        log.debug(f"Registered service: {service.csis_name()} {service.csis_classifier()}")

    # All plugin model/builder classes are now registered; drop any cached cattrs
    # Converter so it rebuilds against the full plugin set on next use.
    from cs_image_system.base.orchestrator import Orchestrator
    Orchestrator().invalidate_converter()
