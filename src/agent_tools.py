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

# DETERMINISM LOCK (verified by determinism_probe config C: byte-identical across
# repeats). temp=0 + seed alone is NOT reproducible on GPU — num_ctx must be
# pinned and decoding forced greedy (top_k=1). Without this, verdicts flip across
# runs and any finding built on single samples is unstable.
_DET_OPTIONS = {"seed": 42, "temperature": 0, "num_ctx": 8192,
                "num_predict": 1024, "top_k": 1, "top_p": 1.0}


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
                          "options": _DET_OPTIONS}).encode("utf-8")
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
        "options": _DET_OPTIONS, "response": verdict,
        "eval_count": data.get("eval_count"), "total_duration_ns": data.get("total_duration")},
        indent=2), encoding="utf-8")
    preview = verdict[:600] + ("\u2026" if len(verdict) > 600 else "")
    return {"content": [{"type": "text", "text":
            f"Critic {model} responded ({data.get('eval_count','?')} tokens). "
            f"Full verdict staged to scratch/critic_runs/{out_file.name} for your review.\n\n"
            f"--- verdict preview ---\n{preview}"}]}


import re as _re


def _call_ollama(model: str, prompt: str) -> tuple:
    import json, urllib.request
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False,
                          "options": _DET_OPTIONS}).encode("utf-8")
    req = urllib.request.Request(_OLLAMA_URL, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("response", ""), data


_CRITIC_REPO = None


@tool(
    "run_critic_batch",
    "Run every candidate in a corruption batch file through a critic model and "
    "stage the collected verdicts ALONGSIDE each item's ground-truth label for "
    "human review. Bounded: only whitelisted critic models, only batch files in "
    "the critic repo eval/ directory (bare filename, no paths). Deterministic. "
    "ASSEMBLES comparison material; does NOT score or judge — reading verdicts "
    "against truth is the researcher's job.",
    {"model": str, "batch_file": str},
)
async def run_critic_batch(args: dict) -> dict:
    import json
    if _MEMORY_DIR is None or _CRITIC_REPO is None:
        return {"content": [{"type": "text", "text": "Tool not initialized."}], "is_error": True}
    model = (args.get("model") or "").strip()
    batch_file = (args.get("batch_file") or "").strip()
    if model not in _ALLOWED_CRITICS:
        return {"content": [{"type": "text", "text":
                f"Refused: '{model}' is not an allowed critic. Allowed: {sorted(_ALLOWED_CRITICS)}."}], "is_error": True}
    if "/" in batch_file or "\\" in batch_file or ".." in batch_file:
        return {"content": [{"type": "text", "text": "Refused: batch_file must be a bare filename (no path)."}], "is_error": True}
    src = (_CRITIC_REPO / "eval" / batch_file).resolve()
    if _CRITIC_REPO / "eval" not in src.parents or not src.is_file():
        return {"content": [{"type": "text", "text": f"Refused: {batch_file} not found in the critic repo eval/ dir."}], "is_error": True}
    items = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try: items.append(json.loads(line))
            except json.JSONDecodeError: pass
    if not items:
        return {"content": [{"type": "text", "text": f"No parseable items in {batch_file}."}], "is_error": True}
    from . import provenance as _prov
    import time as _time
    run_id = f"critrun-{_time.strftime('%Y%m%d-%H%M%S')}"
    prov = _prov.Provenance(_MEMORY_DIR, _CRITIC_REPO, run_id, batch_file, model, seed=42, temperature=0)
    rows = []; errors = 0
    for it in items:
        prompt = ("Critique the following candidate reasoning. Emit your standard "
                  "VERDICT / STEP ANALYSIS / SEVERITY format.\n\n"
                  f"QUESTION:\n{it.get('prompt','')}\n\nCANDIDATE:\n{it.get('candidate','')}")
        try:
            verdict, meta = _call_ollama(model, prompt)
        except Exception as e:
            verdict, meta = f"<error: {e}>", {}; errors += 1
        m = _re.search(r"VERDICT:\s*(\w+)", verdict)
        critic_verdict = m.group(1).lower() if m else "(none)"
        prov.record(item_id=it.get("id"), variant=it.get("variant"), prompt=prompt,
                    raw_response=verdict, parsed_verdict=critic_verdict,
                    eval_count=meta.get("eval_count"), total_duration_ns=meta.get("total_duration"))
        rows.append({"id": it.get("id"), "variant": it.get("variant"),
                     "ground_truth_label": it.get("label"), "error_type": it.get("error_type"),
                     "critic_verdict_token": critic_verdict, "critic_full_response": verdict})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = (_MEMORY_DIR.parent / "scratch" / "critic_runs"); out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"batch_{batch_file.replace('.jsonl','')}_{model.replace(':','_')}_{stamp}.json"
    out_file.write_text(json.dumps({"batch_file": batch_file, "model": model,
        "run_id": run_id, "model_digest": prov.model_digest,
        "code_git_sha": prov.code_sha, "data_git_sha": prov.data_sha,
        "options": _DET_OPTIONS, "n_items": len(rows), "n_errors": errors,
        "NOTE": "Verdicts staged next to ground truth. NOT scored — verdict-token vs label "
                "matching is a proxy; read the full responses to judge genuine diagnosis.",
        "provenance": f"memory/provenance/{run_id}_manifest.json",
        "rows": rows}, indent=2), encoding="utf-8")
    prov.write_manifest(staged_file=f"scratch/critic_runs/{out_file.name}")
    return {"content": [{"type": "text", "text":
            f"Ran {len(rows)} candidates from {batch_file} through {model} ({errors} errors). "
            f"Verdicts staged next to ground-truth labels in scratch/critic_runs/{out_file.name}. "
            f"This is comparison material, NOT a score — whether a matching token reflects a "
            f"genuine diagnosis is yours to judge."}]}


def build_tools_server(memory_dir: Path):
    """Bind the tools to this run's memory dir and return the in-process server."""
    global _MEMORY_DIR, _CRITIC_REPO
    _MEMORY_DIR = memory_dir.resolve()
    import os
    _CRITIC_REPO = Path(os.environ.get('CRITIC_REPO', Path.home() / 'hf-critic')).resolve()
    return create_sdk_mcp_server(
        name="forge",
        version="1.0.0",
        tools=[append_log, run_critic, run_critic_batch],
    )


# The permission name the agent uses to call this: mcp__forge__append_log
APPEND_LOG_TOOL = "mcp__forge__append_log"
RUN_CRITIC_TOOL = "mcp__forge__run_critic"
RUN_CRITIC_BATCH_TOOL = "mcp__forge__run_critic_batch"
