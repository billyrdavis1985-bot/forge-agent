#!/usr/bin/env python3
"""adjudicate.py — blinded human adjudication (council #3, packet corrected).
Presents the ORIGINAL problem, the CANDIDATE reasoning under review, and the
CRITIC'S DIAGNOSIS as three distinct panels — hiding critic identity, ground
truth, and verdict until judgment. The reviewer judges whether the critic's
diagnosis is CORRECT ABOUT THE CANDIDATE, not merely whether it sounds
convincing. Judgments -> memory/adjudications/<run_id>.jsonl (git-versioned).

Usage: python -m src.adjudicate <memory_dir> <critic_runs_dir> [--status]"""
from __future__ import annotations
import json, sys, hashlib, os
from datetime import datetime, timezone
from pathlib import Path

RUBRIC_VERSION = "2"
RUBRIC = [
    ("detected", "Did the critic detect the actual defect in the candidate? (flawed items)  [y/n/na]"),
    ("mechanism", "Did it identify the correct mechanism / location of the defect?  [y/n/na]"),
    ("invented", "Did it invent a defect that is not actually in the candidate?  [y/n]"),
    ("sufficient", "Was the diagnosis materially correct about the candidate's evidence?  [y/n]"),
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

def _load_candidate_source():
    """(batch_file, id, variant) -> {problem, candidate} from the critic repo.
    The staged files hold the critic's diagnosis but NOT the original problem or
    candidate — those live in eval/candidates_*.jsonl and must be joined so the
    reviewer judges the diagnosis against the real evidence."""
    critic_repo = Path(os.environ.get("CRITIC_REPO", Path.home() / "hf-critic"))
    src = {}
    eval_dir = critic_repo / "eval"
    if not eval_dir.is_dir(): return src
    for bf in eval_dir.glob("candidates_*.jsonl"):
        for line in bf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line: continue
            try: it = json.loads(line)
            except json.JSONDecodeError: continue
            src[(bf.name, it.get("id"), it.get("variant"))] = {
                "problem": it.get("prompt",""), "candidate": it.get("candidate","")}
    return src

def collect_pending(critic_runs_dir, already):
    candidate_src = _load_candidate_source()
    latest = {}
    for f in sorted(critic_runs_dir.glob("batch_*.json")):
        try: d = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError: continue
        latest[(d.get("batch_file"), d.get("model"))] = d
    pending = []
    for d in latest.values():
        run_id = d.get("run_id","unknown"); model = d.get("model"); bf = d.get("batch_file")
        for row in d.get("rows", []):
            k = _key(run_id, row.get("id"), row.get("variant"), model)
            if k in already: continue
            src = candidate_src.get((bf, row.get("id"), row.get("variant")), {})
            pending.append({"key":k,"run_id":run_id,"critic":model,
                "item_id":row.get("id"),"variant":row.get("variant"),
                "ground_truth":row.get("ground_truth_label"),"error_type":row.get("error_type"),
                "critic_token":row.get("critic_verdict_token"),
                "problem":src.get("problem","(original problem not found in batch source)"),
                "candidate":src.get("candidate","(candidate reasoning not found in batch source)"),
                "critic_diagnosis":row.get("critic_full_response","")})
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
    print(f"\n{len(pending)} verdict(s) to adjudicate. BLIND MODE: critic identity, "
          f"ground truth, and verdict are hidden until you commit a judgment.\n"
          f"You judge whether the critic's DIAGNOSIS is correct about the CANDIDATE.\n"
          f"Answers: y / n / na. 'skip' to defer, 'quit' to stop (progress saved).\n")
    out_by_run = {}; n_done = 0
    for i, p in enumerate(pending, 1):
        print("="*70)
        print(f"[{i}/{len(pending)}]  (critic identity, ground truth, verdict hidden)")
        print(f"\n--- ORIGINAL PROBLEM ---\n"); print(p["problem"][:2500])
        print(f"\n--- CANDIDATE REASONING (what the critic was asked to judge) ---\n"); print(p["candidate"][:3000])
        print(f"\n--- CRITIC'S DIAGNOSIS (judge whether this is correct about the candidate) ---\n"); print(p["critic_diagnosis"][:3000])
        print("\n"+"-"*70+"\nJudge the critic's diagnosis against the candidate:")
        answers = {}; aborted = False
        for field, q in RUBRIC:
            a = _ask("  "+q, VALID[field])
            if a == "quit": aborted="quit"; break
            if a == "skip": aborted="skip"; break
            answers[field] = a
        if aborted == "quit": print("\nStopping. Progress saved."); break
        if aborted == "skip": print("  (skipped)\n"); continue
        rec = {"key":p["key"],"run_id":p["run_id"],"critic":p["critic"],
               "item_id":p["item_id"],"variant":p["variant"],"rubric_version":RUBRIC_VERSION,
               "judgment":answers,
               "diagnosis_sha256":hashlib.sha256(p["critic_diagnosis"].encode("utf-8")).hexdigest(),
               "candidate_sha256":hashlib.sha256(p["candidate"].encode("utf-8")).hexdigest(),
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
        print("usage: python -m src.adjudicate <memory_dir> <critic_runs_dir> [--status]", file=sys.stderr); return 2
    if "--status" in args: return status(Path(args[0]), Path(args[1]))
    return adjudicate(Path(args[0]), Path(args[1]))

if __name__ == "__main__":
    sys.exit(main())
