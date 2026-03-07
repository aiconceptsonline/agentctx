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
    python scripts/research_watch.py --min-score 3 --max-age-days 14

Designed to run as a weekly GitHub Actions workflow. All state is stored in
research/seen.json so successive runs don't re-process old items.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta, timezone, datetime
from email.utils import parsedate_to_datetime
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


def _parse_dt(s: str) -> datetime | None:
    """Parse an RSS/Atom date string into a timezone-aware datetime."""
    if not s:
        return None
    # ISO 8601 (arxiv: "2026-03-03T00:00:00Z")
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass
    # RFC 2822 (RSS: "Mon, 03 Mar 2026 00:00:00 +0000")
    try:
        return parsedate_to_datetime(s)
    except Exception:
        pass
    return None


def _is_recent(item: ResearchItem, cutoff: datetime) -> bool:
    """Return True if the item was published on or after cutoff."""
    dt = _parse_dt(item.published)
    if dt is None:
        return True  # can't parse date → include it
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= cutoff


# Keywords matched against the TITLE only (not summary).
# Title-matching is a much stronger signal than summary-matching —
# keep this list specific to avoid catching tangentially-related papers.
# Tune here to widen or narrow the pre-filter.
TITLE_KEYWORDS = [
    # LLM agents (specific compound phrases)
    "llm agent", "ai agent", "language model agent", "agentic", "multi-agent",
    # Context / memory (specific to LLMs)
    "context window", "context engineering", "context management", "long context",
    "memory augmented", "memory-augmented",
    # Fleet / multi-agent memory (new scope)
    "fleet memory", "shared memory", "collaborative memory", "memory silo",
    "memory as a service", "agent memory", "cross-agent", "agent fleet",
    "agent coordination", "agent communication",
    # Security
    "prompt injection", "jailbreak", "memory poisoning", "backdoor attack",
    "agent hijacking", "session smuggling",
    # Retrieval-augmented generation
    "retrieval-augmented", "retrieval augmented generation",
    # Tool / function use
    "tool use", "tool-augmented", "function calling",
    # Reasoning
    "chain-of-thought",
    # General LLM (broad but in a title = stronger signal)
    "large language model", "llm",
    # Industry / model releases
    "claude", "gpt-4", "gpt-5", "gemini", "anthropic", "openai",
]


def _keyword_match(item: ResearchItem) -> bool:
    """Return True if any keyword appears in the item's TITLE (not summary)."""
    title = item.title.lower()
    return any(kw in title for kw in TITLE_KEYWORDS)


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
    # Multi-agent memory and fleet context sharing
    "https://export.arxiv.org/api/query?search_query=all:multi-agent+memory+sharing+context&sortBy=submittedDate&sortOrder=descending&max_results=10",
    # Memory silos and collaborative agent memory
    "https://export.arxiv.org/api/query?search_query=all:collaborative+memory+LLM+agents&sortBy=submittedDate&sortOrder=descending&max_results=10",
    # Cross-agent trust and agent-to-agent security
    "https://export.arxiv.org/api/query?search_query=all:agent+trust+security+multi-agent+LLM&sortBy=submittedDate&sortOrder=descending&max_results=5",
]

ARXIV_CATEGORY_FEEDS = [
    "https://rss.arxiv.org/rss/cs.CL",   # Computation and Language
    "https://rss.arxiv.org/rss/cs.CV",   # Computer Vision
    "https://rss.arxiv.org/rss/cs.LG",   # Machine Learning
]

RSS_FEEDS = [
    "https://www.anthropic.com/news/rss.xml",
    "https://openai.com/blog/rss",
    "https://bair.berkeley.edu/blog/feed.xml",
    "https://research.google/blog/rss",
    "https://distill.pub/rss.xml",
    "https://martinfowler.com/feed.atom",
    "https://marktechpost.com/feed/",
    "https://www.artificialintelligence-news.com/feed/rss/",
    "https://machinelearningmastery.com/blog/feed/",
    "https://magazine.sebastianraschka.com/feed",
    "https://unit42.paloaltonetworks.com/rss/",
    "https://feeds.feedburner.com/TheHackersNews",
]

