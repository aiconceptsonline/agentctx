import stat
from datetime import date
from pathlib import Path

import pytest

from agentctx.memory.observation_log import ObservationEntry, ObservationLog


# ---------------------------------------------------------------------------
# ObservationEntry unit tests
# ---------------------------------------------------------------------------

class TestObservationEntryRelativeLag:
    def test_same_day_returns_today(self):
        entry = ObservationEntry(
            priority="🟢",
            observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 23),
            text="",
        )
        assert entry.relative_lag(today=date(2026, 2, 23)) == "today"

    def test_one_day_ago(self):
        entry = ObservationEntry(
            priority="🔴",
            observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 22),
            text="",
        )
        assert entry.relative_lag(today=date(2026, 2, 23)) == "1_day_ago"

    def test_multiple_days_ago(self):
        entry = ObservationEntry(
            priority="🟡",
            observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 20),
            text="",
        )
        assert entry.relative_lag(today=date(2026, 2, 23)) == "3_days_ago"


class TestObservationEntryRender:
    def test_render_includes_relative(self):
        entry = ObservationEntry(
            priority="🟡",
            observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 20),
            text="Pattern detected",
        )
        rendered = entry.render(today=date(2026, 2, 23))
        assert "relative:3_days_ago" in rendered
        assert "Pattern detected" in rendered

    def test_render_external_includes_ext_tag(self):
        entry = ObservationEntry(
            priority="🔴",
            observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 23),
            text="Scraped content caused an error",
            external=True,
        )
        assert "[EXT]" in entry.render(today=date(2026, 2, 23))

    def test_render_internal_no_ext_tag(self):
        entry = ObservationEntry(
            priority="🟢",
            observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 23),
            text="All good",
        )
        assert "[EXT]" not in entry.render(today=date(2026, 2, 23))

    def test_render_has_priority_marker(self):
        entry = ObservationEntry(
            priority="🔴",
            observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 23),
            text="Critical error",
        )
        assert entry.render(today=date(2026, 2, 23)).startswith("🔴")


class TestObservationEntrySerialize:
    def test_serialize_omits_relative(self):
        entry = ObservationEntry(
            priority="🟢",
            observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 20),
            text="All good",
        )
        serialized = entry.serialize()
        assert "relative:" not in serialized

    def test_serialize_contains_dates(self):
        entry = ObservationEntry(
            priority="🟢",
            observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 20),
            text="All good",
        )
        serialized = entry.serialize()
        assert "observed_on:2026-02-23" in serialized
        assert "event_date:2026-02-20" in serialized

    def test_serialize_external_includes_ext(self):
        entry = ObservationEntry(
            priority="🔴",
            observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 23),
            text="Injected text",
            external=True,
        )
        assert "[EXT]" in entry.serialize()


# ---------------------------------------------------------------------------
# ObservationLog._parse static method
# ---------------------------------------------------------------------------

class TestObservationLogParse:
    def test_parse_empty_string(self):
        assert ObservationLog._parse("") == []

    def test_parse_single_entry(self):
        raw = "🟢 observed_on:2026-02-23 event_date:2026-02-23\nRun completed"
        entries = ObservationLog._parse(raw)
        assert len(entries) == 1
        assert entries[0].priority == "🟢"
        assert entries[0].observed_on == date(2026, 2, 23)
        assert entries[0].event_date == date(2026, 2, 23)
        assert entries[0].text == "Run completed"
        assert entries[0].external is False

    def test_parse_multiple_entries_separated_by_blank_line(self):
        raw = (
            "🔴 observed_on:2026-02-23 event_date:2026-02-22\nUpload failed\n\n"
            "🟡 observed_on:2026-02-20 event_date:2026-02-20\nPattern detected"
        )
        entries = ObservationLog._parse(raw)
        assert len(entries) == 2
        assert entries[0].priority == "🔴"
        assert entries[1].priority == "🟡"

    def test_parse_external_tag(self):
        raw = "🔴 observed_on:2026-02-23 event_date:2026-02-23 [EXT]\nScraped injection"
        entries = ObservationLog._parse(raw)
        assert entries[0].external is True

    def test_parse_ignores_stored_relative_field(self):
        raw = "🟡 observed_on:2026-02-23 event_date:2026-02-20 relative:3_days_ago\nOld entry"
        entries = ObservationLog._parse(raw)
        assert len(entries) == 1
        assert entries[0].text == "Old entry"

    def test_parse_multiline_text(self):
        raw = "🔴 observed_on:2026-02-23 event_date:2026-02-23\nLine one\nLine two\nLine three"
        entries = ObservationLog._parse(raw)
        assert entries[0].text == "Line one\nLine two\nLine three"

    def test_parse_skips_malformed_blocks(self):
        raw = (
            "not a valid header\nsome text\n\n"
            "🟢 observed_on:2026-02-23 event_date:2026-02-23\nValid entry"
        )
        entries = ObservationLog._parse(raw)
        assert len(entries) == 1
        assert entries[0].text == "Valid entry"


