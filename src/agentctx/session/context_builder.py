from __future__ import annotations

from datetime import date

from agentctx.memory.observation_log import ObservationLog

_BLOCK1_HEADER = "## Observation Log\n\n"
_BLOCK2_HEADER = "## Current Session\n\n"


class ContextBuilder:
    def __init__(self, observation_log: ObservationLog) -> None:
        self.observation_log = observation_log

    def build_prefix(self, today: date | None = None) -> str:
        """Block 1: stable, cacheable observation log prefix."""
        entries = self.observation_log.entries()
        if not entries:
            return ""
        rendered = "\n\n".join(e.render(today) for e in entries)
        return _BLOCK1_HEADER + rendered

    def build(self, session_messages: list[dict], today: date | None = None) -> str:
        """Assemble Block 1 (observation log) + Block 2 (current session)."""
        prefix = self.build_prefix(today)
        session_text = self._format_session(session_messages)

        if prefix and session_text:
            return prefix + "\n\n" + _BLOCK2_HEADER + session_text
        if prefix:
            return prefix
        if session_text:
            return _BLOCK2_HEADER + session_text
        return ""

    @staticmethod
    def _format_session(messages: list[dict]) -> str:
        return "\n".join(
            f"[{msg.get('role', 'unknown')}]: {msg.get('content', '')}"
            for msg in messages
        )
