import logging
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

import os
import sys
sys.path.append(r"../PyBlendSCXML/src")

from blend_scxml.py_blend_scxml import StateMachine


bl_info = {
    "name": "blend_scxml_addon",
    "author": "Alex Zhornyak",
    "version": (1, 0, 0, 0),
    "description": "Test addon for SCXML Blender",
    "blender": (3, 0, 0),
    "location": "N-Panel",
    "warning": "This addon uses relative path that is in repository!",
    "category": "Window",
}


sm = None


class VIEW3D_PT_Scxml(bpy.types.Panel):
    bl_label = "SCXML"
    bl_context = ""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'SCXML'
    bl_ui_units_x = 14

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        layout.operator(WM_OT_ScxmlStart.bl_idname)


class WM_OT_ScxmlStart(bpy.types.Operator):
    bl_idname = "wm.scxml_start"
    bl_label = "Simple Object Operator"

    def execute(self, context):
        if context.mode:
            s_path = os.path.join(os.path.dirname(__file__), "../../w3c_tests/test144.scxml")
            sm = StateMachine(s_path)
            sm.start()
        return {'FINISHED'}


def register():
    bpy.utils.register_class(WM_OT_ScxmlStart)
    bpy.utils.register_class(VIEW3D_PT_Scxml)

    pass


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_Scxml)
    bpy.utils.unregister_class(WM_OT_ScxmlStart)
    pass
