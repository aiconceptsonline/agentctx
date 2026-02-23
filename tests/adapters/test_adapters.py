"""Adapter tests.

Real adapters (ClaudeAdapter, GeminiAdapter) are tested with injected mock
clients so no live API key is needed. The FakeLLMAdapter tests validate the
protocol contract itself.
"""
from unittest.mock import MagicMock

import pytest

from agentctx.adapters.base import LLMAdapter


# ---------------------------------------------------------------------------
# FakeLLMAdapter — validates the LLMAdapter protocol
# ---------------------------------------------------------------------------

class TestFakeLLMAdapterProtocol:
    def test_satisfies_llm_adapter_protocol(self, fake_llm):
        assert isinstance(fake_llm, LLMAdapter)

    def test_call_returns_configured_response(self, fake_llm):
        from agentctx.testing import FakeLLMAdapter
        adapter = FakeLLMAdapter("hello")
        assert adapter.call([{"role": "user", "content": "test"}]) == "hello"

    def test_stream_yields_configured_response(self):
        from agentctx.testing import FakeLLMAdapter
        adapter = FakeLLMAdapter("streamed")
        chunks = list(adapter.stream([{"role": "user", "content": "test"}]))
        assert chunks == ["streamed"]

    def test_records_call_history(self):
        from agentctx.testing import FakeLLMAdapter
        adapter = FakeLLMAdapter("reply")
        msgs = [{"role": "user", "content": "hi"}]
        adapter.call(msgs, system="sys")
        assert len(adapter.calls) == 1
        assert adapter.calls[0]["messages"] == msgs
        assert adapter.calls[0]["system"] == "sys"

    def test_default_response_is_empty_string(self, fake_llm):
        assert fake_llm.call([]) == ""


# ---------------------------------------------------------------------------
# ClaudeAdapter — mock client injection
# ---------------------------------------------------------------------------

class TestClaudeAdapter:
    def _make_mock_client(self, response_text: str):
        client = MagicMock()
        content_block = MagicMock()
        content_block.text = response_text
        client.messages.create.return_value.content = [content_block]
        return client

    def test_call_returns_response_text(self):
        from agentctx.adapters.claude import ClaudeAdapter
        client = self._make_mock_client("test response")
        adapter = ClaudeAdapter(_client=client)
        result = adapter.call([{"role": "user", "content": "hello"}])
        assert result == "test response"

    def test_call_passes_model_and_max_tokens(self):
        from agentctx.adapters.claude import ClaudeAdapter
        client = self._make_mock_client("ok")
        adapter = ClaudeAdapter(model="claude-opus-4-6", max_tokens=1024, _client=client)
        adapter.call([{"role": "user", "content": "test"}])
        call_kwargs = client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-opus-4-6"
        assert call_kwargs["max_tokens"] == 1024

    def test_call_passes_system_prompt(self):
        from agentctx.adapters.claude import ClaudeAdapter
        client = self._make_mock_client("ok")
        adapter = ClaudeAdapter(_client=client)
        adapter.call([{"role": "user", "content": "test"}], system="Be helpful")
        call_kwargs = client.messages.create.call_args[1]
        assert call_kwargs["system"] == "Be helpful"

    def test_call_omits_system_when_empty(self):
        from agentctx.adapters.claude import ClaudeAdapter
        client = self._make_mock_client("ok")
        adapter = ClaudeAdapter(_client=client)
        adapter.call([{"role": "user", "content": "test"}])
        call_kwargs = client.messages.create.call_args[1]
        assert "system" not in call_kwargs

    def test_satisfies_llm_adapter_protocol(self):
        from agentctx.adapters.claude import ClaudeAdapter
        client = self._make_mock_client("ok")
        adapter = ClaudeAdapter(_client=client)
        assert isinstance(adapter, LLMAdapter)

    def test_missing_anthropic_raises_import_error(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "anthropic", None)
        from agentctx.adapters.claude import ClaudeAdapter
        with pytest.raises(ImportError, match="anthropic"):
            ClaudeAdapter()

# ---------------------------------------------------------------------------
# GeminiAdapter — mock model injection
# ---------------------------------------------------------------------------

class TestGeminiAdapter:
    def _make_mock_model(self, response_text: str):
        model = MagicMock()
        model.generate_content.return_value.text = response_text
        return model

    def test_call_returns_response_text(self):
        from agentctx.adapters.gemini import GeminiAdapter
        model = self._make_mock_model("gemini response")
        adapter = GeminiAdapter(_model_instance=model)
        result = adapter.call([{"role": "user", "content": "hello"}])
        assert result == "gemini response"

    def test_call_converts_assistant_role_to_model(self):
        from agentctx.adapters.gemini import GeminiAdapter
        model = self._make_mock_model("ok")
        adapter = GeminiAdapter(_model_instance=model)
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "thanks"},
        ]
        adapter.call(messages)
        contents = model.generate_content.call_args[0][0]
        roles = [c["role"] for c in contents]
        assert "assistant" not in roles
        assert "model" in roles

    def test_call_prepends_system_to_first_user_message(self):
        from agentctx.adapters.gemini import GeminiAdapter
        model = self._make_mock_model("ok")
        adapter = GeminiAdapter(_model_instance=model)
        messages = [{"role": "user", "content": "question"}]
        adapter.call(messages, system="Be concise")
        contents = model.generate_content.call_args[0][0]
        first_part = contents[0]["parts"][0]
        assert "Be concise" in first_part
        assert "question" in first_part

    def test_satisfies_llm_adapter_protocol(self):
        from agentctx.adapters.gemini import GeminiAdapter
        model = self._make_mock_model("ok")
        adapter = GeminiAdapter(_model_instance=model)
        assert isinstance(adapter, LLMAdapter)
