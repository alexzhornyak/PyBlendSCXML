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

import logging
import os
from pathlib import Path
from timeit import default_timer as timer
import socket

from .src.blend_scxml.py_blend_scxml import StateMachine, default_logfunction
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


class UdpStateMachine(StateMachine):
    def __init__(
            self, source,
            log_function=default_logfunction,
            sessionid=None, default_datamodel="python", setup_session=True,
            filedir="", filename=""):

        super().__init__(
            source, log_function=log_function, sessionid=sessionid, default_datamodel=default_datamodel,
            setup_session=setup_session, filedir=filedir, filename=filename)
        dispatcher.connect(self.send_enter, "signal_enter_state", self.interpreter)
        dispatcher.connect(self.send_exit, "signal_exit_state", self.interpreter)
        dispatcher.connect(self.send_taking_transition, "signal_taking_transition", self.interpreter)

    def send_udp(self, message: str):
        UDP_IP = "127.0.0.1"
        UDP_PORT = 11005

        sock = socket.socket(
            socket.AF_INET,  # Internet
            socket.SOCK_DGRAM)  # UDP
        sock.sendto(message.encode(), (UDP_IP, UDP_PORT))

    def get_scxml_name(self, sender):
        s_name = sender.dm.get("_name", "")
        if not s_name:
            try:
                s_name = Path(sender.dm.self.filename).stem()
            except Exception:
                pass
        return s_name

    def send_enter(self, sender, state):
        s_machine = self.get_scxml_name(sender)
        print("enter:", s_machine, state)
        self.send_udp(f"2@{s_machine}@{state}")

    def send_exit(self, sender, state):
        s_machine = self.get_scxml_name(sender)
        print("exit:", s_machine, state)
        self.send_udp(f"4@{s_machine}@{state}")

    def send_taking_transition(self, sender, state, transition_index):
        s_machine = self.get_scxml_name(sender)
        print("transition:", s_machine, transition_index)
        self.send_udp(f"12@{s_machine}@{state}|{transition_index}")


class WM_OT_ScxmlStart(bpy.types.Operator):
    bl_idname = "wm.scxml_start"
    bl_label = "Start Machine"

    def execute(self, context):
        wm = context.window_manager
        p_scxml: ScxmlSettings = wm.scxml
        global sm
        sm = UdpStateMachine(p_scxml.state_machine_filepath)
        sm.start()
        return {'FINISHED'}


class WM_OT_ScxmlStop(bpy.types.Operator):
    bl_idname = "wm.scxml_stop"
    bl_label = "Stop Machine"

    def execute(self, context):
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
        p_scxml: ScxmlSettings = wm.scxml

        layout.prop(p_scxml, "state_machine_filepath")
        layout.operator(WM_OT_ScxmlStart.bl_idname)
        layout.operator(WM_OT_ScxmlStop.bl_idname)

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

            print("EXIT:", sender, final)
            if p_scxml.w3c_tests_index < len(p_scxml.w3c_tests) - 2:
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
                        self._machine = StateMachine(p_test.filepath)
                        self._start_time = timer()
                        dispatcher.connect(self.on_sm_exit, "signal_exit", self._machine.interpreter)
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

    def execute(self, context):
        wm = context.window_manager
        if wm.scxml.w3c_tests_running:
            wm.scxml.w3c_tests_running = False
            return {'FINISHED'}

        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)

        for idx in range(wm.scxml.w3c_tests_index, len(wm.scxml.w3c_tests), 1):
            p_test = wm.scxml.w3c_tests[idx]
            p_test.clear()
        wm.scxml.w3c_tests_running = True

        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        if self._machine:
            self._machine.cancel()
        wm.scxml.w3c_tests_running = False
        if hasattr(context, "area") and context.area:
            context.area.tag_redraw()


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
    WM_OT_ScxmlTestW3C,

    VIEW3D_PT_Scxml
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.WindowManager.scxml = bpy.props.PointerProperty(type=ScxmlSettings)

    base_dir = os.path.dirname(__file__)
    wm = bpy.context.window_manager
    wm.scxml.w3c_tests.clear()
    for entry in sorted(Path(os.path.join(base_dir, "w3c_tests")).glob("*.scxml")):
        file = str(entry)
        if "sub" not in file:
            wm.scxml.w3c_tests.add()
            p_test: ScxmlTest = wm.scxml.w3c_tests[-1]
            p_test.name = Path(file).name
            p_test.filepath = file


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.WindowManager.scxml
