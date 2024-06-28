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
import traceback

import logging.config
import os
from pathlib import Path
from timeit import default_timer as timer
import xml.etree.ElementTree as etree
from collections import defaultdict

from .src.blend_scxml.monitor_scxml import UdpMonitorMachine
from .src.blend_scxml.louie import dispatcher
from .src.blend_scxml.consts import DispatcherConstants, PYSCXML_LOGGING_CONFIG

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


class UdpStateMachine(UdpMonitorMachine):
    def __init__(
            self, source):

        super().__init__(
            source)

        self.t_bindings = defaultdict(list)

        p_bindings = Path(self.filename).stem
        p_bindings += ".bindings.xml"
        p_bindings = os.path.join(self.filedir, p_bindings)
        if os.path.exists(p_bindings):
            tree = etree.parse(p_bindings)
            root = tree.getroot()
            if root:
                for idx, container in enumerate(root):
                    s_container_name = container.get("NAME", f"Container {idx + 1}")
                    p_container = self.t_bindings[s_container_name]
                    for item in container:
                        p_container.append(
                            {
                                "name": item.get("Name", ""),
                                "scxml_name": item.get("ScxmlName", ""),
                                "param": item.get("Param", ""),
                                "state_machine": item.get("StateMachineName", "")
                            }
                        )


sm: UdpStateMachine = None


class WM_OT_ScxmlStart(bpy.types.Operator):
    bl_idname = "wm.scxml_start"
    bl_label = "Start Machine"

    def execute(self, context):
        wm = context.window_manager
        p_scxml: ScxmlSettings = wm.scxml
        global sm
        sm = UdpStateMachine(
            p_scxml.get_state_machine_filepath_abs(),
            )
        sm.start()
        return {'FINISHED'}


class WM_OT_ScxmlStop(bpy.types.Operator):
    bl_idname = "wm.scxml_stop"
    bl_label = "Stop Machine"

    def execute(self, context):
        if sm:
            sm.cancel()
        return {'FINISHED'}


class WM_OT_ScxmlTrigger(bpy.types.Operator):
    bl_idname = "wm.scxml_trigger"
    bl_label = "Trigger Machine"

    event_name: bpy.props.StringProperty(
        name="Event Name",
        default=""
    )

    def execute(self, context):
        if sm:
            sm.send(self.event_name)
        return {'FINISHED'}


class ScxmlTriggerDataBase:
    event_name: bpy.props.StringProperty(
        name="Event Name",
        default=""
    )

    event_data: None

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def execute(self, context):
        if sm:
            sm.send(self.event_name, self.event_data)
        return {'FINISHED'}


class WM_OT_ScxmlTriggerInt(ScxmlTriggerDataBase, bpy.types.Operator):
    bl_idname = "wm.scxml_trigger_int"
    bl_label = "Trigger Int"

    event_data: bpy.props.IntProperty(
        name="Event Data",
        default=0
    )


class WM_OT_ScxmlTriggerFloat(ScxmlTriggerDataBase, bpy.types.Operator):
    bl_idname = "wm.scxml_trigger_float"
    bl_label = "Trigger Float"

    event_data: bpy.props.FloatProperty(
        name="Event Data",
        default=0.0
    )


class WM_OT_ScxmlTriggerStr(ScxmlTriggerDataBase, bpy.types.Operator):
    bl_idname = "wm.scxml_trigger_str"
    bl_label = "Trigger String"

    event_data: bpy.props.StringProperty(
        name="Event Data",
        default=""
    )


class WM_OT_ScxmlTriggerBool(ScxmlTriggerDataBase, bpy.types.Operator):
    bl_idname = "wm.scxml_trigger_bool"
    bl_label = "Trigger Bool"

    event_data: bpy.props.StringProperty(
        name="Event Data",
        default=""
    )


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
        p_scxml: ScxmlSettings = wm.scxml

        box = layout.box()
        box.prop(p_scxml, "state_machine_filepath")
        col = box.column(align=True)
        col.operator(WM_OT_ScxmlStart.bl_idname)
        col.operator(WM_OT_ScxmlStop.bl_idname)

        if sm and sm.t_bindings:
            for container, items in sm.t_bindings.items():
                box.label(text=container)
                col = box.column(align=True)
                for item in items:
                    row = col.row(align=True)
                    s_ev_name = item.get("scxml_name", "")
                    s_op_text = item.get("name", s_ev_name)
                    s_param = item.get("param", "")
                    op_id = WM_OT_ScxmlTrigger.bl_idname
                    if s_param == "Integer":
                        op_id = WM_OT_ScxmlTriggerInt.bl_idname
                    elif s_param == "Analog":
                        op_id = WM_OT_ScxmlTriggerFloat.bl_idname
                    elif s_param == "Logic":
                        op_id = WM_OT_ScxmlTriggerBool.bl_idname
                    op = col.operator(op_id, text=s_op_text)
                    op.event_name = s_ev_name

        layout.separator()

        p_scxml: ScxmlSettings = wm.scxml

        box = layout.box()
        row = box.row(align=True)
        row.alignment = 'CENTER'
        row.label(text='W3C SCXML Tests')

        col = box.column(align=True)
        col.use_property_split = True
        col.prop(p_scxml, "w3c_stop_on_error")

        row = box.row(align=True)
        row.operator(WM_OT_ScxmlTestW3C.bl_idname, depress=p_scxml.w3c_tests_running)

        box.template_list(
            "SCXML_UL_W3C",
            "name",
            wm.scxml, "w3c_tests",
            wm.scxml, "w3c_tests_index", rows=2, maxrows=3)


