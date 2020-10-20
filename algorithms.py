# MB-Lab
#
# MB-Lab fork website : https://github.com/animate1978/MB-Lab
#
# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 3
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####
#
# ManuelbastioniLAB - Copyright (C) 2015-2018 Manuel Bastioni

import logging
import itertools
import random
import time
import os
import json
import array

import mathutils
import bpy

from . import file_ops
from . import utils

from .utils import get_object_parent

logger = logging.getLogger(__name__)

DEBUG_LEVEL = 3

# ------------------------------------------------------------------------
#    Print Log
# ------------------------------------------------------------------------

def print_log_report(level, text_to_write):
    import warnings
    warnings.warn("print_log_report deprecated, use python logging", DeprecationWarning)
    l = 0
    levels = {"INFO": 0, "DEBUG": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4,}
    if level in levels:
        l = levels[level]
    if l >= DEBUG_LEVEL:
        print(level + ": " + text_to_write)


# ------------------------------------------------------------------------
#    Algorithms
# ------------------------------------------------------------------------

def quick_dist(p_1, p_2):
    return ((p_1[0]-p_2[0])**2) + ((p_1[1]-p_2[1])**2) + ((p_1[2]-p_2[2])**2)


def full_dist(vert1, vert2, axis="ALL"):
    v1 = mathutils.Vector(vert1)
    v2 = mathutils.Vector(vert2)

    if axis not in {"X", "Y", "Z"}:
        v3 = v1 - v2
        return v3.length
    if axis == "X":
        return abs(v1[0]-v2[0])
    if axis == "Y":
        return abs(v1[1]-v2[1])
    # if axis == "Z":
    return abs(v1[2]-v2[2])


def length_of_strip(vertices_coords, indices, axis="ALL"):
    strip_length = 0
    for x in range(len(indices)-1):
        v1 = vertices_coords[indices[x]]
        v2 = vertices_coords[indices[x+1]]
        strip_length += full_dist(v1, v2, axis)
    return strip_length


def closest_point_on_triangle(point, tri_p1, tri_p2, tri_p3):
    # TODO: Added in 2.82 - simplify once released.
    builtin = getattr(mathutils.geometry, 'closest_point_on_tri', None)

    if builtin:
        return builtin(point, tri_p1, tri_p2, tri_p3)

    hit_point = mathutils.geometry.intersect_point_tri(point, tri_p1, tri_p2, tri_p3)

    if hit_point:
        return hit_point

    line_points = [
        mathutils.geometry.intersect_point_line(point, tri_p1, tri_p2),
        mathutils.geometry.intersect_point_line(point, tri_p1, tri_p3),
        mathutils.geometry.intersect_point_line(point, tri_p2, tri_p3),
    ]
    candidates = [tri_p1, tri_p2, tri_p3, *(co for co, fac in line_points if 0 < fac < 1)]

    return min(candidates, key = lambda co: (point - co).length)


def function_modifier_a(val_x):
    return 2 * val_x - 1 if val_x > 0.5 else 0.0


def function_modifier_b(val_x):
    return 1-2 * val_x if val_x < 0.5 else 0.0


def bounding_box(verts_coo, indices, roundness=4):

    val_x, val_y, val_z = [], [], []
    for idx in indices:
        if len(verts_coo) > idx:
            val_x.append(verts_coo[idx][0])
            val_y.append(verts_coo[idx][1])
            val_z.append(verts_coo[idx][2])
        else:
            logger.warning("Error in calculating bounding box: index %s not in verts_coo (len(verts_coo) = %s)",
                           idx, len(verts_coo))
            return None

    box_x = round(max(val_x)-min(val_x), roundness)
    box_y = round(max(val_y)-min(val_y), roundness)
    box_z = round(max(val_z)-min(val_z), roundness)

    return (box_x, box_y, box_z)


def get_bounding_box(v_coords):

    if v_coords:

        val_x, val_y, val_z = [], [], []
        for coord in v_coords:
            val_x.append(coord[0])
            val_y.append(coord[1])
            val_z.append(coord[2])

        box_x = max(val_x)-min(val_x)
        box_y = max(val_y)-min(val_y)
        box_z = max(val_z)-min(val_z)

        return (box_x, box_y, box_z)

    return None


