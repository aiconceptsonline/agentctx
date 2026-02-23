from __future__ import annotations

from typing import Iterator


class ClaudeAdapter:
    """Anthropic Claude adapter.

    Requires the ``anthropic`` extra: ``pip install agentctx[claude]``
    """

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 4_096,
        _client=None,
    ) -> None:
        if _client is None:
            try:
                from anthropic import Anthropic
            except ImportError:
                raise ImportError(
                    "The 'anthropic' package is required. "
                    "Install it with: pip install agentctx[claude]"
                ) from None
            _client = Anthropic()
        self._client = _client
        self.model = model
        self.max_tokens = max_tokens

    def call(self, messages: list[dict], system: str = "") -> str:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        response = self._client.messages.create(**kwargs)
        return response.content[0].text

    def stream(self, messages: list[dict], system: str = "") -> Iterator[str]:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        with self._client.messages.stream(**kwargs) as stream:
            yield from stream.text_stream
