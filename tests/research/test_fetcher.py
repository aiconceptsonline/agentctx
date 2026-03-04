"""Tests for agentctx.research.fetcher.

fetch_feed() requires feedparser, which is in the [research] extra.
We test the pure logic (item_key, _clean_html) directly and use a mock
to avoid network calls in fetch_feed().
"""
from unittest.mock import MagicMock, patch

import pytest

from agentctx.research.fetcher import ResearchItem, item_key, _clean_html


# ---------------------------------------------------------------------------
# ResearchItem
# ---------------------------------------------------------------------------

class TestResearchItem:
    def test_fields_accessible(self):
        item = ResearchItem(
            title="My Paper",
            url="https://arxiv.org/abs/2401.00001",
            summary="A summary",
            published="2024-01-01",
            source="arxiv",
        )
        assert item.title == "My Paper"
        assert item.source == "arxiv"


# ---------------------------------------------------------------------------
# item_key()
# ---------------------------------------------------------------------------

class TestItemKey:
    def test_arxiv_url_returns_arxiv_prefix(self):
        item = ResearchItem(
            title="t", url="https://arxiv.org/abs/2401.00001",
            summary="", published="", source="arxiv",
        )
        assert item_key(item) == "arxiv:2401.00001"

    def test_non_arxiv_url_returned_as_is(self):
        url = "https://martinfowler.com/articles/agent-memory.html"
        item = ResearchItem(title="t", url=url, summary="", published="", source="rss")
        assert item_key(item) == url

    def test_arxiv_url_with_version_stripped(self):
        # arxiv IDs don't usually include 'v1' in /abs/ links, but key captures
        # the numeric group properly regardless of trailing path segments
        item = ResearchItem(
            title="t", url="https://arxiv.org/abs/2312.09876",
            summary="", published="", source="arxiv",
        )
        assert item_key(item) == "arxiv:2312.09876"

    def test_arxiv_url_with_old_format(self):
        # Old arxiv IDs like cs.AI/0612026 won't match the regex → fall back to URL
        url = "https://arxiv.org/abs/cs.AI/0612026"
        item = ResearchItem(title="t", url=url, summary="", published="", source="arxiv")
        # No numeric-only group → falls back to URL
        assert item_key(item) == url


# ---------------------------------------------------------------------------
# _clean_html()
# ---------------------------------------------------------------------------

class TestCleanHtml:
    def test_strips_simple_tags(self):
        assert _clean_html("<b>bold</b>") == "bold"

    def test_strips_nested_tags(self):
        assert _clean_html("<p><em>text</em></p>") == "text"

    def test_strips_tags_with_attributes(self):
        assert _clean_html('<a href="http://x.com">link</a>') == "link"

    def test_plain_text_unchanged(self):
        assert _clean_html("plain text") == "plain text"

    def test_empty_string(self):
        assert _clean_html("") == ""

    def test_strips_whitespace_around_result(self):
        assert _clean_html("  <b> hello </b>  ") == "hello"


# ---------------------------------------------------------------------------
# fetch_feed() — mocked feedparser
# ---------------------------------------------------------------------------

def _make_entry(title: str, link: str, summary: str = "", updated: str = "") -> MagicMock:
    entry = MagicMock()
    entry.title = title
    entry.link = link
    entry.links = []
    entry.summary = summary
    entry.description = ""
    entry.published = ""
    entry.updated = updated
    return entry


class TestFetchFeed:
    def test_missing_feedparser_raises_import_error(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "feedparser", None)
        # Re-import after monkeypatch so the lazy import branch is hit
        import importlib
        import agentctx.research.fetcher as fetcher_mod
        importlib.reload(fetcher_mod)
        with pytest.raises(ImportError, match="feedparser"):
            fetcher_mod.fetch_feed("http://example.com/feed")
        # Reload again to restore for other tests
        importlib.reload(fetcher_mod)

    def test_returns_research_items(self):
        fake_feed = MagicMock()
        fake_feed.entries = [
            _make_entry("Paper One", "https://arxiv.org/abs/2401.00001", "Summary one"),
        ]
        with patch("feedparser.parse", return_value=fake_feed):
            from agentctx.research.fetcher import fetch_feed
            items = fetch_feed("https://export.arxiv.org/api/query?search_query=test")
        assert len(items) == 1
        assert items[0].title == "Paper One"

    def test_sets_source_arxiv_for_arxiv_url(self):
        fake_feed = MagicMock()
        fake_feed.entries = [
            _make_entry("P", "https://arxiv.org/abs/2401.00001"),
        ]
        with patch("feedparser.parse", return_value=fake_feed):
            from agentctx.research.fetcher import fetch_feed
            items = fetch_feed("https://export.arxiv.org/api/query?x=1")
        assert items[0].source == "arxiv"

    def test_sets_source_rss_for_non_arxiv_url(self):
        fake_feed = MagicMock()
        fake_feed.entries = [
            _make_entry("Post", "https://martinfowler.com/articles/foo.html"),
        ]
        with patch("feedparser.parse", return_value=fake_feed):
            from agentctx.research.fetcher import fetch_feed
            items = fetch_feed("https://martinfowler.com/feed.atom")
        assert items[0].source == "rss"

    def test_skips_entries_with_no_title(self):
        fake_feed = MagicMock()
        entry = _make_entry("", "https://example.com/post")
        fake_feed.entries = [entry]
        with patch("feedparser.parse", return_value=fake_feed):
            from agentctx.research.fetcher import fetch_feed
            items = fetch_feed("https://example.com/feed")
        assert items == []

    def test_skips_entries_with_no_link(self):
        fake_feed = MagicMock()
        entry = MagicMock()
        entry.title = "Title"
        entry.link = ""
        entry.links = []
        entry.summary = ""
        entry.description = ""
        entry.published = ""
        entry.updated = ""
        fake_feed.entries = [entry]
        with patch("feedparser.parse", return_value=fake_feed):
            from agentctx.research.fetcher import fetch_feed
            items = fetch_feed("https://example.com/feed")
        assert items == []

    def test_summary_truncated_to_1200_chars(self):
        fake_feed = MagicMock()
        fake_feed.entries = [
            _make_entry("P", "https://arxiv.org/abs/2401.00001", "x" * 2000),
        ]
        with patch("feedparser.parse", return_value=fake_feed):
            from agentctx.research.fetcher import fetch_feed
            items = fetch_feed("https://export.arxiv.org/api/query?x=1")
        assert len(items[0].summary) <= 1200

    def test_strips_html_from_summary(self):
        fake_feed = MagicMock()
        fake_feed.entries = [
            _make_entry("P", "https://arxiv.org/abs/2401.00001", "<b>bold summary</b>"),
        ]
        with patch("feedparser.parse", return_value=fake_feed):
            from agentctx.research.fetcher import fetch_feed
            items = fetch_feed("https://export.arxiv.org/api/query?x=1")
        assert "<b>" not in items[0].summary
        assert "bold summary" in items[0].summary

    def test_uses_updated_when_published_absent(self):
        fake_feed = MagicMock()
        entry = MagicMock()
        entry.title = "P"
        entry.link = "https://arxiv.org/abs/2401.00001"
        entry.links = []
        entry.summary = ""
        entry.description = ""
        entry.published = ""
        entry.updated = "2024-01-15"
        fake_feed.entries = [entry]
        with patch("feedparser.parse", return_value=fake_feed):
            from agentctx.research.fetcher import fetch_feed
            items = fetch_feed("https://export.arxiv.org/api/query?x=1")
        assert items[0].published == "2024-01-15"
