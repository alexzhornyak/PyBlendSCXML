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

# flake8: noqa: E221

import logging


class DispatcherConstants:
    internal_event      = "signal_internal_event"
    external_event      = "signal_external_event"
    exit_state          = "signal_exit_state"
    enter_state         = "signal_enter_state"
    taking_transition   = "signal_taking_transition"
    new_configuration   = "signal_new_configuration"
    exit                = "signal_exit"


class ErrorFilter(logging.Filter):
    def filter(self, record):
        return record.levelno < logging.ERROR


PYSCXML_LOGGING_CONFIG = {
    'version': 1,
    'formatters': {
        'standard': {
            'format': '%(levelname)s> %(asctime)s.%(msecs)03d %(name)s: %(message)s',
            'datefmt': '%H:%M:%S'
        },
    },
    'handlers': {
        'default': {
            'level': 'DEBUG',
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
            'filters': ['error_filter'],
        },
        'error': {
            'level': 'ERROR',
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stderr',
        },
    },
    'filters': {
        'error_filter': {
            '()': ErrorFilter,
        },
    },
    'loggers': {
        'pyscxml': {
            'handlers': ['default', 'error'],
            'level': 'DEBUG',
            'propagate': False
        },
    }
}


PYSCXML_LITERAL = "pyscxml"

PYSCXML_MONITOR_LITERAL = "pyscxml.monitor"
