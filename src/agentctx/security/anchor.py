from __future__ import annotations


class Anchor:
    """Stores the original task intent for the session.

    Phase 1: holds the intent string and renders it into the context prefix.
    Phase 3 will add semantic drift detection against this anchor.
    """

    def __init__(self, intent: str) -> None:
        self._intent = intent.strip()

    @property
    def intent(self) -> str:
        return self._intent

    def render(self) -> str:
        if not self._intent:
            return ""
        return f"## Task Anchor\n\n{self._intent}"

    def __bool__(self) -> bool:
        return bool(self._intent)