# ---------------------------------------------------------------------------
# ObservationLog file I/O
# ---------------------------------------------------------------------------

class TestObservationLogIO:
    def test_read_raw_returns_empty_for_missing_file(self, tmp_path):
        log = ObservationLog(tmp_path / "observations.md")
        assert log.read_raw() == ""

    def test_entries_returns_empty_for_missing_file(self, tmp_path):
        log = ObservationLog(tmp_path / "observations.md")
        assert log.entries() == []

    def test_append_creates_file(self, tmp_path):
        log = ObservationLog(tmp_path / "observations.md")
        log.append(ObservationEntry(
            priority="🟢",
            observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 23),
            text="First entry",
        ))
        assert log.path.exists()

    def test_append_single_roundtrip(self, tmp_path):
        log = ObservationLog(tmp_path / "observations.md")
        log.append(ObservationEntry(
            priority="🔴",
            observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 22),
            text="Error on upload",
        ))
        parsed = log.entries()
        assert len(parsed) == 1
        assert parsed[0].priority == "🔴"
        assert parsed[0].text == "Error on upload"
        assert parsed[0].event_date == date(2026, 2, 22)

    def test_append_multiple_entries_all_recoverable(self, tmp_path):
        log = ObservationLog(tmp_path / "observations.md")
        for i, priority in enumerate(["🔴", "🟡", "🟢"]):
            log.append(ObservationEntry(
                priority=priority,
                observed_on=date(2026, 2, 23),
                event_date=date(2026, 2, 23),
                text=f"Entry {i}",
            ))
        assert len(log.entries()) == 3

    def test_append_preserves_order(self, tmp_path):
        log = ObservationLog(tmp_path / "observations.md")
        log.append(ObservationEntry(
            priority="🔴", observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 23), text="First",
        ))
        log.append(ObservationEntry(
            priority="🟢", observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 23), text="Second",
        ))
        entries = log.entries()
        assert entries[0].text == "First"
        assert entries[1].text == "Second"

    def test_overwrite_replaces_all_entries(self, tmp_path):
        log = ObservationLog(tmp_path / "observations.md")
        for i in range(3):
            log.append(ObservationEntry(
                priority="🟢", observed_on=date(2026, 2, 23),
                event_date=date(2026, 2, 23), text=f"Old entry {i}",
            ))
        log.overwrite([ObservationEntry(
            priority="🔴", observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 23), text="Only this remains",
        )])
        entries = log.entries()
        assert len(entries) == 1
        assert entries[0].text == "Only this remains"

    def test_overwrite_with_empty_list_clears_log(self, tmp_path):
        log = ObservationLog(tmp_path / "observations.md")
        log.append(ObservationEntry(
            priority="🟢", observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 23), text="Something",
        ))
        log.overwrite([])
        assert log.entries() == []

    def test_token_count_approx_nonzero_after_append(self, tmp_path):
        log = ObservationLog(tmp_path / "observations.md")
        log.append(ObservationEntry(
            priority="🟢", observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 23), text="A" * 400,
        ))
        assert log.token_count_approx() > 0


# ---------------------------------------------------------------------------
# File permissions
# ---------------------------------------------------------------------------

class TestObservationLogPermissions:
    def test_memory_dir_created_with_700_permissions(self, tmp_path):
        log = ObservationLog(tmp_path / "memory" / "observations.md")
        log._ensure_file()
        mode = stat.S_IMODE((tmp_path / "memory").stat().st_mode)
        assert mode == 0o700

    def test_existing_dir_not_chmoded_on_reuse(self, tmp_path):
        """Second _ensure_file call on existing dir must not error."""
        log = ObservationLog(tmp_path / "memory" / "observations.md")
        log._ensure_file()
        log._ensure_file()  # must not raise
        assert log.path.exists()
