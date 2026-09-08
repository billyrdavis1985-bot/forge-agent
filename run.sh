#!/usr/bin/env bash
# run.sh — canonical Forge execution entry point.
# All agent sessions route through:
#   global flock -> bubblewrap sandbox -> orchestrator
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

# 75 = temporary failure / execution lock already held.
# This lets queue drains distinguish lock contention from an actual agent failure.
exec flock -n -E 75 .run.lock "$PROJECT_ROOT/sandbox.sh" "$@"
