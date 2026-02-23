from __future__ import annotations

import re
import stat
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PRIORITY_MARKERS = ("🔴", "🟡", "🟢")

# Matches: PRIORITY observed_on:DATE event_date:DATE [relative:X]? [[EXT]]?
_HEADER_RE = re.compile(
    r"^([🔴🟡🟢])"
    r"\s+observed_on:(\d{4}-\d{2}-\d{2})"
    r"\s+event_date:(\d{4}-\d{2}-\d{2})"
    r"(?:\s+relative:\S+)?"   # optional stored relative field — ignored on parse
    r"(\s+\[EXT\])?"          # optional external-content tag
)


@dataclass
class ObservationEntry:
    priority: str        # 🔴 | 🟡 | 🟢
    observed_on: date
    event_date: date
    text: str
    external: bool = False

    def relative_lag(self, today: date | None = None) -> str:
        today = today or date.today()
        delta = (today - self.event_date).days
        if delta == 0:
            return "today"
        if delta == 1:
            return "1_day_ago"
        return f"{delta}_days_ago"

    def render(self, today: date | None = None) -> str:
        """Rendered form injected into the context window (includes relative)."""
        ext = " [EXT]" if self.external else ""
        relative = self.relative_lag(today)
        header = (
            f"{self.priority} observed_on:{self.observed_on}"
            f" event_date:{self.event_date}"
            f" relative:{relative}{ext}"
        )
        return f"{header}\n{self.text}"

    def serialize(self) -> str:
        """Storage form written to observations.md (no relative — computed at build time)."""
        ext = " [EXT]" if self.external else ""
        header = (
            f"{self.priority} observed_on:{self.observed_on}"
            f" event_date:{self.event_date}{ext}"
        )
        return f"{header}\n{self.text}"


class ObservationLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    def _ensure_file(self) -> None:
        parent = self.path.parent
        if not parent.exists():
            parent.mkdir(parents=True)
            parent.chmod(0o700)
        if not self.path.exists():
            self.path.touch()

    def read_raw(self) -> str:
        if not self.path.exists():
            return ""
        return self.path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse(raw: str) -> list[ObservationEntry]:
        entries: list[ObservationEntry] = []
        blocks = re.split(r"\n{2,}", raw.strip())
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            parts = block.split("\n", 1)
            header = parts[0]
            text = parts[1].strip() if len(parts) > 1 else ""

            m = _HEADER_RE.match(header)
            if not m:
                continue

            entries.append(
                ObservationEntry(
                    priority=m.group(1),
                    observed_on=date.fromisoformat(m.group(2)),
                    event_date=date.fromisoformat(m.group(3)),
                    text=text,
                    external=bool(m.group(4)),
                )
            )
        return entries

    def entries(self) -> list[ObservationEntry]:
        return self._parse(self.read_raw())

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def append(self, entry: ObservationEntry) -> None:
        self._ensure_file()
        raw = self.read_raw()
        separator = "\n\n" if raw.strip() else ""
        with self.path.open("a", encoding="utf-8") as f:
            f.write(separator + entry.serialize() + "\n")

    def overwrite(self, entries: list[ObservationEntry]) -> None:
        """Reflector-only: rewrites the entire log in place."""
        self._ensure_file()
        if entries:
            content = "\n\n".join(e.serialize() for e in entries) + "\n"
        else:
            content = ""
        self.path.write_text(content, encoding="utf-8")

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def token_count_approx(self) -> int:
        """Rough approximation: 1 token ≈ 4 characters."""
        return len(self.read_raw()) // 4
