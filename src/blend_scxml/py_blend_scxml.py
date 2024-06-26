'''
This file is part of PySCXML.

    PySCXML is free software: you can redistribute it and/or modify
    it under the terms of the GNU Lesser General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    PySCXML is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU Lesser General Public License for more details.

    You should have received a copy of the GNU Lesser General Public License
    along with PySCXML. If not, see <http://www.gnu.org/licenses/>.

    @author: Johan Roxendal
    @contact: johan@roxendal.com
'''

# NOTE: modified by Alex Zhornyak, alexander.zhornyak@gmail.com

import bpy

import logging
import os
import re
from xml.etree import ElementTree as etree

# author="Patrick K. O'Brien and contributors",
# url="https://github.com/11craft/louie/",
# download_url="https://pypi.python.org/pypi/Louie",
# license="BSD"
from .louie import dispatcher
from .consts import DispatcherConstants

from . import compiler
from .interpreter import Interpreter, CancelEvent


def default_logfunction(label, msg):
    label = label or ""

    def f(x):
        if etree.iselement(x):
            return etree.tostring(x).strip()
        elif not isinstance(x, str):
            return str(x)

        return x

    if isinstance(msg, list):
        msg = list(map(f, msg))
        try:
            msg = "\n".join(msg)
        except Exception:
            msg = str(msg)
    print("%s%s%s" % (label, ": " if label and msg is not None else "", msg))


class StateMachine(object):
    '''
    This class provides the entry point for the PySCXML library.
    '''

    def __init__(
            self, source,
            log_function=default_logfunction,
            sessionid=None, default_datamodel="python", setup_session=True,
            filedir="", filename=""):
        self.is_finished = False
        self.compiler = compiler.Compiler()
        self.compiler.filedir = filedir
        self.compiler.filename = filename
        self.compiler.default_datamodel = default_datamodel
        self.compiler.log_function = log_function

        self.sessionid = sessionid or "pyscxml_session_" + str(id(self))
        self.interpreter = Interpreter()
        dispatcher.connect(self.on_exit, DispatcherConstants.exit, self.interpreter)
        self.logger = logging.getLogger("pyscxml.%s" % self.sessionid)
        self.interpreter.logger = logging.getLogger("pyscxml.%s.interpreter" % self.sessionid)
        self.compiler.logger = logging.getLogger("pyscxml.%s.compiler" % self.sessionid)
        self.doc = self.compiler.parseXML(
            self._open_document(source), self.interpreter)
        self.interpreter.dm = self.doc.datamodel
        self.datamodel = self.doc.datamodel
        self.doc.datamodel["_x"] = {"self": self}
        self.doc.datamodel.self = self
        self.doc.datamodel["_sessionid"] = self.sessionid
        self.doc.datamodel.sessionid = self.sessionid
        self.name = self.doc.name
        if setup_session:
            MultiSession().make_session(self.sessionid, self)

    @property
    def filedir(self):
        return self.compiler.filedir

    @property
    def filename(self):
        return self.compiler.filename

    def _open_document(self, uri):
        if isinstance(uri, str) and re.search("<(.+:)?scxml", uri):  # NOTE: "<scxml" in uri:
            self.compiler.filename = "<string source>"
            self.compiler.filedir = ""
            return uri
        else:
            p_doc = self.compiler.get_document(uri, self.compiler.filedir)
            self.compiler.filedir = p_doc.filedir
            self.compiler.filename = p_doc.filename

            return p_doc.content

    def _start(self):
        self.compiler.instantiate_datamodel()

        self.interpreter.interpret(self.doc)

    def _start_invoke(self, invokeid=None):
        self.compiler.instantiate_datamodel()
        self.interpreter.interpret(self.doc, invokeid)

    def start(self):
        '''Takes the statemachine to its initial state'''
        if not self.interpreter.running:
            raise RuntimeError("The StateMachine instance may only be started once.")
        else:
            doc = (
                os.path.join(self.compiler.filedir, self.compiler.filename)
                if self.compiler.filedir else self.compiler.filename)
            self.logger.info("Starting %s" % doc)
        self._start()
        bpy.app.timers.register(self.interpreter.mainEventLoop, persistent=True)

    def start_threaded(self):
        self._start()
        bpy.app.timers.register(self.interpreter.mainEventLoop, persistent=True)

    def isFinished(self):
        '''Returns True if the statemachine has reached it
        top-level final state or was cancelled.'''
        return self.is_finished

    def cancel(self):
        '''
        Stops the execution of the StateMachine, causing
        all the states in the current configuration to execute
        their onexit blocks. The StateMachine instance now no longer
        accepts events. For clarity, consider using the
        top-level <final /> state in your document instead.
        '''
        self.interpreter.running = False
        self.interpreter.externalQueue.put(CancelEvent())

    def send(self, name, data={}):
        '''
        Send an event to the running machine.
        @param name: the event name (string)
        @param data: the data passed to the _event.data variable (any data type)
        '''
        self._send(name, data)

    def _send(self, name, data={}, invokeid=None, toQueue=None):
        self.interpreter.send(name, data, invokeid, toQueue)

    def In(self, statename):
        '''
        Checks if the state 'statename' is in the current configuration,
        (i.e if the StateMachine instance is currently 'in' that state).
        '''
        return self.interpreter.In(statename)

    def on_exit(self, sender, final):
        if sender is self.interpreter:
            self.is_finished = True
            for timer in self.compiler.timer_mapping.values():
                if bpy.app.timers.is_registered(timer):
                    bpy.app.timers.unregister(timer)
                del timer
            dispatcher.disconnect(self, DispatcherConstants.exit, self.interpreter)
            dispatcher.send(DispatcherConstants.exit, self, final=final)

    def __enter__(self):
        self.start_threaded()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if not self.isFinished():
            self.cancel()