class WM_OT_ScxmlTestW3C(bpy.types.Operator):
    bl_idname = "wm.scxml_test_w3c"
    bl_label = "Test W3C"
    bl_description = "Start-stop testing SCXML W3C\n*Select test to start"

    _timer = None
    _start_time = 0
    _machine = None

    def on_sm_exit(self, sender, final):
        try:
            wm = bpy.context.window_manager
            p_scxml = wm.scxml
            idx = p_scxml.w3c_tests.find(sender.dm.self.filename)
            if idx != -1:
                p_test = p_scxml.w3c_tests[idx]
                if final == 'pass':
                    p_test.state = "PASS"
                elif final == "fail":
                    p_test.state = "FAIL"
                elif final == "final":
                    p_test.state = "MANUAL"
                else:
                    p_test.state = "TIMEOUT"

                if p_test.state in p_scxml.w3c_stop_on_error:
                    wm.scxml.w3c_tests_running = False
                    return

            if p_scxml.w3c_tests_index < len(p_scxml.w3c_tests) - 1:
                p_scxml.w3c_tests_index += 1
            else:
                wm.scxml.w3c_tests_running = False
            self._machine = None
        except Exception as e:
            print(e)

    def modal(self, context, event):

        wm = context.window_manager
        p_scxml: ScxmlSettings = wm.scxml

        if event.type in {'RIGHTMOUSE', 'ESC'} or not p_scxml.w3c_tests_running:
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            if self._machine is None:
                if p_scxml.w3c_tests_index in range(len(p_scxml.w3c_tests)):
                    p_test = wm.scxml.w3c_tests[p_scxml.w3c_tests_index]
                    was_idx = p_scxml.w3c_tests_index
                    try:
                        self._machine = UdpMonitorMachine(p_test.filepath)
                        self._start_time = timer()
                        dispatcher.connect(self.on_sm_exit, DispatcherConstants.exit, self._machine.interpreter)
                        self._machine.start()
                    except Exception as e:
                        p_test.state = 'ERROR'
                        p_test.msg = str(e)
                        self.report({'ERROR'}, str(e))
                        traceback.print_exc()
                        if p_test.state in p_scxml.w3c_stop_on_error:
                            self.cancel(context)
                            return {'CANCELLED'}
                        else:
                            if self._machine:
                                self._machine.cancel()

                            if p_scxml.w3c_tests_index != was_idx + 1:
                                p_scxml.w3c_tests_index = was_idx + 1

                    context.area.tag_redraw()
                else:
                    self.cancel(context)
                    return {'FINISHED'}
            else:
                if timer() - self._start_time > 10.0:
                    if p_scxml.w3c_tests_index in range(len(p_scxml.w3c_tests)):
                        p_test = p_scxml.w3c_tests[p_scxml.w3c_tests_index]
                        p_test.state = 'TIMEOUT'

                    if p_test.state in p_scxml.w3c_stop_on_error:
                        wm.scxml.w3c_tests_running = False

        return {'PASS_THROUGH'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        wm = context.window_manager

        p_scxml: ScxmlSettings = wm.scxml

        if p_scxml.w3c_tests_running:
            p_scxml.w3c_tests_running = False
            return {'CANCELLED'}

        n_tests_count = len(p_scxml.w3c_tests)
        if n_tests_count == 0:
            WM_OT_ScxmlTestW3C.update_tests_list()

        n_tests_count = len(p_scxml.w3c_tests)

        if n_tests_count == 0:
            self.report({'ERROR'}, "W3C tests are not loaded!")
            return {'CANCELLED'}

        if p_scxml.w3c_tests_index not in range(n_tests_count):
            p_scxml.w3c_tests_index = 0

        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)

        for idx in range(p_scxml.w3c_tests_index, n_tests_count, 1):
            p_test = p_scxml.w3c_tests[idx]
            p_test.clear()
        p_scxml.w3c_tests_running = True

        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        if self._machine:
            self._machine.cancel()
        wm.scxml.w3c_tests_running = False
        if hasattr(context, "area") and context.area:
            context.area.tag_redraw()

    @classmethod
    def update_tests_list(cls):
        base_dir = os.path.dirname(__file__)
        wm = bpy.context.window_manager
        wm.scxml.w3c_tests.clear()

        # NOTE: Basic HTTP tests are not supported!
        basichttp_tests = (
            "test201.scxml",
            "test509.scxml",
            "test510.scxml",
            "test518.scxml",
            "test519.scxml",
            "test520.scxml",
            "test522.scxml",
            "test531.scxml",
            "test532.scxml",
            "test534.scxml",
            "test567.scxml",
            "test577.scxml"
        )

        for entry in sorted(Path(os.path.join(base_dir, "w3c_tests")).glob("*.scxml")):
            file = str(entry)

            testname = Path(file).name

            if "sub" not in file and testname not in basichttp_tests:
                wm.scxml.w3c_tests.add()
                p_test: ScxmlTest = wm.scxml.w3c_tests[-1]
                p_test.name = testname
                p_test.filepath = file


