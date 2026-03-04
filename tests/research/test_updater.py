"""Tests for agentctx.research.updater."""
import json
from datetime import date
from pathlib import Path

import pytest

from agentctx.research.fetcher import ResearchItem
from agentctx.research.evaluator import ExtractionResult
from agentctx.research.updater import (
    load_seen,
    save_seen,
    update_lessons,
    update_prd,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(title="Paper A", url="https://arxiv.org/abs/2401.00001") -> ResearchItem:
    return ResearchItem(title=title, url=url, summary="Summary", published="2024-01-01", source="arxiv")


def _make_ext(prd_entry="PRD text.", implications=None, lessons=None) -> ExtractionResult:
    return ExtractionResult(
        key_findings=["Finding"],
        agentctx_implications=implications or ["Impl A"],
        prd_entry=prd_entry,
        lessons=lessons or [],
    )


_PRD_TEMPLATE = """\
## §10 Research Changelog

New entries go at the top.

---

### 2026-02-24 — Phase 1 complete

Some existing content.
"""


# ---------------------------------------------------------------------------
# load_seen / save_seen
# ---------------------------------------------------------------------------

class TestSeenPersistence:
    def test_load_seen_returns_empty_set_when_file_absent(self, tmp_path):
        result = load_seen(tmp_path / "seen.json")
        assert result == set()

    def test_save_then_load_roundtrips_set(self, tmp_path):
        path = tmp_path / "seen.json"
        seen = {"arxiv:2401.00001", "https://example.com/post"}
        save_seen(path, seen)
        loaded = load_seen(path)
        assert loaded == seen

    def test_save_creates_parent_directories(self, tmp_path):
        path = tmp_path / "research" / "seen.json"
        save_seen(path, {"key1"})
        assert path.exists()

    def test_save_produces_sorted_json(self, tmp_path):
        path = tmp_path / "seen.json"
        save_seen(path, {"b", "a", "c"})
        data = json.loads(path.read_text())
        assert data == ["a", "b", "c"]

    def test_load_seen_with_empty_list_returns_empty_set(self, tmp_path):
        path = tmp_path / "seen.json"
        path.write_text("[]", encoding="utf-8")
        assert load_seen(path) == set()


# ---------------------------------------------------------------------------
# update_prd()
# ---------------------------------------------------------------------------

class TestUpdatePrd:
    def test_returns_false_when_incorporated_empty(self, tmp_path):
        path = tmp_path / "PRD.md"
        path.write_text(_PRD_TEMPLATE, encoding="utf-8")
        assert update_prd(path, date(2026, 3, 3), []) is False

    def test_returns_false_when_anchor_not_found(self, tmp_path):
        path = tmp_path / "PRD.md"
        path.write_text("# PRD\n\nNo anchor here.\n", encoding="utf-8")
        incorporated = [(_make_item(), _make_ext())]
        assert update_prd(path, date(2026, 3, 3), incorporated) is False

    def test_returns_true_on_success(self, tmp_path):
        path = tmp_path / "PRD.md"
        path.write_text(_PRD_TEMPLATE, encoding="utf-8")
        incorporated = [(_make_item(), _make_ext())]
        assert update_prd(path, date(2026, 3, 3), incorporated) is True

    def test_inserts_date_heading(self, tmp_path):
        path = tmp_path / "PRD.md"
        path.write_text(_PRD_TEMPLATE, encoding="utf-8")
        update_prd(path, date(2026, 3, 3), [(_make_item(), _make_ext())])
        content = path.read_text(encoding="utf-8")
        assert "### 2026-03-03 — Research digest" in content

    def test_inserts_item_title_as_link(self, tmp_path):
        path = tmp_path / "PRD.md"
        path.write_text(_PRD_TEMPLATE, encoding="utf-8")
        item = _make_item(title="My Paper", url="https://arxiv.org/abs/2401.00001")
        update_prd(path, date(2026, 3, 3), [(item, _make_ext())])
        content = path.read_text(encoding="utf-8")
        assert "[My Paper](https://arxiv.org/abs/2401.00001)" in content

    def test_inserts_prd_entry_text(self, tmp_path):
        path = tmp_path / "PRD.md"
        path.write_text(_PRD_TEMPLATE, encoding="utf-8")
        ext = _make_ext(prd_entry="This is the PRD paragraph.")
        update_prd(path, date(2026, 3, 3), [(_make_item(), ext)])
        content = path.read_text(encoding="utf-8")
        assert "This is the PRD paragraph." in content

    def test_new_entry_appears_before_existing_entries(self, tmp_path):
        path = tmp_path / "PRD.md"
        path.write_text(_PRD_TEMPLATE, encoding="utf-8")
        update_prd(path, date(2026, 3, 3), [(_make_item(), _make_ext())])
        content = path.read_text(encoding="utf-8")
        new_pos = content.index("2026-03-03")
        old_pos = content.index("2026-02-24")
        assert new_pos < old_pos

    def test_existing_content_preserved(self, tmp_path):
        path = tmp_path / "PRD.md"
        path.write_text(_PRD_TEMPLATE, encoding="utf-8")
        update_prd(path, date(2026, 3, 3), [(_make_item(), _make_ext())])
        content = path.read_text(encoding="utf-8")
        assert "Some existing content." in content

    def test_multiple_items_all_included(self, tmp_path):
        path = tmp_path / "PRD.md"
        path.write_text(_PRD_TEMPLATE, encoding="utf-8")
        incorporated = [
            (_make_item(title="Paper A"), _make_ext()),
            (_make_item(title="Paper B", url="https://example.com/b"), _make_ext()),
        ]
        update_prd(path, date(2026, 3, 3), incorporated)
        content = path.read_text(encoding="utf-8")
        assert "Paper A" in content
        assert "Paper B" in content

    def test_implications_rendered_as_list(self, tmp_path):
        path = tmp_path / "PRD.md"
        path.write_text(_PRD_TEMPLATE, encoding="utf-8")
        ext = _make_ext(implications=["Impl one", "Impl two"])
        update_prd(path, date(2026, 3, 3), [(_make_item(), ext)])
        content = path.read_text(encoding="utf-8")
        assert "- Impl one" in content
        assert "- Impl two" in content


# ---------------------------------------------------------------------------
# update_lessons()
# ---------------------------------------------------------------------------

_LESSONS_TEMPLATE = json.dumps({
    "entries": [
        {
            "date": "2026-02-24",
            "phase": "1",
            "category": "testing",
            "lesson": "Existing lesson",
            "context": "ctx",
            "resolution": "res",
            "rule": "rule",
        }
    ]
}, indent=2) + "\n"

_VALID_LESSON = {
    "lesson": "New lesson",
    "context": "Research evaluation",
    "resolution": "Added validation",
    "rule": "Always validate",
}


class TestUpdateLessons:
    def test_returns_false_when_no_new_lessons(self, tmp_path):
        path = tmp_path / "lessons.json"
        path.write_text(_LESSONS_TEMPLATE, encoding="utf-8")
        assert update_lessons(path, date(2026, 3, 3), []) is False

    def test_returns_true_on_success(self, tmp_path):
        path = tmp_path / "lessons.json"
        path.write_text(_LESSONS_TEMPLATE, encoding="utf-8")
        assert update_lessons(path, date(2026, 3, 3), [_VALID_LESSON]) is True

    def test_prepends_new_lessons(self, tmp_path):
        path = tmp_path / "lessons.json"
        path.write_text(_LESSONS_TEMPLATE, encoding="utf-8")
        update_lessons(path, date(2026, 3, 3), [_VALID_LESSON])
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["entries"][0]["lesson"] == "New lesson"

    def test_stamps_date_on_new_lessons(self, tmp_path):
        path = tmp_path / "lessons.json"
        path.write_text(_LESSONS_TEMPLATE, encoding="utf-8")
        update_lessons(path, date(2026, 3, 3), [_VALID_LESSON])
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["entries"][0]["date"] == "2026-03-03"

    def test_stamps_phase_auto_on_new_lessons(self, tmp_path):
        path = tmp_path / "lessons.json"
        path.write_text(_LESSONS_TEMPLATE, encoding="utf-8")
        update_lessons(path, date(2026, 3, 3), [_VALID_LESSON])
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["entries"][0]["phase"] == "auto"

    def test_stamps_category_research_on_new_lessons(self, tmp_path):
        path = tmp_path / "lessons.json"
        path.write_text(_LESSONS_TEMPLATE, encoding="utf-8")
        update_lessons(path, date(2026, 3, 3), [_VALID_LESSON])
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["entries"][0]["category"] == "research"

    def test_existing_lessons_preserved(self, tmp_path):
        path = tmp_path / "lessons.json"
        path.write_text(_LESSONS_TEMPLATE, encoding="utf-8")
        update_lessons(path, date(2026, 3, 3), [_VALID_LESSON])
        data = json.loads(path.read_text(encoding="utf-8"))
        lessons_text = [e["lesson"] for e in data["entries"]]
        assert "Existing lesson" in lessons_text

    def test_invalid_lessons_filtered_out(self, tmp_path):
        path = tmp_path / "lessons.json"
        path.write_text(_LESSONS_TEMPLATE, encoding="utf-8")
        invalid = {"lesson": "Missing fields"}  # no context/resolution/rule
        result = update_lessons(path, date(2026, 3, 3), [invalid])
        assert result is False  # nothing valid → no write

    def test_multiple_valid_lessons_all_prepended(self, tmp_path):
        path = tmp_path / "lessons.json"
        path.write_text(_LESSONS_TEMPLATE, encoding="utf-8")
        new = [
            {**_VALID_LESSON, "lesson": "Lesson X"},
            {**_VALID_LESSON, "lesson": "Lesson Y"},
        ]
        update_lessons(path, date(2026, 3, 3), new)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["entries"][0]["lesson"] in {"Lesson X", "Lesson Y"}
        assert data["entries"][1]["lesson"] in {"Lesson X", "Lesson Y"}
        assert data["entries"][2]["lesson"] == "Existing lesson"
