'''
This file is part of pyscxml.

    PySCXML is free software: you can redistribute it and/or modify
    it under the terms of the GNU Lesser General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    PySCXML is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Lesser General Public License for more details.

    You should have received a copy of the GNU Lesser General Public License
    along with PySCXML. If not, see <http://www.gnu.org/licenses/>.

    @author Johan Roxendal
    @contact: johan@roxendal.com

'''

import bpy

from .node import (
    Final,
    History,
    Initial,
    Onentry, Onexit,
    Parallel,
    SCXMLDocument,
    State, Transition,
    # SCXMLNode
)
import re
# import sys
from functools import partial
from .messaging import get_path
# FIXME: from .louie import dispatcher
import urllib
from .eventprocessor import Event, SCXMLEventProcessor as Processor, ScxmlMessage
from .invoke import InvokeWrapper, InvokeSCXML
from xml.parsers.expat import ExpatError
from xml.etree import ElementTree as etree
import textwrap


# import time
from .datamodel import PythonDataModel
from .errors import (
    ExprEvalError,
    AttributeEvalError,
    ScriptFetchError,
    InvokeError,
    SendError,
    SendExecutionError,
    SendCommunicationError,
    AtomicError,
    ExecutableError,
    CompositeError,
    DataModelError,
    ExecutableContainerError,
    IllegalLocationError
)
from queue import Queue
# from . import pyscxml
# import eventlet
# from scxml.datastructures import Nodeset
import xml.dom.minidom as minidom
from .dotsi import Dict


def prepend_ns(tag):
    return ("{%s}" % ns) + tag


def split_ns(node):
    if "{" not in node.tag:
        return ["", node.tag]

    return node.tag[1:].split("}")


ns = "http://www.w3.org/2005/07/scxml"
pyscxml_ns = "http://code.google.com/p/pyscxml"
tagsForTraversal = ["scxml", "state", "parallel", "history", "final", "transition", "invoke", "onentry", "onexit", "datamodel"]
tagsForTraversal = [prepend_ns(tag) for tag in tagsForTraversal]
custom_exec_mapping = {}
preprocess_mapping = {}
datamodel_mapping = {
    "python": PythonDataModel,
    "null": PythonDataModel,  # probably shouldn't allow script in the null datamodel
}
custom_sendtype_mapping = {}

# FIXME
# fns = etree.FunctionNamespace(None)


def in_func(context, x):
    return context.context_node._parent.self.interpreter.In(x)


# FIXME
# fns["In"] = in_func


