# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
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

# Copyright 2024, Alex Zhornyak, alexander.zhornyak@gmail.com

""" Init Scxml """
import bpy
from bpy_extras.io_utils import ImportHelper

import logging

from .src.blend_scxml.py_blend_scxml import StateMachine

bl_info = {
    "name": "PyBlendSCXML",
    "author": "Alex Zhornyak",
    "version": (1, 0, 0, 0),
    "description": "Test addon for SCXML Blender",
    "blender": (3, 0, 0),
    "location": "N-Panel",
    "warning": "This addon uses relative path that is in repository!",
    "category": "Window",
}


sm = None
logging.basicConfig(level=logging.NOTSET)


class WM_OT_ScxmlStart(bpy.types.Operator, ImportHelper):
    bl_idname = "wm.scxml_start"
    bl_label = "Start Machine"

    filename_ext = ".scxml"
    filter_glob: bpy.props.StringProperty(default="*.scxml", options={'HIDDEN'})

    show_dialog: bpy.props.BoolProperty(
        name="Show Dialog",
        default=True
    )

    def execute(self, context):
        if context.mode:
            global sm
            sm = StateMachine(self.filepath)
            sm.start()
        return {'FINISHED'}


class WM_OT_ScxmlStop(bpy.types.Operator):
    bl_idname = "wm.scxml_stop"
    bl_label = "Stop Machine"

    def execute(self, context):
        if context.mode:
            if sm:
                sm.cancel()
        return {'FINISHED'}


class VIEW3D_PT_Scxml(bpy.types.Panel):
    bl_label = "SCXML"
    bl_context = ""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'SCXML'
    bl_ui_units_x = 14

    def draw(self, context: bpy.types.Context):
        layout = self.layout

        wm = context.window_manager
        op_props = wm.operator_properties_last(WM_OT_ScxmlStart.bl_idname)
        b_show_dialog = True
        if op_props:
            b_show_dialog = op_props.show_dialog
            layout.prop(op_props, "filepath")
            layout.prop(op_props, "show_dialog")

        layout.operator_context = 'INVOKE_DEFAULT' if b_show_dialog else 'EXEC_DEFAULT'
        layout.operator(WM_OT_ScxmlStart.bl_idname)
        layout.operator_context = 'INVOKE_DEFAULT'
        layout.operator(WM_OT_ScxmlStop.bl_idname)


classes = (
    WM_OT_ScxmlStart,
    WM_OT_ScxmlStop,

    VIEW3D_PT_Scxml
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
