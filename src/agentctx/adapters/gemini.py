from __future__ import annotations

from typing import Iterator


class GeminiAdapter:
    """Google Gemini adapter.

    Requires the ``gemini`` extra: ``pip install agentctx[gemini]``

    Authentication: set the ``GOOGLE_API_KEY`` environment variable, or pass
    ``api_key`` explicitly.
    """

    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        api_key: str | None = None,
        _model_instance=None,
    ) -> None:
        if _model_instance is None:
            try:
                import google.generativeai as genai
            except ImportError:
                raise ImportError(
                    "The 'google-generativeai' package is required. "
                    "Install it with: pip install agentctx[gemini]"
                ) from None
            if api_key:
                genai.configure(api_key=api_key)
            _model_instance = genai.GenerativeModel(model_name=model)
        self._model = _model_instance
        self.model = model

    def call(self, messages: list[dict], system: str = "") -> str:
        contents = self._convert_messages(messages, system)
        response = self._model.generate_content(contents)
        return response.text

    def stream(self, messages: list[dict], system: str = "") -> Iterator[str]:
        contents = self._convert_messages(messages, system)
        for chunk in self._model.generate_content(contents, stream=True):
            if chunk.text:
                yield chunk.text

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_messages(messages: list[dict], system: str) -> list[dict]:
        """Convert OpenAI-style messages to Gemini content format.

        Gemini uses role ``"model"`` instead of ``"assistant"``, and does not
        support a ``"system"`` role in the content list — system instructions
        are prepended to the first user message instead.
        """
        contents: list[dict] = []

        if system:
            # Gemini v1 doesn't support system_instruction on all models;
            # prepend to the first user message as a safe fallback.
            first_user = next(
                (i for i, m in enumerate(messages) if m.get("role") == "user"), None
            )
            if first_user is not None:
                messages = list(messages)
                messages[first_user] = {
                    **messages[first_user],
                    "content": f"{system}\n\n{messages[first_user].get('content', '')}",
                }

        for msg in messages:
            role = "model" if msg.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [msg.get("content", "")]})

        return contents
