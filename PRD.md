# PRD: agentctx

**Status:** Living Document · **Last updated:** 2026-02-24
**Owner:** Tommy

> This document is updated continuously as context engineering research
> matures. See [§10 Research Changelog](#10-research-changelog) for a
> log of significant updates.

---

## 1. What Is This

`agentctx` is a **standalone Python library for multi-agent context and
memory management**.

It solves one problem: keeping AI agents coherent and cost-efficient
across long-running, multi-step tasks — without a vector database,
without an external memory service, and without being tied to any
specific agent framework or LLM provider.

Any project drops it in, configures a storage path, and gets persistent
observational memory, agent state checkpointing, and a stable cacheable
context prefix — in under 20 lines of code.

---

## 2. Problem

Every new agent project rebuilds the same plumbing:

- How do I keep the agent from forgetting what happened three sessions
  ago?
- How do I avoid sending the entire conversation history every turn
  (cost)?
- How do I resume a multi-step pipeline after a crash on step 4 of 9?
- How do I make agents learn from patterns across runs, not just the
  current run?
- How do I prevent the observation log from becoming an injection
  surface?

RAG solves some of this but requires a vector database, changes the
prompt prefix every turn (breaking provider caching), and optimizes for
retrieval over continuity. It is the wrong primitive for agents that
need to *accumulate understanding* rather than *search a corpus*.

---

## 3. Goal

A pip-installable Python library that provides:

1. **Observational Memory** — compresses session history into a dated,
   prioritized log that stays as a stable prefix in every agent's
   context window
2. **Run State** — checkpoints each step of a multi-agent pipeline so
   partial failures resume from the last good state, not from scratch
3. **Provider-agnostic** — works with Claude, Gemini, OpenAI, or any
   model via a thin adapter
4. **Zero infrastructure** — no vector DB, no Redis, no external
   service; storage is plain files on disk (git-trackable by design)
5. **Pluggable** — integrates into existing pipelines as a wrapper, not
   a framework you must adopt wholesale
6. **Secure by default** — sanitizes inputs before they enter the
   observation log, enforces trust boundaries between agents, and treats
   the context window as an attack surface

**Out of scope:**

- Agent orchestration / workflow definition (not a LangGraph
  replacement)
- Tool use / function calling management
- Model fine-tuning or training
- Multi-tenant / cloud-hosted memory service
- Real-time streaming context updates

---

## 4. Architecture

### 4.1 Core Components

```text
agentctx/
├── memory/
│   ├── observation_log.py   # read/write/append to observations.md
│   ├── observer.py          # Agent: compresses messages → observations
│   └── reflector.py         # Agent: prunes/restructures observation log
├── security/
│   ├── sanitizer.py         # strips injection payloads before storage
│   ├── anchor.py            # semantic intent anchoring per session
│   ├── audit.py             # append-only audit log of all writes
│   └── provenance.py        # tags every memory write with source + trust level
├── session/
│   ├── run_state.py         # checkpoint individual pipeline steps
│   └── context_builder.py   # assembles final context window for any agent
├── adapters/
│   ├── base.py              # LLMAdapter protocol (call, stream)
│   ├── claude.py            # Anthropic SDK adapter
│   ├── gemini.py            # Google GenAI adapter
│   └── openai.py            # OpenAI SDK adapter
└── config.py                # thresholds, storage path, model config
```

### 4.2 Context Window Layout

Every agent that uses `agentctx` receives a context window structured
as two blocks:

```text
┌─────────────────────────────────────────────────────────────────┐
│  BLOCK 1 — Observation Log  (stable, cacheable prefix)          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ 🔴 2026-02-18 [event:2026-02-17]: Scrape failed on       │  │
│  │    paywalled WSJ links; use archive.ph fallback           │  │
│  │ 🟡 2026-02-15 [event:2026-02-15]: Ransomware cluster     │  │
│  │    appeared in 3 consecutive runs — trend to track        │  │
│  │ 🟢 2026-02-10 [event:2026-02-10]: Run #47 completed      │  │
│  │    in 4m 12s, 9 items, all steps succeeded                │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  BLOCK 2 — Current Session  (rolling window)                    │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  [raw messages from this run only]                        │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

Block 1 is append-only between Reflector passes. The stable prefix
enables **provider prompt caching**, delivering 4–10× token cost
reduction compared to RAG approaches where the prefix changes every
turn.

### 4.3 Observer Agent

Fires automatically when unobserved messages exceed a configurable
token threshold (default: 30K).

- Reads new messages since the last observation pass
- Extracts key facts, decisions, errors, and patterns
- Sanitizes content before writing (see §5 Security)
- Writes dated, priority-tagged observations to `observations.md`
- Drops the raw messages it has processed (keeps Block 2 lean)

### 4.4 Reflector Agent

Fires when the observation log exceeds a configurable size (default:
40K tokens).

- Reads the full observation log
- Merges related observations, removes superseded ones
- Rewrites the log in place (this is the only destructive write)
- Preserves the priority markers and date metadata

### 4.5 Priority System

Observations carry a single emoji marker:

| Marker | Meaning | Example |
| --- | --- | --- |
| 🔴 | Must influence next run (errors, critical decisions) | "Upload failed: expired OAuth token" |
| 🟡 | Potentially relevant pattern (trends, signals) | "Items with no URL produce weaker narrations" |
| 🟢 | Background context (timing, routine metadata) | "Run #52 completed in 3m 48s" |

### 4.6 Three-Date Model

Each observation carries three timestamps to support temporal
reasoning:

```text
🟡 observed_on:2026-02-18 event_date:2026-02-15 relative:3_days_ago
```

- `observed_on` — when Observer wrote this entry
- `event_date` — when the underlying thing happened
- `relative` — human-readable lag, computed fresh at context-build time

### 4.7 Run State (Checkpointing)

Each pipeline step writes a state record before completing:

```json
{
  "run_id": "run-2026-02-20",
  "status": "in_progress",
  "steps": {
    "parse":     { "done": true,  "result": "..." },
    "research":  { "done": true,  "result": "..." },
    "summarize": { "done": false, "result": null  }
  }
}
```

On restart, the pipeline reads state and skips completed steps. No
custom database needed — state is a JSON file on disk.

### 4.8 Context Engineering Principles

Context engineering is the discipline of curating and maintaining the
optimal set of tokens in an agent's context window at each point in
time. It is a superset of prompt engineering: prompt engineering is
about *what you say to the model*; context engineering is about *what
the model knows when you say it*.

Anthropic defines the core challenge: context is a finite resource, and
the engineering problem is maximizing the utility of those tokens
against LLM constraints to consistently achieve a desired outcome.
Unmanaged, context "rots" — early instructions are drowned out,
irrelevant history accumulates, and agents become incoherent.

`agentctx` implements five strategies derived from Manus's production
experience and Anthropic's context engineering guidance:

| Strategy | What | How agentctx implements it |
| --- | --- | --- |
| **Write** | Externalize memory to disk | Observation log + run state JSON |
| **Read** | Load only what is needed | `ContextBuilder` injects Block 1 prefix selectively |
| **Select** | Use a stable, small tool surface | Observer/Reflector/ContextManager are the only three entry points |
| **Compress** | Shrink without losing restorability | Observer drops raw messages but preserves URLs and file paths in observations so content is re-fetchable |
| **Isolate** | Separate context per agent/task | Each agent call receives only its relevant context block; no agent sees another's full history |

The compress principle is critical for security as well as cost: by
retaining a URL or file path instead of raw content, compression is
*reversible* — the agent can re-fetch on demand — while also preventing
large, potentially-injected payloads from persisting indefinitely.

---

## 5. Security

The context window is an attack surface. Any content that flows into
the observation log — scraped articles, tool outputs, external API
responses — is untrusted input. A compromised observation poisons every
future agent call that reads it.

Martin Fowler identifies a **Lethal Trifecta** that creates maximum
exposure: an agent that simultaneously (1) has access to sensitive data,
(2) is exposed to untrusted content, and (3) can externally communicate.
When all three exist, an attacker can embed instructions in untrusted
content that cause the agent to exfiltrate sensitive data silently.

Cisco's 2026 AI Security Report identified MCP and agent memory as the
primary emerging attack surface: attackers are "moving deeper into a
model's memory" as prompt injection defenses improve at the surface
layer. NIST evaluations confirm that even hardened frontier models reach
81% attack success rates under novel adaptive attacks. The HackerNoon
analysis of agent failures reinforces this: agents without bounded,
validated context go off the rails predictably.

The MemoryGraft paper (arxiv 2512.16962) demonstrates the most
concerning attack class: planting poisoned "successful experience"
records in long-term memory so future sessions load malicious patterns
via normal retrieval — the compromise persists indefinitely across
restarts without explicit memory purging.

### 5.1 Threat Model

| Threat | Vector | Impact |
| --- | --- | --- |
| Indirect prompt injection | Malicious text in scraped content flows into observation log | Agent follows attacker instructions on future runs |
| Memory poisoning (MemoryGraft) | Poisoned "successful experience" written to long-term memory | Malicious patterns surface on every future retrieval |
| Session summarization hijack | Attacker-controlled page manipulates the Observer's compression output | Injected instructions persist into long-term observation log |
| Observation log poisoning | Attacker writes to `observations.md` directly (file access) | Persistent compromise of all future context |
| Context drift | Agent loses track of original task intent over many turns | Unintended actions, silent scope creep |
| Session smuggling (A2A) | Multi-turn agent session used to covertly inject instructions | Agent executes unauthorized actions without user awareness |
| Replay / state tampering | Run state JSON modified to skip security steps | Malicious pipeline resumption |
| Supply chain (MCP/adapters) | Malicious LLM adapter package BCC's messages off-system | Silent data exfiltration |

### 5.2 Controls

#### Input sanitization

Before any content touches the observation log:

- Strip known prompt injection patterns from external content before
  Observer processes it,
- Enforce a character/token budget per observation entry — long
  injections are truncated and flagged 🔴
- External content (scrapes, tool outputs, API responses) is always
  wrapped in explicit `<external_content>` delimiters before entering
  the context window so the model can distinguish data from instructions

#### Semantic intent anchoring

- At session start, `ContextManager` creates a *task anchor*: a
  one-sentence hash of the original user intent
- Each agent turn, the anchor is validated against the current
  instruction before execution
- Significant semantic drift raises a `ContextDriftWarning` and logs a
  🔴 observation — the caller decides whether to abort or continue

#### Audit log

- Every write to `observations.md` appends a record to
  `memory/audit.jsonl`: timestamp, write source (observer/reflector/
  manual), character delta, and a SHA-256 hash of the new log state
- Audit log is append-only; there is no delete API
- The `agentctx inspect` CLI can verify log integrity against the audit
  trail

#### Observation log integrity

- File permissions on `memory/` default to `700` (owner-only
  read/write)
- `agentctx` refuses to load an observation log whose current hash does
  not match the last audit entry (tamper detection)

#### Adapter hygiene

- All LLM adapters are pinned dependencies with hashes in
  `pyproject.toml`
- No adapter is allowed to make network calls outside of the configured
  LLM endpoint — enforced by the adapter protocol (no arbitrary
  `requests` / `httpx` usage)
- The `ClaudeAdapter`, `GeminiAdapter`, and `OpenAIAdapter` are
  maintained in this repo; third-party adapters must be explicitly
  opted into

#### Provenance tagging

Inspired by MemoryGraft research: every write to the observation log is
tagged with its source and an assigned trust level before storage.

```json
{
  "source": "observer",
  "trust": "internal",
  "origin_url": null,
  "timestamp": "2026-02-20T14:32:00Z",
  "sha256": "..."
}
```

Trust levels: `internal` (generated by Observer/Reflector) vs.
`external` (derived from scraped/tool content). The Reflector and any
future retrieval path can filter or weight entries by trust level.
External-trust observations are flagged in the log with `[EXT]` so the
model has explicit signal about provenance.

#### Memory tier promotion controls

Observations start as session-scoped (Block 2). Promotion to the
persistent observation log (Block 1) requires passing sanitization and
provenance checks. This mirrors the MemoryGraft defense of requiring
elevated trust before promoting session data to long-term storage.

#### Least privilege for agents

- Observer and Reflector are read-only consumers of the message log;
  they cannot call tools or access the network
- Only the Orchestrator (caller-supplied) has write access to run state
- Agents receive only the blocks of context they need — no agent sees
  another agent's full message history by default
- External content never directly writes to Block 1 — it must pass
  through Observer sanitization first

### 5.3 What We Do Not Solve

- **Adaptive attacks**: NIST evaluations show all static defenses break
  at 50–81% success under novel adaptive attacks (arXiv 2503.00061).
  Our sanitizer blocks known patterns but is not a guarantee. Defense
  in depth — minimizing agent capabilities and sensitive data access —
  remains the caller's responsibility.
- End-to-end encryption of observation files at rest (caller's
  responsibility)
- Authentication / authorization between agents in distributed /
  multi-host deployments
- Network-layer security for the LLM API calls
- A2A / agent-to-agent session security (session smuggling is an
  application-layer concern for the orchestrating system)

---

## 6. Public API

### Installation

```bash
pip install agentctx          # PyPI (target)
# or
pip install git+https://github.com/tspeigner/agentctx
```

### Minimal integration (any project)

```python
from agentctx import ContextManager, RunState
from agentctx.adapters.claude import ClaudeAdapter

# 1. Initialize once per project
ctx = ContextManager(
    storage_path="./memory",
    llm=ClaudeAdapter(model="claude-haiku-4-5"),
    observer_threshold=30_000,    # tokens before Observer fires
    reflector_threshold=40_000,   # observation tokens before Reflector
    task_anchor="Summarize security news into a YouTube episode script",
)

# 2. Add to any agent's system prompt
system_prompt = ctx.build_prefix() + "\n\nYour task: ..."

# 3. After each agent turn, record what happened
ctx.add_message(role="assistant", content=response)

# 4. Checkpoint pipeline steps
state = RunState(run_id="my-run-001", storage_path="./runs")
state.complete("parse", result=parsed_data)

# 5. Resume from last good step
completed = state.completed_steps()  # ["parse"]
```

### Standalone observation write (manual)

```python
ctx.observe("🔴 OAuth token expired during upload step",
            event_date="2026-02-20")
```

---

## 7. Storage Layout

```text
./memory/
  observations.md         # plain text observation log (append-only)
  audit.jsonl             # append-only integrity audit trail
  sessions/
    <run-id>.jsonl        # per-run message log (pre-compression)

./runs/
  <run-id>.json           # pipeline step checkpoint state
```

All files are plain text or JSON. Git-trackable. No binary formats.
`memory/` is created with `700` permissions by default.

---

## 8. Implementation Phases

### Phase 0 — Foundation

- [x] Repo scaffold: `pyproject.toml`, `src/agentctx/`, tests, CI
- [x] `ObservationLog`: read, append, overwrite (Reflector), parse
      priority/dates
- [x] `AuditLog`: append-only JSONL, hash verification
- [x] `ContextBuilder`: assemble Block 1 + Block 2 into a single string
- [x] `RunState`: load/save JSON checkpoint, `complete()`,
      `completed_steps()`
- [x] File permission enforcement on `memory/` creation

### Phase 1 — Observer + Reflector

- [x] `LLMAdapter` protocol + Claude and Gemini implementations
- [x] `Sanitizer`: strip injection patterns, wrap external content in
      delimiters, enforce entry token budget
- [x] `Observer` agent: token-count trigger, compress messages →
      observations (sanitized)
- [x] `Reflector` agent: size trigger, restructure observation log
- [x] `ContextManager`: wires everything together, exposes public API,
      creates task anchor on init

### Phase 2 — Integration + Security Testing

- [ ] Adapt `auto-yt-security-xforce` to use `agentctx` (real-world
      validation)
- [ ] Measure token cost delta before/after (target: ≥ 40% reduction)
- [ ] LongMemEval-style eval: recall facts from 10 runs ago
- [ ] Injection red-team: feed crafted payloads through the scraper
      path and verify sanitizer blocks them
- [ ] Audit log integrity check: tamper `observations.md` out-of-band,
      verify load raises `TamperDetectedError`
- [ ] OpenAI adapter

### Phase 3 — Hardening + CLI

- [ ] Async support (`aio` variants of all blocking calls)
- [ ] Thread-safe file writes (file lock or SQLite as optional backend)
- [ ] `agentctx inspect ./memory` — pretty-print observation log with
      integrity status
- [ ] `agentctx replay ./runs/<id>` — show step-by-step state history
- [ ] Semantic drift CI check: flag observation log divergence from
      task anchor over time

---

## 9. Success Metrics

| Metric | Target |
| --- | --- |
| Token cost with caching vs. without | ≥ 4× reduction on repeated prefixes |
| Observation compression ratio | 3–10× depending on content type |
| Pipeline resume after mid-run failure | Resumes from failed step |
| Integration effort for a new project | < 20 lines of code |
| LongMemEval-style recall (10-run depth) | > 80% |
| Injection payloads blocked by sanitizer | 100% of known patterns |
| Tamper detection on modified log | Detected on next load |

---

## 10. Research Changelog

This section tracks significant research findings that changed the
design, and implementation milestones. New entries go at the top.

---

### 2026-02-24 — Phase 1 shipped: Observer, Reflector, Sanitizer, adapters, ContextManager

All Phase 1 checklist items complete. 171 tests, 93% coverage.

Key implementation decisions:

- **Lazy SDK imports with injected-client seam**: `ClaudeAdapter` and
  `GeminiAdapter` import their SDKs inside `__init__` rather than at module
  level. An optional `_client` / `_model_instance` parameter allows tests to
  inject mocks without patching `sys.modules` or reloading modules.
- **`agentctx.testing` module**: `FakeLLMAdapter` lives in
  `src/agentctx/testing.py` rather than `tests/conftest.py`. This makes it
  importable by downstream users writing their own tests, and avoids the
  `ModuleNotFoundError` that arises from `from tests.conftest import …` when
  the `tests/` directory has no `__init__.py`.
- **Observer separator tolerance**: the LLM response parser strips leading
  ` :-` characters after the priority emoji, handling `🔴: text`,
  `🔴- text`, and `🔴 text` without requiring a strict format.
- **Reflector safety guard**: `reflect()` returns `False` and leaves the log
  untouched if the LLM produces zero parseable entries from a non-empty
  response, preventing silent log destruction from a bad completion.
- **Gemini system instruction fallback**: the Gemini adapter prepends the
  system prompt to the first user message rather than using
  `system_instruction=`, which is not supported on all Gemini models.

---

### 2026-02-23 — Phase 0 shipped: foundation data layer

All Phase 0 checklist items complete. 81 tests, 94% coverage.

Key implementation decisions:

- **`relative` field computed at build time, not stored**: observations store
  only `observed_on` and `event_date`; `ContextBuilder` computes the
  human-readable lag fresh each time it renders Block 1. Stored `relative:`
  fields in existing files are silently ignored by the parser.
- **File permissions via explicit `chmod`**: `Path.mkdir(mode=0o700)` is
  masked by the process umask; `parent.chmod(0o700)` must be called
  separately after creation to guarantee `700` on the `memory/` directory.
- **Blank-line entry delimiter**: observation entries are separated by two or
  more newlines (`\n{2,}`). Single newlines within an entry are preserved as
  multi-line text. Entries with malformed headers are silently skipped.

---

### 2026-02-20 — Context engineering principles + expanded security

Sources: [Anthropic: Effective Context Engineering][anthro-ce] ·
[Manus: Context Engineering for AI Agents][manus] ·
[InfMem, arxiv 2602.02704][infmem] ·
[AgeMem, arxiv 2601.01885][agemem] ·
[Martin Fowler: Agentic AI and Security][fowler] ·
[NIST: Strengthening AI Agent Hijacking Evaluations][nist] ·
[Unit 42: Agent Session Smuggling][unit42-smuggle] ·
[Unit 42: IPI Poisons AI Long-Term Memory][unit42-mem] ·
[MemoryGraft, arxiv 2512.16962][memorygraft] ·
[Microsoft FIDES, arxiv 2505.23643][fides] ·
[Adaptive Attacks Break IPI Defenses, arxiv 2503.00061][adaptive]

Key findings incorporated:

- **Context engineering defined**: Anthropic and Manus converge on the
  same five strategies — Write, Read, Select, Compress, Isolate — as
  the production framework for managing agent context windows. Added as
  §4.8.
- **Restorable compression**: Manus lesson — compress by retaining
  URLs/paths, not raw content, so the agent can re-fetch if needed
  without permanently losing access. Updated Observer design.
- **InfMem (System-2 memory control)**: Active PreThink-Retrieve-Write
  loop outperforms passive compression by 10+ points on ultra-long QA,
  3.9× faster via early stopping. Future Reflector design should
  incorporate active sufficiency checking, not just size triggers.
- **AgeMem (unified LTM + STM)**: Treating memory operations as
  tool-based agent actions (store/retrieve/update/discard) improves
  task performance 4.82–8.57pp. Informs Phase 3 design for agent-driven
  memory management.
- **Lethal Trifecta (Fowler)**: Sensitive data + untrusted content +
  external comms = maximum exposure. Added to §5 framing.
- **MemoryGraft + Unit 42 memory poisoning**: Persistent memory
  poisoning via "successful experience" records and session
  summarization hijacking. Added to threat model; provenance tagging
  and memory tier promotion controls added to §5.2.
- **Adaptive attacks break all static defenses (NIST + arXiv
  2503.00061)**: Acknowledged in §5.3 — sanitizer blocks known patterns
  but is not a guarantee; defense in depth required.
- **Session smuggling (Palo Alto Unit 42)**: A2A stateful multi-turn
  sessions exploited to covertly inject instructions. Added to threat
  model; out-of-scope note added to §5.3.

---

### 2026-02-20 — Security threat model added

Sources: [Cisco 2026 AI Security Report][cisco] ·
[Agents Without Context Go Off the Rails][hackernoon]

Key findings incorporated:

- The observation log and MCP-style connective tissue are the primary
  new attack surface for AI agents in 2026
- Attackers are pivoting from surface-level prompt injection to "deeper
  memory" manipulation as detection improves
- Added `security/` module to architecture, input sanitization before
  Observer writes, semantic intent anchoring, and the `AuditLog`
  tamper-detection mechanism

---

### 2026-02-20 — Initial design

Sources: [Observational Memory — VentureBeat][obsv] · [Mastra deep
dive][mastra] · [AWS agent lessons][aws] · [GEA arxiv 2602.04837][gea]

Key findings incorporated:

- Two-block context window (stable observation prefix + rolling session)
  enables provider prompt caching for 4–10× cost reduction
- Observer fires at ~30K unobserved tokens; Reflector fires at ~40K
  observation tokens
- Plain text + emoji priority markers outperform structured schemas for
  this use case
- Three-date model (observed_on / event_date / relative) improves
  temporal reasoning

---

## 11. References

### Memory and Context Engineering

- [Observational Memory: 10× cost reduction, 94.87% LongMemEval][obsv]
- [Mastra observational memory deep dive][mastra]
- [Anthropic: Effective Context Engineering for AI Agents][anthro-ce]
- [Manus: Context Engineering for AI Agents][manus]
- [AWS: Evaluating AI Agents — real-world lessons from Amazon][aws]
- [GEA: Group-Evolving Agents, arxiv 2602.04837][gea]
- [Memory in the Age of AI Agents survey, arxiv 2512.13564][memsurvey]
- [InfMem: System-2 Memory Control for Long-Context Agents,
  arxiv 2602.02704][infmem]
- [AgeMem: Unified Long-Term and Short-Term Memory Management,
  arxiv 2601.01885][agemem]

### Security

- [AI's 'connective tissue' is woefully insecure — Cisco][cisco]
- [Agents Without Context Go Off the Rails — HackerNoon][hackernoon]
- [Agentic AI and Security — Martin Fowler][fowler]
- [NIST: Strengthening AI Agent Hijacking Evaluations][nist]
- [Unit 42: Agent Session Smuggling in A2A Systems][unit42-smuggle]
- [Unit 42: Indirect Prompt Injection Poisons AI Long-Term
  Memory][unit42-mem]
- [MemoryGraft: Persistent Memory Poisoning, arxiv 2512.16962][memorygraft]
- [Microsoft FIDES: Information-Flow Control for Agents,
  arxiv 2505.23643][fides]
- [Adaptive Attacks Break IPI Defenses, arxiv 2503.00061][adaptive]

[obsv]: https://venturebeat.com/data/observational-memory-cuts-ai-agent-costs-10x-and-outscores-rag-on-long
[mastra]: https://www.techbuddies.io/2026/02/12/how-mastras-observational-memory-beats-rag-for-long-running-ai-agents/
[anthro-ce]: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
[manus]: https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
[aws]: https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/
[gea]: https://arxiv.org/abs/2602.04837
[memsurvey]: https://arxiv.org/abs/2512.13564
[infmem]: https://arxiv.org/abs/2602.02704
[agemem]: https://arxiv.org/abs/2601.01885
[cisco]: https://www.cybersecuritydive.com/news/ai-agents-model-context-protocol-cisco-report/812580/
[hackernoon]: https://hackernoon.com/agents-without-context-go-off-the-rails
[fowler]: https://martinfowler.com/articles/agentic-ai-security.html
[nist]: https://www.nist.gov/news-events/news/2025/01/technical-blog-strengthening-ai-agent-hijacking-evaluations
[unit42-smuggle]: https://unit42.paloaltonetworks.com/agent-session-smuggling-in-agent2agent-systems/
[unit42-mem]: https://unit42.paloaltonetworks.com/indirect-prompt-injection-poisons-ai-longterm-memory/
[memorygraft]: https://arxiv.org/abs/2512.16962
[fides]: https://arxiv.org/abs/2505.23643
[adaptive]: https://arxiv.org/abs/2503.00061
