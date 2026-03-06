"""Utility for client repos to report bugs back to agentctx.

Usage in a client repo:
    from agentctx.reporter import report_issue

    try:
        ctx.add_message(msg)
    except Exception as exc:
        report_issue(exc, context="Processing user message in checkout flow")
        raise

Requires the ``gh`` CLI to be installed and authenticated, or set
AGENTCTX_GITHUB_TOKEN to a token with issues:write on the agentctx repo.
"""
from __future__ import annotations

import importlib.metadata
import os
import platform
import subprocess
import sys
import traceback


_REPO = "aiconceptsonline/agentctx"


def report_issue(
    exc: BaseException,
    context: str = "",
    *,
    repo: str = _REPO,
    dry_run: bool = False,
) -> str | None:
    """Open a bug report issue in the agentctx repo.

    Returns the issue URL on success, None on failure.
    ``dry_run=True`` prints the issue body instead of creating it.
    """
    try:
        version = importlib.metadata.version("agentctx")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"

    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    body = f"""\
## Automated bug report from client repo

**agentctx version:** {version}
**Python:** {py_version}
**Platform:** {platform.system()} {platform.release()}

## Exception

```
{tb.strip()}
```

## Client context

{context or "_Not provided._"}

## Reproduction

_Auto-reported — see client context above. Add a minimal reproduction if possible._
"""

    title = f"bug: {type(exc).__name__}: {str(exc)[:80]}"

    if dry_run:
        print(f"[dry_run] Would open issue: {title!r}")
        print(body)
        return None

    token = os.environ.get("AGENTCTX_GITHUB_TOKEN")
    env = os.environ.copy()
    if token:
        env["GH_TOKEN"] = token

    result = subprocess.run(
        ["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body],
        capture_output=True, text=True, env=env,
    )

    if result.returncode == 0:
        return result.stdout.strip()

    # Don't crash the client — just warn
    print(
        f"[agentctx] Failed to open issue: {result.stderr.strip()[:200]}",
        file=sys.stderr,
    )
    return None
