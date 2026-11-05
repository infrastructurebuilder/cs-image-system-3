# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from collections.abc import Callable
from functools import cache
from importlib.metadata import entry_points
from typing import Any

from cs_image_system.base.constants import VCT, PLUGIN_TYPES
from cs_image_system.contract.core import PluginMetadataProtocol
from cs_image_system.base import registry


log = logging.getLogger(__name__)


@cache
def _discovered_plugins() -> tuple[tuple[str, str, Callable[[], Any]], ...]:
    """Every installed plugin's ``initialize`` by plugin type and name, in
    name order: discovered (entry points read, modules imported) ONCE per
    process; what each one registers is replayed into every registry a run
    makes (stage 124)."""
    found: list[tuple[str, str, Callable[[], Any]]] = []
    for plugin_type, plugin_key in PLUGIN_TYPES:
        log.debug(f"Loading plugins of type: {plugin_type}")
        plugins = entry_points(group=f'cs_image_system.plugins.{plugin_type}')
        if not plugins:
            log.debug(f"No '{plugin_type}' plugins found.")
        plugin_names = sorted([plugin.name for plugin in plugins])
        log.info(f"Found {len(plugins)} {plugin_type} plugins.")
        for pname in plugin_names:
            found.append((plugin_type, pname, plugins[pname].load()))
    return tuple(found)


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
        _md = initialized()
        if not isinstance(_md, list):
            _md = [_md]
        for md in _md:
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
