"""Exception types raised by structquery.

``IndriError``        any failure reported by the Indri engine (subclass of RuntimeError).
``QuerySyntaxError``  the query string is not valid Indri query language (subclass of IndriError).
"""
from ._structquery import IndriError, QuerySyntaxError

__all__ = ["IndriError", "QuerySyntaxError"]