def load_bbox_data(filepath):
    bboxes = []
    database_file = open(filepath, "r")
    for line in database_file:
        bboxes.append(line.split())
    database_file.close()

    bbox_data_dict = {}
    for x_data in bboxes:
        bbox_data_dict[x_data[0]] = [
            int(x_data[1]),
            int(x_data[2]),
            int(x_data[3]),
            int(x_data[4]),
            int(x_data[5]),
            int(x_data[6]),
        ]
    return bbox_data_dict


def smart_combo(prefix, morph_values):

    tags = []
    names = []
    weights = []
    max_morph_values = []

    # Compute the combinations and get the max values
    for v_data in morph_values:
        tags.append(["max", "min"])
        max_morph_values.append(max(v_data))
    for n_data in itertools.product(*tags):
        names.append(prefix+"_"+'-'.join(n_data))

    # Compute the weight of each combination
    for n_data in itertools.product(*morph_values):
        weights.append(sum(n_data))

    factor = max(max_morph_values)
    best_val = max(weights)
    toll = 1.5

    # Filter on bestval and calculate the normalize factor
    summ = 0.0
    for i, weight in enumerate(weights):
        new = max(0, weight - best_val / toll)
        summ += new
        weights[i] = new

    # Normalize using summ
    # FIXME: this is bad idea as
    # >>> (1.0/3) * 3 == 0.0
    # False
    if summ != 0:
        for i in range(len(weights)):
            weights[i] = factor*(weights[i]/summ)

    return (names, weights)


def is_excluded(property_name, excluded_properties):
    for excluded_property in excluded_properties:
        if excluded_property in property_name:
            return True
    return False

# Improved random fix
def generate_parameter(val, random_value, preserve_phenotype=False):
    r = random.random()
    if preserve_phenotype:
        if val > 0.5:
            if val > 0.8:
                new_value = 0.8 + 0.2*r
            else:
                new_value = 0.5+r*random_value
        else:
            if val < 0.2:
                new_value = 0.2*r
            else:
                new_value = 0.5-r*random_value
    else:
        if r > 0.5:
            new_value = min(1.0, 0.5+random.random()*random_value)
        else:
            new_value = max(0.0, 0.5-random.random()*random_value)
    return new_value


def polygon_forma(list_of_verts):

    form_factors = []
    for idx in range(len(list_of_verts)):
        index_a = idx
        index_b = idx-1
        index_c = idx+1
        if index_c > len(list_of_verts)-1:
            index_c = 0

        p_a = list_of_verts[index_a]
        p_b = list_of_verts[index_b]
        p_c = list_of_verts[index_c]

        v_1 = p_b-p_a
        v_2 = p_c-p_a

        v_1.normalize()
        v_2.normalize()

        factor = v_1.dot(v_2)
        form_factors.append(factor)
    return form_factors


def average_center(verts_coords):

    n_verts = len(verts_coords)
    bcenter = mathutils.Vector((0.0, 0.0, 0.0))
    if n_verts != 0:
        for v_coord in verts_coords:
            bcenter += v_coord
        bcenter = bcenter/n_verts
    return bcenter


def linear_interpolation_y(xa, xb, ya, yb, y):
    return (((xa-xb)*y)+(xb*ya)-(xa*yb))/(ya-yb)


def correct_morph(base_form, current_form, morph_deltas, bboxes):
    time1 = time.time()
    new_morph_deltas = []
    for d_data in morph_deltas:

        idx = d_data[0]

        if str(idx) in bboxes:
            indices = bboxes[str(idx)]
            current_bounding_box = bounding_box(current_form, indices)
            if current_bounding_box:
                base_bounding_box = bounding_box(base_form, indices)
                if base_bounding_box:

                    if base_bounding_box[0] != 0:
                        scale_x = current_bounding_box[0]/base_bounding_box[0]
                    else:
                        scale_x = 1

                    if base_bounding_box[1] != 0:
                        scale_y = current_bounding_box[1]/base_bounding_box[1]
                    else:
                        scale_y = 1

                    if base_bounding_box[2] != 0:
                        scale_z = current_bounding_box[2]/base_bounding_box[2]
                    else:
                        scale_z = 1

                    delta_x = d_data[1][0] * scale_x
                    delta_y = d_data[1][1] * scale_y
                    delta_z = d_data[1][2] * scale_z

                    newd = mathutils.Vector((delta_x, delta_y, delta_z))
                    new_morph_deltas.append([idx, newd])
        else:
            new_morph_deltas.append(d_data)
            logger.warning("Index %s not in bounding box database", idx)
    logger.info("Morphing corrected in %s secs", time.time()-time1)
    return new_morph_deltas

