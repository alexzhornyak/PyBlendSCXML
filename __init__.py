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
import os
from pathlib import Path

from .src.blend_scxml.py_blend_scxml import StateMachine
from .src.blend_scxml.louie import dispatcher

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

        row = layout.row(align=True)
        row.active = not wm.scxml.w3c_tests_running
        row.operator(WM_OT_ScxmlTestW3C.bl_idname)

        wm = context.window_manager
        layout.template_list(
            "SCXML_UL_W3C",
            "name",
            wm.scxml, "w3c_tests",
            wm.scxml, "w3c_tests_index", rows=2, maxrows=3)


class WM_OT_ScxmlTestW3C(bpy.types.Operator):
    bl_idname = "wm.scxml_test_w3c"
    bl_label = "Test W3C"

    _timer = None
    _test_files = []
    _machine = None

    def on_sm_exit(self, sender, final):
        wm = bpy.context.window_manager
        print(len(wm.scxml.w3c_tests))
        idx = wm.scxml.w3c_tests.find(sender.dm.self.filename)
        if idx != -1:
            p_item = wm.scxml.w3c_tests[idx]
            if final == 'pass':
                p_item.state = "PASS"
            elif final == "fail":
                p_item.state = "FAIL"
            else:
                p_item.state = "TIMEOUT"

        print("EXIT:", sender, final)
        self._machine = None

    def modal(self, context, event):

        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            if self._machine is None:
                wm = context.window_manager
                p_scxml: ScxmlSceneSettings = wm.scxml
                p_scxml.w3c_tests_index += 1
                if p_scxml.w3c_tests_index in range(len(p_scxml.w3c_tests)):
                    p_test = wm.scxml.w3c_tests[p_scxml.w3c_tests_index]
                    self._machine = StateMachine(p_test.filepath)
                    dispatcher.connect(self.on_sm_exit, "signal_exit", self._machine.interpreter)
                    self._machine.start()
                    context.area.tag_redraw()

        return {'PASS_THROUGH'}

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)

        for test in wm.scxml.w3c_tests:
            test.state = "NONE"
        wm.scxml.w3c_tests_index = -1
        wm.scxml.w3c_tests_running = True

        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        self._machine = None
        wm.scxml.w3c_tests_running = False
        if hasattr(context, "area") and context.area:
            context.area.tag_redraw()


class ScxmlTest(bpy.types.PropertyGroup):
    state: bpy.props.EnumProperty(
        name="State",
        items=[
            ("NONE", "None", ""),
            ("PASS", "Pass", ""),
            ("FAIL", "Fail", ""),
            ("TIMEOUT", "Timeout", "")
        ],
        default="NONE"
    )

    filepath: bpy.props.StringProperty(
        name="Filepath",
        options={'HIDDEN'},
        default=""
    )


class ScxmlSceneSettings(bpy.types.PropertyGroup):
    w3c_tests: bpy.props.CollectionProperty(type=ScxmlTest)
    w3c_tests_index: bpy.props.IntProperty(min=-1, default=-1)
    w3c_tests_running: bpy.props.BoolProperty(
        name="W3C Tests Running",
        default=False
    )


class SCXML_UL_W3C(bpy.types.UIList):
    def draw_item(self, context, layout: bpy.types.UILayout, data, item, icon, active_data, active_propname):
        layout.prop(item, "state", emboss=False, text="")
        layout.prop(item, "name", emboss=False, text="")


classes = (
    ScxmlTest,
    ScxmlSceneSettings,
    SCXML_UL_W3C,

    WM_OT_ScxmlStart,
    WM_OT_ScxmlStop,
    WM_OT_ScxmlTestW3C,

    VIEW3D_PT_Scxml
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.WindowManager.scxml = bpy.props.PointerProperty(type=ScxmlSceneSettings)

    base_dir = os.path.dirname(__file__)
    wm = bpy.context.window_manager
    wm.scxml.w3c_tests.clear()
    for entry in sorted(Path(os.path.join(base_dir, "w3c_tests")).glob("*.scxml")):
        file = str(entry)
        if "sub" not in file:
            wm.scxml.w3c_tests.add()
            p_item: ScxmlTest = wm.scxml.w3c_tests[-1]
            p_item.name = Path(file).name
            p_item.filepath = file


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.WindowManager.scxml
