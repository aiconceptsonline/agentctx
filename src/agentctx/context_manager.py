from __future__ import annotations

from datetime import date
from pathlib import Path

from agentctx.adapters.base import LLMAdapter
from agentctx.config import AgentCtxConfig
from agentctx.memory.observation_log import ObservationEntry, ObservationLog
from agentctx.memory.observer import Observer
from agentctx.memory.reflector import Reflector
from agentctx.security.anchor import Anchor
from agentctx.security.audit import AuditLog
from agentctx.security.sanitizer import Sanitizer
from agentctx.session.context_builder import ContextBuilder


class ContextManager:
    """Top-level coordinator: wires together the observation log, audit log,
    sanitizer, observer, reflector, and context builder.

    Minimal integration::

        ctx = ContextManager(
            storage_path="./memory",
            llm=ClaudeAdapter(model="claude-haiku-4-5-20251001"),
            task_anchor="Summarize security news into a YouTube episode script",
        )

        system_prompt = ctx.build_prefix() + "\\n\\nYour task: ..."
        ctx.add_message(role="assistant", content=response)
    """

    def __init__(
        self,
        storage_path: str | Path,
        llm: LLMAdapter,
        observer_threshold: int = 30_000,
        reflector_threshold: int = 40_000,
        task_anchor: str = "",
    ) -> None:
        self._config = AgentCtxConfig(
            storage_path=storage_path,
            observer_threshold=observer_threshold,
            reflector_threshold=reflector_threshold,
        )
        self._observation_log = ObservationLog(self._config.observations_path)
        self._audit_log = AuditLog(self._config.audit_path)
        self._sanitizer = Sanitizer()
        self._observer = Observer(llm, self._observation_log, self._sanitizer)
        self._reflector = Reflector(llm, self._observation_log, self._sanitizer)
        self._context_builder = ContextBuilder(self._observation_log)
        self._anchor = Anchor(task_anchor)
        self._session_messages: list[dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_prefix(self, today: date | None = None) -> str:
        """Return the stable Block 1 prefix to prepend to any agent's system prompt."""
        parts: list[str] = []
        anchor_text = self._anchor.render()
        if anchor_text:
            parts.append(anchor_text)
        obs_prefix = self._context_builder.build_prefix(today)
        if obs_prefix:
            parts.append(obs_prefix)
        return "\n\n".join(parts)

    def build(self, today: date | None = None) -> str:
        """Return Block 1 + Block 2 (current session) as a single string."""
        prefix = self.build_prefix(today)
        session_text = self._context_builder._format_session(self._session_messages)
        if prefix and session_text:
            return prefix + "\n\n## Current Session\n\n" + session_text
        if prefix:
            return prefix
        if session_text:
            return "## Current Session\n\n" + session_text
        return ""

    def add_message(self, role: str, content: str) -> None:
        """Record a message in the current session; auto-triggers Observer if needed."""
        self._session_messages.append({"role": role, "content": content})
        if self._session_token_count() >= self._config.observer_threshold:
            self._run_observer()

    def observe(self, text: str, event_date: str | None = None) -> ObservationEntry:
        """Manually write an observation to the log.

        The text may optionally begin with a priority marker (🔴/🟡/🟢).
        If omitted, defaults to 🟢.
        """
        priority = "🟢"
        for marker in ("🔴", "🟡", "🟢"):
            if text.startswith(marker):
                priority = marker
                text = text[len(marker):].lstrip(" :-").strip()
                break

        ed = date.fromisoformat(event_date) if event_date else date.today()
        result = self._sanitizer.sanitize_for_observation(text)

        entry = ObservationEntry(
            priority="🔴" if result.was_truncated else priority,
            observed_on=date.today(),
            event_date=ed,
            text=result.text,
        )

        prev = self._observation_log.read_raw()
        self._observation_log.append(entry)
        self._audit_log.append("manual", prev, self._observation_log.read_raw())
        return entry

    def verify_integrity(self) -> bool:
        """Return True if the observation log hash matches the last audit entry."""
        return self._audit_log.verify(self._observation_log.read_raw())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _session_token_count(self) -> int:
        return sum(len(m.get("content", "")) for m in self._session_messages) // 4

    def _run_observer(self) -> None:
        messages = list(self._session_messages)
        prev = self._observation_log.read_raw()
        self._observer.compress(messages)
        self._session_messages = []
        new = self._observation_log.read_raw()
        if new != prev:
            self._audit_log.append("observer", prev, new)
        self._maybe_reflect()

    def _maybe_reflect(self) -> None:
        if self._observation_log.token_count_approx() >= self._config.reflector_threshold:
            prev = self._observation_log.read_raw()
            rewrote = self._reflector.reflect()
            if rewrote:
                self._audit_log.append("reflector", prev, self._observation_log.read_raw())
