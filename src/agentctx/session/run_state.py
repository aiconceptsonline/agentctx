from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class StepRecord:
    done: bool
    result: Any = None


class RunState:
    def __init__(self, run_id: str, storage_path: Path) -> None:
        self.run_id = run_id
        self.storage_path = Path(storage_path)
        self._status: str = "in_progress"
        self._steps: dict[str, StepRecord] = {}
        self._load_if_exists()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _path(self) -> Path:
        return self.storage_path / f"{self.run_id}.json"

    def _load_if_exists(self) -> None:
        if not self._path.exists():
            return
        data = json.loads(self._path.read_text(encoding="utf-8"))
        self._status = data.get("status", "in_progress")
        self._steps = {
            k: StepRecord(**v) for k, v in data.get("steps", {}).items()
        }

    # ------------------------------------------------------------------
    # Step management
    # ------------------------------------------------------------------

    def complete(self, step: str, result: Any = None) -> None:
        self._steps[step] = StepRecord(done=True, result=result)
        self.save()

    def fail(self, step: str, result: Any = None) -> None:
        self._steps[step] = StepRecord(done=False, result=result)
        self.save()

    def completed_steps(self) -> list[str]:
        return [k for k, v in self._steps.items() if v.done]

    def is_complete(self, step: str) -> bool:
        return self._steps.get(step, StepRecord(done=False)).done

    def get_result(self, step: str) -> Any:
        return self._steps.get(step, StepRecord(done=False)).result

    # ------------------------------------------------------------------
    # Run-level status
    # ------------------------------------------------------------------

    def mark_done(self) -> None:
        self._status = "done"
        self.save()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self.to_dict(), indent=2),
            encoding="utf-8",
        )

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self._status,
            "steps": {
                k: {"done": v.done, "result": v.result}
                for k, v in self._steps.items()
            },
        }