# ------------------------------------------------------------------------
#    Functions
# ------------------------------------------------------------------------

def looking_for_humanoid_obj():
    """
    Looking for a mesh that is OK for the lab
    """
    logger.info("Looking for a humanoid object ...")
    if bpy.app.version < (2, 81, 16):
        msg = "Sorry, MB-Lab requires Blender 2.81.16 Minimum"
        logger.warning(msg)
        return("ERROR", msg)

    human_obj = None
    name = ""
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            if "manuellab_vers" in get_object_keys(obj):
                if utils.check_version(obj["manuellab_vers"]):
                    human_obj = obj
                    name = human_obj.name
                    break

    if not human_obj:
        msg = "No lab humanoids in the scene"
        logger.info(msg)
        return "NO_OBJ", msg

    return "FOUND", name


def is_string_in_string(b_string, b_name):
    return b_string and b_name and b_string.lower() in b_name.lower()


def is_too_much_similar(string1, string2, val=2):
    s1, s2 = set(string1), set(string2)

    threshold = len(s1) - val if len(s1) > len(s2) else len(s2) - val

    return len(s1.intersection(s2)) > threshold


def is_in_list(list1, list2, position="ANY"):

    for element1 in list1:
        for element2 in list2:
            if position == "ANY" and element1.lower() in element2.lower():
                return True
            if position == "START" and element1.lower() in element2[:len(element1)].lower():
                return True
            if position == "END" and element1.lower() in element2[len(element1):].lower():
                return True
    return False


def normal_from_points(points):
    return mathutils.geometry.normal(*points[:4]) if len(points) == 4 else mathutils.geometry.normal(*points[:3])


def select_and_change_mode(obj, obj_mode):
    deselect_all_objects()
    if obj:
        obj.select_set(True)
        set_active_object(obj)
        set_object_visible(obj)
        try:
            bpy.ops.object.mode_set(mode=obj_mode)
            logger.debug("Select and change mode of %s = %s", obj.name, obj_mode)
        except AttributeError:
            logger.warning("Can't change the mode of %s to %s", obj.name, obj_mode)


def get_selected_objs_names():
    return [obj.name for obj in bpy.context.selected_objects]


def select_object_by_name(name):
    obj = get_object_by_name(name)
    if obj:
        obj.select_set(True)


def set_selected_objs_by_name(names):
    for name in names:
        if name in bpy.data.objects:
            bpy.data.objects[name].select_set(True)


def get_active_object():
    return bpy.context.view_layer.objects.active


def deselect_all_objects():
    for obj in bpy.data.objects:
        obj.select_set(False)


def set_active_object(obj):
    if obj:
        bpy.context.view_layer.objects.active = obj


def get_object_by_name(name):
    return bpy.data.objects.get(name)


def is_object(obj):
    return isinstance(obj, bpy.types.Object)


def is_mesh(obj):
    return isinstance(obj, bpy.types.Mesh)


def get_objects_selected_names():
    selected_objects = []
    for obj in bpy.context.selected_objects:
        if hasattr(obj, 'name'):
            selected_objects.append(obj.name)
    return selected_objects


def apply_object_transformation(obj):
    if obj:
        selected_objs = get_selected_objs_names()
        active_obj = get_active_object()
        if active_obj:
            active_mode = active_obj.mode
        obj_mode = obj.mode

        select_and_change_mode(obj, 'OBJECT')
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        select_and_change_mode(obj, obj_mode)

        deselect_all_objects()
        set_selected_objs_by_name(selected_objs)
        if active_obj:
            set_active_object(active_obj)
            bpy.ops.object.mode_set(mode=active_mode)

def collect_existing_objects():
    existing_obj_names = []
    for obj in bpy.data.objects:
        name = obj.name
        if name:
            existing_obj_names.append(name)
    return existing_obj_names


def get_newest_object(existing_obj_names):
    for obj in bpy.data.objects:
        name = obj.name
        if name not in existing_obj_names:
            return get_object_by_name(name)
    return None


def get_selected_gender():
    obj = get_active_body()
    template = get_template_model(obj)
    if template:
        if "_female" in template:
            return "FEMALE"
        if "_male" in template:
            return "MALE"
    return "NONE"


