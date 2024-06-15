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
from pathlib import Path
import socket
import xml.etree.ElementTree as etree
import sys
from functools import partial
import threading
import json

s_blend_scxml_path = os.path.join(os.path.dirname(__file__), "src")
sys.path.append(s_blend_scxml_path)

from blend_scxml.py_blend_scxml import StateMachine, default_logfunction
from blend_scxml.louie import dispatcher
from blend_scxml import logger


s_FILE_PATH: str = ""
i_LOCAL_PORT = 11001
s_LOCAL_HOST = "127.0.0.1"

i_REMOTE_PORT = 11005
s_REMOTE_HOST = "127.0.0.1"

b_ISSUE = True


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


class UdpStateMachine(StateMachine):
    def __init__(
            self, source,
            sessionid=None, default_datamodel="python", setup_session=True,
            filedir="", filename=""):

        super().__init__(
            source,
            log_function=flushing_logfunction,
            sessionid=sessionid, default_datamodel=default_datamodel,
            setup_session=setup_session, filedir=filedir, filename=filename)
        dispatcher.connect(self.send_enter, "signal_enter_state", self.interpreter)
        dispatcher.connect(self.send_exit, "signal_exit_state", self.interpreter)
        dispatcher.connect(self.send_taking_transition, "signal_taking_transition", self.interpreter)

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
                self.udp_socket.shutdown(socket.SHUT_RDWR)
                sock = socket.socket(
                    socket.AF_INET,  # Internet
                    socket.SOCK_DGRAM)  # UDP
                sock.sendto("_".encode(), (s_LOCAL_HOST, i_LOCAL_PORT))

                self.listen_thread.join()

            self.listen_thread = None

    def __del__(self):
        self.stop_listen_thread()

    def listen_udp(self):
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            self.udp_socket.bind(("", i_LOCAL_PORT))

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

                    bpy.app.timers.register(partial(self.send, s_event, p_data_value if b_is_context else p_data_map))

                except Exception as e:
                    logger.error(str(e))
        except Exception as e:
            logger.error(f"Error:{str(e)}")
        finally:
            self.udp_socket.close()
            logger.info("socket was closed")

    def send_udp(self, message: str):
        sock = socket.socket(
            socket.AF_INET,  # Internet
            socket.SOCK_DGRAM)  # UDP
        sock.sendto(message.encode(), (s_REMOTE_HOST, i_REMOTE_PORT))

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
        logger.info(f"enter:{s_machine} {state}")
        self.send_udp(f"2@{s_machine}@{state}")

        # NOTE: ScxmlEditor does not intercept Blender output without it
        sys.stdout.flush()

    def send_exit(self, sender, state):
        s_machine = self.get_scxml_name(sender)
        logger.info(f"exit:{s_machine} {state}")
        self.send_udp(f"4@{s_machine}@{state}")

    def send_taking_transition(self, sender, state, transition_index):
        s_machine = self.get_scxml_name(sender)
        logger.info(f"transition:{s_machine} {transition_index}")
        self.send_udp(f"12@{s_machine}@{state}|{transition_index}")


sm: UdpStateMachine = None


def on_ready_to_start():
    global sm
    sm = UdpStateMachine(s_FILE_PATH)
    sm.start()


if __name__ == "__main__":

    for idx, arg in enumerate(sys.argv):
        if arg == '-issue':
            b_ISSUE = bool(sys.argv[idx + 1])
            logger.info(f"issue={b_ISSUE}")
        elif arg == "-r":
            i_REMOTE_PORT = int(sys.argv[idx + 1])
            logger.info(f"remote_port={i_REMOTE_PORT}")
        elif arg == "-l":
            i_LOCAL_PORT = int(sys.argv[idx + 1])
            logger.info(f"local_port={i_LOCAL_PORT}")
        elif arg == "-f":
            s_FILE_PATH = str(sys.argv[idx + 1])
            logger.info(f"file_path={s_FILE_PATH}")

    if not os.path.exists(s_FILE_PATH):
        raise RuntimeError(f"File: {s_FILE_PATH} is not found!")

    on_ready_to_start()
