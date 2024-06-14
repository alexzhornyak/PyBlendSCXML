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
import xml.etree.ElementTree as etree
from collections import defaultdict
import sys
from functools import partial
import socketserver
import threading
import signal
import json

s_blend_scxml_path = os.path.join(os.path.dirname(__file__), "src")
sys.path.append(s_blend_scxml_path)

from blend_scxml.py_blend_scxml import StateMachine
from blend_scxml.louie import dispatcher

logging.basicConfig(level=logging.NOTSET)


s_file_path: str = ""
i_local_port = 11001
i_remote_port = 11005
b_issue = True


class TContentTriggerType:
    cttDefault = 0
    cttBool = 1
    cttInteger = 2
    cttDouble = 3
    cttString = 4
    cttJson = 5
    cttUserData = 6


class UDPHandler(socketserver.DatagramRequestHandler):
    def handle(self):

        logging.log(logging.INFO, "on_handle")

        datagram = self.rfile.readline().strip()

        logging.log(logging.INFO, datagram)


def get_trigger_value(s_text, trigger_type: int):
    if trigger_type == TContentTriggerType.cttInteger:
        return int(s_text)
    elif trigger_type == TContentTriggerType.cttDouble:
        return float(s_text)
    elif trigger_type == TContentTriggerType.cttJson:
        if s_text:
            return json.loads(s_text)
    return s_text


class UdpStateMachine(StateMachine):
    def __init__(
            self, source,
            sessionid=None, default_datamodel="python", setup_session=True,
            filedir="", filename=""):

        super().__init__(
            source,
            sessionid=sessionid, default_datamodel=default_datamodel,
            setup_session=setup_session, filedir=filedir, filename=filename)
        dispatcher.connect(self.send_enter, "signal_enter_state", self.interpreter)
        dispatcher.connect(self.send_exit, "signal_exit_state", self.interpreter)
        dispatcher.connect(self.send_taking_transition, "signal_taking_transition", self.interpreter)

        self._stop_event = threading.Event()
        self.listen_thread = threading.Thread(target=self.listen_udp)
        self.listen_thread.daemon = True
        self.listen_thread.start()

    def __del__(self):

        logging.log(logging.INFO, "1. _stop_event.set()")
        self._stop_event.set()

        logging.log(logging.INFO, "2. join()")
        self.listen_thread.join()

        logging.log(logging.INFO, "Exit point")

    def listen_udp(self):
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            self.udp_socket.bind(("", i_local_port))

            while not self._stop_event.is_set():
                logging.info("starts listening")
                data, addr = self.udp_socket.recvfrom(8096)
                # Process the received data here
                s_data = data.decode()
                logging.info(f"Received:{s_data}")
                try:
                    root = etree.fromstring(data.decode())
                    s_event = root.get("name")
                    p_data_value = {}
                    p_data_map = {}

                    b_is_context = False

                    for elem in root:
                        logging.info(elem.tag)
                        if elem.tag == 'content':
                            trigger_type = int(elem.get("type", 0))
                            p_data_value = get_trigger_value(elem.text, trigger_type)

                            logging.info(f"type:{trigger_type} data:{p_data_value} type:{type(p_data_value)}")

                            b_is_context = True
                        elif elem.tag == 'param':
                            s_key = elem.get("name", "")
                            s_val = elem.get("expr", "")
                            trigger_type = int(elem.get("type", 0))
                            p_data_map[s_key] = get_trigger_value(s_val, trigger_type)

                    logging.info(f'sending:{s_event}[{p_data_value}]')
                    bpy.app.timers.register(partial(self.send, s_event, p_data_value if b_is_context else p_data_map))

                except Exception as e:
                    logging.error(str(e))
        except Exception as e:
            logging.info(f"Error:{str(e)}")
        finally:
            self.udp_socket.close()

    def send_udp(self, message: str):
        UDP_IP = "127.0.0.1"
        UDP_PORT = i_remote_port

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


sm: UdpStateMachine = None


def on_ready_to_start():
    global sm
    sm = UdpStateMachine(s_file_path)
    sm.start()


def signal_handler(sig, frame):
    global sm
    del sm


if __name__ == "__main__":

    for idx, arg in enumerate(sys.argv):
        if arg == '-issue':
            b_issue = bool(sys.argv[idx + 1])
            logging.log(logging.INFO, f"issue={b_issue}")
        elif arg == "-r":
            i_remote_port = int(sys.argv[idx + 1])
            logging.log(logging.INFO, f"remote_port={i_remote_port}")
        elif arg == "-l":
            i_local_port = int(sys.argv[idx + 1])
            logging.log(logging.INFO, f"local_port={i_local_port}")
        elif arg == "-f":
            s_file_path = str(sys.argv[idx + 1])
            logging.log(logging.INFO, f"file_path={s_file_path}")

    if not os.path.exists(s_file_path):
        raise RuntimeError(f"File: {s_file_path} is not found!")

    on_ready_to_start()
    # bpy.app.timers.register(on_ready_to_start, first_interval=2.0)
