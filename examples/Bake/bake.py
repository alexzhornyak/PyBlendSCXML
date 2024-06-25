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

import bpy
from timeit import default_timer as timer
import logging
from datetime import timedelta


class ScxmlBakeLogicException(Exception):
    pass


class ScxmlData:
    t_BAKED_OBJECTS = []
    s_BAKE_OBJECT = ""
    s_BAKE_ERROR = ""

    @bpy.app.handlers.persistent
    def bake_scxml_on_depsgraph_update(self, scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph):
        logging.info(f"Depsgraph update: {str(scene)}, {str(depsgraph)}")
        for update in depsgraph.updates:
            if isinstance(update.id, bpy.types.Scene):
                # NOTE: we should release and do not change anything inside 'depsgraph_update'
                bpy.app.timers.register(lambda: _x["self"].send("scene.update"))  # type: ignore
                break

    @bpy.app.handlers.persistent
    def bake_scxml_on_bake_changed(self, obj: bpy.types.Object, _):
        logging.info(f"Bake changed: {str(obj)}")
        _x["self"].send("bake.changed")  # type: ignore


g_DATA = ScxmlData()


def FormatTimeStr(milliseconds):
    # Check if milliseconds is zero
    if milliseconds <= 0:
        return "00:00.000"

    # Convert milliseconds to timedelta
    delta = timedelta(milliseconds=milliseconds)

    # Extract components
    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    seconds = int(delta.total_seconds() % 60)
    milliseconds = delta.microseconds // 1000

    # Hide zero hours only if they are the only non-zero component
    if hours == 0:
        return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    else:
        # Format the string with leading zeros
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def update_view():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def is_bake_ready():
    ctx = bpy.context
    wm = ctx.window_manager
    p_scxml_props: ScxmlBakeProps = wm.scxml_bake
    n_obj_count = len(p_scxml_props.objects)
    return (
        not bpy.app.is_job_running("OBJECT_BAKE") and
        n_obj_count > 0 and
        In("EngineCycles") and  # type: ignore
        ctx.mode == 'OBJECT')


def is_bake_completed():
    return len(g_DATA.t_BAKED_OBJECTS) == 0


def bake_start():
    try:
        ctx = bpy.context
        wm = ctx.window_manager
        p_scxml_props: ScxmlBakeProps = wm.scxml_bake

        g_DATA.s_BAKE_OBJECT = g_DATA.t_BAKED_OBJECTS.pop(0)
        g_DATA.s_BAKE_ERROR = ""

        idx = p_scxml_props.objects.find(g_DATA.s_BAKE_OBJECT)
        if idx not in range(len(p_scxml_props.objects)):
            raise ScxmlBakeLogicException(f"Can not find internal object:{g_DATA.s_BAKE_OBJECT}")

        p_scxml_props.objects_index = idx
        p_obj_item: ScxmlBakeItem = p_scxml_props.objects[idx]
        p_obj: bpy.types.Object = ctx.view_layer.objects.get(g_DATA.s_BAKE_OBJECT)
        if p_obj is None:
            raise ScxmlBakeLogicException(f"Can not find view layer object:{g_DATA.s_BAKE_OBJECT}")
        p_obj_item.bake_state = 'BAKING'
        p_obj_item.bake_time_start = timer()

        bpy.ops.object.select_all(action='DESELECT')
        p_obj.select_set(True)
        ctx.view_layer.objects.active = p_obj
        bpy.ops.object.bake('INVOKE_DEFAULT')
    except ScxmlBakeLogicException as e:
        g_DATA.s_BAKE_ERROR = str(e)
        logging.error(g_DATA.s_BAKE_ERROR)
        _x["self"].send("bake.error")  # type: ignore


def bake_completed():
    if not g_DATA.s_BAKE_OBJECT:
        return

    try:
        ctx = bpy.context
        wm = ctx.window_manager
        p_scxml_props: ScxmlBakeProps = wm.scxml_bake

        idx = p_scxml_props.objects.find(g_DATA.s_BAKE_OBJECT)
        if idx not in range(len(p_scxml_props.objects)):
            raise ScxmlBakeLogicException(f"Can not find internal object:{g_DATA.s_BAKE_OBJECT}")

        p_obj_item: ScxmlBakeItem = p_scxml_props.objects[idx]
        p_obj_item.bake_state = 'COMPLETED'
        p_obj_item.bake_time = FormatTimeStr((timer() - p_obj_item.bake_time_start) * 1000)
    except ScxmlBakeLogicException as e:
        g_DATA.s_BAKE_ERROR = str(e)
        logging.error(g_DATA.s_BAKE_ERROR)
        _x["self"].send("bake.error")  # type: ignore


def bake_item_update():
    if not g_DATA.s_BAKE_OBJECT:
        return

    try:
        ctx = bpy.context
        wm = ctx.window_manager
        p_scxml_props: ScxmlBakeProps = wm.scxml_bake

        idx = p_scxml_props.objects.find(g_DATA.s_BAKE_OBJECT)
        logging.info(f"obj:{g_DATA.s_BAKE_OBJECT}, idx:{idx}")
        if idx not in range(len(p_scxml_props.objects)):
            raise ScxmlBakeLogicException(f"Can not find internal object:{g_DATA.s_BAKE_OBJECT}")

        p_obj_item: ScxmlBakeItem = p_scxml_props.objects[idx]
        p_obj_item.bake_time = FormatTimeStr((timer() - p_obj_item.bake_time_start) * 1000)
    except ScxmlBakeLogicException as e:
        g_DATA.s_BAKE_ERROR = str(e)
        logging.error(g_DATA.s_BAKE_ERROR)
        _x["self"].send("bake.error")  # type: ignore


