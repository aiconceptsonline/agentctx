# Quickstart — TypeScript / Node.js

agentctx runs as a sidecar HTTP service. Your TypeScript app calls it over JSON.
No Python runtime required in your main process.

---

## 1. Start the sidecar

**Docker Compose** (recommended):

```yaml
services:
  agentctx:
    image: ghcr.io/aiconceptsonline/agentctx-server:latest
    # Or build locally:
    # build: ./services/agentctx
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - AGENTCTX_GITHUB_TOKEN=${AGENTCTX_GITHUB_TOKEN}
      - AGENTCTX_STORAGE=/data/agentctx
    volumes:
      - agentctx_data:/data/agentctx
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"]
      interval: 10s
      timeout: 5s
      retries: 3

volumes:
  agentctx_data:
```

**Or run directly:**

```bash
docker run -p 8001:8001 \
  -e ANTHROPIC_API_KEY=sk-... \
  -v agentctx_data:/data/agentctx \
  ghcr.io/aiconceptsonline/agentctx-server:latest
```

---

## 2. Add the client

Copy [`src/lib/agentctx.ts`](../server/client.ts) into your project, or install
the npm package (coming soon: `npm install @agentctx/client`):

```typescript
// src/lib/agentctx.ts
const BASE = process.env.AGENTCTX_URL ?? 'http://agentctx:8001';

export type TrustTier = 'trusted' | 'semi_trusted' | 'untrusted';

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`agentctx ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const agentctx = {
  async observe(sessionId: string, text: string): Promise<void> {
    await post('/observe', { session_id: sessionId, text });
  },
  async prefix(sessionId: string): Promise<string> {
    const res = await fetch(`${BASE}/prefix/${encodeURIComponent(sessionId)}`);
    return ((await res.json()) as { prefix: string }).prefix ?? '';
  },
  async spotlight(content: string, tier: TrustTier): Promise<string> {
    return (await post<{ content: string }>('/spotlight', { content, tier })).content;
  },
  async report(error: unknown, context: string): Promise<void> {
    const msg = error instanceof Error ? error.message : String(error);
    try { await post('/report', { error: msg, context }); } catch {}
  },
};
```

---

## 3. Use it in your agent

```typescript
import { agentctx } from '@/lib/agentctx';

async function runAgentQuery(sessionId: string, userQuery: string) {
  try {
    // Sanitize all external content before the LLM sees it
    const safeQuery = await agentctx.spotlight(userQuery, 'untrusted');
    const safeDocs  = await agentctx.spotlight(retrievedDocs, 'semi_trusted');

    // Prepend the observation log as the LLM system prompt
    const systemPrompt = await agentctx.prefix(sessionId);

    const answer = await callLLM({ system: systemPrompt, user: safeQuery, docs: safeDocs });

    await agentctx.observe(sessionId, `🟢 Query answered: ${userQuery.slice(0, 60)}`);
    return answer;

  } catch (err) {
    await agentctx.observe(sessionId, `🔴 Error: ${String(err).slice(0, 100)}`);
    await agentctx.report(err, `Agent query — session ${sessionId}`);
    throw err;
  }
}
```

---

## 4. Reporting bugs back to agentctx

When agentctx itself misbehaves (unexpected output, crashes, wrong behaviour),
`agentctx.report()` opens a structured issue in the agentctx GitHub repo
automatically. To enable it, add `AGENTCTX_GITHUB_TOKEN` to your environment
with `issues:write` permission on `aiconceptsonline/agentctx`.

---

## API reference

See [http-api.md](./http-api.md) for the full endpoint list.
