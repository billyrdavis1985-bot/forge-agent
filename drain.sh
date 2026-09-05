#!/usr/bin/env bash
# drain.sh — work through the task queue one item at a time, unattended.
# Auto-loads .env so it can run walk-away. Each task runs inside the sandbox jail.
set -uo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
MEMORY_DIR="$PROJECT_ROOT/memory"
PY="${PY:-$PROJECT_ROOT/.venv/bin/python}"
PAUSE_SECONDS="${PAUSE_SECONDS:-5}"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

command -v bwrap >/dev/null || { echo "bwrap not found"; exit 2; }
[ -x "$PY" ] || { echo "venv python not found at $PY"; exit 2; }
[ -f "$PROJECT_ROOT/sandbox.sh" ] || { echo "sandbox.sh missing"; exit 2; }

# Auto-load .env so the API key is present across all drained runs.
if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a; . "$PROJECT_ROOT/.env"; set +a
fi

# One drain at a time.
exec 9>"$PROJECT_ROOT/.drain.lock"
if ! flock -n 9; then
  echo "another drain is already running (lock held). exiting."; exit 0
fi

reaped=$($PY -m src.queue "$MEMORY_DIR" reap)
[ "$reaped" -gt 0 ] 2>/dev/null && echo "reaped $reaped orphaned task(s) back to pending"
echo "=== drain start: $($PY -m src.queue "$MEMORY_DIR" summary) ==="

drained=0
while true; do
  if ! task="$($PY -m src.queue "$MEMORY_DIR" next)"; then
    echo "queue empty — drain complete ($drained task(s) run this session)."; break
  fi
  task_id="$(printf '%s' "$task" | head -1)"
  instruction="$(printf '%s' "$task" | tail -n +2)"
  echo; echo "--- next task: $task_id ---"
  if [ "$DRY_RUN" = "1" ]; then
    echo "[dry-run] would run: $instruction"
    echo "[dry-run] stopping after showing first pending task."; break
  fi
  "$PY" -m src.queue "$MEMORY_DIR" mark "$task_id" running
  "$PROJECT_ROOT/sandbox.sh" "$instruction"
  code=$?
  case $code in
    0) "$PY" -m src.queue "$MEMORY_DIR" mark "$task_id" done
       echo "task $task_id: done"; drained=$((drained+1)) ;;
    3) "$PY" -m src.queue "$MEMORY_DIR" mark "$task_id" pending
       echo "daily budget reached — stopping drain. $task_id left pending."; break ;;
    *) "$PY" -m src.queue "$MEMORY_DIR" mark "$task_id" error
       echo "task $task_id: ERROR (exit $code). continuing to next task." ;;
  esac
  sleep "$PAUSE_SECONDS"
done
echo "=== drain end: $($PY -m src.queue "$MEMORY_DIR" summary) ==="
