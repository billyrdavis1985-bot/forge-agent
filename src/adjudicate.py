#!/usr/bin/env python3
"""adjudicate.py — blinded human adjudication (council recommendation #3).
Shows each staged verdict with critic identity AND ground truth hidden, asks the
reviewer to judge diagnosis quality against a fixed rubric FIRST, then reveals.
Makes the human gate reproducible/auditable and is the prerequisite for
legitimate scoring. Judgments -> memory/adjudications/<run_id>.jsonl (git-versioned).

Usage: python -m src.adjudicate <memory_dir> <critic_runs_dir> [--status]"""
from __future__ import annotations
import json, sys, hashlib
from datetime import datetime, timezone
from pathlib import Path

RUBRIC_VERSION = "1"
RUBRIC = [
    ("detected", "Did the critic detect the actual defect? (for a flawed item)  [y/n/na]"),
    ("mechanism", "Did it identify the correct mechanism / where the defect is?  [y/n/na]"),
    ("invented", "Did it invent a defect that is not there? (false-alarm check)  [y/n]"),
    ("sufficient", "Was the explanation materially sufficient to trust?  [y/n]"),
]
VALID = {"detected":{"y","n","na"},"mechanism":{"y","n","na"},
         "invented":{"y","n"},"sufficient":{"y","n"}}

def _adj_dir(memory_dir):
    d = memory_dir/"adjudications"; d.mkdir(parents=True, exist_ok=True); return d

def _key(run_id, item_id, variant, critic):
    return f"{run_id}::{item_id}::{variant}::{critic}"

def load_adjudicated(memory_dir):
    done = set()
    for f in _adj_dir(memory_dir).glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try: done.add(json.loads(line)["key"])
                except Exception: pass
    return done

def collect_pending(critic_runs_dir, already):
    latest = {}
    for f in sorted(critic_runs_dir.glob("batch_*.json")):
        try: d = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError: continue
        latest[(d.get("batch_file"), d.get("model"))] = d
    pending = []
    for d in latest.values():
        run_id = d.get("run_id","unknown"); model = d.get("model")
        for row in d.get("rows", []):
            k = _key(run_id, row.get("id"), row.get("variant"), model)
            if k in already: continue
            pending.append({"key":k,"run_id":run_id,"critic":model,
                "item_id":row.get("id"),"variant":row.get("variant"),
                "ground_truth":row.get("ground_truth_label"),"error_type":row.get("error_type"),
                "critic_token":row.get("critic_verdict_token"),
                "reasoning":row.get("critic_full_response","")})
    return pending

def _ask(prompt, valid):
    while True:
        v = input(prompt+" ").strip().lower()
        if v in valid: return v
        if v in ("skip","s"): return "skip"
        if v in ("quit","q"): return "quit"
        print(f"    (enter one of {sorted(valid)}, or 'skip' / 'quit')")

def adjudicate(memory_dir, critic_runs_dir):
    already = load_adjudicated(memory_dir)
    pending = collect_pending(critic_runs_dir, already)
    if not pending:
        print("Nothing pending — all staged verdicts are adjudicated."); return 0
    print(f"\n{len(pending)} verdict(s) to adjudicate. BLIND MODE: critic identity "
          f"and ground truth are hidden until you commit a judgment.\n"
          f"Answers: y / n / na. 'skip' to defer, 'quit' to stop (progress saved).\n")
    out_by_run = {}; n_done = 0
    for i, p in enumerate(pending, 1):
        print("="*70)
        print(f"[{i}/{len(pending)}]  (critic + ground truth hidden)")
        print(f"\nCANDIDATE REASONING UNDER REVIEW:\n")
        print(p["reasoning"][:4000])
        print("\n"+"-"*70+"\nJudge the diagnosis quality:")
        answers = {}; aborted = False
        for field, q in RUBRIC:
            a = _ask("  "+q, VALID[field])
            if a == "quit": aborted = "quit"; break
            if a == "skip": aborted = "skip"; break
            answers[field] = a
        if aborted == "quit": print("\nStopping. Progress saved."); break
        if aborted == "skip": print("  (skipped)\n"); continue
        rec = {"key":p["key"],"run_id":p["run_id"],"critic":p["critic"],
               "item_id":p["item_id"],"variant":p["variant"],"rubric_version":RUBRIC_VERSION,
               "judgment":answers,
               "reasoning_sha256":hashlib.sha256(p["reasoning"].encode("utf-8")).hexdigest(),
               "adjudicated_at":datetime.now(timezone.utc).isoformat(timespec="seconds")}
        out_by_run.setdefault(p["run_id"], []).append(rec); n_done += 1
        print(f"\n  --- reveal ---")
        print(f"  critic:        {p['critic']}")
        print(f"  variant:       {p['variant']}  (ground truth: {p['ground_truth']})")
        if p["error_type"]: print(f"  planted error: {p['error_type']}")
        print(f"  critic token:  {p['critic_token']}\n")
    for run_id, recs in out_by_run.items():
        path = _adj_dir(memory_dir)/f"{run_id}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            for r in recs: f.write(json.dumps(r, ensure_ascii=False)+"\n")
    print("="*70)
    print(f"Adjudicated {n_done} verdict(s) this session. Written to memory/adjudications/.")
    return 0

def status(memory_dir, critic_runs_dir):
    already = load_adjudicated(memory_dir)
    pending = collect_pending(critic_runs_dir, already)
    print(f"Adjudication status: {len(already)} adjudicated, {len(pending)} pending "
          f"({len(already)+len(pending)} total staged verdicts).")
    return 0

def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print("usage: python -m src.adjudicate <memory_dir> <critic_runs_dir> [--status]",
              file=sys.stderr); return 2
    if "--status" in args: return status(Path(args[0]), Path(args[1]))
    return adjudicate(Path(args[0]), Path(args[1]))

if __name__ == "__main__":
    sys.exit(main())