class Compiler(object):
    '''The class responsible for compiling the statemachine'''
    def __init__(self):
        self.doc = SCXMLDocument()

        #        self.setSessionId()
        # used by data passed to invoked processes
        self.initData = Dict()
        self.script_src = {}
        self.datamodel = None
        #        self.sourceline_mapping = {}

        self.log_function = None
        self.strict_parse = False
        self.timer_mapping = {}
        self.instantiate_datamodel = None
        self.default_datamodel = None
        self.invokeid_counter = 0
        self.sendid_counter = 0
        self.parentId = None

    def setupDatamodel(self, datamodel):
        self.datamodel = datamodel
        self.doc.datamodel = datamodel_mapping[datamodel]()

        self.dm = self.doc.datamodel
        self.dm.response = Queue()
        self.dm.websocket = Queue()
        self.dm["__event"] = None
        #        self.dm["_x"]["sessions"] = {}

        self.dm["In"] = self.interpreter.In

    def parseAttr(self, elem, attr, default=None, is_list=False):
        if not elem.get(attr, elem.get(attr + "expr")):
            return default
        else:
            try:
                stringify = {
                    "python": "str"
                }
                expr = elem.get(attr + "expr")

                output = elem.get(attr) or self.getExprValue("%s(%s)" % (stringify[self.datamodel], expr))
                output = str(output)

            except ExprEvalError as e:
                raise AttributeEvalError(e, elem, attr + "expr")
            return output if not is_list else output.split(" ")

    def init_scripts(self, tree):
        scripts = tree.iter(prepend_ns("script"))
        scripts = filter(lambda x: x.get("src"), scripts)

        self.script_src = self.parallelize_download(scripts)

        failedList = list(filter(lambda x: isinstance(x[1], Exception), self.script_src.items()))
        if not failedList:
            return
        # NOTE: decorate the output.
        linenums = list(map(lambda x: str(x[0].sourceline), failedList))
        if len(linenums) > 2:
            linenums[:-2] = map(lambda x: x + ",", linenums[:-2])
        plur = ""
        if len(failedList) > 1:
            plur = "s"
            linenums[-1:] = ["and", linenums[-1]]
        raise ScriptFetchError("Fetching remote script file%s failed on line%s %s." % (plur, plur, " ".join(linenums)))

    def try_execute_content(self, parent):
        try:
            self.do_execute_content(parent)
        except SendError as e:
            xml_str = etree.tostring(e.elem, encoding='unicode')
            self.logger.error("Parsing of send node failed on line %s." % xml_str)
            self.logger.error(str(e))
            self.raiseError("error." + e.error_type, e, sendid=e.sendid)
        except (CompositeError, AtomicError) as e:  # XXX: AttributeEvalError, ExprEvalError as executableError
            self.logger.error(e)
            self.raiseError("error.execution." + type(e.exception).__name__.lower(), e)

        except Exception as e:
            xml_str = etree.tostring(parent, encoding='unicode')
            self.logger.exception("An unknown error occurred when executing content in block on line %s." % xml_str)
            self.raiseError("error.execution", e)

    def do_execute_content(self, parent):
        '''
        @param parent: usually an xml Element containing executable children
        elements, but can also be any iterator of executable elements.
        '''

        for node in parent:
            node_ns, node_name = split_ns(node)
            if node_ns == ns:
                if node_name == "log":
                    try:
                        self.log_function(node.get("label"), self.getExprValue(node.get("expr")))
                    except ExprEvalError as e:
                        raise AttributeEvalError(e, node, "expr")
                elif node_name == "raise":
                    eventName = node.get("event").split(".")
                    self.interpreter.raiseFunction(eventName, {})
                elif node_name == "send":
                    #                    if not hasattr(node, "id_n"): node.id_n = 0
                    #                    else: node.id_n += 1
                    sendid = node.get("id", "send_id_%s_%s" % (id(node), self.sendid_counter))
                    self.sendid_counter += 1
                    #                     sendid = "broken"
                    try:
                        self.parseSend(node, sendid)
                    except AttributeEvalError:
                        raise
                    except (SendExecutionError, SendCommunicationError) as e:
                        raise SendError(e, node, e.type, sendid=sendid)
                    except Exception as e:
                        raise SendError(e, node, "execution", sendid=sendid)
                elif node_name == "cancel":
                    sendid = self.parseAttr(node, "sendid")
                    if sendid in self.timer_mapping:
                        bpy.app.timers.unregister(self.timer_mapping[sendid])
                        del self.timer_mapping[sendid]
                elif node_name == "assign":
                    try:
                        self.dm.assign(node)
                    except CompositeError:
                        raise
                    except Exception as e:
                        raise ExecutableError(AtomicError(e), node)
                elif node_name == "script":
                    try:
                        src = node.text or self.script_src.get(node) or ""
                        self.execExpr(src)
                    except ExprEvalError as e:
                        raise ExecutableError(e, node)

                elif node_name == "if":
                    self.parseIf(node)
                elif node_name == "foreach":
                    startIndex = 0
                    try:
                        array = self.getExprValue(node.get("array"))
                    except ExprEvalError as e:
                        raise AttributeEvalError(e, node, "array")
                    except TypeError as e:
                        err = DataModelError(e)
                        raise AttributeEvalError(err, node, "array")
                    for index, item in enumerate(array, startIndex):
                        try:
                            # if it's not a correct QName: crash.
                            etree.QName(node.get("item"))
                            self.dm[node.get("item")] = item
                        except DataModelError as e:
                            raise AttributeEvalError(e, node, "item")
                        except ValueError as e:
                            raise AttributeEvalError(DataModelError(e), node, "item")

                        try:
                            # if it's not a correct QName: crash.
                            etree.QName(node.get("item"))
                            if node.get("index"):
                                self.dm[node.get("index")] = index

                        except DataModelError as e:
                            raise AttributeEvalError(e, node, "index")
                        try:
                            self.do_execute_content(node)
                        except Exception as e:
                            raise ExecutableContainerError(e, node)
            elif node_ns == pyscxml_ns:
                if node_name == "start_session":
                    xml = None
                    # TODO: why are we using both parseData and parseContent here?
                    data = self.parseData(node, getContent=False)
                    contentNode = node.find(prepend_ns("content"))
                    if contentNode is not None:
                        xml = self.parseContent(contentNode)
                        if type(xml) is list:
                            # TODO: if len(cnt) > 0, we could throw exception.
                            xml = etree.tostring(xml[0])
                        else:
                            raise Exception(F"Error when parsing contentNode, content is {xml}")
                    elif node.get("expr"):
                        try:
                            s_expr = node.get("expr")
                            xml = self.getExprValue(F"({s_expr})")
                        except Exception as e:
                            xml_str = etree.tostring(node, encoding='unicode')
                            e = ExecutableError(
                                node,
                                f"An expr error caused the start_session to fail on line {xml_str}")
                            self.logger.error(str(e))
                            self.raiseError("error.execution", e)
                    elif self.parseAttr(node, "src"):
                        xml = urllib.request.urlopen(self.parseAttr(node, "src")).read()
                    try:
                        multisession = self.dm.sessions
                        sm = multisession.make_session(self.parseAttr(node, "sessionid"), xml)
                        sm.compiler.initData = Dict(data)
                        sm.start_threaded()
                        timeout = self.parseCSSTime(self.parseAttr(node, "timeout", "0s"))
                        if timeout:
                            def cancel():
                                if not sm.isFinished():
                                    sm.cancel()
                            # FIXME
                            # eventlet.spawn_after(timeout, cancel)
                    except AssertionError:
                        raise ExecutableError(
                            node,
                            "You supplied no xml for <pyscxml:start_session /> "
                            "and no default has been declared.")
                    except KeyError:
                        raise ExecutableError(
                            node,
                            "You can only use the pyscxml:start_session "
                            "element for documents in a MultiSession enviroment")
            elif node_ns in custom_exec_mapping:
                # execute functions registered using scxml.pyscxml.custom_executable
                custom_exec_mapping[node_ns](node, self.dm)

            else:
                if self.strict_parse:
                    raise ExecutableError(node, "PySCXML doesn't recognize the executabel content '%s'" % node.tag)

    def parseIf(self, node):
        def gen_prefixExec(itr):
            for elem in itr:
                if elem.tag not in map(prepend_ns, ["elseif", "else"]):
                    yield elem
                else:
                    break

        def gen_ifblock(ifnode):
            yield (ifnode, gen_prefixExec(ifnode))
            for elem in (x for x in ifnode if x.tag == prepend_ns("elseif") or x.tag == prepend_ns("else")):
                elemIndex = list(ifnode).index(elem)
                yield (elem, gen_prefixExec(ifnode[elemIndex+1:]))

        for ifNode, execList in gen_ifblock(node):
            isElse = ifNode.tag == prepend_ns("else")
            if not isElse:
                try:
                    cond = self.getExprValue(ifNode.get("cond"))
                except ExprEvalError as e:
                    raise AttributeEvalError(e, ifNode, "cond")
            try:
                if isElse:
                    self.do_execute_content(execList)
                    break
                elif cond:
                    self.do_execute_content(execList)
                    break
            except Exception as e:
                raise ExecutableContainerError(e, node)

    def parseData(self, child, getContent=True, forSend=False):
        '''
        Given a parent node, returns a data object corresponding to
        its param child nodes, namelist attribute or content child element.
        '''

        contentNode = child.find(prepend_ns("content"))
        if getContent and contentNode is not None:
            return self.parseContent(contentNode)

        # TODO: how does the param behave in <donedata /> ?
        # TODO: location: can we express nested (deep) location?
        output = []
        for p in child.findall(prepend_ns("param")):
            expr = p.get("expr", p.get("location"))
            output.append(
                (p.get("name"), self.getExprValue(expr))
            )

        if child.get("namelist"):
            for name in child.get("namelist").split(" "):
                output.append(
                    (name, self.getExprValue(name))
                )

        return output

    def parseContent(self, contentNode):
        return self.dm.parseContent(contentNode)

    def parseCSSTime(self, timestr):
        n, unit = re.search("(\\d+)(\\w+)", timestr).groups()
        assert unit in ("s", "ms")
        return float(n) if unit == "s" else float(n) / 1000

    def parseSend(self, sendNode, sendid):

        if sendNode.get("idlocation"):
            if not self.dm.hasLocation(sendNode.get("idlocation")):
                msg = "The location expression '%s' was not instantiated in the datamodel." % sendNode.get("location")
                raise ExecutableError(IllegalLocationError(msg), sendNode)
            # XXX self.dm[sendNode.get("idlocation")] = sendid
            self.dm.assign(
                etree.Element(
                    "assign",
                    attrib={
                        "location": sendNode.get("idlocation"),
                        "expr": "'%s'" % sendid}))

        type = self.parseAttr(sendNode, "type", "scxml")
        e = self.parseAttr(sendNode, "event")
        event = e and e.split(".")
        eventstr = ".".join(event) if event else ""
        if type == "scxml" and not eventstr:
            raise SendExecutionError("Illegal send event value: '%s'" % eventstr)

        target = self.parseAttr(sendNode, "target")
        if target == "#_response":
            type = "x-pyscxml-response"
        sender = None
        try:
            raw = self.parseData(sendNode, forSend=True)
            try:
                data = Dict(raw)
            except Exception:
                # data is not key/value pair
                data = raw
        except ExprEvalError as e:
            xml_str = etree.tostring(sendNode, encoding='unicode')
            self.logger.exception("Line %s: send not executed: parsing of data failed" % xml_str)
            # XXX self.raiseError("error.execution", e, sendid=sendid)
            raise e

        # TODO: what about event.origin and the others? and what about if <send idlocation="_event" ?
        defaultSendid = sendid if sendNode.get("id", sendNode.get("idlocation")) else None
        defaultSend = partial(self.interpreter.send, event, data, sendid=defaultSendid, eventtype="external", raw=raw, language=self.datamodel)

        scxmlSendType = ("http://www.w3.org/TR/scxml/#SCXMLEventProcessor", "scxml")
        httpSendType = ("http://www.w3.org/TR/scxml/#BasicHTTPEventProcessor", "basichttp")

        from .py_blend_scxml import StateMachine

        if (type in scxmlSendType or type in httpSendType) and not target:
            # TODO: a shortcut, we're sending without eventprocessors no matter
            # the send type if the target is self. This might break conformance.
            # see test 201.

            sender = defaultSend
        elif target.startswith("#_scxml_"):  # NOTE: sessionid
            sessionid = target.split("#_scxml_")[-1]
            try:
                toQueue = self.dm.sessions[sessionid].interpreter.externalQueue
            except KeyError:
                raise SendCommunicationError("The session '%s' is inaccessible." % sessionid)
            sender = partial(defaultSend, toQueue=toQueue)
        elif isinstance(target, StateMachine):
            # TODO: what happens if this target isFinished when this executes?
            sender = partial(target.interpreter.send, event, data, sendid=defaultSendid)
        elif type in scxmlSendType:
            if target == "#_parent":
                if self.interpreter.exited or self.interpreter.cancelled:
                    # NOTE: if we were cancelled, don't send to _parent
                    return
                try:
                    toQueue = self.dm.sessions[self.parentId].interpreter.externalQueue
                except KeyError:
                    raise SendCommunicationError("There is no parent session.")
                sender = partial(defaultSend, self.interpreter.invokeId, toQueue=toQueue)
            elif target == "#_internal":
                sender = partial(self.interpreter.raiseFunction, event, data, sendid=sendid)
            elif target == "#_websocket":
                self.logger.debug("sending to _websocket")
                eventXML = Processor.toxml(eventstr, target, data, "", sendNode.get("id", ""), language=self.datamodel)
                sender = partial(self.dm.websocket.put, eventXML)
            elif target.startswith("#_") and not target == "#_response":  # invokeid
                try:
                    sessionid = self.dm.sessionid + "." + target[2:]
                    sm = self.dm.sessions[sessionid]
                except KeyError:
                    xml_str = etree.tostring(sendNode, encoding='unicode')
                    e = SendCommunicationError("Line %s: No valid invoke target at '%s'." % (xml_str, sessionid))
                sender = partial(sm.interpreter.send, event, data, sendid=sendid)
            else:
                raise SendExecutionError(
                    f"The send target '{target}' is malformed or unsupported by the platform for the send type '{type}'.")
        elif type == "x-pyscxml-soap":
            sender = partial(self.dm[target[1:]].send, event, data)
        elif type == "x-pyscxml-statemachine":
            try:
                evt_obj = Event(event, data)
                sender = partial(self.dm[target].send, evt_obj)
            except Exception:
                raise SendExecutionError("No StateMachine instance at datamodel location '%s'" % target)
        # this is where to add parsing for more send types.
        else:
            if custom_sendtype_mapping.get(type, None) is None:
                raise SendExecutionError("The send type '%s' is invalid or unsupported by the platform" % type)

            source = self.dm["_ioprocessors"][type]["location"]
            sendid = defaultSendid or ''
            msg = ScxmlMessage(eventstr, source, target, data, sendid, sourcetype='scxml')
            sender_func = custom_sendtype_mapping[type]

            sender = partial(sender_func, msg, self.dm)

        delay = self.parseAttr(sendNode, "delay", "0s")
        try:
            delay = self.parseCSSTime(delay)
        except (AttributeError, AssertionError):
            raise SendExecutionError(
                f"delay format error: the delay attribute should be specified using the CSS time format, you supplied the faulty value: {delay}")

        if delay:
            self.timer_mapping[sendid] = sender
            bpy.app.timers.register(sender, first_interval=delay)
            pass
        else:
            try:
                sender()
            except Exception as e:
                raise SendExecutionError("%s: %s" % (e.__class__, e))

    def raiseError(self, err, exception=None, sendid=None):
        # self.interpreter.send(err.split("."), data=exception)
        self.interpreter.raiseFunction(err.split("."), exception, sendid=sendid, type="platform")

    def parseXML(self, xmlStr, interpreterRef):
        self.interpreter = interpreterRef
        xmlStr = self.addDefaultNamespace(xmlStr)
        try:
            tree = self.xml_from_string(xmlStr)
        except ExpatError:
            xmlStr = "\n".join("%s %s" % (n, line) for n, line in enumerate(xmlStr.split("\n")))
            self.logger.error(xmlStr)
            raise
        # ElementInclude.include(tree)
        self.strict_parse = tree.get("exmode", "lax") == "strict"
        self.doc.binding = tree.get("binding", "early")
        t_items = preprocess(tree)
        self.is_response = tree.get("{%s}%s" % (pyscxml_ns, "response")) in ("true", "True")
        self.setupDatamodel(tree.get("datamodel", self.default_datamodel))

        def init():
            try:
                self.setDatamodel(tree)
            except Exception as e:
                self.raiseError("error.execution", e)
        self.instantiate_datamodel = init
        self.init_scripts(tree)

        for n, parent, node in t_items:
            if parent is not None and parent.get("id"):
                parentState = self.doc.getState(parent.get("id"))

            node_ns, node_tag = split_ns(node)
            if node_tag == "scxml":
                s = State(node.get("id"), None, n)
                s.initial = self.parseInitial(node)
                self.doc.name = node.get("name", "")
                self.dm["_name"] = node.get("name", "")
                for scriptChild in node.findall(prepend_ns("script")):
                    src = scriptChild.text or self.script_src.get(scriptChild, "") or ""
                    # XXX except URLError, e:
                    #     msg = ("A URL error in a top level script element at line %s "
                    #     "prevented the document from executing. Error: %s") % (scriptChild.sourceline, e)
                    #     raise ScriptFetchError(msg)
                    try:
                        self.execExpr(src)
                    except ExprEvalError:
                        # TODO: we should probably crash here.
                        self.logger.exception("An exception was raised in a top-level script element.")

                self.doc.rootState = s
            elif node_tag == "state":
                s = State(node.get("id"), parentState, n)
                s.initial = self.parseInitial(node)

                self.doc.addNode(s)
                parentState.addChild(s)

            elif node_tag == "parallel":
                s = Parallel(node.get("id"), parentState, n)
                self.doc.addNode(s)
                parentState.addChild(s)

            elif node_tag == "final":
                s = Final(node.get("id"), parentState, n)
                self.doc.addNode(s)

                if node.find(prepend_ns("donedata")) is not None:

                    doneNode = node.find(prepend_ns("donedata"))

                    def donedata(node):
                        try:
                            data = self.parseData(node, forSend=True)

                            if self.datamodel == "xpath" and not all(map(lambda x: type(x) is tuple, data)):
                                return data
                            try:
                                return Dict(data)
                            except (TypeError, ValueError):
                                # NOTE: not key/value data, probably from <content>
                                return data
                        except Exception as e:
                            # TODO: what happens if donedata in the top-level final fails?
                            # we can't set the _event.data with anything. answer: catch the error in
                            # the interpreter, insert error in outgoing done event.
                            xml_str = etree.tostring(node, encoding='unicode')
                            self.logger.exception("Line %s: Donedata crashed." % xml_str)
                            self.raiseError("error.execution", exception=e)
                            # TODO: this may not be consistent with how _event.data is populated from <send>
                        return None

                    s.donedata = partial(donedata, doneNode)

                else:
                    s.donedata = lambda: {}

                parentState.addFinal(s)

            elif node_tag == "history":
                h = History(node.get("id"), parentState, node.get("type"), n)
                self.doc.addNode(h)
                parentState.addHistory(h)

            elif node_tag == "transition":
                t = Transition(parentState)
                if node.get("target"):
                    t.target = node.get("target").split(" ")
                if node.get("event"):
                    t.event = map(lambda x: re.sub(r"(.*)\.\*$", r"\1", x).split("."), node.get("event").split(" "))
                if node.get("cond"):
                    def f(expr):
                        try:
                            return self.getExprValue(expr)
                        except Exception as e:
                            self.raiseError("error.execution", e)
                            xml_str = etree.tostring(node, encoding='unicode')
                            self.logger.error("Evaluation of cond failed on line %s: %s" % (xml_str, expr))

                    t.cond = partial(f, node.get("cond"))
                t.type = node.get("type", "external")

                t.exe = partial(self.try_execute_content, node)
                parentState.addTransition(t)

            elif node_tag == "invoke":
                parentState.addInvoke(self.make_invoke_wrapper(node, parentState.id, n))
            elif node_tag == "onentry":
                s = Onentry()

                s.exe = partial(self.try_execute_content, node)
                parentState.addOnentry(s)

            elif node_tag == "onexit":
                s = Onexit()
                s.exe = partial(self.try_execute_content, node)
                parentState.addOnexit(s)

            elif node_tag == "datamodel":
                def initDatamodel(datalist):
                    try:
                        self.setDataList(datalist)
                    except Exception:
                        self.logger.exception("Evaluation of a data element failed.")
                parentState.initDatamodel = partial(initDatamodel, node.findall(prepend_ns("data")))

            else:
                xml_str = etree.tostring(node, encoding='unicode')
                self.logger.error("Parsing of element '%s' failed at line %s" % (node_tag, xml_str or "unknown"))

        return self.doc

    def execExpr(self, expr):
        if not expr or not expr.strip():
            return
        expr = normalizeExpr(expr)
        self.dm.execExpr(expr)

    def getExprValue(self, expr):
        """These expressions are always one-liners, so their value is evaluated and returned."""
        if not expr:
            return None
        # NOTE: throws all kinds of exceptions
        return self.dm.evalExpr(expr)

    def make_invoke_wrapper(self, node, parentId, n):

        def start_invoke(wrapper):
            try:
                inv = self.parseInvoke(node, parentId, n)
            except InvokeError as e:
                xml_str = etree.tostring(node, encoding='unicode')
                self.logger.exception("Line %s: Exception while parsing invoke." % (xml_str))
                self.raiseError("error.execution.invoke.parseerror", e)
                return
            except Exception as e:
                xml_str = etree.tostring(node, encoding='unicode')
                self.logger.exception("Line %s: Exception while parsing invoke." % (xml_str))
                self.raiseError("error.execution.invoke." + type(e).__name__.lower(), e)
                return
            wrapper.set_invoke(inv)

            # FIXME: dispatcher.connect(self.onInvokeSignal, "init.invoke." + inv.invokeid, inv)
            # FIXME: dispatcher.connect(self.onInvokeSignal, "result.invoke." + inv.invokeid, inv)
            # FIXME: dispatcher.connect(self.onInvokeSignal, "error.communication.invoke." + inv.invokeid, inv)
            try:
                if isinstance(inv, InvokeSCXML):
                    def onCreated(sender, sm):
                        sessionid = sm.sessionid
                        self.dm.sessions.make_session(sessionid, sm)
                inv.start(self.dm.sessionid, onCreated)
            except Exception as e:
                # XXX del self.dm["_x"]["sessions"][sessionid]
                xml_str = etree.tostring(node, encoding='unicode')
                self.logger.exception("Line %s: Exception while parsing invoke xml." % (xml_str))
                self.raiseError("error.execution.invoke." + type(e).__name__.lower(), e)

        wrapper = InvokeWrapper()
        wrapper.invoke = start_invoke
        wrapper.autoforward = node.get("autoforward", "false").lower() == "true"

        return wrapper

    def onInvokeSignal(self, signal, sender, **kwargs):
        self.logger.debug("onInvokeSignal " + signal)
        if signal.startswith("error"):
            self.raiseError(signal, kwargs["data"]["exception"])
            return
        self.interpreter.send(signal, data=kwargs.get("data", {}), invokeid=sender.invokeid)

    def parseInvoke(self, node, parentId, n):
        invokeid = node.get("id")
        if not invokeid:

            # XXX           if not hasattr(node, "id_n"): node.id_n = 0
            #            else: node.id_n += 1
            invokeid = "%s.%s.%s" % (parentId, n, self.invokeid_counter)
            self.invokeid_counter += 1
            if node.get("idlocation"):
                self.dm[node.get("idlocation")] = invokeid
        invtype = self.parseAttr(node, "type", "scxml")
        src = self.parseAttr(node, "src")
        if src and src.startswith("file:"):
            newsrc, search_path = get_path(src.replace("file:", ""), self.dm.self.filedir or "")
            if not newsrc:
                # TODO: add search_path info to this exception.
                raise IOError(2, "File not found when searching the PYTHONPATH: %s" % src)
            src = "file:" + newsrc
        data = self.parseData(node, getContent=False)

        scxmlType = ["http://www.w3.org/TR/scxml", "scxml"]
        if invtype.strip("/") in scxmlType:
            inv = InvokeSCXML(Dict(data))
            contentNode = node.find(prepend_ns("content"))
            if contentNode is not None:
                cnt = self.parseContent(contentNode)
                if isinstance(cnt, str):
                    inv.content = cnt
                elif isinstance(cnt, list):
                    # TODO: if len(cnt) > 0, we could throw exception.
                    if len(cnt) == 0:
                        xml_str = etree.tostring(node, encoding='unicode')
                        raise InvokeError("Line %s: The invoke content is empty." % xml_str)
                    if cnt[0].tag != prepend_ns("scxml"):
                        xml_str = etree.tostring(node, encoding='unicode')
                        raise InvokeError("Line %s: The invoke content is invalid for content: \n%s" %
                                          (xml_str, etree.tostring(cnt[0])))
                    inv.content = etree.tostring(cnt[0])
                elif self.datamodel == "ecmascript" and isinstance(cnt, minidom.Element):  # if cnt is a minidom object
                    inv.content = cnt.toxml()
                else:
                    raise Exception("Error when parsing contentNode, content is %s" % cnt)
        else:
            raise NotImplementedError("The invoke type '%s' is not supported by the platform." % invtype)
        inv.invokeid = invokeid
        inv.parentSessionid = self.dm.sessionid
        inv.src = src
        inv.type = invtype
        inv.default_datamodel = self.default_datamodel

        finalizeNode = node.find(prepend_ns("finalize"))
        if finalizeNode is not None and not len(finalizeNode):
            paramList = node.findall(prepend_ns("param"))
            # XXX namelist = filter(bool, map(lambda x: (x, x), node.get("namelist", "").split(" ")))
            namelist = [(x, x) for x in node.get('namelist', "").split(" ") if x]
            paramMapping = [(param.get("name"), param.get("location")) for param in (p for p in paramList if p.get("location"))]

            def f():
                for name, location in namelist + paramMapping:
                    if name in self.dm["_event"].data:
                        self.dm[location] = self.dm["_event"].data[name]
                    elif len(self.dm["$_event/data/data[@id='%s']" % name]):
                        self.dm[location.lstrip("$")] = self.dm["$_event/data/data[@id='%s']/text()|$_event/data/data[@id='%s']/*" % (name, name)]

            inv.finalize = f
        elif finalizeNode is not None:
            inv.finalize = partial(self.try_execute_content, finalizeNode)

        return inv

    def parseInitial(self, node):
        if node.get("initial"):
            return Initial(node.get("initial").split(" "))
        elif node.find(prepend_ns("initial")) is not None:
            transitionNode = node.find(prepend_ns("initial"))[0]
            assert transitionNode.get("target")
            initial = Initial(transitionNode.get("target").split(" "))
            initial.exe = partial(self.try_execute_content, transitionNode)
            return initial
        else:  # NOTE: has neither initial tag or attribute, so we'll make the first valid state a target instead.
            childNodes = filter(lambda x: x.tag in map(prepend_ns, ["state", "parallel", "final"]), list(node))
            firstChild = next(childNodes, None)
            if firstChild:
                return Initial([firstChild.get("id")])
            return None  # NOTE: leaf nodes have no initial

    def setDatamodel(self, tree):
        def iterdata():
            return (x for x in iterMain(tree) if x.tag == prepend_ns("data"))

        for data in iterdata():
            self.dm[data.get("id")] = None

        top_level = tree.find(prepend_ns("datamodel"))
        # set top-level datamodel element
        if top_level is not None:
            try:
                self.setDataList(top_level)
            except Exception as e:
                self.raiseError("error.execution", e)
        # XXX raise ParseError("Parsing of data tag caused document startup to fail. \n%s" % e)

        if self.doc.binding == "early":
            try:
                top_level = top_level if top_level is not None else []
                # filtering out the top-level data elements
                self.setDataList([data for data in iterdata() if data not in top_level])
            except Exception:
                self.logger.exception("Parsing of a data element failed.")

        for key, value in self.initData.items():
            if key in self.dm:
                self.dm[key] = value

    def setDataList(self, datalist):
        dl_mapping = self.parallelize_download(filter(lambda x: x.get("src"), datalist))
        for node in datalist:
            key = node.get("id")
            value = None

            if node.get("src"):
                try:
                    node.append(etree.fromstring(dl_mapping[node]))
                except Exception:
                    node.text = dl_mapping[node]

                if isinstance(value, Exception):
                    self.logger.error("Data src not found : '%s'. \n\t%s" % (node.get("src"), value))
            if node.get("expr") or len(node) > 0 or node.text:
                try:
                    value = self.parseContent(node)
                except Exception as e:
                    xml_str = etree.tostring(node, encoding='unicode')
                    self.logger.error("Failed to parse data element at line %s:\n%s" % (xml_str, e))
                    self.raiseError("error.execution", e)

            # TODO: should we be overwriting values here? see test 226.
            #            if not self.dm.get(key): self.dm[key] = value
            #            self.dm.setdefault(key, value)
            self.dm[key] = value

    def addDefaultNamespace(self, xmlStr):
        root: etree.Element = etree.fromstring(xmlStr)
        warnmsg = (
            "Your document lacks the correct "
            "default namespace declaration. It has been added for you, for parsing purposes.")

        if "scxml" in root.tag and root.tag != prepend_ns("scxml"):
            self.logger.warn(warnmsg)
            return xmlStr.replace("<scxml", "<scxml xmlns='http://www.w3.org/2005/07/scxml'", 1)

        return xmlStr

    def xml_from_string(self, xmlstr):
        parser = etree.XMLParser()
        tree = etree.XML(xmlstr, parser)
        return tree

    def parallelize_download(self, nodelist):
        def download(node):
            src = node.get("src")
            if src.startswith("file:"):
                src, search_path = get_path(node.get("src").replace("file:", ""))
                if not src:
                    return (node, urllib.error.URLError("File not found: %s" % node.get("src")))
                src = "file:" + src
            try:
                return (node, urllib.request.urlopen(src).read())

            except Exception as e:
                return (node, e)

        output = {}
        for node in nodelist:
            output[node] = download(node)
        return output


