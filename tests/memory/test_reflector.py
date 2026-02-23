from datetime import date

import pytest

from agentctx.memory.observation_log import ObservationEntry, ObservationLog
from agentctx.memory.reflector import Reflector
from agentctx.security.sanitizer import Sanitizer


def make_reflector(tmp_path, llm_response: str) -> tuple[Reflector, ObservationLog]:
    from agentctx.testing import FakeLLMAdapter
    log = ObservationLog(tmp_path / "observations.md")
    reflector = Reflector(FakeLLMAdapter(llm_response), log, Sanitizer())
    return reflector, log


def seed_log(log: ObservationLog, n: int = 2) -> None:
    for i in range(n):
        log.append(ObservationEntry(
            priority="🟢",
            observed_on=date(2026, 2, 23),
            event_date=date(2026, 2, 23),
            text=f"Entry {i}",
        ))


# ---------------------------------------------------------------------------
# reflect() — behaviour
# ---------------------------------------------------------------------------

class TestReflectorReflect:
    def test_empty_log_returns_false_and_skips_llm(self, tmp_path):
        from agentctx.testing import FakeLLMAdapter
        fake = FakeLLMAdapter("🟢 observed_on:2026-02-23 event_date:2026-02-23\nSomething")
        log = ObservationLog(tmp_path / "observations.md")
        reflector = Reflector(fake, log, Sanitizer())
        result = reflector.reflect()
        assert result is False
        assert fake.calls == []

    def test_calls_llm_with_current_log_content(self, tmp_path):
        from agentctx.testing import FakeLLMAdapter
        llm_response = (
            "🟢 observed_on:2026-02-23 event_date:2026-02-23\nConsolidated entry"
        )
        fake = FakeLLMAdapter(llm_response)
        log = ObservationLog(tmp_path / "observations.md")
        seed_log(log)
        reflector = Reflector(fake, log, Sanitizer())
        reflector.reflect()
        assert len(fake.calls) == 1
        call_content = fake.calls[0]["messages"][0]["content"]
        assert "Entry 0" in call_content

    def test_overwrites_log_with_parsed_response(self, tmp_path):
        llm_response = (
            "🔴 observed_on:2026-02-23 event_date:2026-02-22\nOnly this remains"
        )
        reflector, log = make_reflector(tmp_path, llm_response)
        seed_log(log, n=3)
        result = reflector.reflect()
        assert result is True
        entries = log.entries()
        assert len(entries) == 1
        assert entries[0].text == "Only this remains"
        assert entries[0].priority == "🔴"

    def test_returns_false_when_llm_produces_empty_response(self, tmp_path):
        reflector, log = make_reflector(tmp_path, "")
        seed_log(log)
        original_raw = log.read_raw()
        result = reflector.reflect()
        assert result is False
        assert log.read_raw() == original_raw

    def test_returns_false_when_llm_output_is_unparseable(self, tmp_path):
        reflector, log = make_reflector(tmp_path, "This is not a valid observation log")
        seed_log(log)
        original = log.entries()
        result = reflector.reflect()
        assert result is False
        assert len(log.entries()) == len(original)

    def test_preserves_multiple_consolidated_entries(self, tmp_path):
        llm_response = (
            "🔴 observed_on:2026-02-23 event_date:2026-02-22\nCritical issue\n\n"
            "🟡 observed_on:2026-02-23 event_date:2026-02-20\nPattern\n\n"
            "🟢 observed_on:2026-02-23 event_date:2026-02-23\nRun completed"
        )
        reflector, log = make_reflector(tmp_path, llm_response)
        seed_log(log, n=5)
        reflector.reflect()
        entries = log.entries()
        assert len(entries) == 3
        priorities = {e.priority for e in entries}
        assert priorities == {"🔴", "🟡", "🟢"}

    def test_reflect_returns_true_on_success(self, tmp_path):
        llm_response = (
            "🟢 observed_on:2026-02-23 event_date:2026-02-23\nConsolidated"
        )
        reflector, log = make_reflector(tmp_path, llm_response)
        seed_log(log)
        assert reflector.reflect() is True
