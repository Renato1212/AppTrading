"""Minimal, dependency-free RSS / Atom feed parser (stdlib only).

We deliberately avoid third-party feed libraries: this keeps the deploy
footprint small and dodges fragile legacy SGML dependencies. It handles the
~95% of real-world financial RSS 2.0 and Atom feeds we care about: titles,
links, summaries, and publish dates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NS_RE = re.compile(r"\{[^}]+\}")

# common namespaced extras some feeds expose
_SLASH_NS = "{http://purl.org/rss/1.0/modules/slash/}comments"


@dataclass
class FeedEntry:
    title: str
    summary: str
    link: str
    published: str | None
    views: int | None = None


def strip_html(text: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", text or "")).strip()


def _localname(tag: str) -> str:
    return _NS_RE.sub("", tag)


def _find_text(elem, names: set[str]) -> str:
    for child in elem:
        if _localname(child.tag) in names and child.text:
            return child.text.strip()
    return ""


def _find_link(elem) -> str:
    # RSS: <link>url</link>  |  Atom: <link href="url" rel="alternate"/>
    fallback = ""
    for child in elem:
        if _localname(child.tag) != "link":
            continue
        href = child.get("href")
        if href:
            rel = child.get("rel", "alternate")
            if rel == "alternate":
                return href.strip()
            fallback = fallback or href.strip()
        elif child.text:
            return child.text.strip()
    return fallback


def _find_views(elem) -> int | None:
    for child in elem:
        if child.tag == _SLASH_NS and child.text:
            try:
                return int(child.text.strip())
            except ValueError:
                return None
    return None


def parse(content: bytes) -> list[FeedEntry]:
    """Parse raw feed bytes into a list of entries. Never raises."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    entries: list[FeedEntry] = []
    # RSS items live under channel/item; Atom entries are <entry> at top level.
    items = root.iter()
    for elem in items:
        name = _localname(elem.tag)
        if name not in ("item", "entry"):
            continue
        title = _find_text(elem, {"title"})
        if not title:
            continue
        summary_raw = _find_text(elem, {"description", "summary", "content"})
        link = _find_link(elem)
        if not link:
            continue
        published = _find_text(elem, {"pubDate", "published", "updated", "date"}) or None
        entries.append(
            FeedEntry(
                title=strip_html(title),
                summary=strip_html(summary_raw),
                link=link,
                published=published,
                views=_find_views(elem),
            )
        )
    return entries
