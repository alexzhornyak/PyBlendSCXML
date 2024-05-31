'''
Created on Nov 1, 2011

@author: johan
'''
import sys
import traceback
import re
from xml.etree import ElementTree as etree
# from copy import deepcopy
from .errors import (
    ExecutableError, IllegalLocationError,
    # AttributeEvalError,
    ExprEvalError, DataModelError,
    # AtomicError
)
# import logging
import xml.dom.minidom as minidom


assignOnce = ["_sessionid", "_x", "_name", "_ioprocessors"]
hidden = ["_event"]


def getTraceback():
    tb_list = traceback.extract_tb(sys.exc_info()[2])
    tb_list = [(lineno, fname, text)
               for (filename, lineno, fname, text) in tb_list
               if filename == "<string>" and fname != "<module>"]
    return tb_list


def exceptionFormatter(f):
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            traceback = getTraceback()
            raise ExprEvalError(e, traceback)
    return wrapper


class ImperativeDataModel(object):
    '''A base class for the python and ecmascript datamodels'''

    #    def __init__(self):
    #        self["_x"] = {}

    def assign(self, assignNode):
        if not self.hasLocation(assignNode.get("location")):
            msg = "The location expression '%s' was not instantiated in the datamodel." % assignNode.get("location")
            raise ExecutableError(IllegalLocationError(msg), assignNode)

        # TODO: this should function like the data element.
        #        expression = assignNode.get("expr") or assignNode.text.strip()

        #        try:
        #            #TODO: we might need to make a 'setlocation' method on the dm objects.
        #            self.execExpr(assignNode.get("location") + " = " + expression)
        #        except ExprEvalError, e:
        #            raise ExecutableError(e, assignNode)

        if assignNode.get("expr"):
            self.evalExpr(assignNode.get("location") + "= %s" % assignNode.get("expr"))
        else:
            self[assignNode.get("location")] = self.parseContent(assignNode)
            # XXX    print "assign", val
            #        self[assignNode.get("location")] = self.parseContent(assignNode)
            #        print self[assignNode.get("location")]

    def getInnerXML(self, node):
        return etree.tostring(node).split(">", 1)[1].rsplit("<", 1)[0]

    def normalizeContent(self, contentNode):
        domNode = minidom.parseString(etree.tostring(contentNode)).documentElement

        def f(node):
            if node.nodeType == node.CDATA_SECTION_NODE:
                return node.nodeValue
            else:
                return node.toxml()

        contentStr = " ".join(map(f, domNode.childNodes))

        #        if domNode.nodeType == domNode.CDATA_SECTION_NODE:
        #            return contentNode.text
        #        else:
        return re.sub(r"\s+", " ", contentStr).strip()


class PythonDataModel(dict, ImperativeDataModel):
    '''The default Python Datamodel'''
    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)

    def __setitem__(self, key, val):
        if (key in assignOnce and key in self) or key in hidden or not self.isLegalName(key):
            raise DataModelError("You can't assign to the name '%s'." % key)
        else:
            dict.__setitem__(self, key, val)

    def __getitem__(self, key):
        # NOTE: raises keyerror
        if key in hidden:
            return dict.__getitem__(self, "_" + key)
        return dict.__getitem__(self, key)

    def hasLocation(self, location):
        try:
            eval(location, self)
            return True
        except Exception:
            return False

    def isLegalName(self, name):
        # TODO: what about reserved names?
        return bool(re.match("[a-zA-Z_][0-9a-zA-Z_]*", name))

    def assign(self, assignNode):
        if not self.hasLocation(assignNode.get("location")):
            msg = "The location expression '%s' was not instantiated in the datamodel." % assignNode.get("location")
            raise ExecutableError(IllegalLocationError(msg), assignNode)

        self[assignNode.get("location")] = self.parseContent(assignNode)

    def parseContent(self, contentNode):
        output = None

        if contentNode is not None:
            if contentNode.get("expr"):
                s_expr = contentNode.get("expr")
                output = self.evalExpr(f"({s_expr})")
            elif len(contentNode) == 0:
                # XXX output = contentNode.xpath("./text()")
                output = self.normalizeContent(contentNode)
            elif len(contentNode) > 0:
                output = contentNode.xpath("./*")
            else:
                xml_str = etree.tostring(contentNode, encoding='unicode')
                self.logger.error("Line %s: error when parsing content node." % xml_str)
                return
        return output

    @exceptionFormatter
    def evalExpr(self, expr):
        return eval(expr, self)

    @exceptionFormatter
    def execExpr(self, expr):
        exec(expr, self)
