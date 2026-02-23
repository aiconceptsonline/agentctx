from __future__ import annotations

import re
from dataclasses import dataclass, field

# (pattern, flags) pairs — order matters; more specific patterns first
_INJECTION_PATTERNS: list[tuple[str, int]] = [
    # Classic "ignore/disregard/forget/override previous instructions"
    (
        r"(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|prior|above)\s+"
        r"(?:instructions?|context|prompts?|directions?|constraints?)",
        re.IGNORECASE,
    ),
    # "you are now a/an/the ..."
    (r"you\s+are\s+now\s+(?:a|an|the)\s+\w+", re.IGNORECASE),
    # "new/updated/secret instructions:"
    (r"(?:new|updat\w*|revis\w*|secret|hidden)\s+instructions?\s*:", re.IGNORECASE),
    # "forget everything/all/your/prior ..."
    (r"forget\s+(?:everything|all|your|what|prior\w*)", re.IGNORECASE),
    # "act/behave/pretend/roleplay as ..."
    (
        r"(?:act|behave|pretend|roleplay)\s+as\s+(?:if\s+)?(?:you\s+(?:are|were)\s+)?(?:a|an|the)\s+\w+",
        re.IGNORECASE,
    ),
    # "### System:" / "### Instructions:"
    (r"#{1,3}\s*(?:system|instructions?|prompt)\s*:", re.IGNORECASE),
    # XML-style injection: <system>...</system>
    (r"<\s*system\s*>[\s\S]*?<\s*/\s*system\s*>", re.IGNORECASE | re.DOTALL),
    # <instructions>...</instructions>
    (r"<\s*instructions?\s*>[\s\S]*?<\s*/\s*instructions?\s*>", re.IGNORECASE | re.DOTALL),
    # LLM special tokens: [INST]...[/INST], <|im_start|>
    (r"\[INST\][\s\S]*?\[/INST\]", re.DOTALL),
    (r"<\|im_start\|>[\s\S]*?(?:<\|im_end\|>|$)", re.DOTALL),
    (r"\|\s*im_start\s*\|", 0),
]

_COMPILED = [(re.compile(p, f), p) for p, f in _INJECTION_PATTERNS]

# Default per-entry character budget (~500 tokens at 4 chars/token)
DEFAULT_MAX_ENTRY_CHARS = 2_000


@dataclass
class SanitizeResult:
    text: str
    was_truncated: bool = False
    injection_count: int = 0


class Sanitizer:
    def __init__(self, max_entry_chars: int = DEFAULT_MAX_ENTRY_CHARS) -> None:
        self.max_entry_chars = max_entry_chars

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sanitize_for_observation(
        self, text: str, max_chars: int | None = None
    ) -> SanitizeResult:
        """Strip injections from observation text and enforce the entry budget."""
        budget = max_chars if max_chars is not None else self.max_entry_chars
        cleaned, count = self._strip_injections(text)

        truncated = False
        if len(cleaned) > budget:
            cleaned = cleaned[:budget].rstrip() + " … [TRUNCATED]"
            truncated = True

        return SanitizeResult(text=cleaned, was_truncated=truncated, injection_count=count)

    def wrap_external(self, content: str) -> str:
        """Wrap untrusted external content in delimiters after stripping injections."""
        cleaned, _ = self._strip_injections(content)
        return f"<external_content>\n{cleaned.strip()}\n</external_content>"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _strip_injections(self, content: str) -> tuple[str, int]:
        count = 0
        for compiled, _ in _COMPILED:
            new_content, n = compiled.subn("[REDACTED]", content)
            count += n
            content = new_content
        return content.strip(), count
