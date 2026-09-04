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


_ALLOWED_CRITICS = {"critic-mistral", "critic-mistral:latest", "critic", "critic:latest"}
_OLLAMA_URL = "http://localhost:11434/api/generate"


@tool(
    "run_critic",
    "Send a prompt to one of the local Ollama critic models and stage the raw "
    "verdict for human review. Bounded: only the project's critic models can be "
    "targeted, and generation is deterministic (fixed seed, temperature 0). The "
    "full response is written to scratch/critic_runs/ for the researcher to "
    "judge. This tool STAGES a verdict; it does not evaluate whether the verdict "
    "is correct - that is the researcher's call.",
    {"model": str, "prompt": str},
)
async def run_critic(args: dict) -> dict:
    """Invoke a local critic via the Ollama API. Contained by construction:
    only whitelisted critic models, deterministic generation, result staged."""
    import json, urllib.request, urllib.error
    if _MEMORY_DIR is None:
        return {"content": [{"type": "text", "text": "Tool not initialized."}], "is_error": True}
    model = (args.get("model") or "").strip()
    prompt = (args.get("prompt") or "").strip()
    if model not in _ALLOWED_CRITICS:
        return {"content": [{"type": "text", "text":
                f"Refused: '{model}' is not an allowed critic. Allowed: {sorted(_ALLOWED_CRITICS)}."}],
                "is_error": True}
    if not prompt:
        return {"content": [{"type": "text", "text": "Refused: empty prompt."}], "is_error": True}
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False,
                          "options": {"seed": 42, "temperature": 0}}).encode("utf-8")
    req = urllib.request.Request(_OLLAMA_URL, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {"content": [{"type": "text", "text":
                f"Ollama unreachable ({e}). Is ollama serve running? (localhost:11434)"}], "is_error": True}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Critic call failed: {e}"}], "is_error": True}
    verdict = data.get("response", "")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = (_MEMORY_DIR.parent / "scratch" / "critic_runs")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{model.replace(':', '_')}_{stamp}.json"
    out_file.write_text(json.dumps({"model": model, "prompt": prompt,
        "options": {"seed": 42, "temperature": 0}, "response": verdict,
        "eval_count": data.get("eval_count"), "total_duration_ns": data.get("total_duration")},
        indent=2), encoding="utf-8")
    preview = verdict[:600] + ("\u2026" if len(verdict) > 600 else "")
    return {"content": [{"type": "text", "text":
            f"Critic {model} responded ({data.get('eval_count','?')} tokens). "
            f"Full verdict staged to scratch/critic_runs/{out_file.name} for your review.\n\n"
            f"--- verdict preview ---\n{preview}"}]}


def build_tools_server(memory_dir: Path):
    """Bind the tools to this run's memory dir and return the in-process server."""
    global _MEMORY_DIR
    _MEMORY_DIR = memory_dir.resolve()
    return create_sdk_mcp_server(
        name="forge",
        version="1.0.0",
        tools=[append_log, run_critic],
    )


# The permission name the agent uses to call this: mcp__forge__append_log
APPEND_LOG_TOOL = "mcp__forge__append_log"
RUN_CRITIC_TOOL = "mcp__forge__run_critic"