def identify_template(obj):
    if obj:
        if obj.type == 'MESH':
            verts = obj.data.vertices
            polygons = obj.data.polygons
            config_data = file_ops.get_configuration()
            # TODO error messages
            if verts and polygons:
                for template in config_data["templates_list"]:
                    n_verts2 = config_data[template]["vertices"]
                    n_polygons2 = config_data[template]["faces"]
                    if n_verts2 == len(verts) and n_polygons2 == len(polygons):
                        return template
    return None


def get_polygon_vertices_coords(obj_data, index):

    if is_object(obj_data):
        polygon = obj_data.data.polygons[index]
    elif is_mesh(obj_data):
        polygon = obj_data.polygons[index]

    polygon_vindex = polygon.vertices
    verts_coords = []

    for i in polygon_vindex:
        if is_object(obj_data):
            v = obj_data.data.vertices[i]
        elif is_mesh(obj_data):
            v = obj_data.vertices[i]
        verts_coords.append(v.co)

    return verts_coords


def get_template_model(obj):
    template = identify_template(obj)
    config_data = file_ops.get_configuration()
    if template:
        return config_data[template]["template_model"]
    return None


def get_template_polygons(obj):
    template = identify_template(obj)
    config_data = file_ops.get_configuration()
    if template:
        return config_data[template]["template_polygons"]
    return None


def is_a_lab_character(obj):
    return get_template_model(obj) is not None


def get_active_body():
    obj = get_active_object()
    if obj:
        if obj.type == 'MESH':
            return obj
        if obj.type == 'ARMATURE' and obj.children:
            for c_obj in obj.children:
                obj_id = get_template_model(c_obj)
                if obj_id:
                    return c_obj
    return None


def get_linked_armature(obj):
    if obj.type == 'MESH':
        for modfr in obj.modifiers:
            if modfr.type == 'ARMATURE':
                return modfr.object
    return None


def raw_mesh_from_object(obj, apply_modifiers=False):
    if obj.type == 'MESH':
        return obj.to_mesh(bpy.context.scene, apply_modifiers, 'PREVIEW')
    return None


def get_all_bones_z_axis(armature):
    armature_z_axis = {}
    select_and_change_mode(armature, 'EDIT')
    source_edit_bones = get_edit_bones(armature)
    if source_edit_bones:
        for e_bone in source_edit_bones:
            armature_z_axis[e_bone.name] = e_bone.z_axis.copy()
    select_and_change_mode(armature, 'OBJECT')
    return armature_z_axis


def reset_bone_rot(p_bone):
    # TODO: check pose mode
    if p_bone.rotation_mode == 'QUATERNION':
        p_bone.rotation_quaternion = [1.0, 0.0, 0.0, 0.0]
    elif p_bone.rotation_mode == 'AXIS_ANGLE':
        p_bone.rotation_axis_angle = [0.0, 0.0, 1.0, 0.0]
    else:
        p_bone.rotation_euler = [0.0, 0.0, 0.0]


def import_mesh_from_lib(lib_filepath, name):
    existing_mesh_names = collect_existing_meshes()
    file_ops.append_mesh_from_library(lib_filepath, [name])
    new_mesh = get_newest_mesh(existing_mesh_names)
    return new_mesh


def collect_existing_meshes():
    existing_mesh_names = []
    for mesh in bpy.data.meshes:
        existing_mesh_names.append(mesh.name)
    return existing_mesh_names


def get_mesh(name):
    return bpy.data.meshes.get(name, None)


def get_newest_mesh(existing_mesh_names):
    for mesh in bpy.data.meshes:
        if mesh.name not in existing_mesh_names:
            return get_mesh(mesh.name)
    return None


def new_shapekey(obj, shapekey_name, slider_min=0, slider_max=1.0, value=1.0):

    # TODO a new shapekey should overwrite the existing one
    if shapekey_name in get_shapekeys_names(obj):
        shapekey = get_shapekey(obj, shapekey_name)
    else:
        shapekey = obj.shape_key_add(name=shapekey_name, from_mix=False)
    shapekey.slider_min = slider_min
    shapekey.slider_max = slider_max
    shapekey.value = value
    obj.use_shape_key_edit_mode = True
    return shapekey


