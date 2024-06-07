'''
This file is part of pyscxml.

    pyscxml is free software: you can redistribute it and/or modify
    it under the terms of the GNU Lesser General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    pyscxml is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Lesser General Public License for more details.

    You should have received a copy of the GNU Lesser General Public License
    along with pyscxml.  If not, see <http://www.gnu.org/licenses/>.

    @author Johan Roxendal
    @contact: johan@roxendal.com
'''

import bpy

import logging

# author="Patrick K. O'Brien and contributors",
# url="https://github.com/11craft/louie/",
# download_url="https://pypi.python.org/pypi/Louie",
# license="BSD"
from .louie import dispatcher
from .interpreter import CancelEvent


class InvokeWrapper(object):

    def __init__(self):
        self.logger = logging.getLogger(F"pyscxml.invoke.{type(self).__name__}")
        self.invoke = lambda: None
        self.invokeid = None
        self.cancel = lambda: None
        self.invoke_obj = None
        self.autoforward = False

    def set_invoke(self, inv):
        inv.logger = self.logger
        self.invoke_obj = inv
        self.invokeid = inv.invokeid
        inv.autoforward = self.autoforward
        self.cancel = inv.cancel
        self.send = getattr(inv, "send", None)

    def finalize(self):
        if self.invoke_obj:
            self.invoke_obj.finalize()


class BaseInvoke(object):
    def __init__(self):
        self.invokeid = None
        self.parentSessionid = None
        self.autoforward = False
        self.src = None
        self.finalize = lambda: None

    def start(self, parentQueue):
        pass

    def cancel(self):
        pass

    def __str__(self):
        return '<Invoke id="%s">' % self.invokeid


class InvokeSCXML(BaseInvoke):
    def __init__(self, data):
        BaseInvoke.__init__(self)
        self.sm = None
        self.parentQueue = None
        self.content = None
        self.initData = data
        self.cancelled = False
        self.default_datamodel = "python"
        self.filedir = ""
        self.filename = ""

    def start(self, parentId):
        self.parentId = parentId
        self._start(self.content)

    def _start(self, doc):
        if self.cancelled:
            return
        from .py_blend_scxml import StateMachine

        self.sm = StateMachine(
            doc,
            sessionid=self.parentSessionid + "." + self.invokeid,
            default_datamodel=self.default_datamodel,
            setup_session=False, filedir=self.filedir, filename=self.filename)
        self.interpreter = self.sm.interpreter
        self.sm.compiler.initData = self.initData
        self.sm.compiler.parentId = self.parentId
        self.sm.interpreter.parentId = self.parentId
        dispatcher.send("created", sender=self, sm=self.sm)

        self.sm._start_invoke(self.invokeid)
        bpy.app.timers.register(self.sm.interpreter.mainEventLoop)

    def send(self, eventobj):
        if self.sm and not self.sm.isFinished():
            self.sm.interpreter.externalQueue.put(eventobj)

    def cancel(self):
        self.cancelled = True
        if not self.sm:
            return
        self.sm.interpreter.cancelled = True
        self.sm.interpreter.externalQueue.put(CancelEvent())
