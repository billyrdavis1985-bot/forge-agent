"""provenance.py — the evidence chain (council recommendation #1).
Captures raw critic output + full experimental identity INSIDE the tool, below
the agent, the instant Ollama responds — so displayed evidence is traceable to
raw output and independently verifiable."""
from __future__ import annotations
import hashlib, json, platform, subprocess, urllib.request
from datetime import datetime, timezone
from pathlib import Path

PARSER_VERSION = "1"

def sha256_text(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _git_head(repo):
    try:
        r = subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or None
    except Exception:
        return None

def _ollama_version():
    try:
        with urllib.request.urlopen("http://localhost:11434/api/version", timeout=5) as r:
            return json.loads(r.read().decode("utf-8")).get("version")
    except Exception:
        return None

def _model_digest(model):
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            tags = json.loads(r.read().decode("utf-8")).get("models", [])
        for m in tags:
            if m.get("name")==model or m.get("model")==model or m.get("name","").split(":")[0]==model:
                return m.get("digest")
    except Exception:
        pass
    return None

def _environment():
    return {"ollama_version": _ollama_version(), "python": platform.python_version(),
            "platform": platform.platform(), "hostname": platform.node()}

class Provenance:
    def __init__(self, memory_dir, critic_repo, run_id, batch_file, model, seed, temperature):
        self.dir = memory_dir / "provenance"; self.dir.mkdir(parents=True, exist_ok=True)
        self.run_id=run_id; self.batch_file=batch_file; self.model=model
        self.seed=seed; self.temperature=temperature
        self.model_digest=_model_digest(model); self.env=_environment()
        self.code_sha=_git_head(memory_dir.parent)
        self.data_sha=_git_head(critic_repo) if critic_repo else None
        self.inv_path=self.dir/f"{run_id}_invocations.jsonl"; self.records=[]
    def record(self, *, item_id, variant, prompt, raw_response, parsed_verdict,
               attempt=1, eval_count=None, total_duration_ns=None):
        rec={"run_id":self.run_id,"batch_file":self.batch_file,"item_id":item_id,
             "variant":variant,"attempt":attempt,
             "timestamp":datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "model":self.model,"model_digest":self.model_digest,"seed":self.seed,
             "temperature":self.temperature,"prompt_sha256":sha256_text(prompt),
             "parser_version":PARSER_VERSION,"raw_response":raw_response,
             "raw_response_sha256":sha256_text(raw_response),"parsed_verdict":parsed_verdict,
             "code_git_sha":self.code_sha,"data_git_sha":self.data_sha,"environment":self.env,
             "eval_count":eval_count,"total_duration_ns":total_duration_ns}
        with self.inv_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False)+"\n")
        self.records.append(rec); return rec
    def write_manifest(self, staged_file):
        manifest={"run_id":self.run_id,"batch_file":self.batch_file,"model":self.model,
                  "model_digest":self.model_digest,"seed":self.seed,"temperature":self.temperature,
                  "code_git_sha":self.code_sha,"data_git_sha":self.data_sha,"environment":self.env,
                  "n_invocations":len(self.records),
                  "invocation_hashes":[r["raw_response_sha256"] for r in self.records],
                  "staged_file":staged_file,
                  "created":datetime.now(timezone.utc).isoformat(timespec="seconds")}
        mpath=self.dir/f"{self.run_id}_manifest.json"
        mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8"); return mpath

def verify_run(memory_dir, run_id):
    pdir=memory_dir/"provenance"
    inv=pdir/f"{run_id}_invocations.jsonl"; man=pdir/f"{run_id}_manifest.json"
    if not inv.exists() or not man.exists():
        return {"run_id":run_id,"verified":False,"reason":"records missing"}
    manifest=json.loads(man.read_text(encoding="utf-8"))
    recorded=manifest.get("invocation_hashes",[]); rehashed=[]; mismatches=[]
    for line in inv.read_text(encoding="utf-8").splitlines():
        line=line.strip()
        if not line: continue
        rec=json.loads(line); actual=sha256_text(rec["raw_response"]); rehashed.append(actual)
        if actual!=rec["raw_response_sha256"]: mismatches.append(rec.get("item_id"))
    manifest_ok=rehashed==recorded; verified=manifest_ok and not mismatches
    return {"run_id":run_id,"verified":verified,"n_invocations":len(rehashed),
            "rehash_mismatches":mismatches,"manifest_matches":manifest_ok,
            "reason":"ok" if verified else ("raw response tampered" if mismatches else "manifest/record set differs")}
