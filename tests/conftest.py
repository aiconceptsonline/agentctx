"""Shared test configuration and fixtures."""
import pytest

from agentctx.testing import FakeLLMAdapter

__all__ = ["FakeLLMAdapter"]


@pytest.fixture
def fake_llm() -> FakeLLMAdapter:
    """FakeLLMAdapter with an empty default response."""
    return FakeLLMAdapter()
