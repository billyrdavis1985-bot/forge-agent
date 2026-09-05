#!/usr/bin/env bash
# load_grid.sh — populate memory/queue.jsonl with the corruption-study grid.
# JSON is built by Python (json.dumps) so quotes in the instruction escape correctly.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-$PROJECT_ROOT/.venv/bin/python}"
SHOW=0
[ "${1:-}" = "--show" ] && SHOW=1
SHOW=$SHOW "$PY" - "$PROJECT_ROOT" << 'PYEOF'
import json, os, sys
from pathlib import Path
root = Path(sys.argv[1])
show = os.environ.get("SHOW") == "1"
batches = ["candidates_b2.jsonl", "candidates_b3.jsonl", "candidates_b4.jsonl"]
models = ["critic-mistral", "critic"]
tasks = []
for batch in batches:
    for model in models:
        instr = (f'Use the run_critic_batch tool to run the batch file '
                 f'"{batch}" through the "{model}" model. Make exactly ONE call '
                 f'to run_critic_batch. Report how many items were processed and '
                 f'where results were staged. Do NOT score or judge verdicts '
                 f'against labels — the tool stages comparison material for the '
                 f'researcher. Append your log handoff when done.')
        tasks.append({"id": f"{batch[:-6]}-{model}", "instruction": instr, "status": "pending"})
if show:
    print(f"Would queue {len(tasks)} tasks:")
    for t in tasks:
        print("  " + t["id"])
    sys.exit(0)
q = root / "memory" / "queue.jsonl"
q.parent.mkdir(parents=True, exist_ok=True)
q.write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in tasks) + "\n", encoding="utf-8")
print(f"Queued {len(tasks)} tasks into memory/queue.jsonl:")
for t in tasks:
    print("  " + t["id"])
print("\nDrain with:  ./drain.sh   (or ./drain.sh --dry-run to preview)")
PYEOF
