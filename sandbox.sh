#!/usr/bin/env bash
# sandbox.sh — run Forge Agent inside an OS-level bubblewrap jail.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
CRITIC_REPO="${CRITIC_REPO:-$HOME/hf-critic}"
PY="${PY:-$PROJECT_ROOT/.venv/bin/python}"

command -v bwrap >/dev/null || { echo "bwrap not found. sudo apt install bubblewrap"; exit 2; }
[ -x "$PY" ] || { echo "venv python not found at $PY"; exit 2; }

bwrap_args=(
  --ro-bind /usr /usr
  --ro-bind /etc /etc
  --symlink usr/lib /lib
  --symlink usr/lib64 /lib64
  --symlink usr/bin /bin
  --symlink usr/sbin /sbin
  --proc /proc
  --dev /dev
  --tmpfs /tmp
  --unshare-pid
  --unshare-ipc
  --unshare-uts
  --die-with-parent
  --new-session
  --hostname forge-sandbox
)
bwrap_args+=(--ro-bind "$PROJECT_ROOT" "$PROJECT_ROOT")
bwrap_args+=(--bind "$PROJECT_ROOT/memory" "$PROJECT_ROOT/memory")
bwrap_args+=(--bind "$PROJECT_ROOT/scratch" "$PROJECT_ROOT/scratch")
bwrap_args+=(--bind "$PROJECT_ROOT/runs" "$PROJECT_ROOT/runs")

# DNS: on WSL /etc/resolv.conf is a symlink into /mnt/wsl that the jail can't
# follow, so DNS resolution fails and the API call times out. Bind the REAL
# resolv.conf to the canonical path inside the jail.
# /etc/resolv.conf in the jail is a dangling symlink (-> /mnt/wsl/...), and
# bwrap can't create a file through a broken symlink. So we bind the real
# resolv.conf over the symlink's TARGET path, which we also ensure exists.
RESOLV_REAL="$(readlink -f /etc/resolv.conf)"
if [ -f "$RESOLV_REAL" ]; then
  # Replace the symlink with a real bind at /etc/resolv.conf by first binding
  # a tmpfs over /etc is too broad; instead bind the real file to the symlink
  # TARGET so the existing symlink resolves correctly inside the jail.
  bwrap_args+=(--ro-bind "$RESOLV_REAL" "$RESOLV_REAL")
fi

# CLI config: the Claude Code CLI reads ~/.claude.json (a file directly in
# $HOME, which the jail hides). Bind just that file, read-only.
if [ -f "$HOME/.claude.json" ]; then
  bwrap_args+=(--ro-bind "$HOME/.claude.json" "$HOME/.claude.json")
fi

if [ -d "$CRITIC_REPO" ]; then
  bwrap_args+=(--ro-bind "$CRITIC_REPO" "$CRITIC_REPO")
else
  echo "note: CRITIC_REPO ($CRITIC_REPO) not found — skipping its mount"
fi

if ls /dev/nvidia* >/dev/null 2>&1; then
  for dev in /dev/nvidia*; do
    bwrap_args+=(--dev-bind "$dev" "$dev")
  done
  echo "note: bound nvidia device node(s) for GPU access"
fi

# The Claude Code CLI lives under nvm in $HOME, which the jail hides. Bind the
# node version directory read-only and put its bin on PATH so the SDK can find
# `claude` inside the jail — without exposing the rest of $HOME.
CLAUDE_BIN="$(command -v claude || true)"
if [ -n "$CLAUDE_BIN" ]; then
  NODE_DIR="$(cd "$(dirname "$CLAUDE_BIN")/.." && pwd)"   # .../node/vXX.X.X
  bwrap_args+=(--ro-bind "$NODE_DIR" "$NODE_DIR")
  bwrap_args+=(--setenv PATH "$NODE_DIR/bin:/usr/bin:/bin")
else
  echo "warning: claude CLI not found on host PATH; the run will fail preflight"
fi

for cfgdir in ".claude" ".config/claude"; do
  if [ -d "$HOME/$cfgdir" ]; then
    bwrap_args+=(--ro-bind "$HOME/$cfgdir" "$HOME/$cfgdir")
  fi
done

bwrap_args+=(--chdir "$PROJECT_ROOT")

if [ "${SANDBOX_DEBUG:-0}" = "1" ]; then
  echo "=== bwrap command ==="
  printf '  %s\n' "bwrap" "${bwrap_args[@]}" "-- $PY -m src.orchestrator $*"
  echo "====================="
fi

exec bwrap "${bwrap_args[@]}" -- "$PY" -m src.orchestrator "$@"
