# Windows Quickstart (PowerShell)

## 1. Move the project out of Downloads

`Downloads` is a bad home for a git repo that an agent writes to and that you
may later schedule. Pick a stable path:

```powershell
mkdir C:\dev
Move-Item C:\Users\Billy\Downloads\forge-agent-phase1-vscode C:\dev\forge-agent
cd C:\dev\forge-agent
```

## 2. Create the venv and install dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then in VS Code: `Ctrl+Shift+P` → **Python: Select Interpreter** → choose
`.venv\Scripts\python.exe`.

## 3. Verify without spending anything

```powershell
.\.venv\Scripts\python.exe -m src.orchestrator --status
```

Expect: `No runs recorded yet.` That confirms imports, config parsing, and
ledger creation all work. This path deliberately does not require the Claude
Code CLI or an API key.

## 4. Set your key

```powershell
Copy-Item .env.example .env
notepad .env        # paste your real ANTHROPIC_API_KEY
```

## 5. Install the Claude Code CLI

The Python SDK shells out to it. Preflight will tell you (exit 2) if it's
missing:

```powershell
npm install -g @anthropic-ai/claude-code
claude --version
```

Requires Node.js 18+. If `claude` isn't found afterward, restart PowerShell so
the PATH refresh takes effect.

## 6. First run

```powershell
.\run.ps1 "Read the memory directory and write a short orientation note to findings/orientation.md describing what you can see and what context you're missing"
```

If PowerShell blocks the script:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

`run.ps1` loads `.env`, holds an exclusive lock file so two sessions can't race
on `memory/`, and reports the exit code in plain language.

## Windows vs Linux — what differs

| | Windows | Linux |
|---|---|---|
| Launcher | `run.ps1` | `run.sh` |
| Concurrency guard | exclusive file lock | `flock` |
| Env loading | `run.ps1` reads `.env` | systemd `EnvironmentFile` |
| Scheduling | Task Scheduler (not provided) | systemd timer (in `deploy/`) |

**The systemd deployment in `deploy/` is Linux-only.** For unattended
operation on a schedule, run the agent on a Linux box and use VS Code's
Remote-SSH extension to develop against it. Windows is fine for building and
manual runs; it is not the deployment target the runbook describes.

If you want unattended runs on Windows anyway, Task Scheduler can call
`run.ps1` — but you lose the exit-code handling (`SuccessExitStatus=0 3`),
`journalctl` logging, and the hardening directives in the unit file. Worth
knowing before you commit to it.
