from __future__ import annotations

from typing import Iterator, Protocol, runtime_checkable


@runtime_checkable
class LLMAdapter(Protocol):
    """Minimal protocol that all LLM adapters must satisfy."""

    def call(self, messages: list[dict], system: str = "") -> str:
        """Send messages and return the full response text."""
        ...

    def stream(self, messages: list[dict], system: str = "") -> Iterator[str]:
        """Send messages and yield response text chunks."""
        ...
