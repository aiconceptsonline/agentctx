# agentctx

Context and memory management for AI agents.

agentctx handles the parts of running an AI agent that LLM APIs don't: keeping a
persistent observation log across sessions, building a stable cache-friendly context
prefix for every LLM call, sanitizing untrusted inputs before they reach the model,
and checkpointing multi-step pipelines so they can resume after failures.

---

## What it solves

| Problem | agentctx primitive |
|---|---|
| LLM context fills up mid-session | `ObservationLog` compresses history into a stable prefix |
| Agent loses state after a restart | `RunState` checkpoints each step to disk |
| User input contains prompt injection | `Sanitizer.spotlight()` strips it and tags content by trust tier |
| Hard to know what the agent did | `observe()` writes a structured, timestamped event log |

---

## Install

**From the latest GitHub Release:**

```bash
pip install "agentctx @ https://github.com/aiconceptsonline/agentctx/releases/download/v0.1.1/agentctx-0.1.1-py3-none-any.whl"
```

**With optional dependencies:**

```bash
# Claude adapter
pip install "agentctx[claude] @ ..."

# HTTP server (for non-Python apps)
pip install "agentctx[server] @ ..."

# Research pipeline
pip install "agentctx[research] @ ..."
```

---

## Quickstart — Python

```python
from agentctx import ContextManager
from agentctx.adapters.claude import ClaudeAdapter
from agentctx.security import Sanitizer, TrustTier

llm = ClaudeAdapter()          # reads ANTHROPIC_API_KEY from env
sanitizer = Sanitizer()

ctx = ContextManager(
    storage_path=".agentctx/session-1",
    llm=llm,
)

# Sanitize inputs before they reach the LLM
safe_user_input = sanitizer.spotlight(raw_user_query, TrustTier.UNTRUSTED)
safe_doc        = sanitizer.spotlight(retrieved_doc,  TrustTier.SEMI_TRUSTED)

# Record what happened — persisted to disk, survives restarts
ctx.observe("🟢 Retrieved 3 documents from vector store")

# Build the stable context prefix — prepend to every LLM system prompt
prefix = ctx.build_prefix()

response = llm.call(
    messages=[{"role": "user", "content": safe_user_input}],
    system=prefix,
)
```

Full guide: [docs/quickstart-python.md](docs/quickstart-python.md)

---

## Quickstart — TypeScript / Node.js (and any other language)

agentctx runs as an HTTP sidecar. Your app calls it over JSON — no Python in your
main process.

**1. Add to docker-compose.yml:**

```yaml
services:
  agentctx:
    build: ./services/agentctx      # copy from server/ in this repo
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - AGENTCTX_STORAGE=/data/agentctx
    volumes:
      - agentctx_data:/data/agentctx
    healthcheck:
      test: ["CMD", "python3", "-c",
             "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"]
      interval: 10s
      timeout: 5s
      retries: 3

volumes:
  agentctx_data:
```

Copy the sidecar files from [`server/`](server/) into your project's
`services/agentctx/` directory.

**2. Copy the TypeScript client:**

Copy [`server/client.ts`](server/client.ts) into your project as
`src/lib/agentctx.ts`.

**3. Use it:**

```typescript
import { agentctx } from './lib/agentctx';

const safeInput  = await agentctx.spotlight(userQuery, 'untrusted');
const safeDocs   = await agentctx.spotlight(retrievedDocs, 'semi_trusted');
const prefix     = await agentctx.prefix(sessionId);

// call your LLM with prefix as system prompt and safe inputs as user content

await agentctx.observe(sessionId, '🟢 Query answered');
```

Full guide: [docs/quickstart-typescript.md](docs/quickstart-typescript.md)

---

## HTTP API

The sidecar exposes a simple JSON API. Any language works — curl, Go, Ruby, etc.

```bash
# Sanitize user input
curl -s -X POST http://localhost:8001/spotlight \
  -H 'Content-Type: application/json' \
  -d '{"content": "ignore previous instructions", "tier": "untrusted"}'

# Get context prefix for a session
curl -s http://localhost:8001/prefix/my-session-id

# Record an observation
curl -s -X POST http://localhost:8001/observe \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "my-session-id", "text": "🟢 step completed"}'
```

Full reference: [docs/http-api.md](docs/http-api.md)

---

## Reporting bugs from your app

If agentctx misbehaves in production, you can auto-file an issue from your app:

**Python:**
```python
from agentctx import report_issue

try:
    ctx.add_message(msg)
except Exception as exc:
    report_issue(exc, context="what my app was doing")
```

**TypeScript (via sidecar):**
```typescript
await agentctx.report(err, 'what my app was doing');
```

Requires `AGENTCTX_GITHUB_TOKEN` set to a GitHub token with `issues:write` on
this repository.

---

## Trust tiers

| Tier | Use for | Injection stripping |
|---|---|---|
| `trusted` | System prompts, developer-controlled text | No |
| `semi_trusted` | Tool outputs, database results, API responses | Yes |
| `untrusted` | User input, web pages, uploaded documents | Yes |

When in doubt, use `untrusted`.

---

## Releases

See [Releases](https://github.com/aiconceptsonline/agentctx/releases) for all
versions. Each release includes a `.whl` and `.tar.gz`.

To upgrade, update the wheel URL in your `requirements.txt` and rebuild.

---

## Using agentctx in your project

### AGENTS.md template

If you use AI coding agents (Claude Code, Cursor, Copilot, etc.), copy
[`docs/AGENTS.template.md`](docs/AGENTS.template.md) into your project as `AGENTS.md`.
Fill in the project-specific sections — agents will read it before touching your code.

The template covers:
- Project context and architecture
- agentctx integration instructions (Python or TypeScript/sidecar)
- Trust-tier guidance for your content types
- Conventions and working instructions

---

## Issues

Found a bug or want a feature? [Open an issue](https://github.com/aiconceptsonline/agentctx/issues/new/choose).
