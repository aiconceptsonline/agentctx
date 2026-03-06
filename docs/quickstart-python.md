# Quickstart — Python

Install directly from the latest GitHub Release:

```bash
pip install "agentctx @ https://github.com/aiconceptsonline/agentctx/releases/download/v0.1.1/agentctx-0.1.1-py3-none-any.whl"
```

Or once on PyPI:

```bash
pip install agentctx
```

---

## Core usage

```python
from agentctx import ContextManager
from agentctx.adapters.claude import ClaudeAdapter
from agentctx.security import Sanitizer, TrustTier

llm = ClaudeAdapter()  # reads ANTHROPIC_API_KEY from env
sanitizer = Sanitizer()

ctx = ContextManager(
    storage_path=".agentctx/my-session",
    llm=llm,
    task_anchor="Summarise HOA documents for the user",
)

# Sanitize inputs before they enter the LLM context
user_input  = sanitizer.spotlight(raw_user_query, TrustTier.UNTRUSTED)
doc_content = sanitizer.spotlight(retrieved_doc,  TrustTier.SEMI_TRUSTED)

# Record what happened (persisted to disk, survives restarts)
ctx.observe("🟢 Retrieved 3 HOA documents from pgvector")

# Get the stable prefix to prepend to every LLM call
prefix = ctx.build_prefix()

response = llm.call(
    messages=[{"role": "user", "content": f"{user_input}\n\n{doc_content}"}],
    system=prefix,
)

ctx.observe(f"🟢 Answered query: {raw_user_query[:60]}")
```

---

## Auto-report bugs

```python
from agentctx import report_issue

try:
    ctx.add_message(msg)
except Exception as exc:
    report_issue(exc, context="HOA document retrieval pipeline")
    raise
```

Requires `gh` CLI authenticated, or `AGENTCTX_GITHUB_TOKEN` set to a token
with `issues:write` on `aiconceptsonline/agentctx`.

---

## What gets persisted

Each session writes to `storage_path/`:

```
.agentctx/
  my-session/
    observation_log.json   # structured event log
    audit.json             # tamper-detection audit trail
    run_state.json         # checkpointed step records
```

Sessions are portable — copy the directory to resume on another machine.
