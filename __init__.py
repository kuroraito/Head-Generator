# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import logging

import time
import datetime
import json
import os
import numpy
#from pathlib import Path
from math import radians, degrees

import bpy
from bpy.app.handlers import persistent
from bpy_extras.io_utils import ExportHelper, ImportHelper

# from . import addon_updater_ops
from . import algorithms
# from . import animationengine
from . import creation_tools_ops
# from . import expressionengine
# from . import expressionscreator
# from . import facerig
from . import file_ops
# from . import hairengine
from . import humanoid
# from . import humanoid_rotations
# from . import jointscreator
from . import morphcreator
# from . import node_ops
from . import numpy_ops
from . import object_ops
# from . import proxyengine
from . import transfor
from . import utils
# from . import preferences
from . import mesh_ops
from . import measurescreator
# from . import skeleton_ops
# from . import vgroupscreator

logger = logging.getLogger(__name__)

bl_info = {
    "name" : "Head Generator",
    "author" : "KuroLight",
    "description" : "Dataset generation addon",
    "blender" : (2, 80, 0),
    "location" : "Operators> StartSession",
    "version" : (0, 0, 2),
    "location" : "",
    "warning" : "",
    "category" : "Characters"
}


humanoid = humanoid.Humanoid()

gui_status = "NEW_SESSION"
gui_err_msg = ""
gui_allows_other_modes = False

# mblab_retarget = animationengine.RetargetEngine()
# mblab_shapekeys = expressionengine.ExpressionEngineShapeK()
# mblab_proxy = proxyengine.ProxyEngine()
# mbcrea_expressionscreator = expressionscreator.ExpressionsCreator()
mbcrea_transfor = transfor.Transfor(humanoid)



def start_session():
    global humanoid
    global gui_status, gui_err_msg
    
    logger.info("Starting Lab Session...")

    scn = bpy.context.scene
    character_identifier = scn.mblab_character_name
    lib_filepath = file_ops.get_blendlibrary_path()
    rigging_type = "base"

    obj = None
    is_existing = False
    is_obj = algorithms.looking_for_humanoid_obj()

    if is_obj[0] == "ERROR":
        gui_status = "ERROR_SESSION"
        gui_err_msg = is_obj[1]
        return

    if is_obj[0] == "NO_OBJ":
        base_model_name = humanoid.characters_config[character_identifier]["template_model"]
        obj = file_ops.import_object_from_lib(lib_filepath, base_model_name, character_identifier)
        if obj != None:
            # obj can be None when a config file has missing data.
            obj["manuellab_vers"] = bl_info["version"]
            obj["manuellab_id"] = character_identifier
            obj["manuellab_rig"] = rigging_type

    if is_obj[0] == "FOUND":
        obj = file_ops.get_object_by_name(is_obj[1])
        character_identifier = obj["manuellab_id"]
        rigging_type = obj["manuellab_rig"]
        is_existing = True


    if not obj:
        logger.critical("Init failed...")
        gui_status = "ERROR_SESSION"
        gui_err_msg = "Init failed. Check the log file"
    else:
        humanoid.init_database(obj, character_identifier, rigging_type)
        if humanoid.has_data:
            gui_status = "ACTIVE_SESSION"

            if scn.mblab_use_cycles or scn.mblab_use_eevee:
                if scn.mblab_use_cycles:
                    scn.render.engine = 'CYCLES'
                else:
                    scn.render.engine = 'BLENDER_EEVEE'
                if scn.mblab_use_lamps:

                    object_ops.add_lighting()

            else:
                scn.render.engine = 'BLENDER_WORKBENCH'

            logger.info("Rendering engine now is %s", scn.render.engine)
            init_morphing_props(humanoid)
            # init_categories_props(humanoid)
            init_measures_props(humanoid)
            # init_restposes_props(humanoid)
            init_presets_props(humanoid)
            init_ethnic_props(humanoid)
            init_metaparameters_props(humanoid)
            # init_material_parameters_props(humanoid)
            # humanoid.update_materials()

            if is_existing:
                logger.info("Re-init the character %s", obj.name)
                humanoid.store_mesh_in_cache()
                humanoid.reset_mesh()
                humanoid.recover_prop_values_from_obj_attr()
                humanoid.restore_mesh_from_cache()
            else:
                humanoid.reset_mesh()
                humanoid.update_character(mode="update_all")
            
            # All inits for creation tools.
            morphcreator.init_morph_names_database()
            # mbcrea_expressionscreator.reset_expressions_items()
            mbcrea_transfor.set_scene(scn)
            init_cmd_props(humanoid)
            measurescreator.init_all()
            creation_tools_ops.init_config()
            # End for that.
            algorithms.deselect_all_objects()
    algorithms.remove_censors()


