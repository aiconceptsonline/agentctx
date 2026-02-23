from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class AuditEntry:
    timestamp: str
    source: str      # observer | reflector | manual
    char_delta: int
    sha256: str


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    def _ensure_file(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    # ------------------------------------------------------------------
    # Hashing
    # ------------------------------------------------------------------

    @staticmethod
    def hash_content(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def append(self, source: str, previous_content: str, new_content: str) -> AuditEntry:
        self._ensure_file()
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            source=source,
            char_delta=len(new_content) - len(previous_content),
            sha256=self.hash_content(new_content),
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.__dict__) + "\n")
        return entry

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def all_entries(self) -> list[AuditEntry]:
        if not self.path.exists():
            return []
        entries = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(AuditEntry(**json.loads(line)))
        return entries

    def last_entry(self) -> AuditEntry | None:
        entries = self.all_entries()
        return entries[-1] if entries else None

    def last_hash(self) -> str | None:
        entry = self.last_entry()
        return entry.sha256 if entry else None

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, current_content: str) -> bool:
        """Return True if current_content matches the last recorded hash.

        Returns True when no audit history exists (nothing to verify against).
        """
        last = self.last_hash()
        if last is None:
            return True
        return self.hash_content(current_content) == last
