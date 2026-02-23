from datetime import date

import pytest

from agentctx.context_manager import ContextManager
from agentctx.memory.observation_log import ObservationEntry, ObservationLog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx(tmp_path, llm_response: str = "", task_anchor: str = "",
             observer_threshold: int = 30_000) -> ContextManager:
    from agentctx.testing import FakeLLMAdapter
    return ContextManager(
        storage_path=tmp_path / "memory",
        llm=FakeLLMAdapter(llm_response),
        observer_threshold=observer_threshold,
        task_anchor=task_anchor,
    )


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestContextManagerInit:
    def test_creates_without_error(self, tmp_path):
        ctx = make_ctx(tmp_path)
        assert ctx is not None

    def test_session_starts_empty(self, tmp_path):
        ctx = make_ctx(tmp_path)
        assert ctx._session_messages == []


# ---------------------------------------------------------------------------
# build_prefix()
# ---------------------------------------------------------------------------

class TestContextManagerBuildPrefix:
    def test_empty_log_no_anchor_returns_empty(self, tmp_path):
        ctx = make_ctx(tmp_path)
        assert ctx.build_prefix() == ""

    def test_includes_task_anchor_when_set(self, tmp_path):
        ctx = make_ctx(tmp_path, task_anchor="Summarise security news")
        prefix = ctx.build_prefix()
        assert "Summarise security news" in prefix

    def test_anchor_section_header_present(self, tmp_path):
        ctx = make_ctx(tmp_path, task_anchor="Do the thing")
        assert "Task Anchor" in ctx.build_prefix()

    def test_includes_observations_from_log(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.observe("🔴 Upload failed")
        prefix = ctx.build_prefix(today=date(2026, 2, 23))
        assert "Upload failed" in prefix

    def test_anchor_appears_before_observations(self, tmp_path):
        ctx = make_ctx(tmp_path, task_anchor="My task")
        ctx.observe("🟢 Run completed")
        prefix = ctx.build_prefix(today=date(2026, 2, 23))
        anchor_pos = prefix.index("My task")
        obs_pos = prefix.index("Run completed")
        assert anchor_pos < obs_pos

    def test_no_anchor_with_observations_has_no_task_anchor_header(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.observe("🟢 Done")
        assert "Task Anchor" not in ctx.build_prefix()


# ---------------------------------------------------------------------------
# observe()
# ---------------------------------------------------------------------------

class TestContextManagerObserve:
    def test_observe_writes_entry_to_log(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.observe("Run completed")
        assert len(ctx._observation_log.entries()) == 1

    def test_observe_default_priority_is_green(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.observe("Routine event")
        assert ctx._observation_log.entries()[0].priority == "🟢"

    def test_observe_parses_red_from_text(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.observe("🔴 OAuth token expired")
        assert ctx._observation_log.entries()[0].priority == "🔴"

    def test_observe_parses_yellow_from_text(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.observe("🟡 Cluster pattern detected")
        assert ctx._observation_log.entries()[0].priority == "🟡"

    def test_observe_with_explicit_event_date(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.observe("Old event", event_date="2026-02-01")
        entry = ctx._observation_log.entries()[0]
        assert entry.event_date == date(2026, 2, 1)

    def test_observe_records_audit_entry(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.observe("Something happened")
        assert len(ctx._audit_log.all_entries()) == 1

    def test_observe_audit_source_is_manual(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.observe("Something happened")
        assert ctx._audit_log.last_entry().source == "manual"

    def test_observe_returns_observation_entry(self, tmp_path):
        ctx = make_ctx(tmp_path)
        entry = ctx.observe("🟢 Done")
        assert isinstance(entry, ObservationEntry)
        assert entry.text == "Done"

    def test_multiple_observe_calls_accumulate(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.observe("🔴 Error one")
        ctx.observe("🟢 Done")
        assert len(ctx._observation_log.entries()) == 2


# ---------------------------------------------------------------------------
# add_message() + auto-observer
# ---------------------------------------------------------------------------

class TestContextManagerAddMessage:
    def test_add_message_stored_in_session(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.add_message("user", "Hello")
        assert len(ctx._session_messages) == 1
        assert ctx._session_messages[0]["role"] == "user"

    def test_observer_not_fired_below_threshold(self, tmp_path):
        ctx = make_ctx(tmp_path, observer_threshold=10_000)
        ctx.add_message("user", "Short message")
        # Observer hasn't fired — no entries in observation log
        assert ctx._observation_log.entries() == []

    def test_observer_fires_when_threshold_exceeded(self, tmp_path):
        # LLM will return one observation when called
        ctx = make_ctx(
            tmp_path,
            llm_response="🟢 Session compressed",
            observer_threshold=5,  # ~20 chars triggers at any real message
        )
        ctx.add_message("user", "This message is definitely long enough to cross the threshold")
        assert len(ctx._observation_log.entries()) == 1

    def test_session_cleared_after_observer_fires(self, tmp_path):
        ctx = make_ctx(
            tmp_path,
            llm_response="🟢 Done",
            observer_threshold=5,
        )
        ctx.add_message("user", "A message that exceeds the tiny threshold")
        assert ctx._session_messages == []

    def test_audit_log_updated_when_observer_writes(self, tmp_path):
        ctx = make_ctx(
            tmp_path,
            llm_response="🟢 Compressed",
            observer_threshold=5,
        )
        ctx.add_message("user", "Long enough message to trigger the observer")
        assert len(ctx._audit_log.all_entries()) == 1
        assert ctx._audit_log.last_entry().source == "observer"

    def test_observer_fires_based_on_approximate_tokens(self, tmp_path):
        # 40 chars = 10 tokens; threshold = 8 → should fire
        ctx = make_ctx(
            tmp_path,
            llm_response="🟢 Done",
            observer_threshold=8,
        )
        ctx.add_message("user", "1234567890123456789012345678901234567890")  # 40 chars
        assert len(ctx._observation_log.entries()) == 1


# ---------------------------------------------------------------------------
# verify_integrity()
# ---------------------------------------------------------------------------

class TestContextManagerIntegrity:
    def test_verify_returns_true_on_clean_state(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.observe("test event")
        assert ctx.verify_integrity() is True

    def test_verify_returns_true_with_no_writes(self, tmp_path):
        ctx = make_ctx(tmp_path)
        # No writes at all — audit log is empty → verify returns True
        assert ctx.verify_integrity() is True

    def test_verify_returns_false_after_tampering(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.observe("legitimate observation")
        # Tamper with the file out-of-band
        ctx._observation_log.path.write_text("tampered content", encoding="utf-8")
        assert ctx.verify_integrity() is False