def new_shapekey_from_current_vertices(obj, shapekey_name):
    shapekey = new_shapekey(obj, shapekey_name)
    for i in range(len(obj.data.vertices)):
        shapekey.data[i].co = obj.data.vertices[i].co
    return shapekey


def reset_shapekeys(obj):
    if has_shapekeys(obj):
        for sk in obj.data.shape_keys.key_blocks:
            sk.value = 0.0


def get_object_keys(obj):
    if obj:
        return obj.keys()
    return None


def get_vertgroup_verts(obj, vgroup_name):

    g = get_vertgroup_by_name(obj, vgroup_name)
    verts_idxs = []
    if g is not None:
        for i in range(len(obj.data.vertices)):
            try:
                if g.weight(i) > 0:
                    verts_idxs.append(i)
            except AttributeError:
                pass
                # Blender return an error if the vert is not in group
    return verts_idxs


def set_object_visible(obj):
    if obj:
        logger.debug("Turn the visibility of %s ON", obj.name)
        obj.hide_set(False)

        # TODO: I don't think this is needed in blender 2.8
        # bpy.context.scene.layers = obj.layers in some cases this return DAG zero error (with old depsgraph)!
        #n = bpy.context.scene.active_layer
        # set_object_layer(obj,n) #TODO not perfect because it changes the layer


def image_to_array(blender_image):
    return array.array('f', blender_image.pixels[:])


def array_to_image(pixel_array, blender_image):
    blender_image.pixels = pixel_array.tolist()


def get_edit_bones(armature):
    if bpy.context.mode != 'EDIT_ARMATURE':
        logger.warning("Cannot get the edit bones because the obj is not in edit mode")
        return None
    return armature.data.edit_bones


def get_pose_bones(armature):
    if bpy.context.mode == 'EDIT_ARMATURE':
        logger.warning("Cannot get the pose bones because the obj is not in pose mode")
        return None
    return armature.pose.bones


def get_edit_bone(armature, name):
    edit_bones = get_edit_bones(armature)
    if edit_bones:
        if name in edit_bones:
            return edit_bones[name]
    return None


def set_bone_rotation(bone, value, mode='QUATERNION'):
    if mode == 'QUATERNION':
        bone.rotation_quaternion = value


def get_bone_rotation(bone, mode='QUATERNION'):
    if mode == 'QUATERNION':
        return bone.rotation_quaternion
    return None


def has_anime_shapekeys(obj):

    anime_specific_sks = {"Expressions_brow01L_max", "Expressions_brow01L_min",
                          "Expressions_brow01R_max", "Expressions_brow01R_min",
                          "Expressions_brow02L_min", "Expressions_brow02R_min",
                          "Expressions_brow03_max", "Expressions_brow03_min",
                          "Expressions_eyes01_max", "Expressions_eyes01_min",
                          "Expressions_eyes02_max", "Expressions_eyes02_min",
                          "Expressions_eyes03_max", "Expressions_eyes03_min",
                          "Expressions_eyes04_max", "Expressions_eyes04_min",
                          "Expressions_eyes05_max", "Expressions_eyes05_min",
                          "Expressions_eyes06_max"}
    current_sks = set()
    if has_shapekeys(obj):
        current_sks = set(get_shapekeys_names(obj))
        anime_sk_in_current_sk = current_sks.intersection(anime_specific_sks)
        return len(anime_sk_in_current_sk) >= (len(anime_specific_sks)/2)

    return False


def get_rest_lengths(armat):
    armature_rest_lengths = {}
    if armat:
        select_and_change_mode(armat, 'EDIT')
        edit_bones = get_edit_bones(armat)
        for e_bone in edit_bones:
            armature_rest_lengths[e_bone.name] = e_bone.length
        select_and_change_mode(armat, 'POSE')
    return armature_rest_lengths


def get_bone_constraint_by_type(bone, constraint_type):
    for constraint in bone.constraints:
        if constraint.type == constraint_type:
            return constraint
    return None


def set_bone_constraint_parameter(constraint, parameter, value):
    if hasattr(constraint, parameter):
        try:
            setattr(constraint, parameter, value)
        except AttributeError:
            logger.info("Setattr failed for attribute '%s' of constraint %s",
                        parameter, constraint.name)


def get_vertgroup_by_name(obj, group_name):
    if obj and obj.type == 'MESH' and group_name in obj.vertex_groups:
        return obj.vertex_groups[group_name]
    return None


