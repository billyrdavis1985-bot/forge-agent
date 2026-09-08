"""Blinded adjudication tests: collect, dedup, blind flow, persistence."""
import json, io, contextlib
from pathlib import Path
import pytest
from src import adjudicate as adj


def _stage(runs, run_id="critrun-T"):
    staged = {"batch_file":"b5.jsonl","model":"critic-mistral","run_id":run_id,"rows":[
        {"id":"MPQ-07","variant":"corrupted","ground_truth_label":"flawed",
         "error_type":"x","critic_verdict_token":"sound","critic_full_response":"VERDICT: sound"},
        {"id":"LSQ-12","variant":"clean","ground_truth_label":"sound",
         "error_type":None,"critic_verdict_token":"sound","critic_full_response":"VERDICT: sound ok"},
    ]}
    (runs/"batch_b5_critic-mistral_1.json").write_text(json.dumps(staged))


def test_collect_and_dedup(tmp_path):
    runs = tmp_path/"runs"; runs.mkdir(); mem = tmp_path/"mem"; mem.mkdir()
    _stage(runs)
    pending = adj.collect_pending(runs, adj.load_adjudicated(mem))
    assert len(pending) == 2
    d = adj._adj_dir(mem)
    (d/"critrun-T.jsonl").write_text(json.dumps({"key": pending[0]["key"]})+"\n")
    pending2 = adj.collect_pending(runs, adj.load_adjudicated(mem))
    assert len(pending2) == 1


def test_blind_flow_reveal_after_judgment(tmp_path, monkeypatch):
    runs = tmp_path/"runs"; runs.mkdir(); mem = tmp_path/"mem"; mem.mkdir()
    _stage(runs)
    monkeypatch.setattr("sys.stdin", io.StringIO("n\nna\nn\nn\nquit\n"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        adj.adjudicate(mem, runs)
    out = buf.getvalue()
    assert out.find("CANDIDATE REASONING") < out.find("reveal")
    saved = list((mem/"adjudications").glob("*.jsonl"))
    assert saved
    rec = json.loads(saved[0].read_text().splitlines()[0])
    assert rec["judgment"]["detected"] == "n" and "diagnosis_sha256" in rec
    assert rec["rubric_version"] == "2"
