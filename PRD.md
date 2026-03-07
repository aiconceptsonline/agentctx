# PRD: agentctx

**Status:** Living Document · **Last updated:** 2026-03-04
**Owner:** Tommy

> This document is updated continuously as context engineering research
> matures. See [§10 Research Changelog](#10-research-changelog) for a
> log of significant updates.

---

## 1. What Is This

`agentctx` is a **standalone Python library for multi-agent context and
memory management**.

It solves one problem: keeping AI agents coherent, cost-efficient, and
secure — whether a single agent running across long sessions, or a fleet
of specialized agents that must share context without contaminating each
other — without a vector database, without an external memory service,
and without being tied to any specific agent framework, orchestrator, or
LLM provider.

Any project drops it in, configures a storage path, and gets persistent
observational memory, agent state checkpointing, and a stable cacheable
context prefix — in under 20 lines of code. A fleet of agents adds a
shared bus and cross-agent trust boundaries with a few more lines.

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

And every multi-agent project hits a second layer of unsolved problems:

- How do specialized agents share what they have learned without one
  agent's noise polluting another's context?
- How do I prevent a compromised agent from propagating an injection
  into the rest of the fleet via shared memory?
- How do I enforce the 1,000–2,000 token summary discipline that
  Anthropic's own production systems require on agent-to-agent handoffs?
- How do I apply trust tiers to content that arrives *from another
  agent* rather than from a user or external source?

The research term for the core multi-agent problem is **memory silos**:
current architectures bind memory to a single entity, so agents cannot
collaborate across sessions without either sharing everything (unsafe,
expensive) or sharing nothing (uninformed). Every major framework
(LangGraph, AutoGen, Swarm) conflates memory with orchestration — the
memory model is inseparable from the workflow graph. This means there is
no portable memory layer that works across frameworks or with no
framework at all.
(Sources: [MaaS arxiv 2506.22815], [G-Memory arxiv 2506.07398],
[MAGMA arxiv 2601.03236])

RAG solves some of the single-agent problems but requires a vector
database, changes the prompt prefix every turn (breaking provider
caching), and optimizes for retrieval over continuity. It is the wrong
primitive for agents that need to *accumulate understanding* rather than
*search a corpus*. It is even less suited to fleet-level shared memory.

---

## 3. Goal

A pip-installable Python library that provides:

1. **Observational Memory** — compresses session history into a dated,
   prioritized log that stays as a stable prefix in every agent's
   context window
2. **Run State** — checkpoints each step of a pipeline so partial
   failures resume from the last good state, not from scratch
3. **Fleet Memory** — a shared observation bus that any agent in a fleet
   can write to and read from, with per-agent private logs maintained
   separately; cross-agent context is sanitized at semi-trusted tier
   before entering any agent's context window
4. **Provider-agnostic** — works with Claude, Gemini, OpenAI, or any
   model via a thin adapter
5. **Framework-agnostic** — the memory substrate that sits *below* any
   orchestration layer; plugs into LangGraph, AutoGen, Swarm, or no
   framework at all without adopting their memory model
6. **Zero infrastructure** — no vector DB, no Redis, no external
   service; storage is plain files on disk (git-trackable by design)
7. **Secure by default** — sanitizes inputs before they enter the
   observation log, enforces trust boundaries between agents and between
   agents and external content, and treats the context window as an
   attack surface

**Out of scope — these belong to orchestration frameworks:**

- Agent orchestration / workflow definition / task routing
  (agentctx is the memory layer, not the workflow layer)
- Tool use / function calling management
- Model fine-tuning or training
- Multi-tenant / cloud-hosted memory service
- Real-time streaming context updates
- Authentication / authorization between agents in distributed
  deployments (caller's responsibility)

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

Runs automatically when unobserved messages exceed a configurable
token threshold (default: 30K).

- Reads new messages since the last observation pass
- Extracts key facts, decisions, errors, and patterns
- Sanitizes content before writing (see §5 Security)
- Writes dated, priority-tagged observations to `observations.md`
- Drops the raw messages it has processed (keeps Block 2 lean)

### 4.4 Reflector Agent

Runs when the observation log exceeds a configurable size (default:
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

### 4.9 Fleet Memory (Multi-Agent)

When multiple specialized agents run in a fleet, each agent maintains
its own private `ObservationLog`. In addition, a single `FleetLog`
serves as a shared broadcast bus:

```text
./memory/
  fleet/
    fleet.md        # shared observation bus (append-only)
    fleet_audit.jsonl
  agents/
    scraper/
      observations.md
      audit.jsonl
    rag/
      observations.md
      audit.jsonl
    moderation/
      observations.md
      audit.jsonl
```

**Key design decisions grounded in research:**

1. **Private by default, shared by choice.** An agent calls
   `ctx.observe(...)` to write privately or `ctx.broadcast(...)` to
   publish to the fleet log. Nothing crosses the boundary implicitly.

2. **Cross-agent content is semi-trusted.** Content arriving from
   another agent — even a trusted team member — passes through the same
   `spotlight()` sanitization as tool outputs. An injected agent becomes
   an injection vector for every agent it shares context with. This is
   the session-smuggling threat applied to shared memory.

3. **Context budget on handoffs.** When one agent passes context to
   another, agentctx enforces a configurable token budget (default:
   2,000 tokens). Agents summarize before sharing; they do not dump raw
   history. This mirrors Anthropic's production pattern where subagents
   return condensed 1,000–2,000 token summaries to a coordinator.

4. **Peer prefix scoping.** `build_prefix(include_peers=["scraper",
   "ocr"])` adds a filtered view of the fleet log — only entries
   relevant to the requesting agent's task anchor — to Block 1. An
   agent does not receive every entry from every peer; it receives
   what is relevant.

5. **No orchestration.** agentctx does not decide which agent runs
   next, route tasks, or define workflows. The orchestrator (LangGraph,
   Swarm, custom code, human) does that. agentctx is the memory
   substrate those orchestrators sit on top of.

6. **Single FleetLog is the MaaS pattern.** The HTTP sidecar exposes
   fleet memory as a service callable from any language. This aligns
   with the Memory-as-a-Service (MaaS) architecture identified in arxiv
   2506.22815 as the missing primitive in multi-agent systems.

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

#### Cross-agent trust (Fleet Memory)

Agent-to-agent communication is treated as `semi_trusted` — the same
tier as tool outputs and database results. The reasoning: an agent that
has been successfully injected will propagate that injection through any
content it shares with peers. Trusting peer agents unconditionally
converts a single-agent compromise into a fleet-wide compromise.

Concretely:
- Content written to the `FleetLog` by any agent passes through
  `spotlight(tier="semi_trusted")` before entering any other agent's
  context window
- Agents cannot write directly to another agent's private
  `ObservationLog`
- The `FleetLog` has its own `audit.jsonl` tracking all writes,
  including which agent wrote each entry
- Bulk fleet writes (e.g., a scraper agent publishing 3,000 URL fetches)
  are rejected at the API level — agents publish semantic summaries to
  the fleet, not raw operational traces

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

### Phase 4 — Fleet Memory

- [ ] `FleetLog`: shared append-only observation bus with per-agent
      attribution; own audit trail
- [ ] `AgentRegistry`: lightweight agent ID + role registry (in-memory
      + optional disk persistence); no orchestration logic
- [ ] `build_prefix(include_peers=[...])`: filtered fleet log view in
      Block 1; relevance filtered against requesting agent's task anchor
- [ ] `ctx.broadcast(text)`: publish to fleet log via semi-trusted
      sanitization
- [ ] Context budget enforcement on cross-agent handoffs (configurable
      token cap, default 2,000 tokens)
- [ ] HTTP server fleet endpoints: `POST /agents/register`,
      `GET /agents`, `POST /broadcast`,
      `GET /agents/{id}/prefix?peers=...`
- [ ] Fleet audit + tamper detection (same pattern as single-agent
      audit log)
- [ ] Documentation: "What to broadcast vs. keep private" best
      practices guide

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

### 2026-03-04 — Multi-agent memory architecture research

Sources: [Anthropic: Effective Context Engineering][anthro-ce] ·
[Anthropic: How we built our multi-agent research system][anthro-mas] ·
[MaaS: Memory as a Service, arxiv 2506.22815][maas] ·
[G-Memory: Hierarchical Memory for Multi-Agent Systems, arxiv 2506.07398][gmem] ·
[MAGMA: Multi-Graph Agentic Memory, arxiv 2601.03236][magma] ·
[Collaborative Memory with Access Control, arxiv 2505.18279][colmem] ·
[Intrinsic Memory Agents, arxiv 2508.08997][intrinsic] ·
[LangGraph, AutoGen, Swarm comparative analysis][openagents]

Key findings incorporated:

- **Memory silos are the defining unsolved problem in multi-agent
  systems.** Every current framework (LangGraph, AutoGen, Swarm) binds
  memory to its orchestration model, making memory non-portable. No
  framework-agnostic shared memory layer exists. This is agentctx's
  lane for Phase 4.
- **MaaS pattern validates the HTTP sidecar.** The Memory-as-a-Service
  architecture (decoupled, independently callable, composable memory
  module) independently converges on the same pattern as agentctx's HTTP
  sidecar. The sidecar is already the right architecture; it needs fleet
  endpoints added.
- **Cross-agent trust is an open wound.** Agent-to-agent content is
  universally treated as trusted in current frameworks. Session smuggling
  (Unit 42) and the FIDES threat model (arxiv 2505.23643) show this is
  the next major attack surface. agentctx's semi-trusted tier for peer
  content is the correct countermeasure.
- **Anthropic's production system enforces a 1,000–2,000 token
  handoff budget.** Subagents return condensed summaries to the
  coordinator; they do not pass raw context. agentctx should enforce
  this budget at the API level for fleet broadcasts.
- **Scope confirmed: memory layer, not orchestration layer.**
  LangGraph owns workflow graphs. Swarm owns handoff routing. AutoGen
  owns conversation patterns. agentctx owns the memory substrate beneath
  all of them. These are complementary, not competing.
- **Hierarchical memory** (G-Memory insight/query/interaction tiers;
  MAGMA semantic/temporal/causal/entity graphs) points to future work
  beyond Phase 4 — the current flat observation log is a starting point,
  not the end state.

Design decisions updated: §1, §2, §3, §4.9 (new), §5.2 (cross-agent
trust), §8 Phase 4 (new).

---

### 2026-03-06 — Research digest (automated)

Auto-incorporated 2 item(s) with relevance ≥ 4.

**[Towards Multimodal Lifelong Understanding: A Dataset and Agentic Baseline](https://arxiv.org/abs/2603.05484v1)**

The MM-Lifelong paper (arXiv 2603.05484, March 2026) introduces a 181-hour multimodal lifelong dataset and identifies two critical failure modes in long-horizon agentic reasoning: the Working Memory Bottleneck (context saturation in end-to-end MLLMs) and Global Localization Collapse (positional disorientation in agentic baselines over sparse timelines). The proposed Recursive Multimodal Agent (ReMA) resolves both via dynamic, recursive belief-state management. These findings validate agentctx's core memory and checkpointing primitives and provide concrete design targets: (1) recursive summarisation hooks in observational memory, (2) temporal anchor fields in run-state checkpoints, and (3) density-adaptive retention policies in the context engineering layer. This paper should be treated as a primary reference for §4 (Observational Memory) and §6 (Checkpointing) design decisions.

- The Working Memory Bottleneck directly motivates agentctx's observational memory design: raw context must be compressed and summarised recursively rather than appended linearly, especially for long-running agents.
- Global Localization Collapse is a checkpointing failure — agentctx's run-state checkpointing should store explicit temporal/positional anchors alongside state snapshots so agents can re-orient after resumption.
- ReMA's recursive belief state update pattern is a strong prior for agentctx's context engineering API: expose a belief-state abstraction that agents update incrementally rather than reconstructing from full history.
- The Day/Week/Month density tiers suggest agentctx should support configurable memory retention policies (e.g., high-fidelity recent window + compressed long-term summary) rather than a single eviction strategy.
- Input sanitisation in agentctx should account for temporal sparsity: filtering or down-sampling dense input streams before they reach the context window prevents premature saturation.

**[Fooling AI Agents: Web-Based Indirect Prompt Injection Observed in the Wild](https://unit42.paloaltonetworks.com/ai-agent-prompt-injection/)**

§10 Research Changelog — 2026-03-06: Unit 42 (Palo Alto Networks) published the first large-scale empirical study of indirect prompt injection (IDPI) observed in production AI agents, cataloguing 12 real-world attack patterns ranging from financial fraud to destructive filesystem commands. Key delivery vectors include CSS/font concealment, runtime Base64 decoding, and social-engineering jailbreak framing (present in 85.2% of cases). The study validates agentctx's existing input-sanitisation and context-engineering mandates and surfaces three concrete gaps: (1) recursive decoding of encoded payloads, (2) structural spotlighting of untrusted context zones, and (3) intent-drift detection via run-state checkpoint comparison. These gaps are now tracked as actionable items for the sanitisation, context-engineering, and checkpointing subsystems.

- agentctx's input sanitisation layer must be extended to strip or flag visual-concealment vectors: zero-width/zero-font spans, off-screen CSS positioning, colour-matched text, invisible Unicode characters, and homoglyph substitutions before content reaches the LLM context.
- Base64 and XML/SVG payloads that decode at runtime must be handled — sanitisation should recursively decode and inspect encoded blobs rather than passing them through opaque.
- The context engineering layer should implement spotlighting by design: wrapping all externally-fetched content (web pages, tool outputs, retrieved documents) in a distinct XML-tagged zone so the model receives a structural signal that those tokens are untrusted.
- Run state checkpointing should record a canonical 'intent fingerprint' derived from the original user goal; a post-step comparator can detect when an agent's next planned action diverges from that fingerprint, surfacing potential injection-driven hijacking.
- Observational memory should log jailbreak-framing patterns ('developer mode', 'god mode', 'ignore previous instructions') as anomaly signals; repeated pattern matches across a session should escalate to a human-in-the-loop interrupt.
- agentctx should expose a trust-tier API so integrators can tag context sources (system prompt = TRUSTED, web retrieval = UNTRUSTED, tool output = SEMI-TRUSTED) and apply differential sanitisation budgets accordingly.

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

### Multi-Agent Memory

- [MaaS: Memory as a Service for Collaborative Agents, arxiv 2506.22815][maas]
- [G-Memory: Hierarchical Memory for Multi-Agent Systems, arxiv 2506.07398][gmem]
- [MAGMA: Multi-Graph Agentic Memory Architecture, arxiv 2601.03236][magma]
- [Collaborative Memory with Dynamic Access Control, arxiv 2505.18279][colmem]
- [Intrinsic Memory Agents: Heterogeneous Multi-Agent LLMs, arxiv 2508.08997][intrinsic]
- [Anthropic: How we built our multi-agent research system][anthro-mas]
- [CrewAI vs LangGraph vs AutoGen vs OpenAgents 2026][openagents]

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

[maas]: https://arxiv.org/html/2506.22815v1
[gmem]: https://arxiv.org/abs/2506.07398
[magma]: https://arxiv.org/abs/2601.03236
[colmem]: https://arxiv.org/html/2505.18279v1
[intrinsic]: https://arxiv.org/html/2508.08997v1
[anthro-mas]: https://www.anthropic.com/engineering/multi-agent-research-system
[openagents]: https://openagents.org/blog/posts/2026-02-23-open-source-ai-agent-frameworks-compared

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
