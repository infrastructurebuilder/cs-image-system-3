import logging
from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol
from cs_image_system.base import registry
from .plugin_b_types import PluginBModel
from .plugin_b_builders import PluginBBuilder
log = logging.getLogger(__name__)
 # This is how the plugin is referenced within
 # the system (ie. type: group-plugin-bee)
PLUGIN_B_NAME = "group-plugin-bee"
class PluginBMetadata(AbstractPluginMetadata, PluginMetadataProtocol):
  def __init__(self) -> None:
    super().__init__("1", "3.13",
                    {PLUGIN_B_NAME: [
                       PluginBModel,
                       PluginBBuilder,
                     ]},
                     {PluginBModel: PluginBBuilder}
                     )
  ...
def initialize():
  log.info("Initializing Plugin B")
  # You may also return a list of PluginMetadataProtocol instances if needed
  return PluginBMetadata()
