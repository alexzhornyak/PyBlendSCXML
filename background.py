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
import os
import sys
import logging

s_blend_scxml_path = os.path.join(os.path.dirname(__file__), "src")
sys.path.append(s_blend_scxml_path)

from blend_scxml.monitor_scxml import UdpTestingMachine, UdpMonitorSettings  # noqa: E402


logging.basicConfig(level=logging.NOTSET)


if __name__ == "__main__":
    logger = logging.getLogger("scxml_tester")

    monitor_settings = UdpMonitorSettings()

    for idx, arg in enumerate(sys.argv):
        if arg == '-issue':
            monitor_settings.check_issue = bool(sys.argv[idx + 1])
            logger.info(f"issue={monitor_settings.check_issue}")
        elif arg == "-r":
            monitor_settings.remote_port = int(sys.argv[idx + 1])
            logger.info(f"remote_port={monitor_settings.remote_port}")
        elif arg == "-l":
            monitor_settings.local_port = int(sys.argv[idx + 1])
            logger.info(f"local_port={monitor_settings.local_port}")
        elif arg == "-f":
            monitor_settings.scxml_file_path = str(sys.argv[idx + 1])
            logger.info(f"file_path={monitor_settings.scxml_file_path}")

    sm = UdpTestingMachine(monitor_settings)
    sm.start()
