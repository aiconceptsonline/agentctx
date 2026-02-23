"""Test doubles for agentctx.

Useful for anyone integrating agentctx who wants to test their code without
making real LLM API calls.
"""
from __future__ import annotations

from typing import Iterator


class FakeLLMAdapter:
    """Deterministic LLM adapter that returns a fixed response string.

    Example::

        from agentctx.testing import FakeLLMAdapter
        from agentctx import ContextManager

        llm = FakeLLMAdapter("🟢 Run completed successfully")
        ctx = ContextManager(storage_path="./memory", llm=llm)
    """

    def __init__(self, response: str = "") -> None:
        self.response = response
        self.calls: list[dict] = []

    def call(self, messages: list[dict], system: str = "") -> str:
        self.calls.append({"messages": messages, "system": system})
        return self.response

    def stream(self, messages: list[dict], system: str = "") -> Iterator[str]:
        self.calls.append({"messages": messages, "system": system})
        yield self.response