def prepare_baking():
    ctx = bpy.context
    wm = ctx.window_manager
    p_scxml_props: ScxmlBakeProps = wm.scxml_bake

    t_selected_objects = [obj.name for obj in ctx.selected_objects if obj.type == 'MESH']
    if t_selected_objects != g_DATA.t_BAKED_OBJECTS:
        g_DATA.t_BAKED_OBJECTS = t_selected_objects
        g_DATA.s_BAKE_OBJECT = ""
        p_scxml_props.objects.clear()
        p_scxml_props.objects_index = -1
        for obj in ctx.selected_objects:
            if obj.type == 'MESH':
                p_scxml_props.objects.add()
                p_obj_item: ScxmlBakeItem = p_scxml_props.objects[-1]
                p_obj_item.name = obj.name


def exit_baking():
    ctx = bpy.context
    wm = ctx.window_manager
    p_scxml_props: ScxmlBakeProps = wm.scxml_bake
    for item in p_scxml_props.objects:
        p_obj: bpy.types.Object = ctx.view_layer.objects.get(item.name)
        if p_obj:
            p_obj.select_set(True)


class SCXML_PT_Bake(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_label = "Bake"
    bl_region_type = "UI"
    bl_category = "SCXML"

    def draw(self, context: bpy.types.Context):
        layout = self.layout

        wm = context.window_manager
        p_scxml_props: ScxmlBakeProps = wm.scxml_bake

        row = layout.row()
        col = row.column()
        col.template_list(
            "SCXML_UL_BakeList",
            "name",
            p_scxml_props,
            "objects",
            p_scxml_props,
            "objects_index",
            rows=5
        )

        row = layout.row(align=True)

        r1 = row.row(align=True)
        r1.enabled = In("BakeReady")  # type: ignore
        op = r1.operator(WM_OT_ScxmlBakeTrigger.bl_idname, text="Bake Start")
        op.event_name = "bake.start"

        r2 = row.row(align=True)
        r2.enabled = In("BakingActive") or In("BakingPaused")  # type: ignore
        s_text = "Resume" if In("BakingPaused") else "Pause"  # type: ignore
        op = r2.operator(WM_OT_ScxmlBakeTrigger.bl_idname, text=s_text)
        op.event_name = "bake.pause"

        r3 = row.row(align=True)
        r3.enabled = In("Baking")  # type: ignore
        op = r3.operator(WM_OT_ScxmlBakeTrigger.bl_idname, text="Bake Cancel")
        op.event_name = "bake.cancel"

        if In("BakeAllDone"):  # type: ignore
            if In("BakeError"):  # type: ignore
                col = layout.column(align=True)
                col.alert = True
                col.label(text="Bake Process Failed:")
                col.label(text=g_DATA.s_BAKE_ERROR)

            row = layout.row(align=True)
            op = row.operator(WM_OT_ScxmlBakeTrigger.bl_idname, text="Bake Reset")
            op.event_name = "bake.reset"


class WM_OT_ScxmlBakeTrigger(bpy.types.Operator):
    bl_idname = "wm.scxml_bake_trigger"
    bl_label = "Trigger Machine"

    event_name: bpy.props.StringProperty(
        name="Event Name",
        default=""
    )

    def execute(self, context):
        _x["self"].send(self.event_name)  # type: ignore
        return {'FINISHED'}


class ScxmlBakeItem(bpy.types.PropertyGroup):
    bake_time: bpy.props.StringProperty(name="Bake Time", default="00:00")
    bake_time_start: bpy.props.FloatProperty(name="Bake Time Start", default=0.0, min=0.0)
    bake_state: bpy.props.EnumProperty(
        name="Bake State",
        items=[
            ('NONE', 'None', ''),
            ('BAKING', 'Baking', ''),
            ('COMPLETED', 'Completed', ''),
        ])


class ScxmlBakeProps(bpy.types.PropertyGroup):
    objects: bpy.props.CollectionProperty(type=ScxmlBakeItem)
    objects_index: bpy.props.IntProperty(min=-1, default=-1)


class SCXML_UL_BakeList(bpy.types.UIList):
    def draw_item(self, context, layout: bpy.types.UILayout, data, item: ScxmlBakeItem, icon, active_data, active_propname, index):
        layout.prop(item, "name", text="", emboss=False)
        layout.prop(item, "bake_state", text="", emboss=False)
        layout.prop(item, "bake_time", text="", emboss=False)


scxml_classes = (
    ScxmlBakeItem,
    ScxmlBakeProps,

    SCXML_UL_BakeList,
    WM_OT_ScxmlBakeTrigger,
    SCXML_PT_Bake,
)


def register():
    for cls in scxml_classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.scxml_bake = bpy.props.PointerProperty(type=ScxmlBakeProps)

    bpy.app.handlers.depsgraph_update_post.append(g_DATA.bake_scxml_on_depsgraph_update)

    bpy.app.handlers.object_bake_cancel.append(g_DATA.bake_scxml_on_bake_changed)
    bpy.app.handlers.object_bake_pre.append(g_DATA.bake_scxml_on_bake_changed)
    bpy.app.handlers.object_bake_complete.append(g_DATA.bake_scxml_on_bake_changed)


def unregister():

    bpy.app.handlers.depsgraph_update_post.remove(g_DATA.bake_scxml_on_depsgraph_update)
    bpy.app.handlers.object_bake_cancel.remove(g_DATA.bake_scxml_on_bake_changed)
    bpy.app.handlers.object_bake_pre.remove(g_DATA.bake_scxml_on_bake_changed)
    bpy.app.handlers.object_bake_complete.remove(g_DATA.bake_scxml_on_bake_changed)

    del bpy.types.WindowManager.scxml_bake
    for cls in reversed(scxml_classes):
        bpy.utils.unregister_class(cls)