def remove_vertgroups_all(obj):
    obj.vertex_groups.clear()


def remove_vertgroup(obj, group_name):
    vertgroup = get_vertgroup_by_name(obj, group_name)
    if vertgroup:
        obj.vertex_groups.remove(vertgroup)


def new_vertgroup(obj, group_name):
    return obj.vertex_groups.new(name=group_name)



def get_shapekey_reference(obj):
    if has_shapekeys(obj):
        return obj.data.shape_keys.reference_key
    return None


def get_shapekey(obj, shapekey_name):
    shapekey_data = None
    if has_shapekeys(obj):
        if shapekey_name in get_shapekeys_names(obj):
            shapekey_data = obj.data.shape_keys.key_blocks[shapekey_name]
    return shapekey_data


def remove_shapekey(obj, shapekey_name):
    shapekey_to_remove = get_shapekey(obj, shapekey_name)
    if shapekey_to_remove:
        obj.shape_key_remove(shapekey_to_remove)


def remove_shapekeys_all(obj):
    if has_shapekeys(obj):
        for sk in obj.data.shape_keys.key_blocks:
            if sk != obj.data.shape_keys.reference_key:
                sk.value = 0
                obj.shape_key_remove(sk)
        obj.shape_key_remove(obj.data.shape_keys.reference_key)


def get_shapekeys_names(obj):
    shapekeys_names = []
    if has_shapekeys(obj):
        for sk in obj.data.shape_keys.key_blocks:
            shapekeys_names.append(sk.name)
    return shapekeys_names


def has_shapekeys(obj):
    return hasattr(obj.data.shape_keys, 'key_blocks')


def get_stretch_to_targets(armat):
    mapping = dict()
    if armat:
        for p_bone in get_pose_bones(armat):
            stretch_to_constraint = get_bone_constraint_by_type(p_bone, 'STRETCH_TO')
            if stretch_to_constraint:
                mapping[p_bone.name] = stretch_to_constraint.subtarget
    return mapping


def apply_stretch_to(armat, mapping):
    if armat:
        edit_bones = get_edit_bones(armat)
        for name, target_name in mapping.items():
            edit_bones[name].tail = edit_bones[target_name].head


def update_stretch_to_length(armat):
    if armat:
        for p_bone in get_pose_bones(armat):
            stretch_to_constraint = get_bone_constraint_by_type(p_bone, 'STRETCH_TO')
            set_bone_constraint_parameter(stretch_to_constraint, 'rest_length', p_bone.bone.length)


def update_bendy_bones(armat):
    if armat:
        select_and_change_mode(armat, "OBJECT")
        stretch_targets = get_stretch_to_targets(armat)
        select_and_change_mode(armat, "EDIT")
        apply_stretch_to(armat, stretch_targets)
        select_and_change_mode(armat, "OBJECT")
        update_stretch_to_length(armat)


def apply_auto_align_bones(armat):
    align_table = {
        "upperarm_twist_L": "upperarm_L",
        "upperarm_twist_R": "upperarm_R",
        "lowerarm_twist_L": "lowerarm_L",
        "lowerarm_twist_R": "lowerarm_R",
        "thigh_twist_L": "thigh_L",
        "thigh_twist_R": "thigh_R",
        "calf_twist_L": "calf_L",
        "calf_twist_R": "calf_R",
        "rot_helper01_L": "calf_L",
        "rot_helper01_R": "calf_R",
        "rot_helper02_L": "lowerarm_L",
        "rot_helper02_R": "lowerarm_R",
        "rot_helper03_L": "thigh_L",
        "rot_helper03_R": "thigh_R",
        "rot_helper04_L": "foot_L",
        "rot_helper04_R": "foot_R",
        "rot_helper06_L": "thigh_L",
        "rot_helper06_R": "thigh_R",
    }

    if armat:
        select_and_change_mode(armat, "EDIT")
        edit_bones = get_edit_bones(armat)
        for name, target_name in align_table.items():
            bone = edit_bones.get(name)
            if bone:
                bone_target = edit_bones[target_name]
                bone.tail = bone.head + bone_target.vector.normalized() * bone.length
                bone.roll = bone_target.roll


def has_deformation_vgroups(obj, armat):
    if obj.type == 'MESH':
        if armat:
            for vgroup in obj.vertex_groups:
                for b in armat.data.bones:
                    if b.name == vgroup.name:
                        return True
    return False


