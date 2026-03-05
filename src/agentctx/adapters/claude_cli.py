from __future__ import annotations

import subprocess


class ClaudeCLIAdapter:
    """Adapter that calls ``claude -p`` in non-interactive (print) mode.

    Uses the Claude Code CLI instead of the Anthropic SDK, so it authenticates
    via ``CLAUDE_CODE_OAUTH_TOKEN`` (Claude subscription) rather than an API
    key with credit balance.

    Requirements:
        npm install -g @anthropic-ai/claude-code
        export CLAUDE_CODE_OAUTH_TOKEN=<token from GitHub App>
    """

    def __init__(self, model: str | None = None) -> None:
        self._model = model

    def call(self, messages: list[dict], system: str = "") -> str:
        # The CLI doesn't take a separate system prompt flag, so prepend it.
        parts: list[str] = []
        if system:
            parts.append(system)
        for msg in messages:
            if msg.get("role") == "user":
                parts.append(msg["content"])

        prompt = "\n\n".join(parts)

        cmd = ["claude", "-p", prompt]
        if self._model:
            cmd.extend(["--model", self._model])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(
                f"claude CLI exited {result.returncode}: {result.stderr[:300]}"
            )

        return result.stdout.strip()
