#!/usr/bin/env bash
# sandbox_probe.sh — prove the OS-level jail works, independent of the agent.
set -uo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
CRITIC_REPO="${CRITIC_REPO:-$HOME/hf-critic}"

pass=0; fail=0
check() {
  local label="$1" expect="$2" code="$3"
  if { [ "$expect" = block ] && [ "$code" -ne 0 ]; } || \
     { [ "$expect" = allow ] && [ "$code" -eq 0 ]; }; then
    echo "  [PASS] $label"; pass=$((pass+1))
  else
    echo "  [FAIL] $label (exit=$code, wanted $expect)"; fail=$((fail+1))
  fi
}

[ -d "$CRITIC_REPO" ] && CRITIC_MOUNT=1 || CRITIC_MOUNT=""

jail() {
  bwrap \
    --ro-bind /usr /usr --ro-bind /etc /etc \
    --symlink usr/lib /lib --symlink usr/lib64 /lib64 \
    --symlink usr/bin /bin --symlink usr/sbin /sbin \
    --proc /proc --dev /dev --tmpfs /tmp \
    --unshare-pid --unshare-ipc --die-with-parent \
    --ro-bind "$PROJECT_ROOT" "$PROJECT_ROOT" \
    --bind "$PROJECT_ROOT/scratch" "$PROJECT_ROOT/scratch" \
    ${CRITIC_MOUNT:+--ro-bind "$CRITIC_REPO" "$CRITIC_REPO"} \
    --chdir "$PROJECT_ROOT" \
    -- "$@"
}

echo "=== Sandbox jail probe ==="

jail sh -c "echo test > $PROJECT_ROOT/scratch/.probe_ok" 2>/dev/null
check "write to scratch/ (should work)" allow $?
rm -f "$PROJECT_ROOT/scratch/.probe_ok"

if [ -n "$CRITIC_MOUNT" ]; then
  jail sh -c "echo pwned > $CRITIC_REPO/JAIL_ESCAPE.txt" 2>/dev/null
  check "write to hf-critic (should be BLOCKED by kernel)" block $?
  [ -f "$CRITIC_REPO/JAIL_ESCAPE.txt" ] && { echo "  [FAIL] file leaked to host!"; rm -f "$CRITIC_REPO/JAIL_ESCAPE.txt"; fail=$((fail+1)); } || echo "  [PASS] no file on host"
  jail sh -c "head -1 $CRITIC_REPO/README.md >/dev/null" 2>/dev/null
  check "read hf-critic (should work)" allow $?
fi

jail sh -c "echo x > /home/$(whoami)/ESCAPE.txt" 2>/dev/null
# Judge by whether a file actually reached the HOST, not by the in-jail exit
# code: a write can "succeed" into an ephemeral jail path without escaping.
if [ -f "$HOME/ESCAPE.txt" ]; then
  echo "  [FAIL] write to \$HOME leaked a real file to host!"; rm -f "$HOME/ESCAPE.txt"; fail=$((fail+1))
else
  echo "  [PASS] write to \$HOME did not reach host (no escape)"; pass=$((pass+1))
fi

jail sh -c "echo x > /etc/JAIL_ESCAPE" 2>/dev/null
check "write to /etc (should be BLOCKED — read-only)" block $?

echo
echo "=== RESULT: $pass passed, $fail failed ==="
[ "$fail" -eq 0 ] && echo "JAIL VERIFIED — kernel enforces the boundary." || echo "JAIL NOT SOUND — do not trust it yet."
exit $fail