class ScxmlTest(bpy.types.PropertyGroup):
    state: bpy.props.EnumProperty(
        name="State",
        items=[
            ("NONE", "None", ""),
            ("PASS", "Pass", "Test was successfully passed"),
            ("FAIL", "Fail", "Test was finished but did not reach 'Pass' state"),
            ("MANUAL", "Manual", "Test should be reviewed manually"),
            ("TIMEOUT", "Timeout", "Test was terminated by timeout"),
            ("ERROR", "Error", "Test has Python execution error")
        ],
        default="NONE"
    )

    filepath: bpy.props.StringProperty(
        name="Filepath",
        options={'HIDDEN'},
        default=""
    )

    msg: bpy.props.StringProperty(
        name="Message",
        default=""
    )

    def clear(self):
        self.state = "NONE"
        self.msg = ""


class ScxmlSettings(bpy.types.PropertyGroup):
    w3c_tests: bpy.props.CollectionProperty(type=ScxmlTest)
    w3c_tests_index: bpy.props.IntProperty(min=-1, default=-1)
    w3c_tests_running: bpy.props.BoolProperty(
        name="W3C Tests Running",
        default=False
    )
    w3c_stop_on_error: bpy.props.EnumProperty(
        name="Stop On Error",
        items=[
            ("FAIL", "Fail", "Test was finished but did not reach 'Pass' state"),
            ("MANUAL", "Manual", "Test should be reviewed manually"),
            ("TIMEOUT", "Timeout", "Test was terminated by timeout"),
            ("ERROR", "Error", "Test has Python execution error")
        ],
        options={'ENUM_FLAG'},
        default={'FAIL', 'ERROR', 'TIMEOUT'}
    )

    state_machine_filepath: bpy.props.StringProperty(
        name="FilePath",
        description="State machine filepath",
        subtype='FILE_PATH',
        default=""
    )

    def get_state_machine_filepath_abs(self):
        return bpy.path.abspath(self.state_machine_filepath)


class SCXML_UL_W3C(bpy.types.UIList):
    def draw_item(self, context, layout: bpy.types.UILayout, data, item: ScxmlTest, icon, active_data, active_propname):
        row = layout.row()
        row.alert = item.state in {'ERROR', 'FAIL', 'TIMEOUT'}
        row.active = item.state != "MANUAL"
        r_state = row.row(align=True)
        r_state.label(text=layout.enum_item_name(item, "state", item.state))
        row.prop(item, "name", emboss=False, text="")

        row.label(text=item.msg)


classes = (
    ScxmlTest,
    ScxmlSettings,
    SCXML_UL_W3C,

    WM_OT_ScxmlStart,
    WM_OT_ScxmlStop,

    WM_OT_ScxmlTrigger,
    WM_OT_ScxmlTriggerInt,
    WM_OT_ScxmlTriggerBool,
    WM_OT_ScxmlTriggerFloat,
    WM_OT_ScxmlTriggerStr,

    WM_OT_ScxmlTestW3C,

    VIEW3D_PT_Scxml
)


def register():
    logging.config.dictConfig(PYSCXML_LOGGING_CONFIG)

    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.WindowManager.scxml = bpy.props.PointerProperty(type=ScxmlSettings)

    WM_OT_ScxmlTestW3C.update_tests_list()


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.WindowManager.scxml
