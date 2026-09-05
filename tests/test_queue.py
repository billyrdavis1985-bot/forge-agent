"""Queue drain logic tests — the bookkeeping unattended drain depends on."""
import json
from pathlib import Path
import pytest
from src import queue as q


@pytest.fixture
def qdir(tmp_path):
    (tmp_path / "queue.jsonl").write_text("\n".join(json.dumps(t) for t in [
        {"id": "b2", "instruction": "run b2", "status": "pending"},
        {"id": "b3", "instruction": "run b3", "status": "pending"},
        {"id": "b4", "instruction": "run b4", "status": "pending"},
    ]) + "\n")
    return tmp_path


def test_next_returns_first_pending(qdir):
    assert q.next_pending(qdir)["id"] == "b2"


def test_mark_skips_done_and_running(qdir):
    q.mark(qdir, "b2", "done")
    q.mark(qdir, "b3", "running")
    assert q.next_pending(qdir)["id"] == "b4"


def test_empty_when_all_done(qdir):
    for t in ("b2", "b3", "b4"):
        q.mark(qdir, t, "done")
    assert q.next_pending(qdir) is None


def test_reaper_resets_orphans_not_done(qdir):
    q.mark(qdir, "b2", "done")
    q.mark(qdir, "b3", "running")
    n = q.reap_orphans(qdir)
    assert n == 1
    assert q.next_pending(qdir)["id"] == "b3"
    assert q.summary(qdir)["done"] == 1


def test_summary_counts(qdir):
    q.mark(qdir, "b2", "done")
    s = q.summary(qdir)
    assert s["total"] == 3 and s["done"] == 1 and s["pending"] == 2
