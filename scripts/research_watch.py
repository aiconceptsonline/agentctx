#!/usr/bin/env python3
"""Research monitor for agentctx.

Fetches new papers and blog posts from arxiv and curated RSS feeds, scores
each item for relevance to agentctx using Claude, and — for items scoring ≥ 4
— extracts key findings and automatically updates PRD.md and
lessons-learned.json.

Usage (manual):
    pip install agentctx[claude,research]
    python scripts/research_watch.py
    python scripts/research_watch.py --dry-run
    python scripts/research_watch.py --min-score 3 --model claude-sonnet-4-6

Designed to run as a weekly GitHub Actions workflow. All state is stored in
research/seen.json so successive runs don't re-process old items.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timezone, datetime
from pathlib import Path

# Resolve repo root regardless of where the script is invoked from
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from agentctx.research.fetcher import ResearchItem, fetch_feed, item_key
from agentctx.research.evaluator import evaluate_item, extract_findings
from agentctx.research.updater import (
    load_seen, save_seen, update_prd, update_lessons,
)


def _make_adapter(model: str):
    """Return the best available LLM adapter based on environment variables.

    Priority:
    1. CLAUDE_CODE_OAUTH_TOKEN  → ClaudeCLIAdapter (no API credits needed)
    2. ANTHROPIC_API_KEY        → ClaudeAdapter (direct SDK)
    """
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        from agentctx.adapters.claude_cli import ClaudeCLIAdapter
        return ClaudeCLIAdapter(model=model)
    from agentctx.adapters.claude import ClaudeAdapter
    return ClaudeAdapter(model=model)


# ── Sources ───────────────────────────────────────────────────────────────────

ARXIV_FEEDS = [
    # Agent memory and context engineering
    "https://export.arxiv.org/api/query?search_query=all:agent+memory+context+engineering&sortBy=submittedDate&sortOrder=descending&max_results=10",
    # Prompt injection and agent security
    "https://export.arxiv.org/api/query?search_query=all:prompt+injection+LLM+agent+security&sortBy=submittedDate&sortOrder=descending&max_results=10",
    # Long-context and context window management
    "https://export.arxiv.org/api/query?search_query=all:long+context+LLM+context+window&sortBy=submittedDate&sortOrder=descending&max_results=5",
    # Memory poisoning / backdoor in LLM memory
    "https://export.arxiv.org/api/query?search_query=all:memory+poisoning+LLM+agent&sortBy=submittedDate&sortOrder=descending&max_results=5",
]

RSS_FEEDS = [
    "https://www.anthropic.com/news/rss.xml",
    "https://martinfowler.com/feed.atom",
    "https://unit42.paloaltonetworks.com/rss/",
    "https://feeds.feedburner.com/TheHackersNews",
]

SEEN_PATH = _REPO_ROOT / "research" / "seen.json"
PRD_PATH = _REPO_ROOT / "PRD.md"
LESSONS_PATH = _REPO_ROOT / "lessons-learned.json"


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run(
    min_score: int = 4,
    dry_run: bool = False,
    eval_model: str = "claude-haiku-4-5-20251001",
    extract_model: str = "claude-sonnet-4-6",
    verbose: bool = False,
) -> dict:
    """Run the research watch pipeline and return a summary dict."""
    eval_llm = _make_adapter(eval_model)
    extract_llm = _make_adapter(extract_model)

    seen = load_seen(SEEN_PATH)

    # Fetch all feeds
    all_items: list[ResearchItem] = []
    for url in ARXIV_FEEDS + RSS_FEEDS:
        try:
            items = fetch_feed(url)
            all_items.extend(items)
            if verbose:
                print(f"  fetched {len(items):>3} items from {url[:60]}")
        except Exception as exc:
            print(f"  [warn] fetch failed for {url[:60]}: {exc}", file=sys.stderr)

    # Deduplicate and filter seen
    new_items: list[ResearchItem] = []
    for item in all_items:
        key = item_key(item)
        if key not in seen:
            new_items.append(item)

    # Remove duplicates within this batch (same key from multiple feeds)
    seen_keys: set[str] = set()
    deduped: list[ResearchItem] = []
    for item in new_items:
        k = item_key(item)
        if k not in seen_keys:
            seen_keys.add(k)
            deduped.append(item)

    print(f"Found {len(deduped)} new items (of {len(all_items)} fetched)")

    # Evaluate relevance
    relevant: list[tuple[ResearchItem, int, str]] = []
    for item in deduped:
        result = evaluate_item(eval_llm, item)
        seen.add(item_key(item))
        if verbose:
            print(f"  [{result.score}/5] {item.title[:70]}")
        if result.score >= min_score:
            relevant.append((item, result.score, result.reason))

    print(f"{len(relevant)} items scored ≥ {min_score}")

    # Extract findings from relevant items
    incorporated: list[tuple[ResearchItem, object]] = []
    all_lessons: list[dict] = []
    for item, score, reason in relevant:
        ext = extract_findings(extract_llm, item)
        incorporated.append((item, ext))
        all_lessons.extend(ext.lessons)
        if verbose:
            print(f"  extracted: {item.title[:60]}")

    # Update files
    prd_updated = False
    lessons_updated = False
    today = date.today()

    if not dry_run:
        save_seen(SEEN_PATH, seen)
        if incorporated:
            prd_updated = update_prd(PRD_PATH, today, incorporated)
            lessons_updated = update_lessons(LESSONS_PATH, today, all_lessons)

    summary = {
        "date": str(today),
        "fetched": len(all_items),
        "new": len(deduped),
        "relevant": len(relevant),
        "incorporated": len(incorporated),
        "prd_updated": prd_updated,
        "lessons_updated": lessons_updated,
        "dry_run": dry_run,
    }
    return summary


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Fetch and evaluate but do not write any files")
    parser.add_argument("--min-score", type=int, default=4, metavar="N", help="Minimum relevance score to incorporate (1-5, default: 4)")
    parser.add_argument("--eval-model", default="claude-haiku-4-5-20251001", metavar="MODEL", help="Claude model for relevance scoring")
    parser.add_argument("--extract-model", default="claude-sonnet-4-6", metavar="MODEL", help="Claude model for finding extraction")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    summary = run(
        min_score=args.min_score,
        dry_run=args.dry_run,
        eval_model=args.eval_model,
        extract_model=args.extract_model,
        verbose=args.verbose,
    )

    print("\nSummary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    if summary["incorporated"] > 0 and not summary["dry_run"]:
        print("\nFiles updated:")
        if summary["prd_updated"]:
            print("  PRD.md")
        if summary["lessons_updated"]:
            print("  lessons-learned.json")
        print("  research/seen.json")


if __name__ == "__main__":
    main()
