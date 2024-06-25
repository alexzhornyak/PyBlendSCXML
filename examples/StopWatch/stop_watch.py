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

import time
from datetime import timedelta


def FormatTimeStr(milliseconds):
    # Convert milliseconds to timedelta
    delta = timedelta(milliseconds=milliseconds)

    # Check if milliseconds is zero
    if milliseconds <= 0:
        return "00:00.000"

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


class StopWatch:
    """A stopwatch class for timing durations."""

    def __init__(self):
        self.time_ms = None
        self.pause_time_ms = None
        self.pause_duration_ms = 0

    def start(self):
        """Starts the stopwatch."""
        self.reset()
        self.time_ms = time.time() * 1000  # Convert to milliseconds

    def suspend(self):
        """Suspends the stopwatch."""
        if self.time_ms is not None:
            self.pause_time_ms = time.time() * 1000

    def resume(self):
        """Resumes the stopwatch."""
        if self.pause_time_ms is not None:
            self.pause_duration_ms += time.time() * 1000 - self.pause_time_ms
            self.pause_time_ms = None

    def reset(self):
        """Resets the stopwatch."""
        self.time_ms = None
        self.pause_time_ms = None
        self.pause_duration_ms = 0

    def elapsed(self):
        """Returns the elapsed time in milliseconds."""
        if self.time_ms is None:
            return 0
        return (time.time() * 1000 if self.pause_time_ms is None else self.pause_time_ms) - self.time_ms - self.pause_duration_ms


Timer = StopWatch()
iLapCount = 0
iLapElapsed = 0


def on_display():

    p_scxml_props: ScxmlStopWatchProps = bpy.context.window_manager.scxml_stop_watch

    ElapsedMS = FormatTimeStr(Timer.elapsed())
    LapMS = FormatTimeStr(Timer.elapsed() - iLapElapsed)

    p_scxml_props.text_time = ElapsedMS
    p_scxml_props.text_lap = LapMS

    if iLapCount == 0:
        if len(p_scxml_props.laps) > 0:
            p_scxml_props.laps.clear()

    # User Pressed Lap Button
    else:
        # New Lap
        n_lap_count = len(p_scxml_props.laps)
        if n_lap_count - 1 != iLapCount:
            # If this is the first press of 'Lap' button
            # display previous lap
            if iLapCount == 1:
                p_scxml_props.laps.add()
                p_item: ScxmlStopWatchItem = p_scxml_props.laps[-1]
                p_item.lapIndex = 1
                p_item.startTime = "00:00.000"
                p_item.endTime = ElapsedMS

            # Current lap
            p_scxml_props.laps.add()
            p_item: ScxmlStopWatchItem = p_scxml_props.laps[-1]
            p_item.lapIndex = iLapCount + 1
            p_item.startTime = ElapsedMS
            p_item.endTime = "00:00.000"

            # Scroll to top item
            p_scxml_props.laps_index = len(p_scxml_props.laps) - 1

        # Updating Current Lap Values
        else:
            if n_lap_count > 1:
                p_item: ScxmlStopWatchItem = p_scxml_props.laps[n_lap_count-1]
                p_item.endTime = LapMS

    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


class SCXML_PT_StopWatch(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_label = "StopWatch"
    bl_region_type = "UI"
    bl_category = "SCXML"

    def draw(self, context: bpy.types.Context):
        layout = self.layout

        wm = context.window_manager
        p_scxml_props: ScxmlStopWatchProps = wm.scxml_stop_watch

        row = layout.row()
        row.prop(p_scxml_props, "text_time")

        if len(p_scxml_props.laps) > 0:

            box = layout.box()
            box.prop(p_scxml_props, "text_lap")

            row = layout.row()
            col = row.column()
            col.template_list(
                "SCXML_UL_StopWatchList",
                "lapIndex",
                p_scxml_props,
                "laps",
                p_scxml_props,
                "laps_index",
                rows=5
            )

        row = layout.row()
        r1 = row.row(align=True)
        b_is_in_read = In("ready")  # type: ignore
        s_text = "Start" if b_is_in_read else ("Pause" if In("active") else "Resume")  # type: ignore
        op = r1.operator(WM_OT_ScxmlStopWatchTrigger.bl_idname, text=s_text)
        op.event_name = "button.1"

        if not b_is_in_read:
            s_text = "Lap" if In("active") else "Reset"  # type: ignore
            op = r1.operator(WM_OT_ScxmlStopWatchTrigger.bl_idname, text=s_text)
            op.event_name = "button.2"


class WM_OT_ScxmlStopWatchTrigger(bpy.types.Operator):
    bl_idname = "wm.scxml_stop_watch_trigger"
    bl_label = "Trigger Machine"

    event_name: bpy.props.StringProperty(
        name="Event Name",
        default=""
    )

    def execute(self, context):
        _x["self"].send(self.event_name)  # type: ignore
        return {'FINISHED'}


class ScxmlStopWatchItem(bpy.types.PropertyGroup):
    lapIndex: bpy.props.IntProperty()
    startTime: bpy.props.StringProperty()
    endTime: bpy.props.StringProperty()


class ScxmlStopWatchProps(bpy.types.PropertyGroup):
    laps: bpy.props.CollectionProperty(type=ScxmlStopWatchItem)
    laps_index: bpy.props.IntProperty(min=-1, default=-1)

    text_time: bpy.props.StringProperty(
        name="Time", default="00:00")
    text_lap: bpy.props.StringProperty(
        name="Lap", default="00:00")


class SCXML_UL_StopWatchList(bpy.types.UIList):
    def __init__(self) -> None:
        super().__init__()
        self.use_filter_show = False
        self.use_filter_sort_reverse = True

    def draw_item(self, context, layout: bpy.types.UILayout, data, item: ScxmlStopWatchItem, icon, active_data, active_propname, index):
        layout.prop(item, "lapIndex", text="")
        layout.prop(item, "startTime", text="")
        layout.prop(item, "endTime", text="")


scxml_classes = (
    ScxmlStopWatchItem,
    ScxmlStopWatchProps,

    SCXML_UL_StopWatchList,
    WM_OT_ScxmlStopWatchTrigger,
    SCXML_PT_StopWatch,
)


def register():
    for cls in scxml_classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.scxml_stop_watch = bpy.props.PointerProperty(type=ScxmlStopWatchProps)


def unregister():
    del bpy.types.WindowManager.scxml_stop_watch
    for cls in reversed(scxml_classes):
        bpy.utils.unregister_class(cls)
