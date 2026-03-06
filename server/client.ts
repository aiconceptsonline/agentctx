/**
 * agentctx TypeScript client.
 *
 * Copy this file into your project as src/lib/agentctx.ts.
 * Set AGENTCTX_URL to the sidecar address (default: http://agentctx:8001).
 *
 * The sidecar (services/agentctx/) must be running — see README.md.
 */

const BASE = (process.env.AGENTCTX_URL ?? 'http://agentctx:8001').replace(/\/$/, '');

export type TrustTier = 'trusted' | 'semi_trusted' | 'untrusted';

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`agentctx ${path} → ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export const agentctx = {
  /**
   * Record an observation in the session's persistent log.
   * Use emoji prefixes as priority signals: 🟢 success · 🟡 warning · 🔴 error
   *
   * @example
   *   await agentctx.observe(sessionId, '🟢 Retrieved 5 documents');
   */
  async observe(sessionId: string, text: string): Promise<void> {
    await post('/observe', { session_id: sessionId, text });
  },

  /**
   * Return the stable observation-log prefix to prepend to every LLM call.
   * Pass the returned string as your LLM system prompt.
   * It is structured to be token-cache-friendly.
   */
  async prefix(sessionId: string): Promise<string> {
    const res = await fetch(`${BASE}/prefix/${encodeURIComponent(sessionId)}`);
    if (!res.ok) throw new Error(`agentctx /prefix → ${res.status}`);
    return ((await res.json()) as { prefix: string }).prefix ?? '';
  },

  /**
   * Wrap external content in trust-tier XML before it reaches the LLM.
   * Strips prompt-injection patterns from untrusted and semi_trusted content.
   *
   * Tiers:
   *   trusted      — developer-controlled text, no stripping
   *   semi_trusted — tool outputs, DB results, API responses — injection-stripped
   *   untrusted    — user input, web pages, uploads — injection-stripped
   *
   * When in doubt, use 'untrusted'.
   */
  async spotlight(content: string, tier: TrustTier): Promise<string> {
    return (await post<{ content: string }>('/spotlight', { content, tier })).content;
  },

  /**
   * Auto-file a bug report in the agentctx GitHub repo.
   * Safe to call in catch blocks — never throws, silently fails if unconfigured.
   * Requires AGENTCTX_GITHUB_TOKEN set in the sidecar environment.
   */
  async report(error: unknown, context: string): Promise<void> {
    const msg = error instanceof Error ? error.message : String(error);
    try {
      await post('/report', { error: msg, context });
    } catch {
      // Never crash the caller over a failed report
    }
  },
};
