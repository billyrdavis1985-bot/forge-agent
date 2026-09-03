"""
agent_tools.py — narrow custom tools that replace raw Bash.

The escape-hatch problem: with raw Bash, the agent can write anywhere via
redirects (`echo x > /outside`), and no regex reliably jails that. The fix is
to remove Bash entirely and give the agent only the specific capabilities it
legitimately needs, each locked down by construction.

This module provides `append_log`: the ONE write the agent used Bash for — the
append-only research log. It can append to research_log.md and nothing else.
There is no path argument, so there is no path to abuse.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from claude_agent_sdk import tool, create_sdk_mcp_server

# Set by build_tools_server() before the server is used.
_MEMORY_DIR: Path | None = None


@tool(
    "append_log",
    "Append a dated entry to the append-only research log (research_log.md). "
    "This is the ONLY way to write to the log. Provide the entry body; the "
    "timestamp header is added automatically. Use this at the end of every "
    "session for your mandatory handoff.",
    {"entry": str},
)
async def append_log(args: dict) -> dict:
    """Append one entry to research_log.md. No path argument — cannot target
    any other file."""
    if _MEMORY_DIR is None:
        return {
            "content": [{"type": "text", "text": "Log tool not initialized."}],
            "is_error": True,
        }
    entry = (args.get("entry") or "").strip()
    if not entry:
        return {
            "content": [{"type": "text", "text": "Refused: empty log entry."}],
            "is_error": True,
        }

    log_path = _MEMORY_DIR / "research_log.md"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # Append only. Open in 'a' mode — cannot truncate.
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {stamp}\n{entry}\n")

    return {
        "content": [
            {"type": "text", "text": f"Appended {len(entry)} chars to research_log.md."}
        ]
    }


def build_tools_server(memory_dir: Path):
    """Bind the tools to this run's memory dir and return the in-process server."""
    global _MEMORY_DIR
    _MEMORY_DIR = memory_dir.resolve()
    return create_sdk_mcp_server(
        name="forge",
        version="1.0.0",
        tools=[append_log],
    )


# The permission name the agent uses to call this: mcp__forge__append_log
APPEND_LOG_TOOL = "mcp__forge__append_log"
