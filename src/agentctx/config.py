from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AgentCtxConfig:
    storage_path: Path
    observer_threshold: int = 30_000   # approximate tokens before Observer fires
    reflector_threshold: int = 40_000  # approximate observation tokens before Reflector fires
    memory_dir_permissions: int = 0o700

    def __post_init__(self) -> None:
        self.storage_path = Path(self.storage_path)

    @property
    def memory_path(self) -> Path:
        return self.storage_path

    @property
    def observations_path(self) -> Path:
        return self.storage_path / "observations.md"

    @property
    def audit_path(self) -> Path:
        return self.storage_path / "audit.jsonl"

    @property
    def sessions_path(self) -> Path:
        return self.storage_path / "sessions"
