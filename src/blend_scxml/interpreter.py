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
    along with PySCXML.  If not, see <http://www.gnu.org/licenses/>.

    This is an implementation of the interpreter algorithm described in the W3C standard document,
    which can be found at:

    http://www.w3.org/TR/2009/WD-scxml-20091029/

    @author Johan Roxendal
    @contact: johan@roxendal.com
'''

# NOTE: modified by Alex Zhornyak, alexander.zhornyak@gmail.com

import queue
import logging

from .node import (
    Final,
    History,
    Parallel,
    State,
    SCXMLNode,
    SCXMLDocument,
    Transition
)

from .datastructures import OrderedSet
from .eventprocessor import Event, ScxmlOriginType

# author="Patrick K. O'Brien and contributors",
# url="https://github.com/11craft/louie/",
# download_url="https://pypi.python.org/pypi/Louie",
# license="BSD"
from .louie import dispatcher
from .consts import DispatcherConstants


class Interpreter(object):
    '''
    The class repsonsible for keeping track of the execution of the
    statemachine.
    '''
    def __init__(self):
        self.running = True
        self.exited = False
        self.cancelled = False
        self.configuration = OrderedSet()

        self.sleep_timeout = 0.001
        self.internalQueue = queue.Queue()
        self.externalQueue = queue.Queue()
        self.externalQueueGuard = False

        self.statesToInvoke = OrderedSet()
        self.historyValue = {}
        self.dm = None
        self.invokeId = None
        self.parentId = None
        self.logger: logging.Logger = None

        self.enabledTransitions = None

    def interpret(self, document: SCXMLDocument, invokeId=None):
        '''Initializes the interpreter given an SCXMLDocument instance'''

        self.doc = document
        self.invokeId = invokeId

        transition = Transition(document.rootState)
        transition.target = document.rootState.initial
        transition.exe = document.rootState.initial.exe

        self.executeTransitionContent([transition])
        self.enterStates([transition])

    def mainEventLoop(self):
        if self.running:
            if not self.externalQueueGuard:
                self.enabledTransitions = None
                stable = False

                # now take any newly enabled null transitions and any transitions triggered by internal events
                while self.running and not stable:
                    self.enabledTransitions = self.selectEventlessTransitions()
                    if not self.enabledTransitions:
                        if self.internalQueue.empty():
                            stable = True
                        else:
                            internalEvent: Event = self.internalQueue.get()  # this call returns immediately if no event is available

                            dispatcher.send(DispatcherConstants.internal_event, self, event=internalEvent)

                            self.dm["__event"] = internalEvent
                            self.enabledTransitions = self.selectTransitions(internalEvent)

                    if self.enabledTransitions:
                        self.microstep(self.enabledTransitions)

                for state in self.statesToInvoke:
                    for inv in state.invoke:
                        inv.invoke(inv)
                self.statesToInvoke.clear()

                if not self.internalQueue.empty():
                    return self.sleep_timeout

            if self.externalQueue.empty():
                self.externalQueueGuard = True
                return self.sleep_timeout
            else:
                self.externalQueueGuard = False
                externalEvent: Event = self.externalQueue.get()  # this call blocks until an event is available

            # our parent session also might cancel us.  The mechanism for this is platform specific,
            if isCancelEvent(externalEvent):
                self.running = False
                return self.sleep_timeout

            dispatcher.send(DispatcherConstants.external_event, self, event=externalEvent)

            self.dm["__event"] = externalEvent

            for state in self.configuration:
                for inv in state.invoke:
                    if inv.invokeid == externalEvent.invokeid:  # event is the result of an <invoke> in this state
                        self.applyFinalize(inv, externalEvent)
                    if inv.autoforward:
                        inv.send(externalEvent)

            self.enabledTransitions = self.selectTransitions(externalEvent)
            if self.enabledTransitions:
                self.microstep(self.enabledTransitions)

            return self.sleep_timeout
        else:
            # if we get here, we have reached a top-level final state or some external entity has set running to False
            self.exitInterpreter()

    def exitInterpreter(self):
        statesToExit = sorted(self.configuration, key=exitOrder)
        for s in statesToExit:
            for content in s.onexit:
                self.executeContent(content)
            for inv in s.invoke:
                self.cancelInvoke(inv)
            self.configuration.delete(s)
            dispatcher.send(DispatcherConstants.exit_state, self, state=s.id)
            if isFinalState(s) and isScxmlState(s.parent):
                if self.invokeId and self.parentId and self.parentId in self.dm.sessions:
                    self.send(
                        [
                            "done", "invoke", self.invokeId
                        ],
                        s.donedata(), self.invokeId, self.dm.sessions[self.parentId].interpreter.externalQueue)
                dispatcher.send(DispatcherConstants.exit, self, final=s.id)
                self.exited = True
                return
        self.exited = True
        dispatcher.send(DispatcherConstants.exit, self, final=None)

    def selectEventlessTransitions(self):
        enabledTransitions = OrderedSet()
        atomicStates = filter(isAtomicState, self.configuration)
        atomicStates = sorted(atomicStates, key=documentOrder)
        for state in atomicStates:
            done = False
            for s in [state] + getProperAncestors(state, None):
                if done:
                    break
                for t in s.transition:
                    if not t.event and self.conditionMatch(t):
                        enabledTransitions.add(t)
                        done = True
                        break
        # NOTE: enabled alghorithm passes 'test405', but second fails
        filteredTransitions1 = self.filterPreempted(enabledTransitions)
        # filteredTransitions2 = self.removeConflictingTransitions(enabledTransitions)
        return filteredTransitions1

    def selectTransitions(self, event):
        enabledTransitions = OrderedSet()
        atomicStates = filter(isAtomicState, self.configuration)
        atomicStates = sorted(atomicStates, key=documentOrder)

        for state in atomicStates:
            done = False
            for s in [state] + getProperAncestors(state, None):
                if done:
                    break
                for t in s.transition:
                    if t.event and nameMatch(t.event, event.name.split(".")) and self.conditionMatch(t):
                        enabledTransitions.add(t)
                        done = True
                        break

        # NOTE: enabled alghorithm passes 'test403c', but second fails
        # filteredTransitions1 = self.filterPreempted(enabledTransitions)
        filteredTransitions2 = self.removeConflictingTransitions(enabledTransitions)
        return filteredTransitions2

    def getEffectiveTargetStates(self, transition):
        targets = OrderedSet()
        for s in transition.target:
            if isHistoryState(s):
                if s.id in self.historyValue:
                    for elem in self.historyValue[s.id]:
                        targets.add(elem)
                else:
                    for elem in self.getEffectiveTargetStates(s.transition):
                        targets.add(elem)
            else:
                targets.add(s)
        return targets

    def getTransitionDomain(self, t):
        tstates = self.getEffectiveTargetStates(t)
        if not tstates:
            return None
        elif t.type == "internal" and isCompoundState(t.source) and all(isDescendant(s, t.source) for s in tstates):
            return t.source
        else:
            return self.findLCCA([t.source] + tstates)

    def computeExitSet(self, transitions):
        statesToExit = OrderedSet()
        for t in transitions:
            if t.target:
                domain = self.getTransitionDomain(t)
                for s in self.configuration:
                    if isDescendant(s, domain):
                        statesToExit.add(s)
        return statesToExit

    def removeConflictingTransitions(self, enabledTransitions):
        filteredTransitions = OrderedSet()
        # //toList sorts the transitions in the order of the states that selected them
        for t1 in enabledTransitions:
            t1Preempted = False
            transitionsToRemove = OrderedSet()
            for t2 in filteredTransitions:
                if set(self.computeExitSet([t1])).intersection(self.computeExitSet([t2])):
                    if isDescendant(t1.source, t2.source):
                        transitionsToRemove.add(t2)
                    else:
                        t1Preempted = True
                        break
            if not t1Preempted:
                for t3 in transitionsToRemove:
                    filteredTransitions.delete(t3)
                filteredTransitions.add(t1)

        return filteredTransitions

    def preemptsTransition(self, t, t2):

        if self.isType1(t):
            return False
        elif self.isType2(t) and self.isType3(t2):
            return True
        elif self.isType3(t):
            return True

        return False

    def findLCPA(self, states):
        '''
        Gets the least common parallel ancestor of states.
        Just like findLCCA but only for parallel states.
        '''
        for anc in filter(isParallelState, getProperAncestors(states[0], None)):
            if all(map(lambda s: isDescendant(s, anc), states[1:])):
                return anc

    def isType1(self, t):
        return not t.target

    def isType2(self, t):
        source = t.source if t.type == "internal" else t.source.parent
        p = self.findLCPA([source] + self.getTargetStates(t.target))
        return p is not None

    def isType3(self, t):
        return not self.isType2(t) and not self.isType1(t)

    def filterPreempted(self, enabledTransitions):
        filteredTransitions = []
        for t in enabledTransitions:
            # does any t2 in filteredTransitions preempt t? if not, add t to filteredTransitions
            if not any(map(lambda t2: self.preemptsTransition(t2, t), filteredTransitions)):
                filteredTransitions.append(t)

        return OrderedSet(filteredTransitions)

    def getConfigurationIDs(self):
        return [s.id for s in self.configuration if s.id != "__main__"]

    def microstep(self, enabledTransitions):
        self.exitStates(enabledTransitions)
        self.executeTransitionContent(enabledTransitions)
        self.enterStates(enabledTransitions)
        dispatcher.send(DispatcherConstants.new_configuration, self)

    def exitStates(self, enabledTransitions):
        statesToExit = OrderedSet()
        for t in enabledTransitions:
            if t.target:
                tstates = self.getTargetStates(t.target)
                if t.type == "internal" and isCompoundState(t.source) and all(map(lambda s: isDescendant(s, t.source), tstates)):
                    ancestor = t.source
                else:
                    ancestor = self.findLCCA([t.source] + tstates)

                for s in self.configuration:
                    if isDescendant(s, ancestor):
                        statesToExit.add(s)

        for s in statesToExit:
            self.statesToInvoke.delete(s)

        statesToExit.sort(key=exitOrder)

        for s in statesToExit:
            for h in s.history:
                if h.type == "deep":
                    def f(s0):
                        return isAtomicState(s0) and isDescendant(s0, s)
                else:
                    def f(s0):
                        return s0.parent == s
                self.historyValue[h.id] = list(filter(f, self.configuration))
        for s in statesToExit:
            for content in s.onexit:
                self.executeContent(content)
            for inv in s.invoke:
                self.cancelInvoke(inv)
            self.configuration.delete(s)
            dispatcher.send(DispatcherConstants.exit_state, self, state=s.id)

    def cancelInvoke(self, inv):
        inv.cancel()

    def executeTransitionContent(self, enabledTransitions):
        for t in enabledTransitions:
            try:
                transition_index = t.source.transition.index(t)
                dispatcher.send(DispatcherConstants.taking_transition, self, state=t.source.id, transition_index=transition_index)
            except Exception:
                # NOTE: just fast skip by exception if scxml is not identified, etc.
                pass
            self.executeContent(t)

    def enterStates(self, enabledTransitions):
        statesToEnter = OrderedSet()
        statesForDefaultEntry = OrderedSet()
        defaultHistoryContent = {}  # NOTE: 'test579'
        for t in enabledTransitions:
            if t.target:
                tstates = self.getTargetStates(t.target)
                if t.type == "internal" and isCompoundState(t.source) and all(map(lambda s: isDescendant(s, t.source), tstates)):
                    ancestor = t.source
                else:
                    ancestor = self.findLCCA([t.source] + tstates)
                for s in tstates:
                    self.addStatesToEnter(s, statesToEnter, statesForDefaultEntry, defaultHistoryContent)
                for s in tstates:
                    for anc in getProperAncestors(s, ancestor):
                        statesToEnter.add(anc)
                        if isParallelState(anc):
                            for child in getChildStates(anc):
                                if not any(map(lambda s: isDescendant(s, child), statesToEnter)):
                                    self.addStatesToEnter(child, statesToEnter, statesForDefaultEntry, defaultHistoryContent)

        statesToEnter.sort(key=enterOrder)
        for s in statesToEnter:
            self.statesToInvoke.add(s)
            self.configuration.add(s)
            if self.doc.binding == "late" and s.isFirstEntry:
                s.initDatamodel()
                s.isFirstEntry = False

            dispatcher.send(DispatcherConstants.enter_state, self, state=s.id)

            for content in s.onentry:
                self.executeContent(content)
            if s in statesForDefaultEntry:
                self.executeContent(s.initial)
            # NOTE: 'test579'
            p_content = defaultHistoryContent.get(s.id, None)
            if p_content is not None:
                self.executeContent(p_content)
            if isFinalState(s):
                parent = s.parent
                grandparent = parent.parent
                self.internalQueue.put(Event(["done", "state", parent.id], s.donedata()))
                if isParallelState(grandparent):
                    if all(map(self.isInFinalState, getChildStates(grandparent))):
                        self.internalQueue.put(Event(["done", "state", grandparent.id]))
        for s in self.configuration:
            if isFinalState(s) and isScxmlState(s.parent):
                self.running = False

    def addStatesToEnter(self, state, statesToEnter, statesForDefaultEntry, defaultHistoryContent):
        if isHistoryState(state):
            if state.id in self.historyValue:
                for s in self.historyValue[state.id]:
                    self.addStatesToEnter(s, statesToEnter, statesForDefaultEntry, defaultHistoryContent)
                    for anc in getProperAncestors(s, state):
                        statesToEnter.add(anc)
            else:
                for t in state.transition:
                    for s in self.getTargetStates(t.target):
                        defaultHistoryContent[s.parent.id] = t
                        self.addStatesToEnter(s, statesToEnter, statesForDefaultEntry, defaultHistoryContent)
        else:
            statesToEnter.add(state)
            if isCompoundState(state):
                statesForDefaultEntry.add(state)
                for s in self.getTargetStates(state.initial):
                    self.addStatesToEnter(s, statesToEnter, statesForDefaultEntry, defaultHistoryContent)
            elif isParallelState(state):
                for s in getChildStates(state):
                    self.addStatesToEnter(s, statesToEnter, statesForDefaultEntry, defaultHistoryContent)

    def isInFinalState(self, s):
        if isCompoundState(s):
            return any(map(lambda s: isFinalState(s) and s in self.configuration, getChildStates(s)))
        elif isParallelState(s):
            return all(map(self.isInFinalState, getChildStates(s)))
        else:
            return False

    def findLCCA(self, stateList):
        for anc in filter(isCompoundState, getProperAncestors(stateList[0], None)):
            if all(map(lambda s: isDescendant(s, anc), stateList[1:])):
                return anc

    def applyFinalize(self, inv, event):
        inv.finalize()

    def getTargetStates(self, targetIds):
        if targetIds is None:
            pass
        states = []
        for id in targetIds:
            state = self.doc.getState(id)
            if not state:
                raise Exception("The target state '%s' does not exist" % id)
            states.append(state)
        return states

    def executeContent(self, obj):
        if hasattr(obj, "exe") and callable(obj.exe):
            obj.exe()

    def conditionMatch(self, t):
        if not t.cond:
            return True
        else:
            return t.cond()

    def In(self, name):
        return name in map(lambda x: x.id, self.configuration)

    def send(self, name, data=None, invokeid=None, toQueue=None, sendid=None, eventtype="platform", raw=None, language=None):
        """Send an event to the statemachine
        @param name: a dot delimited string, the event name
        @param data: the data associated with the event
        @param invokeid: if specified, the id of sending invoked process
        @param toQueue: if specified, the target queue on which to add the event

        """
        if isinstance(name, str):
            name = name.split(".")
        if not toQueue:
            toQueue = self.externalQueue
        evt = Event(name, data, invokeid, sendid=sendid, eventtype=eventtype)
        evt.origin = "#_scxml_" + self.dm.sessionid
        evt.origintype = ScxmlOriginType()
        evt.raw = raw
        # TODO: and for ecmascript?
        evt.language = language
        toQueue.put(evt)

    def raiseFunction(self, event, data, sendid=None, type="internal"):
        e = Event(event, data, eventtype=type, sendid=sendid)
        e.origintype = None
        self.internalQueue.put(e)


def getProperAncestors(state, root):
    ancestors = []
    while hasattr(state, 'parent') and state.parent and state.parent != root:
        state = state.parent
        ancestors.append(state)
    return ancestors


def isDescendant(state1, state2):
    while hasattr(state1, 'parent'):
        state1 = state1.parent
        if state1 == state2:
            return True
    return False


def getChildStates(state):
    return state.state + state.final + state.history


def nameMatch(eventList, event):
    t_events = list(eventList)
    if ["*"] in t_events:
        return True

    def prefixList(l1, l2):
        if len(l1) > len(l2):
            return False
        for tup in zip(l1, l2):
            if tup[0] != tup[1]:
                return False
        return True

    for elem in t_events:
        if prefixList(elem, event):
            return True
    return False

# #
# # Various tests for states
# #


def isParallelState(s):
    return isinstance(s, Parallel)


def isFinalState(s):
    return isinstance(s, Final)


def isHistoryState(s):
    return isinstance(s, History)


def isScxmlState(s):
    return s.parent is None


def isAtomicState(s):
    return isinstance(s, Final) or (isinstance(s, SCXMLNode) and s.state == [] and s.final == [])


def isCompoundState(s):
    return (isinstance(s, State) and (s.state != [] or s.final != [])) or s.parent is None  # include root state


def enterOrder(s):
    return s.n


def exitOrder(s):
    return 0 - s.n


def documentOrder(s):
    key = [s.n]
    p = s.parent
    while p.n:
        key.append(p.n)
        p = p.parent
    key.reverse()
    return key


class CancelEvent(object):
    pass


def isCancelEvent(evt):
    return isinstance(evt, CancelEvent)