def is_rigged(obj, armat):
    # if is_armature_linked(obj, armat):
    return has_deformation_vgroups(obj, armat)


def get_boundary_verts(obj):
    polygons_dict = {}
    for polyg in obj.data.polygons:
        for i in polyg.vertices:
            if str(i) not in polygons_dict:
                indices = [n for n in polyg.vertices if n != i]
                polygons_dict[str(i)] = indices
            else:
                for vert_id in polyg.vertices:
                    if vert_id != i and vert_id not in polygons_dict[str(i)]:
                        polygons_dict[str(i)].append(vert_id)

    return polygons_dict


def get_object_groups(obj):
    obj_groups = {}
    for grp in obj.vertex_groups:
        weights = []
        for idx in range(len(obj.data.vertices)):
            try:
                if grp.weight(idx) > 0:
                    weights.append([idx, grp.weight(idx)])
            except AttributeError:
                pass
        obj_groups[grp.name] = weights
    return obj_groups

#
def set_scene_modifiers_status_by_type(modfr_type, visib):
    for obj in bpy.data.objects:
        for modfr in obj.modifiers:
            if modfr.type == modfr_type:
                set_modifier_viewport(modfr, visib)

#
def set_scene_modifiers_status(visib, status_data=None):
    if not status_data:
        for obj in bpy.data.objects:
            for modfr in obj.modifiers:
                set_modifier_viewport(modfr, visib)
    else:
        for obj in bpy.data.objects:
            obj_name = obj.name
            if obj_name in status_data:
                modifier_status = status_data[obj_name]
                set_object_modifiers_visibility(obj, modifier_status)

#
def disable_object_modifiers(obj, types_to_disable=[]):
    for modfr in obj.modifiers:
        modifier_type = modfr.type
        if modifier_type in types_to_disable:
            set_modifier_viewport(modfr, False)
            logger.info("Modifier %s of %s can create unpredictable fitting results. MB-Lab has disabled it",
                        modifier_type, obj.name)
        elif types_to_disable == []:
            set_modifier_viewport(modfr, False)
            logger.info("Modifier %s of %s can create unpredictable fitting results. MB-Lab has disabled it",
                        modifier_type, obj.name)

#
def get_object_modifiers_visibility(obj):
    # Store the viewport visibility for all modifiers of the obj
    obj_modifiers_status = {}
    for modfr in obj.modifiers:
        modfr_name = get_modifier_name(modfr)
        modfr_status = get_modifier_viewport(modfr)
        if modfr_name:
            obj_modifiers_status[modfr_name] = modfr_status
    return obj_modifiers_status

#
def set_object_modifiers_visibility(obj, modifier_status):
    # Store the viewport visibility for all modifiers of the obj
    for modfr in obj.modifiers:
        modfr_name = get_modifier_name(modfr)
        if modfr_name in modifier_status:
            set_modifier_viewport(modfr, modifier_status[modfr_name])

#
def get_modifier(obj, modifier_name):
    return obj.modifiers.get(modifier_name)

#
def get_modifier_name(modfr):
    return getattr(modfr, 'name')

#

#
def remove_modifier(obj, modifier_name):
    print("Removing ", modifier_name)
    if modifier_name in obj.modifiers:
        obj.modifiers.remove(obj.modifiers[modifier_name])

#
def disable_modifier(modfr):
    logger.info("Disable %s", modfr.name)
    for mdf in ('show_viewport', 'show_render', 'show_in_editmode', 'show_on_cage'):
        if hasattr(modfr, mdf):
            setattr(modfr, mdf, False)

#
def get_modifier_viewport(modfr):
    return getattr(modfr, 'show_viewport', None)

#
def set_modifier_viewport(modfr, value):
    if hasattr(modfr, 'show_viewport'):
        modfr.show_viewport = value

#
# - Play and Stop Animation


def play_animation():
    if not bpy.context.screen.is_animation_playing:
        bpy.ops.screen.animation_play()


def stop_animation():
    if bpy.context.screen.is_animation_playing:
        bpy.ops.screen.animation_play()



#
def set_modifier_parameter(modifier, parameter, value):
    if hasattr(modifier, parameter):
        try:
            setattr(modifier, parameter, value)
        except AttributeError:
            logger.info("Setattr failed for attribute '%s' of modifier %s", parameter, modifier)

