"""
    author="Patrick K. O'Brien and contributors",
    url="https://github.com/11craft/louie/",
    download_url="https://pypi.python.org/pypi/Louie",
    license="BSD"
"""

"""Sender classes."""


class _SENDER(type):
    """Base metaclass for sender classes."""

    def __str__(cls):
        return f"<Sender: {cls.__name__}>"


class Any(object, metaclass=_SENDER):
    """Used to represent either 'any sender'.

    The Any class can be used with connect, disconnect, send, or
    sendExact to denote that the sender paramater should react to any
    sender, not just a particular sender.
    """


class Anonymous(object, metaclass=_SENDER):
    """Singleton used to signal 'anonymous sender'.

    The Anonymous class is used to signal that the sender of a message
    is not specified (as distinct from being 'any sender').
    Registering callbacks for Anonymous will only receive messages
    sent without senders.  Sending with anonymous will only send
    messages to those receivers registered for Any or Anonymous.

    Note: The default sender for connect is Any, while the default
    sender for send is Anonymous.  This has the effect that if you do
    not specify any senders in either function then all messages are
    routed as though there was a single sender (Anonymous) being used
    everywhere.
    """