class MultiSession(object):

    def __init__(self, default_scxml_source=None, init_sessions={}, default_datamodel="python", log_function=default_logfunction):
        '''
        MultiSession is a local runtime environment for multiple StateMachine sessions. It's
        the base class for the PySCXMLServer. You probably won't need to instantiate it directly.
        @param default_scxml_source: an scxml document source (see StateMachine for the format).
        If one is provided, each call to a sessionid will initialize a new
        StateMachine instance at that session, running the default document.
        @param init_sessions: the optional keyword arguments run
        make_session(key, value) on each init_sessions pair, thus initalizing
        a set of sessions. Set value to None as a shorthand for deferring to the
        default xml for that session.
        '''
        self.default_scxml_source = default_scxml_source
        self.sm_mapping = {}
        self.get = self.sm_mapping.get
        self.default_datamodel = default_datamodel
        self.log_function = log_function
        self.logger = logging.getLogger("pyscxml.multisession")
        for sessionid, xml in init_sessions.items():
            self.make_session(sessionid, xml)

    def __iter__(self):
        return iter(list(self.sm_mapping.itervalues()))

    def __delitem__(self, val):
        del self.sm_mapping[val]

    def __getitem__(self, val):
        return self.sm_mapping[val]

    def __setitem__(self, key, val):
        self.make_session(key, val)

    def __contains__(self, item):
        return item in self.sm_mapping

    def start(self):
        ''' launches the initialized sessions by calling start_threaded() on each sm'''
        for sm in self:
            sm.start_threaded()

    def make_session(self, sessionid, source):
        '''initalizes and starts a new StateMachine session at the provided sessionid.

        @param source: A string. if None or empty, the statemachine at this
        sesssionid will run the document specified as default_scxml_doc
        in the constructor. Otherwise, the source will be run.
        @return: the resulting scxml.pyscxml.StateMachine instance. It has
        not been started, only initialized.
         '''
        assert source or self.default_scxml_source
        if isinstance(source, str):
            sm = StateMachine(
                source or self.default_scxml_source,
                sessionid=sessionid,
                default_datamodel=self.default_datamodel,
                setup_session=False,
                log_function=self.log_function)
        else:
            sm = source  # source is assumed to be a StateMachine instance
        self.sm_mapping[sessionid] = sm

        sm.datamodel.sessions = self
        self.set_processors(sm)
        dispatcher.connect(self.on_sm_exit, DispatcherConstants.exit, sm)
        return sm

    def set_processors(self, sm):
        processors = {
            "scxml": {
                "location": "#_scxml_" + sm.sessionid}}

        processors["http://www.w3.org/TR/scxml/#SCXMLEventProcessor"] = {"location": "#_scxml_" + sm.sessionid}

        sm.datamodel["_ioprocessors"] = processors

    def send(self, event, data={}, to_session=None):
        '''send an event to the specified session. if to_session is None or "",
        the event is sent to all active sessions.'''
        if to_session:
            self[to_session].send(event, data)
        else:
            for session in self.sm_mapping:
                self.sm_mapping[session].send(event, data)

    def cancel(self):
        for sm in self:
            sm.cancel()

    def on_sm_exit(self, sender, final):
        if sender.sessionid in self:
            self.logger.debug("The session '%s' finished" % sender.sessionid)
            del self[sender.sessionid]
        else:
            self.logger.error(
                "The session '%s' reported exit but it "
                "can't be found in the mapping." % sender.sessionid)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cancel()


class custom_executable(object):
    '''A decorator for defining custom executable content'''
    def __init__(self, namespace):
        self.namespace = namespace

    def __call__(self, f):
        compiler.custom_exec_mapping[self.namespace] = f
        return f


class custom_sendtype(object):
    '''A decorator for defining custom send types'''
    def __init__(self, sendtype):
        self.sendtype = sendtype

    def __call__(self, fun):
        compiler.custom_sendtype_mapping[self.sendtype] = fun
        return fun


def register_datamodel(id, klass):
    ''' registers a datamodel class to an id for use with the
    datamodel attribute of the scxml element.
    Datamodel class must satisfy the interface:
    __setitem__ # modifies
    __getitem__ # gets
    evalExpr(expr) # returns value
    execExpr(expr) # returns None
    hasLocation(location) # returns bool (check for deep location value)
    isLegalName(name) # returns bool
    @param klass: A function that returns an instance that satisfies the above api.
    '''
    compiler.datamodel_mapping[id] = klass

# __all__ = [
#     "StateMachine",
#     "MultiSession",
#     "custom_executable",
#     "preprocessor",
#     "expr_evaluator",
#     "expr_exec",
#     "custom_sendtype"
# ]
