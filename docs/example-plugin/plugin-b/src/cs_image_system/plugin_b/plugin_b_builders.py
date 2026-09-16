from cs_image_system.base.basic.builder_base import BuilderBase
from cs_image_system.base.constants import VCT
from .plugin_b_types import PluginBModel

# Probably a more specific type of parent builder class
class PluginBBuilder(BuilderBase[PluginBModel]): 

    @classmethod
    def csis_name(cls) -> str:
        return "Plugin_B_Builder"

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.GROUP_BUILDER # Or whatever type

    # Your code implements here
    pass
