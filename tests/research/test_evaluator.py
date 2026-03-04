"""Tests for agentctx.research.evaluator."""
import json

import pytest

from agentctx.research.evaluator import (
    ExtractionResult,
    RelevanceResult,
    evaluate_item,
    extract_findings,
)
from agentctx.research.fetcher import ResearchItem
from agentctx.testing import FakeLLMAdapter


def _make_item(**kwargs) -> ResearchItem:
    defaults = dict(
        title="Agent Memory Survey",
        url="https://arxiv.org/abs/2401.00001",
        summary="A survey of agent memory techniques.",
        published="2024-01-01",
        source="arxiv",
    )
    return ResearchItem(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# evaluate_item()
# ---------------------------------------------------------------------------

class TestEvaluateItem:
    def test_returns_relevance_result(self):
        raw = json.dumps({"score": 4, "reason": "Directly relevant"})
        llm = FakeLLMAdapter(raw)
        result = evaluate_item(llm, _make_item())
        assert isinstance(result, RelevanceResult)

    def test_parses_score_correctly(self):
        raw = json.dumps({"score": 5, "reason": "Core topic"})
        llm = FakeLLMAdapter(raw)
        result = evaluate_item(llm, _make_item())
        assert result.score == 5

    def test_parses_reason_correctly(self):
        raw = json.dumps({"score": 3, "reason": "Tangentially related"})
        llm = FakeLLMAdapter(raw)
        result = evaluate_item(llm, _make_item())
        assert result.reason == "Tangentially related"

    def test_score_clamped_to_1_when_out_of_range_low(self):
        raw = json.dumps({"score": 0, "reason": "Below range"})
        llm = FakeLLMAdapter(raw)
        result = evaluate_item(llm, _make_item())
        assert result.score == 1

    def test_score_clamped_to_5_when_out_of_range_high(self):
        raw = json.dumps({"score": 10, "reason": "Above range"})
        llm = FakeLLMAdapter(raw)
        result = evaluate_item(llm, _make_item())
        assert result.score == 5

    def test_invalid_json_returns_score_1(self):
        llm = FakeLLMAdapter("not json at all")
        result = evaluate_item(llm, _make_item())
        assert result.score == 1
        assert result.reason == "parse error"

    def test_missing_score_field_returns_score_1(self):
        raw = json.dumps({"reason": "No score field"})
        llm = FakeLLMAdapter(raw)
        result = evaluate_item(llm, _make_item())
        assert result.score == 1

    def test_raw_field_contains_llm_response(self):
        raw = json.dumps({"score": 4, "reason": "Good"})
        llm = FakeLLMAdapter(raw)
        result = evaluate_item(llm, _make_item())
        assert result.raw == raw

    def test_calls_llm_with_title_and_summary_in_message(self):
        raw = json.dumps({"score": 2, "reason": "Weak"})
        llm = FakeLLMAdapter(raw)
        item = _make_item(title="Special Title", summary="Special Summary")
        evaluate_item(llm, item)
        call_content = llm.calls[0]["messages"][0]["content"]
        assert "Special Title" in call_content
        assert "Special Summary" in call_content

    def test_calls_llm_with_relevance_system_prompt(self):
        raw = json.dumps({"score": 3, "reason": "OK"})
        llm = FakeLLMAdapter(raw)
        evaluate_item(llm, _make_item())
        assert llm.calls[0]["system"] is not None
        assert "agentctx" in llm.calls[0]["system"]


# ---------------------------------------------------------------------------
# extract_findings()
# ---------------------------------------------------------------------------

class TestExtractFindings:
    def _valid_extraction(self, **overrides) -> str:
        data = {
            "key_findings": ["Finding one", "Finding two"],
            "agentctx_implications": ["Implication A"],
            "prd_entry": "A paragraph for the PRD.",
            "lessons": [
                {
                    "lesson": "Use structured prompts",
                    "context": "Evaluating papers",
                    "resolution": "Added JSON schema",
                    "rule": "Always use JSON",
                }
            ],
        }
        data.update(overrides)
        return json.dumps(data)

    def test_returns_extraction_result(self):
        llm = FakeLLMAdapter(self._valid_extraction())
        result = extract_findings(llm, _make_item())
        assert isinstance(result, ExtractionResult)

    def test_parses_key_findings(self):
        llm = FakeLLMAdapter(self._valid_extraction())
        result = extract_findings(llm, _make_item())
        assert "Finding one" in result.key_findings

    def test_parses_implications(self):
        llm = FakeLLMAdapter(self._valid_extraction())
        result = extract_findings(llm, _make_item())
        assert "Implication A" in result.agentctx_implications

    def test_parses_prd_entry(self):
        llm = FakeLLMAdapter(self._valid_extraction())
        result = extract_findings(llm, _make_item())
        assert result.prd_entry == "A paragraph for the PRD."

    def test_parses_lessons(self):
        llm = FakeLLMAdapter(self._valid_extraction())
        result = extract_findings(llm, _make_item())
        assert len(result.lessons) == 1
        assert result.lessons[0]["lesson"] == "Use structured prompts"

    def test_null_prd_entry_stays_none(self):
        llm = FakeLLMAdapter(self._valid_extraction(prd_entry=None))
        result = extract_findings(llm, _make_item())
        assert result.prd_entry is None

    def test_invalid_json_returns_empty_result(self):
        llm = FakeLLMAdapter("not json")
        result = extract_findings(llm, _make_item())
        assert result.key_findings == []
        assert result.agentctx_implications == []
        assert result.prd_entry is None
        assert result.lessons == []

    def test_non_dict_lessons_filtered_out(self):
        raw = json.dumps({
            "key_findings": [],
            "agentctx_implications": [],
            "prd_entry": None,
            "lessons": ["a string", 42, {"lesson": "x", "context": "y", "resolution": "z", "rule": "r"}],
        })
        llm = FakeLLMAdapter(raw)
        result = extract_findings(llm, _make_item())
        assert len(result.lessons) == 1

    def test_raw_field_contains_llm_response(self):
        raw = self._valid_extraction()
        llm = FakeLLMAdapter(raw)
        result = extract_findings(llm, _make_item())
        assert result.raw == raw

    def test_calls_llm_with_title_url_and_summary(self):
        llm = FakeLLMAdapter(self._valid_extraction())
        item = _make_item(title="Test Paper", url="https://example.com", summary="Test summary")
        extract_findings(llm, item)
        content = llm.calls[0]["messages"][0]["content"]
        assert "Test Paper" in content
        assert "https://example.com" in content
        assert "Test summary" in content

    def test_missing_optional_fields_use_defaults(self):
        raw = json.dumps({"key_findings": ["Only this"]})
        llm = FakeLLMAdapter(raw)
        result = extract_findings(llm, _make_item())
        assert result.key_findings == ["Only this"]
        assert result.agentctx_implications == []
        assert result.prd_entry is None
        assert result.lessons == []
