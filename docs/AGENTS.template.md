# AGENTS.md
<!--
  Copy this file to the root of your project as AGENTS.md.
  Fill in every <!-- FILL IN --> section. Delete comments when done.
  This file is read by AI agents (Claude, Cursor, Copilot, etc.) before
  they touch your code. The more specific you are, the better they perform.
-->

This file provides guidance to AI agents working in this repository.

---

## Project

<!-- FILL IN: One sentence. What does this do and for whom? -->
**[Project name]** — [what it does, who uses it, current status].

**Repo:** <!-- FILL IN: GitHub URL -->
**Stack:** <!-- FILL IN: e.g. Node.js 20 / PostgreSQL / React -->
**Docs:** <!-- FILL IN: link to PRD, wiki, Notion, etc. or "none yet" -->

---

## Architecture

<!-- FILL IN: List the main components and how they relate. -->
<!--
Example:
- **API**: Express.js on port 3000 — src/api/
- **Workers**: Background job processor — src/workers/
- **Database**: PostgreSQL 16 + pgvector — accessed via Prisma
- **Auth**: JWT, tokens validated in src/auth/middleware.ts
- **External services**: Stripe (payments), SendGrid (email), S3 (uploads)
-->

### Key directories

| Path | What lives there |
|---|---|
| <!-- path --> | <!-- description --> |
| <!-- path --> | <!-- description --> |

### External dependencies

<!-- FILL IN: Services this repo talks to but doesn't own -->
| Service | Purpose | How to reach it |
|---|---|---|
| <!-- name --> | <!-- purpose --> | <!-- host:port or env var --> |

---

## Context Management (agentctx)

This project uses **agentctx** for AI agent context management, input sanitization,
and automatic bug reporting.

- **agentctx docs:** https://github.com/aiconceptsonline/agentctx
- **HTTP API reference:** https://github.com/aiconceptsonline/agentctx/blob/main/docs/http-api.md

<!-- Pick ONE of the two blocks below and delete the other. -->

<!-- ── OPTION A: TypeScript / non-Python project (HTTP sidecar) ── -->
agentctx runs as a Python sidecar (`services/agentctx/`) called over HTTP.

| File | Purpose |
|---|---|
| `services/agentctx/main.py` | FastAPI sidecar — do not edit unless upgrading |
| `services/agentctx/requirements.txt` | Pins the agentctx version |
| `services/agentctx/Dockerfile` | Sidecar container |
| `src/lib/agentctx.ts` | TypeScript client — import this in application code |

```typescript
import { agentctx } from '@/lib/agentctx';

// Sanitize external content before it reaches the LLM
const safeInput = await agentctx.spotlight(userQuery,       'untrusted');
const safeData  = await agentctx.spotlight(dbOrApiResult,   'semi_trusted');

// Prepend observation log to every LLM system prompt
const system = await agentctx.prefix(sessionId);

// Record significant events (persisted, survive restarts)
await agentctx.observe(sessionId, '🟢 Step completed');
await agentctx.observe(sessionId, '🔴 Step failed: reason');

// Auto-file bug reports (safe in catch blocks, never throws)
await agentctx.report(err, '[Project] context of what was happening');
```

<!-- ── OPTION B: Python project (native library) ── -->
<!--
```python
from agentctx import ContextManager
from agentctx.security import Sanitizer, TrustTier

sanitizer = Sanitizer()
ctx = ContextManager(storage_path=".agentctx/session", llm=your_llm)

safe_input = sanitizer.spotlight(user_input, TrustTier.UNTRUSTED)
safe_data  = sanitizer.spotlight(db_result,  TrustTier.SEMI_TRUSTED)
prefix     = ctx.build_prefix()
ctx.observe("🟢 Step completed")
```
-->

### Trust tiers — what goes in each

| Tier | Use for in this project |
|---|---|
| `trusted` | <!-- FILL IN: e.g. system prompts, hardcoded instructions --> |
| `semi_trusted` | <!-- FILL IN: e.g. database query results, internal API responses --> |
| `untrusted` | <!-- FILL IN: e.g. user input, uploaded files, scraped web content --> |

### Upgrading agentctx

1. Check https://github.com/aiconceptsonline/agentctx/releases
2. Update the wheel URL in `services/agentctx/requirements.txt`
3. `docker compose build agentctx && docker compose up -d agentctx`

### Required environment variables / secrets

```
ANTHROPIC_API_KEY          — LLM calls made by the sidecar
AGENTCTX_GITHUB_TOKEN      — GitHub PAT with issues:write on aiconceptsonline/agentctx
                             (enables agentctx.report() to auto-file bugs upstream)
```

---

## Conventions

<!-- FILL IN: The rules an agent must follow to not break things. -->
<!-- Be specific — vague rules get ignored. -->

### Must always
- <!-- e.g. "Run the test suite before marking work complete" -->
- <!-- e.g. "Never commit secrets — all secrets come from Vault/env" -->
- <!-- e.g. "Use UUIDs for all primary keys" -->
- Any code that calls an LLM must pass inputs through `agentctx.spotlight()` first

### Must never
- <!-- e.g. "Never modify the Prisma schema without a migration" -->
- <!-- e.g. "Never push directly to main — always open a PR" -->
- Commit `AGENTCTX_GITHUB_TOKEN` or `ANTHROPIC_API_KEY` to source control

### Patterns to follow
- <!-- e.g. "API endpoints go in src/api/, one file per resource" -->
- <!-- e.g. "Errors are logged then re-thrown — don't swallow them" -->

---

## Working in this repo

### Running locally

```bash
# FILL IN: how to start the project
# e.g.:
docker compose up --build
```

### Running tests

```bash
# FILL IN: test command
# e.g.:
npm test
```

### Making changes

1. <!-- FILL IN: e.g. "Branch from main, name it feat/description or fix/description" -->
2. <!-- FILL IN: e.g. "Open a PR — CI must pass before merge" -->
3. <!-- FILL IN: e.g. "Tag PRs with the relevant GitHub issue number" -->

---

## Open questions / known issues

<!-- FILL IN: Things an agent should know are unresolved or in flux. -->
<!-- This prevents agents from "fixing" things that are intentionally incomplete. -->
- <!-- e.g. "Auth middleware is stubbed — do not rely on req.user being populated yet" -->
- <!-- e.g. "Worker queue is not yet wired to the database — in progress" -->

---

## Reporting agentctx issues

If agentctx behaves unexpectedly (wrong output, crashes, injection not stripped),
call `agentctx.report(err, context)` in code, or open an issue directly at
https://github.com/aiconceptsonline/agentctx/issues/new/choose.
