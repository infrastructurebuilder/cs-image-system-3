from cs_image_system.base.constants import VCT
from cs_image_system.base.models.builder_model import BuilderModel, RuntimeEnabledBuilderModel

# Probably use a more specific type of parent model class, like GroupBuilderModel
# if your plugin represents groups, etc.
class PluginBModel(RuntimeEnabledBuilderModel): 
    
    type = "pluginb"
        
    @classmethod
    def csis_name(cls) -> str:
        return "Plugin_B_Model"

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.GROUP_BUILDER_MODEL # or whtever the VCT type

    # Your code implements here

    pass    
