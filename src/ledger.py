"""
ledger.py — the operational record.

SQLite is the source of truth for RUN HISTORY and SPEND. It is deliberately
NOT the source of truth for tasks: `memory/open_questions.md` owns the task
frontier, because the agent itself reads and rewrites it. Two stores tracking
the same tasks would drift the first time the agent edited the markdown.

Responsibilities:
  - record every run attempt and its outcome (even crashes)
  - track cost per run and cumulative spend per UTC day
  - enforce a daily budget ceiling that spans runs, which the SDK's
    per-session max_budget_usd cannot do on its own
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    status       TEXT NOT NULL,      -- running | ok | error | aborted
    instruction  TEXT,
    cost_usd     REAL DEFAULT 0.0,
    num_turns    INTEGER,
    commit_sha   TEXT,
    error        TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Ledger:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # ---- run lifecycle -------------------------------------------------
    def start_run(self, run_id: str, instruction: str | None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO runs (run_id, started_at, status, instruction) "
                "VALUES (?, ?, 'running', ?)",
                (run_id, _utcnow(), instruction),
            )

    def finish_run(
        self,
        run_id: str,
        status: str,
        cost_usd: float = 0.0,
        num_turns: int | None = None,
        commit_sha: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE runs SET ended_at=?, status=?, cost_usd=?, num_turns=?, "
                "commit_sha=?, error=? WHERE run_id=?",
                (_utcnow(), status, cost_usd, num_turns, commit_sha, error, run_id),
            )

    def reap_stale_runs(self) -> int:
        """Mark orphaned 'running' rows as aborted (process was killed mid-run).

        Safe because flock guarantees only one session runs at a time: any row
        still marked running at startup is by definition dead.
        """
        with self._conn() as c:
            cur = c.execute(
                "UPDATE runs SET status='aborted', ended_at=?, "
                "error='orphaned: process died before finishing' "
                "WHERE status='running'",
                (_utcnow(),),
            )
            return cur.rowcount

    # ---- budget --------------------------------------------------------
    def spend_today(self) -> float:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._conn() as c:
            row = c.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM runs "
                "WHERE started_at LIKE ?",
                (f"{today}%",),
            ).fetchone()
        return float(row["total"])

    def budget_check(self, daily_cap_usd: float) -> tuple[bool, float]:
        """Return (allowed, spend_so_far). Blocks the run if the day's cap is hit."""
        spent = self.spend_today()
        return (spent < daily_cap_usd, spent)

    # ---- reporting -----------------------------------------------------
    def recent(self, limit: int = 10) -> list[sqlite3.Row]:
        with self._conn() as c:
            return c.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
