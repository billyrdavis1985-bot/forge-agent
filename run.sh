#!/usr/bin/env bash
# Phase 0 launcher. Invoke by hand; Phase 1 wires this to a systemd timer.
set -euo pipefail
cd "$(dirname "$0")"
# flock guards against concurrent sessions racing on the same memory dir.
exec flock -n .run.lock .venv/bin/python -m src.orchestrator "$@"
