from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ResearchItem:
    title: str
    url: str
    summary: str
    published: str
    source: str  # "arxiv" | "rss"


def fetch_feed(url: str) -> list[ResearchItem]:
    """Fetch an arxiv Atom feed or RSS feed and return normalised items.

    Requires the ``research`` extra: ``pip install agentctx[research]``
    """
    try:
        import feedparser
    except ImportError:
        raise ImportError(
            "The 'feedparser' package is required. "
            "Install it with: pip install agentctx[research]"
        ) from None

    feed = feedparser.parse(url)
    items: list[ResearchItem] = []
    for entry in feed.entries:
        link = _first_link(entry)
        summary = _clean_html(
            getattr(entry, "summary", "")
            or getattr(entry, "description", "")
        )[:1_200]
        published = (
            getattr(entry, "published", "")
            or getattr(entry, "updated", "")
        )
        source = "arxiv" if "arxiv.org" in url else "rss"
        title = getattr(entry, "title", "").strip()
        if title and link:
            items.append(ResearchItem(
                title=title,
                url=link,
                summary=summary,
                published=published,
                source=source,
            ))
    return items


def item_key(item: ResearchItem) -> str:
    """Return a stable deduplication key for an item."""
    if "arxiv.org" in item.url:
        m = re.search(r"arxiv\.org/abs/([\d.]+)", item.url)
        if m:
            return f"arxiv:{m.group(1)}"
    return item.url


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_link(entry) -> str:
    link = getattr(entry, "link", "")
    if link:
        return link
    links = getattr(entry, "links", [])
    return links[0].href if links else ""


def _clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()
