# Forge Agent — Phase 1

A minimal autonomous research agent with git-versioned persistent memory,
built on the Claude Agent SDK. Phase 1 adds unattended operation: a systemd
timer, a SQLite operations ledger with a daily budget ceiling, a dead-man's
switch, and enforced append-only memory.

**Validate a manual run before enabling the timer** — see `deploy/RUNBOOK.md`.
The scheduler multiplies whatever the agent does, mistakes included.

## What each piece does

| Path | Role |
|------|------|
| `config/agent.yaml` | Model routing + safety caps + tool/write allowlists — the only file you edit to retune behavior. |
| `memory/CLAUDE.md` | Standing mission + memory protocol, loaded into every session. |
| `memory/open_questions.md` | The task frontier. Agent picks the top item each run. |
| `memory/research_log.md` | Append-only run journal. |
| `memory/findings/` | One markdown file per topic. |
| `src/orchestrator.py` | Entry point: preflight → budget gate → SDK loop under guards → git-commit → ledger → health ping. |
| `src/ledger.py` | SQLite operations record: run history, cost, daily budget ceiling. |
| `src/health.py` | Dead-man's switch (healthchecks.io). Fail-open: never breaks a run. |
| `deploy/` | systemd unit + timer, env template, deployment runbook. |
| `src/memory_manager.py` | Git plumbing + snapshot assembly. Every run is an atomic, revertible commit. |
| `src/guards.py` | Permission gate: write containment, enforced append-only log, bash command gating. |
| `runs/` | Full transcript per session (audit trail). |

## Setup

Requires Python 3.10+ and the Claude Code CLI on PATH.

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...        # your API key
```

## Run one session

```bash
./run.sh                          # agent picks the top open question
./run.sh "summarize findings"     # or give it an explicit instruction
python -m src.orchestrator --status   # recent runs, cost, today's spend
```

Exit codes: 0 ok, 1 run failed, 2 preflight failed, 3 skipped (budget reached).

After a run: inspect `memory/research_log.md` for the new entry, and
`git log --oneline` for the commit. If the agent ever clobbers its notes,
`git revert <sha>` restores them byte-for-byte.

## Safety properties

- **Write containment** — the permission gate denies any write outside the
  configured roots, including path-traversal escapes. Reads are unrestricted.
- **Budget kill-switch** — `max_budget_usd` aborts the run at the spend cap.
- **Turn cap** — `max_turns` bounds the agent loop.
- **Recoverability** — every run is a git commit; nothing the agent does is
  unrecoverable.
- **Concurrency guard** — `run.sh` uses `flock` so two launches can't race on
  the same memory directory; orphaned runs are reaped on next start.
- **Append-only log** — enforced at the gate: Write/Edit on `research_log.md`
  is denied, and truncating `>` redirects onto it are blocked. Only `>>`.
- **Daily budget ceiling** — spans runs, so many small sessions can't add up
  past the cap the way a per-session limit alone would allow.

## Known limitations (by design)

- **No web access.** Phase 2 adds it behind a read-only subagent so fetched
  content cannot trigger writes (prompt-injection containment).
- **Bash gating is denylist-based.** It blocks known-destructive patterns, not
  every conceivable one. Git recoverability is the real backstop, not the regex.
- **No context compaction yet.** When `findings/` outgrows the window, add a
  Haiku summarization pass (Phase 2) before reaching for a vector store.

## Building in VS Code

See `VSCODE.md` — setup, debug configs, and the platform note (`run.sh` needs
Linux or WSL; use Remote-SSH if the agent runs on a separate box).

## Deployment

See `deploy/RUNBOOK.md` for install, systemd setup, monitoring, exit codes,
recovery procedure, and known failure modes.
