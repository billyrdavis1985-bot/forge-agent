"""queue.py — task queue for unattended drain runs."""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

QUEUE_NAME = "queue.jsonl"

def _queue_path(memory_dir: Path) -> Path:
    return memory_dir / QUEUE_NAME

def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out

def _save(path: Path, tasks: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in tasks) + "\n",
                    encoding="utf-8")

def next_pending(memory_dir: Path) -> dict | None:
    for t in _load(_queue_path(memory_dir)):
        if t.get("status") == "pending":
            return t
    return None

def mark(memory_dir: Path, task_id: str, status: str) -> None:
    path = _queue_path(memory_dir)
    tasks = _load(path)
    for t in tasks:
        if t.get("id") == task_id:
            t["status"] = status
            t[f"{status}_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            break
    _save(path, tasks)

def reap_orphans(memory_dir: Path) -> int:
    """Reset tasks stuck in 'running' (orphaned by sleep/kill) back to pending.
    flock guarantees one drain at a time, so any 'running' at start is orphaned."""
    path = _queue_path(memory_dir)
    tasks = _load(path)
    n = 0
    for t in tasks:
        if t.get("status") == "running":
            t["status"] = "pending"
            t["reaped_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            n += 1
    if n:
        _save(path, tasks)
    return n

def summary(memory_dir: Path) -> dict:
    tasks = _load(_queue_path(memory_dir))
    counts: dict[str, int] = {}
    for t in tasks:
        s = t.get("status", "pending")
        counts[s] = counts.get(s, 0) + 1
    return {"total": len(tasks), **counts}

def _main() -> int:
    if len(sys.argv) < 3:
        print("usage: python -m src.queue <memory_dir> <next|mark|summary|reap> [args]", file=sys.stderr)
        return 2
    memory_dir = Path(sys.argv[1]); cmd = sys.argv[2]
    if cmd == "reap":
        print(reap_orphans(memory_dir)); return 0
    if cmd == "next":
        t = next_pending(memory_dir)
        if t is None:
            return 1
        # id on line 1, instruction on line 2 (bash cannot hold NUL bytes).
        sys.stdout.write(t["id"] + "\n" + t.get("instruction", "")); return 0
    if cmd == "mark":
        mark(memory_dir, sys.argv[3], sys.argv[4]); return 0
    if cmd == "summary":
        s = summary(memory_dir)
        print(" ".join(f"{k}={v}" for k, v in s.items())); return 0
    print(f"unknown command: {cmd}", file=sys.stderr); return 2

if __name__ == "__main__":
    sys.exit(_main())
