"""
    author="Patrick K. O'Brien and contributors",
    url="https://github.com/11craft/louie/",
    download_url="https://pypi.python.org/pypi/Louie",
    license="BSD"
"""

"""Signal class.

This class is provided as a way to consistently define and document
signal types.  Signal classes also have a useful string
representation.

Louie does not require you to use a subclass of Signal for signals.
"""


class _SIGNAL(type):
    """Base metaclass for signal classes."""

    def __str__(cls):
        return f"<Signal: {cls.__name__}>"


class Signal(object, metaclass=_SIGNAL):
    pass


class All(Signal):
    """Used to represent 'all signals'.

    The All class can be used with connect, disconnect, send, or
    sendExact to denote that the signal should react to all signals,
    not just a particular signal.
    """
