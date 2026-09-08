#!/usr/bin/env bash
# run.sh — CANONICAL launcher. Every execution path converges here:
# manual runs, the systemd service, and the queue drain all route through
#   flock (single session)  ->  sandbox.sh (bubblewrap jail)  ->  orchestrator
# so the agent is ALWAYS sandboxed by default, not only when sandbox.sh is
# invoked deliberately. This closes the gap where run.sh / systemd previously
# called the orchestrator directly, bypassing the kernel jail.
set -euo pipefail
cd "$(dirname "$0")"

# flock guards against concurrent sessions racing on the same memory dir.
# The lock lives HERE (the one canonical entry), not in sandbox.sh, so the
# jail layer stays a pure launcher and there is exactly one lock holder.
exec flock -n .run.lock "$(dirname "$0")/sandbox.sh" "$@"
