# Deployment Runbook — Phase 1

## Before you automate: validate one manual run

Do not enable the timer until a hand-run succeeds. The scheduler multiplies
whatever the agent does, including mistakes.

```bash
cd /opt/forge-agent
export ANTHROPIC_API_KEY=sk-ant-...
./run.sh "Summarize the current program state into findings/program_overview.md"
```

Then verify all four:

```bash
git log --oneline                 # a "run: run-..." commit exists
tail -30 memory/research_log.md   # a new dated entry was appended
cat memory/open_questions.md      # the frontier was updated
python -m src.orchestrator --status   # cost and turns look sane
```

If the agent wrote nothing to the log, fix that before automating — the
handoff discipline is the thing that makes unattended runs worth anything.

## Install

```bash
sudo mkdir -p /opt/forge-agent /etc/forge-agent
sudo rsync -a ./ /opt/forge-agent/
python3 -m venv /opt/forge-agent/.venv
/opt/forge-agent/.venv/bin/pip install -r requirements.txt

sudo cp deploy/env.example /etc/forge-agent/env
sudo chmod 600 /etc/forge-agent/env && sudo chown root:root /etc/forge-agent/env
sudo nano /etc/forge-agent/env          # add your real key

sudo cp deploy/forge-agent.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
```

Edit the `User=` line in the service (it ships as `%i`; set it to the account
that owns `/opt/forge-agent`).

## Dry run through systemd before enabling the timer

```bash
sudo systemctl start forge-agent.service
journalctl -u forge-agent.service -n 50 --no-pager
```

This is where PATH problems surface. systemd does not inherit your login
shell's PATH, so the Claude Code CLI is frequently missing here even though it
works in your terminal. Preflight catches it and exits 2 with a clear message.

## Enable the schedule

```bash
sudo systemctl enable --now forge-agent.timer
systemctl list-timers forge-agent.timer   # confirm next fire time
```

## Exit codes

| Code | Meaning | systemd treats as |
|------|---------|-------------------|
| 0 | Run succeeded | success |
| 1 | Run failed (agent error/crash) | failure |
| 2 | Preflight failed (misconfiguration) | failure |
| 3 | Skipped: daily budget reached | success (`SuccessExitStatus=0 3`) |

Exit 3 is listed as a success so a budget-capped day does not page you.

## Monitoring

Set `HEALTHCHECK_URL` in `/etc/forge-agent/env` to a healthchecks.io check URL.
The agent pings `/start` on begin, the base URL on success, `/fail` on error.
Configure the check's period to ~7h with a 1h grace for the 6-hourly timer.
Absent the variable, pings are a silent no-op.

## Budget control

Two independent ceilings:
- `max_budget_usd` (per session) — enforced by the SDK, aborts a runaway loop.
- `daily_budget_usd` (per UTC day, across all runs) — enforced by the ledger
  before the session starts. The per-session cap alone would not stop many
  sessions adding up.

Both live in `config/agent.yaml`. Start conservative; raise once you have a few
days of real cost data from `--status`.

## Recovery

Every run is one git commit. If the agent damages its notes:

```bash
git log --oneline                # find the run's commit
git revert <sha>                 # undo it, keeping history
git show <sha> --stat            # or inspect what it changed first
```

`research_log.md` is additionally protected: Write/Edit on it is denied at the
permission gate, and a truncating `>` redirect is blocked. Only `>>` appends.

## Known failure modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| Exit 2, "CLI not found" | systemd PATH | Set `Environment=PATH=` in the unit |
| Exit 2, no API key | EnvironmentFile unreadable/missing | Check `/etc/forge-agent/env` perms |
| Runs but no log entry | Agent skipped the handoff step | Strengthen the finish instruction in `memory/CLAUDE.md` |
| Timer never fires | Timer not enabled | `systemctl enable --now forge-agent.timer` |
| Two runs collide | — | `flock` in `run.sh` prevents this; second run exits immediately |
| Repeated exit 3 | Daily cap too low, or a run overspent | Review `--status`, tune caps |

## Deliberate design choices worth remembering

- **`Persistent=false`** on the timer: missed runs are NOT caught up. A
  catch-up storm after downtime would fire several sessions at once against the
  same memory. A skipped window costs nothing since work is queue-driven.
- **Markdown owns tasks, SQLite owns operations.** The agent reads and rewrites
  `open_questions.md`; the ledger never tracks tasks. One source of truth each.
- **No web access yet.** Phase 2 adds it behind a read-only subagent so fetched
  content cannot trigger writes (prompt-injection containment).
