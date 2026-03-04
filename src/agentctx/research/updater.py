from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from agentctx.research.fetcher import ResearchItem
from agentctx.research.evaluator import ExtractionResult


# ── Seen-set persistence ──────────────────────────────────────────────────────

def load_seen(path: Path) -> set[str]:
    """Load the set of already-processed item keys from disk."""
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def save_seen(path: Path, seen: set[str]) -> None:
    """Persist the seen-set to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(seen), indent=2), encoding="utf-8")


# ── PRD updater ───────────────────────────────────────────────────────────────

def update_prd(
    prd_path: Path,
    today: date,
    incorporated: list[tuple[ResearchItem, ExtractionResult]],
) -> bool:
    """Prepend a research digest entry to §10 of PRD.md.

    Returns True if the file was modified.
    """
    if not incorporated:
        return False

    entry = _format_prd_entry(today, incorporated)
    text = prd_path.read_text(encoding="utf-8")

    # Insert before the first level-3 heading inside §10
    # (i.e. right after "New entries go at the top.\n\n---\n\n")
    pattern = r"(New entries go at the top\.\n\n---\n\n)"
    if not re.search(pattern, text):
        return False

    new_text = re.sub(pattern, r"\1" + entry + "\n\n---\n\n", text, count=1)
    if new_text == text:
        return False

    prd_path.write_text(new_text, encoding="utf-8")
    return True


def _format_prd_entry(
    today: date,
    incorporated: list[tuple[ResearchItem, ExtractionResult]],
) -> str:
    lines = [f"### {today} — Research digest (automated)\n"]
    lines.append(
        f"Auto-incorporated {len(incorporated)} item(s) with relevance ≥ 4.\n"
    )

    for item, ext in incorporated:
        lines.append(f"**[{item.title}]({item.url})**\n")
        if ext.prd_entry:
            lines.append(ext.prd_entry + "\n")
        if ext.agentctx_implications:
            for impl in ext.agentctx_implications:
                lines.append(f"- {impl}")
            lines.append("")

    return "\n".join(lines).rstrip()


# ── Lessons updater ───────────────────────────────────────────────────────────

def update_lessons(
    lessons_path: Path,
    today: date,
    new_lessons: list[dict],
) -> bool:
    """Prepend new lesson entries to lessons-learned.json.

    Returns True if the file was modified.
    """
    if not new_lessons:
        return False

    data = json.loads(lessons_path.read_text(encoding="utf-8"))
    entries: list[dict] = data.get("entries", [])

    stamped = [
        {"date": str(today), "phase": "auto", "category": "research", **lesson}
        for lesson in new_lessons
        if _is_valid_lesson(lesson)
    ]
    if not stamped:
        return False

    data["entries"] = stamped + entries
    lessons_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def _is_valid_lesson(lesson: dict) -> bool:
    return bool(
        lesson.get("lesson")
        and lesson.get("context")
        and lesson.get("resolution")
        and lesson.get("rule")
    )