def get_scene_modifiers_status():
    scene_viewport_status = {}
    for obj in bpy.data.objects:
        obj_name = obj.name
        scene_viewport_status[obj_name] = get_object_modifiers_visibility(obj)
    return scene_viewport_status


def apply_modifier(obj, modifier):
    modifier_name = get_modifier_name(modifier)
    if modifier_name in obj.modifiers:
        set_active_object(obj)
        try:
            bpy.ops.object.modifier_apply(apply_as='DATA', modifier=modifier_name)
        except AttributeError:
            logger.warning("Problems in applying %s. Is the modifier disabled?", modifier_name)

#
def move_up_modifier(obj, modifier):
    modifier_name = get_modifier_name(modifier)
    set_active_object(obj)
    for n in range(len(obj.modifiers)):
        bpy.ops.object.modifier_move_up(modifier=modifier_name)

#
def move_down_modifier(obj, modifier):
    modifier_name = get_modifier_name(modifier)
    set_active_object(obj)
    for n in range(len(obj.modifiers)):
        bpy.ops.object.modifier_move_down(modifier=modifier_name)

def swap_material(old_mat_name, new_mat_name, char_name):

    #Get Object if it doesn't exist return none
    obj = bpy.data.objects[char_name]
    if obj == None:
        return None
        
    #Try and get materials if either does not exist return None
    
    try:

        mat_old = bpy.data.materials[old_mat_name]
        mat_new = bpy.data.materials[new_mat_name]
    
    except:
        logger.debug("Material not found")
        return None
    
    
    #Assign new material to old material slot
    materialslen = len(obj.data.materials)
    for i in range(0,materialslen):
        if obj.data.materials[i] == mat_old:
            obj.data.materials[i] = mat_new

    return None

def remove_censors():

    my_prefs = bpy.context.preferences.addons.get(__package__, None)
    if (not my_prefs.preferences.use_censors):
        is_char = looking_for_humanoid_obj()
        if is_char[0] == "FOUND":
            char_name = is_char[1]
            if char_name in("f_an01","f_an02","m_an01","m_an02"):
                swap_material("MBlab_generic", "MBLab_anime_skin",char_name)
            else:
                swap_material("MBlab_generic", "MBLab_skin2",char_name)


    return None

#Teto
# ------------------------------------------------------------------------
#    UI and UI init Functions
# ------------------------------------------------------------------------

# Recover from an enumProperty.
# The component returns the key. So the function seeks the key
# in tuples used in it, and extract the real value, or the 3rd if needed.
# In real life, it's really cumbersome to get this value if
# we use things like bpy.types.scene.whatever.
def get_enum_property_item(key, enum_property, index=1, split_first_part=False):
    value = None
    if enum_property == None or len(enum_property) < 1:
        enum_property = ('NONE', 'CHOOSE', 'Choose one')
    for ind in range(len(enum_property)):
        if key in enum_property[ind]:
            value = enum_property[ind]
            return_value = value[index]
            if split_first_part:
                return_value = return_value.split("_")[1]
            return return_value
    return ""

#create an enumProperty list of tuples, from a list.
def create_enum_property_items(values=[], key_length=3, tip_length=4):
    if values == None or len(values) < 1:
        return [("0", "NONE", "")]
    return_list = []
    for i in range(len(values)):
        return_list.append(
            (str(i).zfill(key_length),
            values[i],
            str(values[i])[0:tip_length]))
    return return_list
    
def split_name(name, splitting_char=' -_²&=¨^$£%µ,?;!§+*/:[]\"\'{}', indexes=[]):
    if len(splitting_char) < 1:
        return name
    if len(indexes) < 1:
        indexes = [0]*len(splitting_char)
    chars = list(splitting_char)
    result = name
    for i in range(len(chars)):
        result = result.split(chars[i])[indexes[i]]
    return result

# Remade it because in Blender, the actual split() doesn't work
# as intented, only one character is permitted for a reason.
def split(name, splitting_char=' -_²&=¨^$£%µ,?;!§+*/:[]\"\'{}'):
    if len(splitting_char) < 1:
        return name
    return_list = []
    tmp = []
    if not isinstance(name, list):
        name = [name]
    for txt in name:
        tmp = txt.split(splitting_char[0])
        for t in tmp:
            if len(t) > 0:
                return_list.append(t)
    return split(return_list, splitting_char[1:])
        