SEEN_PATH = _REPO_ROOT / "research" / "seen.json"
PRD_PATH = _REPO_ROOT / "PRD.md"
LESSONS_PATH = _REPO_ROOT / "lessons-learned.json"
METRICS_LOG_PATH = _REPO_ROOT / "research" / "metrics.jsonl"
PENDING_ISSUES_PATH = _REPO_ROOT / "research" / "pending-issues.json"


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run(
    min_score: int = 4,
    dry_run: bool = False,
    eval_model: str = "claude-haiku-4-5-20251001",
    extract_model: str = "claude-sonnet-4-6",
    max_age_days: int = 7,
    max_per_feed: int = 10,
    workers: int = 4,
    verbose: bool = False,
) -> dict:
    """Run the research watch pipeline and return a summary dict."""
    pipeline_start = time.monotonic()

    eval_llm = _make_adapter(eval_model)
    extract_llm = _make_adapter(extract_model)
    seen = load_seen(SEEN_PATH)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    # ── Fetch (with per-feed cap) ──────────────────────────────────────────
    fetch_start = time.monotonic()
    all_items: list[ResearchItem] = []
    for url in ARXIV_FEEDS + ARXIV_CATEGORY_FEEDS + RSS_FEEDS:
        try:
            items = fetch_feed(url)[:max_per_feed]
            all_items.extend(items)
            if verbose:
                print(f"  fetched {len(items):>3} items from {url[:65]}")
        except Exception as exc:
            print(f"  [warn] fetch failed for {url[:65]}: {exc}", file=sys.stderr)

    fetch_secs = time.monotonic() - fetch_start

    # ── Filter 1: seen + date window ───────────────────────────────────────
    after_date: list[ResearchItem] = []
    seen_keys_batch: set[str] = set()
    too_old = 0
    for item in all_items:
        key = item_key(item)
        if key in seen or key in seen_keys_batch:
            continue
        if not _is_recent(item, cutoff):
            too_old += 1
            continue
        seen_keys_batch.add(key)
        after_date.append(item)

    # ── Filter 2: keyword pre-screen (zero LLM cost) ──────────────────────
    deduped = [item for item in after_date if _keyword_match(item)]
    keyword_dropped = len(after_date) - len(deduped)

    print(
        f"Fetched {len(all_items)} items — "
        f"{too_old} too old, {keyword_dropped} no keyword match → "
        f"{len(deduped)} queued for LLM evaluation"
    )

    # ── Evaluate relevance (concurrent) ────────────────────────────────────
    eval_start = time.monotonic()
    seen_lock = threading.Lock()
    relevant: list[tuple[ResearchItem, int, str]] = []
    relevant_lock = threading.Lock()

    eval_errors = 0

    def _eval_one(item: ResearchItem):
        nonlocal eval_errors
        try:
            result = evaluate_item(eval_llm, item)
        except Exception as exc:
            print(f"  [warn] eval failed for {item.title[:60]!r}: {exc}", file=sys.stderr)
            with seen_lock:
                eval_errors += 1
            return
        with seen_lock:
            seen.add(item_key(item))
        if verbose:
            print(f"  [{result.score}/5] {item.title[:70]}")
        if result.score >= min_score:
            with relevant_lock:
                relevant.append((item, result.score, result.reason))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_eval_one, item) for item in deduped]
        for f in as_completed(futures):
            f.result()  # propagate unexpected non-eval exceptions only

    eval_secs = time.monotonic() - eval_start
    err_note = f", {eval_errors} eval errors" if eval_errors else ""
    print(f"{len(relevant)} items scored ≥ {min_score}  (eval took {eval_secs:.0f}s{err_note})")

    # ── Extract findings from relevant items ───────────────────────────────
    extract_start = time.monotonic()
    incorporated: list[tuple[ResearchItem, object]] = []
    all_lessons: list[dict] = []
    for item, score, reason in relevant:
        ext = extract_findings(extract_llm, item)
        incorporated.append((item, ext))
        all_lessons.extend(ext.lessons)
        if verbose:
            print(f"  extracted: {item.title[:60]}")

    extract_secs = time.monotonic() - extract_start

    # ── Write files ────────────────────────────────────────────────────────
    prd_updated = False
    lessons_updated = False
    today = date.today()

    if not dry_run:
        save_seen(SEEN_PATH, seen)
        if incorporated:
            prd_updated = update_prd(PRD_PATH, today, incorporated)
            lessons_updated = update_lessons(LESSONS_PATH, today, all_lessons)

    total_secs = time.monotonic() - pipeline_start

    summary = {
        "date": str(today),
        "fetched": len(all_items),
        "skipped_too_old": too_old,
        "skipped_no_keyword": keyword_dropped,
        "evaluated": len(deduped),
        "eval_errors": eval_errors,
        "relevant": len(relevant),
        "incorporated": len(incorporated),
        "prd_updated": prd_updated,
        "lessons_updated": lessons_updated,
        "dry_run": dry_run,
        "timing_secs": {
            "fetch": round(fetch_secs, 1),
            "evaluate": round(eval_secs, 1),
            "extract": round(extract_secs, 1),
            "total": round(total_secs, 1),
        },
        "relevant_items": [
            {"title": item.title, "url": item.url, "score": score, "reason": reason}
            for item, score, reason in relevant
        ],
    }

    # Append to metrics log
    if not dry_run:
        METRICS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with METRICS_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(summary) + "\n")

    # Write pending issues for incorporated items (workflow creates GitHub issues from this)
    if not dry_run and incorporated:
        pending = []
        for (item, score, reason), (_, ext) in zip(relevant, incorporated):
            pending.append({
                "title": item.title,
                "url": item.url,
                "score": score,
                "reason": reason,
                "key_findings": ext.key_findings,
                "agentctx_implications": ext.agentctx_implications,
                "prd_entry": ext.prd_entry,
            })
        PENDING_ISSUES_PATH.parent.mkdir(parents=True, exist_ok=True)
        PENDING_ISSUES_PATH.write_text(json.dumps(pending, indent=2), encoding="utf-8")

    return summary


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Fetch and evaluate but do not write any files")
    parser.add_argument("--min-score", type=int, default=4, metavar="N", help="Minimum relevance score to incorporate (1-5, default: 4)")
    parser.add_argument("--eval-model", default="claude-haiku-4-5-20251001", metavar="MODEL", help="Claude model for relevance scoring")
    parser.add_argument("--extract-model", default="claude-sonnet-4-6", metavar="MODEL", help="Claude model for finding extraction")
    parser.add_argument("--max-age-days", type=int, default=7, metavar="N", help="Only evaluate items published within this many days (default: 7)")
    parser.add_argument("--max-per-feed", type=int, default=10, metavar="N", help="Cap items taken from each feed before filtering (default: 10)")
    parser.add_argument("--workers", type=int, default=4, metavar="N", help="Concurrent evaluation workers (default: 4)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    summary = run(
        min_score=args.min_score,
        dry_run=args.dry_run,
        eval_model=args.eval_model,
        extract_model=args.extract_model,
        max_age_days=args.max_age_days,
        max_per_feed=args.max_per_feed,
        workers=args.workers,
        verbose=args.verbose,
    )

    t = summary["timing_secs"]
    print(f"\nTiming: fetch={t['fetch']}s  eval={t['evaluate']}s  extract={t['extract']}s  total={t['total']}s")

    print("\nRelevant items found:")
    if summary["relevant_items"]:
        for item in summary["relevant_items"]:
            print(f"  [{item['score']}/5] {item['title'][:70]}")
            print(f"         {item['url']}")
    else:
        print("  (none)")

    print(f"\nSummary: {summary['evaluated']} items evaluated, "
          f"{summary['relevant']} relevant, {summary['incorporated']} incorporated")

    if summary["incorporated"] > 0 and not summary["dry_run"]:
        print("Files updated: PRD.md, lessons-learned.json, research/seen.json, research/metrics.jsonl")


if __name__ == "__main__":
    main()
