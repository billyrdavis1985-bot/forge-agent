"""
orchestrator.py — Phase 1 entry point (unattended-capable).

One bounded session, safe to run from a systemd timer:
    preflight -> daily budget gate -> load memory -> SDK agent loop under
    guards + caps -> git commit -> ledger record -> health ping.

Exit codes (systemd/healthchecks care about these):
    0  success
    1  run failed (agent error, crash)
    2  preflight failed (misconfiguration)
    3  skipped deliberately (daily budget reached, nothing to do)

Usage:
    python -m src.orchestrator                  # pick top open question
    python -m src.orchestrator "instruction"    # explicit task
    python -m src.orchestrator --status         # show recent runs, no agent call
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import traceback
from pathlib import Path

import yaml

from . import health
from .ledger import Ledger
from .memory_manager import MemoryManager

# NOTE: claude_agent_sdk is imported lazily inside run_session(), not here.
# --status and preflight are pure local operations and must work before the
# SDK is installed — a top-level import would make the cheapest diagnostic
# path depend on the heaviest dependency.
# guards is also imported lazily because it imports SDK permission types.

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "agent.yaml"
DB_PATH = PROJECT_ROOT / "memory" / "state.db"


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def preflight(cfg: dict) -> list[str]:
    """Return a list of problems. Empty list = good to go."""
    problems: list[str] = []

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")):
        problems.append("No ANTHROPIC_API_KEY / CLAUDE_API_KEY in environment.")

    # The Python SDK shells out to the Claude Code CLI unless it is bundled.
    if not shutil.which("claude"):
        problems.append(
            "Claude Code CLI not found on PATH. Install it, or set cli_path "
            "in options. (Note: systemd timers do not inherit your shell PATH — "
            "set it explicitly in the unit file.)"
        )

    for rel in ("memory/CLAUDE.md", "memory/open_questions.md", "memory/research_log.md"):
        if not (PROJECT_ROOT / rel).exists():
            problems.append(f"Missing required memory file: {rel}")

    for key in ("model", "allowed_tools", "max_turns", "max_budget_usd", "write_roots"):
        if key not in cfg:
            problems.append(f"config/agent.yaml missing key: {key}")

    return problems


def build_prompt(snapshot: str, instruction: str | None) -> str:
    directive = (
        f"Your instruction for this session:\n{instruction}"
        if instruction
        else "No explicit instruction was given. Select the top unchecked task "
        "from the task frontier below and work on exactly that one. If the "
        "frontier is empty, write a short log entry saying so and stop."
    )
    return (
        f"{snapshot}\n\n"
        f"---\n{directive}\n\n"
        "Remember the mandatory finish step: append a dated entry to "
        "memory/research_log.md (append with '>>', it cannot be edited in "
        "place) and update memory/open_questions.md before you stop."
    )


async def run_session(instruction: str | None) -> int:
    cfg = load_config()

    problems = preflight(cfg)
    if problems:
        print("PREFLIGHT FAILED:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        health.failure("preflight failed: " + "; ".join(problems))
        return 2

    # Imported here, not at module scope, so --status works without the SDK.
    try:
        from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, HookMatcher
        from claude_agent_sdk.types import ResultMessage

        from .guards import make_pretooluse_hook
        from .agent_tools import build_tools_server, APPEND_LOG_TOOL, RUN_CRITIC_TOOL
    except ImportError as e:
        print(
            f"PREFLIGHT FAILED:\n  - Claude Agent SDK not installed ({e}).\n"
            f"    Install deps into your venv:\n"
            f"      python -m venv .venv\n"
            f"      .venv\\Scripts\\python.exe -m pip install -r requirements.txt   (Windows)\n"
            f"      .venv/bin/pip install -r requirements.txt                      (Linux/macOS)",
            file=sys.stderr,
        )
        health.failure("SDK not installed")
        return 2

    ledger = Ledger(DB_PATH)
    reaped = ledger.reap_stale_runs()
    if reaped:
        print(f"note: marked {reaped} orphaned run(s) as aborted")

    daily_cap = float(cfg.get("daily_budget_usd", 2.00))
    allowed, spent = ledger.budget_check(daily_cap)
    if not allowed:
        msg = f"daily budget reached (${spent:.4f} of ${daily_cap:.2f}) — skipping run"
        print(msg)
        health.success(msg)  # deliberate skip is healthy, not a failure
        return 3

    mem = MemoryManager(PROJECT_ROOT)
    mem.ensure_repo()
    run_id = mem.new_run_id()

    health.start()
    ledger.start_run(run_id, instruction)

    tools_server = build_tools_server(mem.memory_dir)
    allowed_tools = ["Read", "Glob", "Grep", "Write", APPEND_LOG_TOOL, RUN_CRITIC_TOOL]
    disallowed_tools = ["Bash", "Edit", "MultiEdit", "NotebookEdit", "WebFetch", "WebSearch"]

    options = ClaudeAgentOptions(
        model=cfg["model"],
        fallback_model=cfg.get("fallback_model"),
        mcp_servers={"forge": tools_server},
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
        max_turns=cfg["max_turns"],
        max_budget_usd=cfg["max_budget_usd"],
        cwd=str(PROJECT_ROOT),
        hooks={"PreToolUse": [HookMatcher(matcher="*", hooks=[make_pretooluse_hook(PROJECT_ROOT, cfg["write_roots"])])]},
        permission_mode="dontAsk",
        # can_use_tool removed: it was shadowed (zero enforcement) and emitted a
        # misleading warning. The PreToolUse hook is the real, verified gate.
        system_prompt=(
            "You are Forge Agent operating one bounded research session. "
            "Follow the mission and memory protocol given in the context."
        ),
    )

    print(f"[{run_id}] start (model={cfg['model']}, session cap=${cfg['max_budget_usd']}, "
          f"day spent=${spent:.4f}/${daily_cap:.2f})")

    transcript_path = PROJECT_ROOT / "runs" / f"{run_id}.log"
    cost, turns, result_text = 0.0, None, ""

    try:
        with transcript_path.open("w", encoding="utf-8") as tf:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt_for(mem, instruction))
                async for message in client.receive_response():
                    tf.write(f"{message}\n")
                    tf.flush()  # keep the transcript useful if the process is killed
                    if isinstance(message, ResultMessage):
                        cost = getattr(message, "total_cost_usd", 0.0) or 0.0
                        turns = getattr(message, "num_turns", None)
                        result_text = getattr(message, "result", "") or ""
    except Exception:
        err = traceback.format_exc(limit=5)
        sha = mem.commit_run(run_id)  # commit whatever partial work survived
        ledger.finish_run(run_id, "error", cost, turns, sha, err)
        print(f"[{run_id}] FAILED\n{err}", file=sys.stderr)
        health.failure(f"{run_id} failed:\n{err}")
        return 1

    sha = mem.commit_run(run_id)
    ledger.finish_run(run_id, "ok", cost, turns, sha, None)

    print(f"[{run_id}] result: {result_text[:500]}")
    print(f"[{run_id}] cost=${cost:.4f} turns={turns} "
          f"commit={sha[:10] if sha else 'none (no changes)'}")
    health.success(f"{run_id} ok | ${cost:.4f} | {result_text[:300]}")
    return 0


def prompt_for(mem: MemoryManager, instruction: str | None) -> str:
    return build_prompt(mem.load_snapshot(), instruction)


def show_status() -> int:
    ledger = Ledger(DB_PATH)
    rows = ledger.recent(10)
    if not rows:
        print("No runs recorded yet.")
        return 0
    print(f"{'run_id':<24} {'status':<8} {'cost':>8}  {'turns':>5}  commit")
    for r in rows:
        sha = (r["commit_sha"] or "")[:10]
        print(f"{r['run_id']:<24} {r['status']:<8} "
              f"${r['cost_usd'] or 0:>7.4f}  {str(r['num_turns'] or '-'):>5}  {sha}")
    print(f"\nSpend today: ${ledger.spend_today():.4f}")
    return 0


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--status":
        sys.exit(show_status())
    instruction = " ".join(args).strip() or None
    sys.exit(asyncio.run(run_session(instruction)))


if __name__ == "__main__":
    main()
