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

from pathlib import Path
import socket
import xml.etree.ElementTree as etree
import sys
from functools import partial
import threading
import json
from dataclasses import dataclass
import logging

from .py_blend_scxml import StateMachine, default_logfunction
from .consts import DispatcherConstants, PYSCXML_MONITOR_LITERAL
from .louie import dispatcher


@dataclass
class UdpMonitorSettings:
    check_issue: bool = False
    exit_stop: bool = False
    monitor_log: bool = False
    hide_debug_info: bool = False

    remote_port: int = 11005
    remote_host: str = "127.0.0.1"

    local_port: int = 11001
    local_host: str = "0.0.0.0"

    scxml_file_path: str = ""


class TContentTriggerType:
    cttDefault = 0
    cttBool = 1
    cttInteger = 2
    cttDouble = 3
    cttString = 4
    cttJson = 5
    cttUserData = 6


def get_trigger_value(s_text, trigger_type: int):
    if trigger_type == TContentTriggerType.cttInteger:
        return int(s_text)
    elif trigger_type == TContentTriggerType.cttDouble:
        return float(s_text)
    elif trigger_type == TContentTriggerType.cttJson:
        if s_text:
            return json.loads(s_text)
    return s_text


def flushing_logfunction(label, msg):
    default_logfunction(label, msg)
    # NOTE: ScxmlEditor does not intercept if it is not flushed
    sys.stdout.flush()


class UdpMonitorMachine(StateMachine):
    def __init__(
            self, source,
            monitor_enabled: bool = True,
            monitor_settings: UdpMonitorSettings = UdpMonitorSettings(),
            log_function=default_logfunction,
            sessionid=None,
            default_datamodel="python", setup_session=True,
            filedir="", filename=""):

        self._monitor_enabled = False

        self.monitor_settings = monitor_settings
        self.monitor_logger = logging.getLogger(PYSCXML_MONITOR_LITERAL)

        super().__init__(
            source,
            log_function=log_function,
            sessionid=sessionid, default_datamodel=default_datamodel,
            setup_session=setup_session, filedir=filedir, filename=filename)

        self.monitor_enabled = monitor_enabled

    @property
    def monitor_enabled(self):
        return self._monitor_enabled

    @monitor_enabled.setter
    def monitor_enabled(self, value: bool):
        if value != self._monitor_enabled:
            self._monitor_enabled = value
            if self._monitor_enabled:
                dispatcher.connect(self.send_enter, DispatcherConstants.enter_state, self.interpreter)
                dispatcher.connect(self.send_exit, DispatcherConstants.exit_state, self.interpreter)
                dispatcher.connect(self.send_taking_transition, DispatcherConstants.taking_transition, self.interpreter)
            else:
                dispatcher.disconnect(self.send_enter, DispatcherConstants.enter_state, self.interpreter)
                dispatcher.disconnect(self.send_exit, DispatcherConstants.exit_state, self.interpreter)
                dispatcher.disconnect(self.send_taking_transition, DispatcherConstants.taking_transition, self.interpreter)

    def send_udp(self, message: str):
        sock = socket.socket(
            socket.AF_INET,  # Internet
            socket.SOCK_DGRAM)  # UDP
        sock.sendto(
            message.encode(),
            (self.monitor_settings.remote_host, self.monitor_settings.remote_port))

    def get_scxml_name(self, sender):
        s_name = sender.dm.get("_name", "")
        if not s_name:
            try:
                s_name = Path(sender.dm.self.filename).stem
            except Exception:
                pass
        return s_name

    def send_enter(self, sender, state):
        s_machine = self.get_scxml_name(sender)

        self.monitor_logger.info(f"machine: {s_machine} enter: {state}")
        # NOTE: ScxmlEditor does not intercept Blender output without it
        sys.stdout.flush()

        self.send_udp(f"2@{s_machine}@{state}")

    def send_exit(self, sender, state):
        s_machine = self.get_scxml_name(sender)

        self.monitor_logger.info(f"machine: {s_machine} exit: {state}")
        self.send_udp(f"4@{s_machine}@{state}")

    def send_taking_transition(self, sender, state, transition_index):
        s_machine = self.get_scxml_name(sender)
        self.monitor_logger.info(f"machine: {s_machine} transition: {state} index: {transition_index}")
        self.send_udp(f"12@{s_machine}@{state}|{transition_index}")


class UdpTestingMachine(UdpMonitorMachine):
    def __init__(
            self,
            monitor_settings: UdpMonitorSettings,
            monitor_enabled: bool = True):

        if not monitor_settings.scxml_file_path:
            raise RuntimeError("Scxml filepath is not defined!")

        super().__init__(
            monitor_settings.scxml_file_path,
            monitor_enabled=monitor_enabled,
            monitor_settings=monitor_settings,
            log_function=flushing_logfunction)

        self._stop_event = threading.Event()
        self.listen_thread = threading.Thread(target=self.listen_udp)
        self.listen_thread.daemon = True
        self.listen_thread.start()

    def on_exit(self, sender, final):
        super().on_exit(sender, final)

        if sender is self.interpreter:
            self.stop_listen_thread()
            bpy.ops.wm.quit_blender()

    def stop_listen_thread(self):
        if self.listen_thread:
            self._stop_event.set()

            if self.listen_thread.is_alive:
                sock = socket.socket(
                    socket.AF_INET,  # Internet
                    socket.SOCK_DGRAM)  # UDP
                sock.sendto(
                    "_".encode(),
                    ("localhost", self.monitor_settings.local_port))

                self.listen_thread.join()

            self.listen_thread = None

    def __del__(self):
        self.stop_listen_thread()

    def listen_udp(self):
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            self.udp_socket.bind((self.monitor_settings.local_host, self.monitor_settings.local_port))

            while not self._stop_event.is_set():
                data, addr = self.udp_socket.recvfrom(8096)
                try:
                    s_data = data.decode()
                    if s_data == '_':
                        break
                    root = etree.fromstring(s_data)
                    s_event = root.get("name")
                    p_data_value = {}
                    p_data_map = {}

                    b_is_context = False

                    for elem in root:
                        if elem.tag == 'content':
                            trigger_type = int(elem.get("type", 0))
                            p_data_value = get_trigger_value(elem.text, trigger_type)
                            b_is_context = True
                        elif elem.tag == 'param':
                            s_key = elem.get("name", "")
                            s_val = elem.get("expr", "")
                            trigger_type = int(elem.get("type", 0))
                            p_data_map[s_key] = get_trigger_value(s_val, trigger_type)

                    bpy.app.timers.register(partial(self.send, s_event, p_data_value if b_is_context else p_data_map), persistent=True)

                except Exception as e:
                    self.monitor_logger.error(str(e))
        except Exception as e:
            self.monitor_logger.error(f"Error:{str(e)}")
        finally:
            self.udp_socket.close()
            self.monitor_logger.info("socket was closed")