class StartSession(bpy.types.Operator):
    bl_idname = "mbast.init_character"
    bl_label = "Create character"
    bl_description = 'Create the character selected above'
    bl_context = 'objectmode'
    bl_options = {'REGISTER', 'INTERNAL', 'UNDO'}

    def execute(self, context):
        start_session()
        return {'FINISHED'}

def update_characters_name(self, context):
    global humanoid
    return humanoid.humanoid_types

bpy.types.Scene.mblab_character_name = bpy.props.EnumProperty(
    items=update_characters_name,
    name="Select",
    default=None)

def init_morphing_props(humanoid_instance):
    for prop in humanoid_instance.character_data:
        setattr(
            bpy.types.Object,
            prop,
            bpy.props.FloatProperty(
                name=prop.split("_")[1],
                min=-5.0,
                max=5.0,
                soft_min=0.0,
                soft_max=1.0,
                precision=3,
                default=0.5,
                subtype='FACTOR',
                update=realtime_update))

def init_cmd_props(humanoid_instance):
    for prop in morphcreator.get_all_cmd_attr_names(humanoid_instance):
        setattr(
            bpy.types.Object,
            prop,
            bpy.props.BoolProperty(
                name=prop.split("_")[2],
                default=False))

def init_measures_props(humanoid_instance):
    for measure_name, measure_val in humanoid_instance.morph_engine.measures.items():
        setattr(
            bpy.types.Object,
            measure_name,
            bpy.props.FloatProperty(
                name=measure_name, min=0.0, max=500.0,
                subtype='FACTOR',
                default=measure_val))
    humanoid_instance.sync_gui_according_measures()

# def init_restposes_props(humanoid_instance):
#     if humanoid_instance.exists_rest_poses_database():
#         restpose_items = file_ops.generate_items_list(humanoid_instance.restposes_path)
#         bpy.types.Object.rest_pose = bpy.props.EnumProperty(
#             items=restpose_items,
#             name="Rest pose",
#             default=restpose_items[0][0],
#             update=restpose_update)


# def init_maleposes_props():
#     global mblab_retarget
#     if mblab_retarget.maleposes_exist:
#         if not hasattr(bpy.types.Object, 'male_pose'):
#             malepose_items = file_ops.generate_items_list(mblab_retarget.maleposes_path)
#             bpy.types.Object.male_pose = bpy.props.EnumProperty(
#                 items=malepose_items,
#                 name="Male pose",
#                 default=malepose_items[0][0],
#                 update=malepose_update)


# def init_femaleposes_props():
#     global mblab_retarget
#     if mblab_retarget.femaleposes_exist:
#         if not hasattr(bpy.types.Object, 'female_pose'):
#             femalepose_items = file_ops.generate_items_list(mblab_retarget.femaleposes_path)
#             bpy.types.Object.female_pose = bpy.props.EnumProperty(
#                 items=femalepose_items,
#                 name="Female pose",
#                 default=femalepose_items[0][0],
#                 update=femalepose_update)


# def init_expression_props():
#     for expression_name in mblab_shapekeys.expressions_labels:
#         if not hasattr(bpy.types.Object, expression_name):
#             setattr(
#                 bpy.types.Object,
#                 expression_name,
#                 bpy.props.FloatProperty(
#                     name=expression_name,
#                     min=0.0,
#                     max=1.0,
#                     precision=3,
#                     default=0.0,
#                     subtype='FACTOR',
#                     update=human_expression_update))


def init_presets_props(humanoid_instance):
    if humanoid_instance.exists_preset_database():
        preset_items = file_ops.generate_items_list(humanoid_instance.presets_path)
        bpy.types.Object.preset = bpy.props.EnumProperty(
            items=preset_items,
            name="Types",
            update=preset_update)


def init_ethnic_props(humanoid_instance):
    if humanoid_instance.exists_phenotype_database():
        ethnic_items = file_ops.generate_items_list(humanoid_instance.phenotypes_path)
        bpy.types.Object.ethnic = bpy.props.EnumProperty(
            items=ethnic_items,
            name="Phenotype",
            update=ethnic_update)


def init_metaparameters_props(humanoid_instance):
    for meta_data_prop in humanoid_instance.character_metaproperties.keys():
        upd_function = None

        if "age" in meta_data_prop:
            upd_function = age_update
        if "mass" in meta_data_prop:
            upd_function = mass_update
        if "tone" in meta_data_prop:
            upd_function = tone_update
        if "last" in meta_data_prop:
            upd_function = None

        if "last_" not in meta_data_prop:
            setattr(
                bpy.types.Object,
                meta_data_prop,
                bpy.props.FloatProperty(
                    name=meta_data_prop, min=-1.0, max=1.0,
                    precision=3,
                    default=0.0,
                    subtype='FACTOR',
                    update=upd_function))


