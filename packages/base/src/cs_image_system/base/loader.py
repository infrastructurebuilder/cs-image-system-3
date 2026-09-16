# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from importlib.metadata import entry_points

from cs_image_system.base.constants import VCT, PLUGIN_TYPES
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol
from cs_image_system.base import registry


log = logging.getLogger(__name__)

def load_plugins():
    # Discovery via entry_points
    reg = registry.Registry()
    if reg.vct_type_registry:
        # Idempotent: plugins register exactly once per registry lifetime
        # (Registry.reset() empties it). A second call within one process --
        # the CLI callback after a library caller already loaded, or a test
        # harness -- must not raise type collisions.
        log.debug("Plugins already loaded; skipping discovery")
        return
    # reg.register_plugin_metadata(DefaultExecutableModelPluginMetadata())
    for plugin_type, plugin_key in PLUGIN_TYPES:
        log.info(f"Loading plugins of type: {plugin_type}")
        plugins = entry_points(group=f'cs_image_system.plugins.{plugin_type}')
        if not plugins:
            log.warning(f"No '{plugin_type}' plugins found.")
        plugin_names = sorted([plugin.name for plugin in plugins])    
        log.info(f"Found {len(plugins)} plugins.")
        for pname in plugin_names:
            plugin = plugins[pname]
            log.info(f"Loading plugin: {plugin.name}")
            initialized = plugin.load()
            # In our case, this can return a single PluginMetadataProtocol instance or a list of them
            _md = initialized()
            if not isinstance(_md, list):
                _md = [_md]
            for md in _md:            
                if not isinstance(md, PluginMetadataProtocol):
                    log.error(f"Plugin {plugin.name} did not return a valid PluginMetadataProtocol instance.")
                    continue
                reg.register_plugin_metadata(md)
                for service_name, services in md.services.items():
                    for service in services:                    
                        reg.register_service(service)
                        if service.csis_classifier() in [VCT.CLOUD_BUILDER_MODEL, VCT.CONTAINER_BUILDER_MODEL]:
                            log.info(f"Registering service: {service.csis_name()} {service.csis_classifier()} as RUNTIME")
                            reg.register_service(service, override_classifier=VCT.RUNTIME_BUILDER_MODEL)
                            log.debug(f"Registered service: {service.csis_name()} {service.csis_classifier()}")
                # for model, builder in md.builders_for_models.items():
                #     log.info(f"Registering builder for model: {model.__name__} -> {builder.__name__}")
                #     reg.register_builder_for_model(model, builder)
                #     log.debug(f"Registered builder for model: {model.__name__} -> {builder.__name__}")

    # All plugin model/builder classes are now registered; drop any cached cattrs
    # Converter so it rebuilds against the full plugin set on next use.
    from cs_image_system.base.orchestrator import Orchestrator
    Orchestrator().invalidate_converter()
