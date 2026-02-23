from __future__ import annotations

from datetime import date

from agentctx.adapters.base import LLMAdapter
from agentctx.memory.observation_log import ObservationEntry, ObservationLog
from agentctx.security.sanitizer import Sanitizer

_SYSTEM = """\
You are a memory extraction agent for an AI agent system.

Read the conversation messages below and extract key observations: facts, decisions, \
errors, warnings, and patterns that would be useful in future runs.

Format each observation as a single line starting with a priority marker:
  🔴  critical issues that MUST influence the next run (errors, failures, expired tokens, \
blocked paths)
  🟡  patterns and signals worth tracking (trends, anomalies, recurring themes)
  🟢  routine context (timing, metadata, completions, normal outcomes)

Rules:
- One observation per line, maximum ~200 characters
- Start each line with the emoji and a space, then the observation text
- Only include observations useful in future runs — skip pleasantries and ephemeral details
- If nothing is worth recording, return an empty response\
"""


class Observer:
    def __init__(
        self,
        llm: LLMAdapter,
        observation_log: ObservationLog,
        sanitizer: Sanitizer,
    ) -> None:
        self.llm = llm
        self.observation_log = observation_log
        self.sanitizer = sanitizer

    def compress(
        self,
        messages: list[dict],
        event_date: date | None = None,
    ) -> list[ObservationEntry]:
        """Compress a list of messages into observations and append to the log."""
        if not messages:
            return []

        today = date.today()
        event_date = event_date or today

        formatted = "\n".join(
            f"[{m.get('role', 'unknown')}]: {m.get('content', '')}"
            for m in messages
        )

        response = self.llm.call(
            messages=[{"role": "user", "content": formatted}],
            system=_SYSTEM,
        )

        return self._parse_and_write(response, today=today, event_date=event_date)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_and_write(
        self, response: str, today: date, event_date: date
    ) -> list[ObservationEntry]:
        entries: list[ObservationEntry] = []

        for line in response.splitlines():
            line = line.strip()
            if not line:
                continue

            priority = None
            text = line
            for marker in ("🔴", "🟡", "🟢"):
                if line.startswith(marker):
                    priority = marker
                    # Handle optional separator chars: "🔴: text", "🔴- text", "🔴 text"
                    text = line[len(marker):].lstrip(" :-").strip()
                    break

            if priority is None:
                continue

            result = self.sanitizer.sanitize_for_observation(text)
            entry = ObservationEntry(
                priority="🔴" if result.was_truncated else priority,
                observed_on=today,
                event_date=event_date,
                text=result.text,
            )
            self.observation_log.append(entry)
            entries.append(entry)

        return entries
