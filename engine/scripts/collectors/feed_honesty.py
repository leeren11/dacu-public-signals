"""Decide whether a saved body is a feed, a login wall, or unusable.

HTTP 200 is not evidence of an empty discussion. An HTML welcome page is
auth_wall or html_not_feed, and that result is missing rather than zero.
"""

from __future__ import annotations

import re

_FEED_ROOT = re.compile(
    r"<(?:\w+:)?feed\b|<(?:\w+:)?rss\b",
    re.IGNORECASE,
)
_HTML_START = re.compile(r"<!doctype\s+html\b|<html\b", re.IGNORECASE)
_LOGIN = ("welcome to reddit", "log in to use old reddit", "accounts are required to access old reddit")


def _head(body: str, limit: int = 4000) -> str:
    return (body or "")[:limit].lower()


def has_feed_root(body: str) -> bool:
    return bool(_FEED_ROOT.search(body or ""))


def classify_document(body: str, content_type: str | None = None) -> str:
    text = body or ""
    stripped = text.lstrip()
    head = _head(text)
    ctype = (content_type or "").lower()
    htmlish = bool(_HTML_START.search(head)) or "text/html" in ctype
    if htmlish and not stripped.startswith("<?xml"):
        if any(phrase in head for phrase in _LOGIN):
            return "auth_wall"
        if not has_feed_root(text):
            return "html_not_feed"
    if "<!doctype" in head and "feed" not in head[:200] and not stripped.startswith("<?xml"):
        if any(phrase in head for phrase in _LOGIN):
            return "auth_wall"
        return "html_not_feed"
    if stripped.startswith("<?xml") or has_feed_root(text):
        if re.search(r"<(?:\w+:)?feed\b", text, re.IGNORECASE):
            return "atom"
        if re.search(r"<(?:\w+:)?rss\b", text, re.IGNORECASE):
            return "rss"
        return "xml_not_feed"
    if "<!entity" in head or "<!doctype" in head:
        return "invalid_xml"
    if stripped.startswith("{") or stripped.startswith("["):
        return "json"
    if not stripped:
        return "empty_body"
    return "unrecognized"
