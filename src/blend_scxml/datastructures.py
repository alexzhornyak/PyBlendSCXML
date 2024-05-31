'''
Created on Jan 4, 2010

@author: johan
'''
from functools import reduce


class Nodeset(list):
    def toXML(self):
        def f(x, y):
            return str(x) + "\n" + str(y)
        return reduce(f, self, "")


class OrderedSet(list):
    def delete(self, elem):
        try:
            self.remove(elem)
        except ValueError:
            pass

    def member(self, elem):
        return elem in self

    def isEmpty(self):
        return len(self) == 0

    def add(self, elem):
        if elem not in self:
            self.append(elem)

    def clear(self):
        self.__init__()
