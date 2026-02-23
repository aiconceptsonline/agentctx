import json

import pytest

from agentctx.session.run_state import RunState, StepRecord


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestRunStateInitial:
    def test_starts_with_no_completed_steps(self, tmp_path):
        state = RunState("run-001", tmp_path)
        assert state.completed_steps() == []

    def test_starts_with_in_progress_status(self, tmp_path):
        state = RunState("run-001", tmp_path)
        assert state._status == "in_progress"

    def test_unknown_step_is_not_complete(self, tmp_path):
        state = RunState("run-001", tmp_path)
        assert state.is_complete("nonexistent") is False

    def test_unknown_step_result_is_none(self, tmp_path):
        state = RunState("run-001", tmp_path)
        assert state.get_result("nonexistent") is None


# ---------------------------------------------------------------------------
# complete() / fail()
# ---------------------------------------------------------------------------

class TestRunStateStepMutations:
    def test_complete_marks_step_done(self, tmp_path):
        state = RunState("run-001", tmp_path)
        state.complete("parse")
        assert state.is_complete("parse") is True

    def test_complete_stores_result(self, tmp_path):
        state = RunState("run-001", tmp_path)
        state.complete("parse", result={"items": 5})
        assert state.get_result("parse") == {"items": 5}

    def test_complete_result_none_by_default(self, tmp_path):
        state = RunState("run-001", tmp_path)
        state.complete("parse")
        assert state.get_result("parse") is None

    def test_fail_does_not_add_to_completed_steps(self, tmp_path):
        state = RunState("run-001", tmp_path)
        state.fail("research", result="timeout")
        assert "research" not in state.completed_steps()

    def test_fail_stores_result(self, tmp_path):
        state = RunState("run-001", tmp_path)
        state.fail("research", result="timeout error")
        assert state.get_result("research") == "timeout error"

    def test_completed_steps_excludes_failed(self, tmp_path):
        state = RunState("run-001", tmp_path)
        state.complete("parse")
        state.fail("research")
        assert state.completed_steps() == ["parse"]

    def test_multiple_completed_steps(self, tmp_path):
        state = RunState("run-001", tmp_path)
        state.complete("parse")
        state.complete("research")
        state.complete("summarize")
        assert set(state.completed_steps()) == {"parse", "research", "summarize"}

    def test_complete_result_with_list(self, tmp_path):
        state = RunState("run-001", tmp_path)
        state.complete("gather", result=[1, 2, 3])
        assert state.get_result("gather") == [1, 2, 3]


# ---------------------------------------------------------------------------
# Persistence (save / load)
# ---------------------------------------------------------------------------

class TestRunStatePersistence:
    def test_complete_creates_json_file(self, tmp_path):
        state = RunState("run-001", tmp_path)
        state.complete("parse")
        assert (tmp_path / "run-001.json").exists()

    def test_resume_recovers_completed_steps(self, tmp_path):
        s1 = RunState("run-001", tmp_path)
        s1.complete("parse", result=42)
        s1.complete("research", result="done")

        s2 = RunState("run-001", tmp_path)
        assert "parse" in s2.completed_steps()
        assert "research" in s2.completed_steps()
        assert s2.get_result("parse") == 42

    def test_resume_does_not_mark_unfinished_steps_complete(self, tmp_path):
        s1 = RunState("run-001", tmp_path)
        s1.complete("parse")

        s2 = RunState("run-001", tmp_path)
        assert not s2.is_complete("summarize")

    def test_separate_run_ids_are_independent(self, tmp_path):
        s1 = RunState("run-001", tmp_path)
        s2 = RunState("run-002", tmp_path)
        s1.complete("step_a")
        assert not s2.is_complete("step_a")

    def test_to_dict_structure(self, tmp_path):
        state = RunState("run-002", tmp_path)
        state.complete("step_a", result="ok")
        d = state.to_dict()
        assert d["run_id"] == "run-002"
        assert d["status"] == "in_progress"
        assert d["steps"]["step_a"]["done"] is True
        assert d["steps"]["step_a"]["result"] == "ok"

    def test_mark_done_persists_status(self, tmp_path):
        state = RunState("run-001", tmp_path)
        state.mark_done()
        reloaded = RunState("run-001", tmp_path)
        assert reloaded._status == "done"

    def test_json_file_is_valid_json(self, tmp_path):
        state = RunState("run-001", tmp_path)
        state.complete("parse", result="done")
        raw = (tmp_path / "run-001.json").read_text()
        data = json.loads(raw)
        assert data["run_id"] == "run-001"

    def test_storage_dir_created_automatically(self, tmp_path):
        nested = tmp_path / "deep" / "nested" / "runs"
        state = RunState("run-001", nested)
        state.complete("parse")
        assert (nested / "run-001.json").exists()