def preprocess(tree: etree.ElementTree):
    tree.set("id", "__main__")
    toAppend = []
    for parent in tree.iter():
        for child in parent:
            node_ns, node_tag = split_ns(child)
            if node_ns in preprocess_mapping:
                xmlstr = preprocess_mapping[node_ns](child)
                i = list(parent).index(child)

                newNode = etree.fromstring("<wrapper>%s</wrapper>" % xmlstr)
                for node in newNode:
                    if "{" not in node.tag:
                        node.set("xmlns", ns)
                newNode = etree.fromstring(etree.tostring(newNode))
                toAppend.append((parent, (i, len(newNode)-1), newNode))
    for parent, (i, j), newNode in toAppend:
        parent[i:j] = newNode[:]

    t_items = []
    for n, parent, node in iter_elems(tree):
        node_ns, node_tag = split_ns(node)
        if node_tag in ["state", "parallel", "final", "history"] and not node.get("id"):
            id = parent.get("id") + "_%s_child_%s" % (node_tag, n)
            node.set('id', id)
        t_items.append((n, parent, node))
    return t_items


# TODO: this should be moved to the python datamodel class.
def normalizeExpr(expr):
    return textwrap.dedent(expr)


def iter_elems(tree: etree.ElementTree):
    stack = [(None, tree)]
    n = 0

    while (len(stack) > 0):
        parent, child = stack.pop()
        yield (n, parent, child)
        n += 1
        el: etree.Element
        for el in reversed(child):
            if el.tag in tagsForTraversal:
                stack.append((child, el))


def iterMain(tree: etree.ElementTree):
    '''returns an iterator over this scxml document,
    but not over scxml documents specified inline as a child of content'''
    for child in tree:
        if child.tag != prepend_ns("content"):
            if split_ns(child)[0] == ns:
                yield child
                for sub in iterMain(child):
                    if split_ns(child)[0] == ns:
                        yield sub
