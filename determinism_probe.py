#!/usr/bin/env python3
"""Diagnose why critic verdicts flip across identical runs.
Tests the two flipping items under 3 configs to isolate num_ctx as the cause."""
import json, sys, hashlib, urllib.request
from pathlib import Path
from collections import Counter

OLLAMA = "http://localhost:11434/api/generate"
CRITIC_REPO = Path.home() / "hf-critic"
FLIPPERS = {"LSQ-12", "MPQ-07"}

def call(model, prompt, options):
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False,
                          "options": options}).encode()
    req = urllib.request.Request(OLLAMA, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode()).get("response", "")

def verdict_of(text):
    import re
    m = re.search(r"VERDICT:\s*(\w+)", text)
    return m.group(1).lower() if m else "(none)"

def load_flipping_items():
    src = CRITIC_REPO / "eval" / "candidates_b5.jsonl"
    items = []
    for line in src.read_text().splitlines():
        if not line.strip(): continue
        it = json.loads(line)
        if it.get("id") in FLIPPERS:
            items.append(it)
    return items

def make_prompt(it):
    return ("Critique the following candidate reasoning. Emit your standard "
            "VERDICT / STEP ANALYSIS / SEVERITY format.\n\n"
            f"QUESTION:\n{it.get('prompt','')}\n\nCANDIDATE:\n{it.get('candidate','')}")

def run_config(model, items, n, options, label):
    print(f"\n=== {label} ===  options={options}")
    for it in items:
        prompt = make_prompt(it)
        verdicts, hashes = [], set()
        for _ in range(n):
            text = call(model, prompt, options)
            verdicts.append(verdict_of(text))
            hashes.add(hashlib.sha256(text.encode()).hexdigest())
        vc = Counter(verdicts)
        flipped = len(set(verdicts)) > 1
        byte_ident = len(hashes) == 1
        flag = "FLIPS" if flipped else ("byte-stable" if byte_ident else "text-varies/verdict-stable")
        print(f"  {it['id']:8} ({it['variant']:16}) x{n}: {dict(vc)}  [{flag}]")

def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "critic-mistral"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    items = load_flipping_items()
    if not items:
        print("could not load flipping items"); return 1
    print(f"Probing {len(items)} flipping items on {model}, {n} repeats each.")
    run_config(model, items, n, {"seed": 42, "temperature": 0}, "A: CURRENT (no num_ctx)")
    run_config(model, items, n, {"seed": 42, "temperature": 0, "num_ctx": 8192},
               "B: num_ctx=8192 pinned")
    run_config(model, items, n, {"seed": 42, "temperature": 0, "num_ctx": 8192,
               "num_predict": 1024, "top_k": 1, "top_p": 1.0},
               "C: num_ctx + top_k=1 greedy lock")
    print("\nInterpretation:")
    print("  If A flips but B/C stable -> fix is pinning num_ctx (one line).")
    print("  If all configs flip       -> GPU FP nondeterminism; sample-N redesign.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
