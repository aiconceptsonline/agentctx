from datetime import date

import pytest

from agentctx.memory.observation_log import ObservationEntry, ObservationLog
from agentctx.session.context_builder import ContextBuilder


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_log(tmp_path):
    return ObservationLog(tmp_path / "observations.md")


@pytest.fixture
def log_with_two_entries(tmp_path):
    log = ObservationLog(tmp_path / "observations.md")
    log.append(ObservationEntry(
        priority="🔴",
        observed_on=date(2026, 2, 23),
        event_date=date(2026, 2, 22),
        text="Upload failed",
    ))
    log.append(ObservationEntry(
        priority="🟢",
        observed_on=date(2026, 2, 20),
        event_date=date(2026, 2, 20),
        text="Run #47 completed",
    ))
    return log


# ---------------------------------------------------------------------------
# build_prefix
# ---------------------------------------------------------------------------

class TestContextBuilderPrefix:
    def test_empty_log_returns_empty_string(self, empty_log):
        builder = ContextBuilder(empty_log)
        assert builder.build_prefix() == ""

    def test_prefix_contains_all_observations(self, log_with_two_entries):
        builder = ContextBuilder(log_with_two_entries)
        prefix = builder.build_prefix(today=date(2026, 2, 23))
        assert "Upload failed" in prefix
        assert "Run #47 completed" in prefix

    def test_prefix_includes_relative_lag(self, log_with_two_entries):
        builder = ContextBuilder(log_with_two_entries)
        prefix = builder.build_prefix(today=date(2026, 2, 23))
        assert "relative:1_day_ago" in prefix

    def test_prefix_has_observation_log_header(self, log_with_two_entries):
        builder = ContextBuilder(log_with_two_entries)
        prefix = builder.build_prefix(today=date(2026, 2, 23))
        assert "Observation Log" in prefix

    def test_prefix_starts_with_block1_header(self, log_with_two_entries):
        builder = ContextBuilder(log_with_two_entries)
        prefix = builder.build_prefix(today=date(2026, 2, 23))
        assert prefix.startswith("## Observation Log")


# ---------------------------------------------------------------------------
# build — combining Block 1 + Block 2
# ---------------------------------------------------------------------------

class TestContextBuilderFull:
    def test_empty_log_and_empty_messages_returns_empty(self, empty_log):
        builder = ContextBuilder(empty_log)
        assert builder.build([]) == ""

    def test_session_only_no_observations(self, empty_log):
        builder = ContextBuilder(empty_log)
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        result = builder.build(messages)
        assert "[user]: Hello" in result
        assert "[assistant]: Hi" in result

    def test_session_only_has_block2_header(self, empty_log):
        builder = ContextBuilder(empty_log)
        result = builder.build([{"role": "user", "content": "Start"}])
        assert "Current Session" in result

    def test_both_blocks_present_when_log_and_messages_exist(self, log_with_two_entries):
        builder = ContextBuilder(log_with_two_entries)
        messages = [{"role": "user", "content": "Start task"}]
        result = builder.build(messages, today=date(2026, 2, 23))
        assert "Observation Log" in result
        assert "Current Session" in result
        assert "Upload failed" in result
        assert "Start task" in result

    def test_prefix_only_when_no_messages(self, log_with_two_entries):
        builder = ContextBuilder(log_with_two_entries)
        result = builder.build([], today=date(2026, 2, 23))
        assert "Upload failed" in result
        assert "Current Session" not in result

    def test_block1_appears_before_block2(self, log_with_two_entries):
        builder = ContextBuilder(log_with_two_entries)
        result = builder.build(
            [{"role": "user", "content": "task message"}],
            today=date(2026, 2, 23),
        )
        obs_pos = result.index("Observation Log")
        session_pos = result.index("Current Session")
        assert obs_pos < session_pos

    def test_message_with_missing_role_handled(self, empty_log):
        builder = ContextBuilder(empty_log)
        result = builder.build([{"content": "no role here"}])
        assert "[unknown]: no role here" in result

    def test_message_with_missing_content_handled(self, empty_log):
        builder = ContextBuilder(empty_log)
        result = builder.build([{"role": "user"}])
        assert "[user]:" in result

    def test_multiple_session_messages_in_order(self, empty_log):
        builder = ContextBuilder(empty_log)
        messages = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
            {"role": "user", "content": "Third"},
        ]
        result = builder.build(messages)
        first_pos = result.index("First")
        second_pos = result.index("Second")
        third_pos = result.index("Third")
        assert first_pos < second_pos < third_pos
