"""
    author="Patrick K. O'Brien and contributors",
    url="https://github.com/11craft/louie/",
    download_url="https://pypi.python.org/pypi/Louie",
    license="BSD"
"""

"""Error types for Louie."""


class LouieError(Exception):
    """Base class for all Louie errors"""


class DispatcherError(LouieError):
    """Base class for all Dispatcher errors"""


class DispatcherKeyError(KeyError, DispatcherError):
    """Error raised when unknown (sender, signal) specified"""


class DispatcherTypeError(TypeError, DispatcherError):
    """Error raised when inappropriate signal-type specified (None)"""


class PluginTypeError(TypeError, LouieError):
    """Error raise when trying to install more than one plugin of a
    certain type."""
