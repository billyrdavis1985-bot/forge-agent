"""
memory_manager.py — the persistence + recoverability layer.

Wraps the memory/ directory in git so every session's changes are an atomic,
revertible commit. This is the single most important safety property in the
system: if the agent clobbers its own notes, `git revert` gets them back
byte-for-byte with full attribution of which run caused the damage.

Phase 0 responsibilities only:
  - ensure the repo exists
  - load the memory snapshot that seeds the system prompt
  - commit the working tree after a run, tagged with the run id
"""

from __future__ import annotations

import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path


class MemoryManager:
    """Manages the agent's memory as its OWN git repo, independent of the code repo.

    Git operations target `memory/`, not the project root. This is the core of
    the two-repo design: the code (src/, deploy/, config) is one repo — public,
    the showcased machinery — and the agent's working memory is a SEPARATE repo
    with its own history. The code repo carries memory/ only as an empty
    scaffold (.gitkeep files); the real memory repo is initialized here on first
    run and accumulates the run: commits. Keeping them apart stops thousands of
    run commits from burying the code history, and keeps research memory out of
    the public showcase.
    """

    def __init__(self, project_root: Path):
        self.root = project_root
        self.memory_dir = project_root / "memory"

    # ---- git plumbing (scoped to the memory repo) ---------------------
    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(self.memory_dir), *args],
            capture_output=True,
            text=True,
        )

    def ensure_repo(self) -> None:
        # A .git INSIDE memory/ means the memory repo is initialized. This is
        # distinct from the code repo's .git at the project root.
        if not (self.memory_dir / ".git").exists():
            self._git("init", "-q")
            self._git("add", "-A")
            self._git("commit", "-q", "-m", "chore: initial memory state")

    def commit_run(self, run_id: str) -> str | None:
        """Commit everything changed during a run. Returns the commit sha, or None if clean."""
        self._git("add", "-A")
        status = self._git("status", "--porcelain")
        if not status.stdout.strip():
            return None  # nothing changed this run
        self._git("commit", "-q", "-m", f"run: {run_id}")
        sha = self._git("rev-parse", "HEAD").stdout.strip()
        return sha

    # ---- snapshot for the system prompt -------------------------------
    def load_snapshot(self, log_tail_lines: int = 40) -> str:
        """Assemble the standing context the agent reads on start."""
        claude_md = (self.memory_dir / "CLAUDE.md").read_text(encoding="utf-8")
        questions = (self.memory_dir / "open_questions.md").read_text(encoding="utf-8")

        log_path = self.memory_dir / "research_log.md"
        log_lines = log_path.read_text(encoding="utf-8").splitlines()
        log_tail = "\n".join(log_lines[-log_tail_lines:])

        return (
            f"{claude_md}\n\n"
            f"# Current Task Frontier (open_questions.md)\n\n{questions}\n\n"
            f"# Recent Log (tail of research_log.md)\n\n{log_tail}\n"
        )

    @staticmethod
    def new_run_id() -> str:
        """Timestamped, with a random suffix.

        Second-resolution timestamps alone collide when two runs start within
        the same second (common during manual back-to-back testing), which
        violates the ledger's run_id primary key.
        """
        stamp = datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S")
        return f"{stamp}-{secrets.token_hex(2)}"