def init_material_parameters_props(humanoid_instance):
    for material_data_prop, value in humanoid_instance.character_material_properties.items():
        setattr(
            bpy.types.Object,
            material_data_prop,
            bpy.props.FloatProperty(
                name=material_data_prop,
                min=0.0,
                max=1.0,
                precision=2,
                subtype='FACTOR',
                update=material_update,
                default=value))


# def init_categories_props(humanoid_instance):
#     global mbcrea_expressionscreator
#     bpy.types.Scene.morphingCategory = bpy.props.EnumProperty(
#         items=get_categories_enum(),
#         update=modifiers_update,
#         name="Morphing categories")
    
    # # Sub-categories for "Facial expressions"
    # mbcrea_expressionscreator.set_expressions_modifiers(humanoid)
    # sub_categories_enum = mbcrea_expressionscreator.get_expressions_sub_categories()
    
    # bpy.types.Scene.expressionsSubCategory = bpy.props.EnumProperty(
    #     items=sub_categories_enum,
    #     update=modifiers_update,
    #     name="Expressions sub-categories")

    # # Special properties used by transfor.Transfor
    # bpy.types.Scene.transforMorphingCategory = bpy.props.EnumProperty(
    #     items=get_categories_enum(["Expressions"]),
    #     update=modifiers_update,
    #     name="Morphing categories")

#End Teto

def realtime_update(self, context):
    """
    Update the character while the prop slider moves.
    """
    global humanoid
    if humanoid.bodydata_realtime_activated:
        # time1 = time.time()
        scn = bpy.context.scene
        humanoid.update_character(category_name=scn.morphingCategory, mode="update_realtime")
        #Teto
        # Dirty, but I didn't want to touch the code too much.
        # I tried things, but I am pretty sure that they would
        # bring inconsistencies when changing model without
        # quitting Blender.
        # So we always update expressions category, because same
        # prop are used in "facial expression creator".
        if scn.morphingCategory != "Expressions":
            humanoid.update_character(category_name="Expressions", mode="update_realtime")
        #End Teto
        humanoid.sync_gui_according_measures()
        # print("realtime_update: {0}".format(time.time()-time1))

def age_update(self, context):
    global humanoid
    time1 = time.time()
    if humanoid.metadata_realtime_activated:
        time1 = time.time()
        humanoid.calculate_transformation("AGE")


def mass_update(self, context):
    global humanoid
    if humanoid.metadata_realtime_activated:
        humanoid.calculate_transformation("FAT")


def tone_update(self, context):
    global humanoid
    if humanoid.metadata_realtime_activated:
        humanoid.calculate_transformation("MUSCLE")

def preset_update(self, context):
    """
    Update the character while prop slider moves
    """
    scn = bpy.context.scene
    global humanoid
    obj = humanoid.get_object()
    filepath = os.path.join(
        humanoid.presets_path,
        "".join([obj.preset, ".json"]))
    humanoid.load_character(filepath, mix=scn.mblab_mix_characters)


def ethnic_update(self, context):
    scn = bpy.context.scene
    global humanoid
    obj = humanoid.get_object()
    filepath = os.path.join(
        humanoid.phenotypes_path,
        "".join([obj.ethnic, ".json"]))
    humanoid.load_character(filepath, mix=scn.mblab_mix_characters)


def material_update(self, context):
    global humanoid
    if humanoid.material_realtime_activated:
        humanoid.update_materials(update_textures_nodes=False)


def measure_units_update(self, context):
    global humanoid
    humanoid.sync_gui_according_measures()


# def human_expression_update(self, context):
#     global mblab_shapekeys
#     scn = bpy.context.scene
#     mblab_shapekeys.sync_expression_to_gui()


# def restpose_update(self, context):
#     global humanoid
#     armature = humanoid.get_armature()
#     filepath = os.path.join(
#         humanoid.restposes_path,
#         "".join([armature.rest_pose, ".json"]))
#     mblab_retarget.load_pose(filepath, armature)


# def malepose_update(self, context):
#     global mblab_retarget
#     armature = utils.get_active_armature()
#     filepath = os.path.join(
#         mblab_retarget.maleposes_path,
#         "".join([armature.male_pose, ".json"]))
#     mblab_retarget.load_pose(filepath, use_retarget=True)


# def femalepose_update(self, context):
#     global mblab_retarget
#     armature = utils.get_active_armature()
#     filepath = os.path.join(
#         mblab_retarget.femaleposes_path,
#         "".join([armature.female_pose, ".json"]))
#     mblab_retarget.load_pose(filepath, use_retarget=True)

classes = (StartSession)

def register():
    # register the example panel, to show updater buttons
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

# register, unregister = bpy.utils.register_classes_factory(classes)

if __name__ == "__main__":
    register()