from __future__ import annotations

from agentctx.adapters.base import LLMAdapter
from agentctx.memory.observation_log import ObservationLog
from agentctx.security.sanitizer import Sanitizer

_SYSTEM = """\
You are a memory consolidation agent for an AI agent system.

You will receive an observation log. Your job is to consolidate it:
1. Merge related or redundant observations into single, more precise entries
2. Remove observations that have been fully superseded by newer ones
3. Preserve all three priority markers (🔴, 🟡, 🟢) exactly as-is
4. For merged entries, keep the most recent observed_on date and the earliest event_date
5. Keep every 🔴 entry unless it is genuinely superseded and resolved

Return the consolidated log in EXACTLY this format — no other text:

PRIORITY observed_on:YYYY-MM-DD event_date:YYYY-MM-DD
Observation text here

PRIORITY observed_on:YYYY-MM-DD event_date:YYYY-MM-DD [EXT]
External observation text here

Separate each entry with a single blank line.\
"""


class Reflector:
    def __init__(
        self,
        llm: LLMAdapter,
        observation_log: ObservationLog,
        sanitizer: Sanitizer,
    ) -> None:
        self.llm = llm
        self.observation_log = observation_log
        self.sanitizer = sanitizer

    def reflect(self) -> bool:
        """Consolidate the observation log in place.

        Returns True if the log was rewritten, False if skipped (empty log or
        the LLM output produced fewer valid entries than expected).
        """
        raw = self.observation_log.read_raw()
        if not raw.strip():
            return False

        original_entries = self.observation_log.entries()
        if not original_entries:
            return False

        response = self.llm.call(
            messages=[{"role": "user", "content": raw}],
            system=_SYSTEM,
        )

        new_entries = ObservationLog._parse(response)

        # Safety check: don't silently destroy the log if the LLM produced
        # nothing parseable from a non-empty response.
        if not new_entries:
            return False

        self.observation_log.overwrite(new_entries)
        return True
