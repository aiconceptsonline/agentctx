from __future__ import annotations

import json
from dataclasses import dataclass, field

from agentctx.adapters.base import LLMAdapter
from agentctx.research.fetcher import ResearchItem

# ── Prompts ──────────────────────────────────────────────────────────────────

_RELEVANCE_SYSTEM = """\
You are a relevance classifier for the agentctx Python library.

agentctx is the framework-agnostic memory and context layer for AI agents.
It solves these problems:
1. Observational memory — compressing session history into a stable, cacheable
   observation log (Block 1 prefix)
2. Run state checkpointing — resuming multi-step pipelines after failures
3. Fleet memory — shared context bus across a fleet of specialized agents,
   with per-agent private logs, cross-agent trust boundaries, and context
   budget enforcement on handoffs (memory silos problem)
4. Security — sanitizing inputs before they enter the observation log, tamper
   detection, provenance tagging, semantic intent anchoring, cross-agent
   semi-trusted tier to prevent injection propagation across agents
5. Context engineering — maximising token utility in the agent's context window
   (Write / Read / Select / Compress / Isolate strategies)

agentctx is NOT an orchestration framework — it does not route tasks or define
workflows. It is the memory substrate that sits below LangGraph, AutoGen,
Swarm, or any other orchestrator.

Rate the relevance of the item below on a 1–5 scale:
  5 = directly relevant; finding should change the library design
  4 = clearly relevant; worth incorporating into the PRD
  3 = tangentially related; good background context
  2 = slightly related; probably not actionable
  1 = not relevant

Reply with ONLY a valid JSON object — no markdown fences:
{"score": <1-5>, "reason": "<one concise sentence>"}\
"""

_EXTRACT_SYSTEM = """\
You are a research analyst for the agentctx Python library.

agentctx provides: observational memory, run state checkpointing, fleet memory
(shared context bus across agent fleets with cross-agent trust boundaries),
input sanitisation, and context engineering for AI agents. It is the
framework-agnostic memory substrate — not an orchestrator.

Analyse the paper or post below and extract actionable intelligence.

Reply with ONLY a valid JSON object — no markdown fences:
{
  "key_findings": ["<finding 1>", "<finding 2>"],
  "agentctx_implications": ["<implication 1>", "<implication 2>"],
  "prd_entry": "<one-paragraph summary for the PRD §10 research changelog, or null>",
  "lessons": [
    {"lesson": "...", "context": "...", "resolution": "...", "rule": "..."}
  ]
}\
"""


# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class RelevanceResult:
    score: int         # 1–5
    reason: str
    raw: str = ""      # raw LLM response, for debugging


@dataclass
class ExtractionResult:
    key_findings: list[str] = field(default_factory=list)
    agentctx_implications: list[str] = field(default_factory=list)
    prd_entry: str | None = None
    lessons: list[dict] = field(default_factory=list)
    raw: str = ""


# ── Functions ─────────────────────────────────────────────────────────────────

def evaluate_item(llm: LLMAdapter, item: ResearchItem) -> RelevanceResult:
    """Score an item's relevance to agentctx (1–5)."""
    user_msg = f"Title: {item.title}\n\nSummary:\n{item.summary}"
    raw = llm.call([{"role": "user", "content": user_msg}], system=_RELEVANCE_SYSTEM)
    return _parse_relevance(raw)


def extract_findings(llm: LLMAdapter, item: ResearchItem) -> ExtractionResult:
    """Extract key findings and agentctx implications from a relevant item."""
    user_msg = f"Title: {item.title}\nURL: {item.url}\n\nSummary:\n{item.summary}"
    raw = llm.call([{"role": "user", "content": user_msg}], system=_EXTRACT_SYSTEM)
    return _parse_extraction(raw)


# ── Internal parsers ──────────────────────────────────────────────────────────

def _extract_json(raw: str) -> str:
    """Return the first {...} JSON object found in raw, or raw itself."""
    import re
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    return m.group(0) if m else raw.strip()


def _parse_relevance(raw: str) -> RelevanceResult:
    try:
        data = json.loads(_extract_json(raw))
        return RelevanceResult(
            score=max(1, min(5, int(data["score"]))),
            reason=str(data.get("reason", "")),
            raw=raw,
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return RelevanceResult(score=1, reason="parse error", raw=raw)


def _parse_extraction(raw: str) -> ExtractionResult:
    try:
        data = json.loads(_extract_json(raw))
        return ExtractionResult(
            key_findings=list(data.get("key_findings", [])),
            agentctx_implications=list(data.get("agentctx_implications", [])),
            prd_entry=data.get("prd_entry") or None,
            lessons=[l for l in data.get("lessons", []) if isinstance(l, dict)],
            raw=raw,
        )
    except (json.JSONDecodeError, KeyError):
        return ExtractionResult(raw=raw)
