"""agentctx HTTP server.

Run this alongside any application — Node.js, Go, Ruby, whatever —
to get context management over a simple JSON API.

Quick start:
    docker run -p 8001:8001 -e ANTHROPIC_API_KEY=sk-... agentctx/server

Or directly:
    pip install agentctx[server]
    python -m agentctx.server
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from agentctx import ContextManager, report_issue
from agentctx.adapters.claude import ClaudeAdapter
from agentctx.security import Sanitizer, TrustTier
from agentctx._version import __version__

STORAGE = Path(os.getenv("AGENTCTX_STORAGE", "/data/agentctx"))

llm = ClaudeAdapter()
sanitizer = Sanitizer()
app = FastAPI(title="agentctx", version=__version__)


def _ctx(session_id: str) -> ContextManager:
    return ContextManager(storage_path=STORAGE / session_id, llm=llm)


# ── Models ────────────────────────────────────────────────────────────────────

class ObserveRequest(BaseModel):
    session_id: str
    text: str

class MessageRequest(BaseModel):
    session_id: str
    role: str
    content: str

class SpotlightRequest(BaseModel):
    content: str
    tier: str   # "trusted" | "semi_trusted" | "untrusted"

class ReportRequest(BaseModel):
    error: str
    context: str = ""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Liveness probe."""
    return {"ok": True, "version": __version__}


@app.post("/observe")
def observe(req: ObserveRequest):
    """Append an observation to the session's persistent log."""
    _ctx(req.session_id).observe(req.text)
    return {"ok": True}


@app.post("/message")
def add_message(req: MessageRequest):
    """Add a chat message to the session. Triggers auto-compression when threshold is reached."""
    _ctx(req.session_id).add_message({"role": req.role, "content": req.content})
    return {"ok": True}


@app.get("/prefix/{session_id}")
def prefix(session_id: str):
    """
    Return the stable observation-log prefix (Block 1).
    Prepend this to every LLM system prompt — it is designed to be token-cache-friendly.
    """
    return {"prefix": _ctx(session_id).build_prefix()}


@app.post("/spotlight")
def spotlight(req: SpotlightRequest):
    """
    Wrap content in trust-tier XML before it reaches the LLM.

    Tiers:
    - trusted: system-controlled content, no injection stripping
    - semi_trusted: tool outputs, database results — injection-stripped
    - untrusted: user input, web pages, uploaded docs — injection-stripped
    """
    return {"content": sanitizer.spotlight(req.content, TrustTier(req.tier))}


@app.post("/report")
def report(req: ReportRequest):
    """Auto-file a bug report in the agentctx GitHub repo."""
    url = report_issue(RuntimeError(req.error), context=req.context)
    return {"issue_url": url}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8001")))
