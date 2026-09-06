"""Evidence-chain tests: capture, verify, and tamper-detection."""
import json, subprocess
from pathlib import Path
from unittest.mock import patch
import pytest


def _git_init(p):
    subprocess.run(["git","init","-q",str(p)])
    subprocess.run(["git","-C",str(p),"-c","user.email=t@t","-c","user.name=t",
                    "commit","-q","--allow-empty","-m","i"])


@pytest.fixture
def env(tmp_path, monkeypatch):
    repo = tmp_path/"hf-critic"; (repo/"eval").mkdir(parents=True)
    (repo/"eval"/"b.jsonl").write_text(
        '{"id":"X1","variant":"clean","label":"sound","error_type":null,"prompt":"Q1","candidate":"C1"}\n')
    _git_init(repo)
    mem = tmp_path/"proj"/"memory"; mem.mkdir(parents=True); _git_init(mem.parent)
    monkeypatch.setenv("CRITIC_REPO", str(repo))
    return mem


@pytest.mark.asyncio
async def test_capture_verify_tamper(env):
    import src.agent_tools as at, src.provenance as pv
    def fake(model, prompt): return "VERDICT: sound\nok", {"eval_count":5,"total_duration":10}
    with patch.object(at,"_call_ollama",fake), \
         patch.object(pv,"_model_digest",lambda m:"sha256:beef"), \
         patch.object(pv,"_ollama_version",lambda:"x"):
        at.build_tools_server(env)
        await at.run_critic_batch({"model":"critic-mistral","batch_file":"b.jsonl"})
    man = list((env/"provenance").glob("*_manifest.json"))
    assert len(man) == 1
    rid = man[0].name.replace("_manifest.json","")
    from src.provenance import verify_run
    assert verify_run(env, rid)["verified"] is True
    inv = env/"provenance"/f"{rid}_invocations.jsonl"
    rec = json.loads(inv.read_text().splitlines()[0]); rec["raw_response"]="X"
    inv.write_text(json.dumps(rec)+"\n")
    r = verify_run(env, rid)
    assert r["verified"] is False and "X1" in r["rehash_mismatches"]
