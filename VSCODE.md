# Building in VS Code

## Setup (3 steps)

1. Open the project folder. Accept the recommended extensions prompt
   (Python, debugpy, YAML, Remote-SSH).
2. Run task **"Setup: create venv + install deps"** — `Ctrl+Shift+P` →
   *Tasks: Run Task*. Then `Ctrl+Shift+P` → *Python: Select Interpreter* →
   pick `./.venv`.
3. `cp .env.example .env` and put your real API key in it. `.env` is
   gitignored; `launch.json` loads it automatically via `envFile`.

## Platform note — read this first

`run.sh` uses `flock`, which is Linux-only. On Windows it will not run.

- **Agent runs on a Linux box** (recommended): use the **Remote-SSH**
  extension and open the project *on that machine*. You get real editing with
  the correct filesystem, PATH, and systemd underneath. This is the setup that
  matches the runbook.
- **Windows local dev**: use WSL (Remote-WSL extension). A native Windows
  checkout will fail on `run.sh` and on the systemd deployment entirely.
- The debug configs bypass `run.sh` and invoke the module directly, so **they
  work on any platform** — but note they also bypass the `flock` guard. Don't
  debug a session while the timer might fire.

## Debugging: the thing worth doing on day one

Set a breakpoint inside `gate()` in `src/guards.py`, then launch
**"Agent: run session (prompt for instruction)"**.

Because `can_use_tool` runs in-process, execution pauses on *every tool call
the agent attempts, before it executes*. Inspect `tool_name` and `input_data`
to watch the agent's actual decisions — which files it reaches for, what bash
it tries, whether it respects the append-only protocol. Half an hour of this
teaches you more about the agent's behavior than any amount of reading logs.

`justMyCode: false` is set, so you can also step into the SDK internals if you
want to see the agent loop itself.

## Debug configs

| Config | Use |
|--------|-----|
| Agent: run session (auto-pick task) | Normal run; agent picks top open question |
| Agent: run session (prompt for instruction) | Prompts for a task string, then runs |
| Agent: status (no API call) | Ledger view — free, no tokens spent |

## Tasks

| Task | Use |
|------|-----|
| Setup: create venv + install deps | First-time setup |
| Agent: status | Recent runs, cost, today's spend |
| Memory: show run history | `git log` of run commits |
| Memory: what did the last run change? | Full diff of the most recent run |
| Memory: revert last run | Undo a bad run (prompts for confirmation) |
| Tail latest transcript | Live-follow the newest run log |

## Working alongside a running agent

The agent rewrites `memory/` and commits to git while you may have those files
open. Two consequences:

- `files.autoSave` is set to `onFocusChange` so your edits don't sit unsaved
  and collide with the agent's writes.
- The Source Control panel will fill with `run: run-...` commits. That's the
  audit trail working as intended — each one is independently revertible.

If you're editing `memory/CLAUDE.md` or `open_questions.md` while a session
runs, you're both writing the same files. Stop the timer first
(`sudo systemctl stop forge-agent.timer`) when doing significant memory edits.

## Secrets

Two separate places, deliberately:

- `.env` (gitignored) — local VS Code runs only.
- `/etc/forge-agent/env` (root-owned, 0600) — the systemd deployment.

Keep `HEALTHCHECK_URL` out of your local `.env` so laptop test runs don't ping
the production check and mask a real outage.
