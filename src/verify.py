"""verify.py — CLI to independently verify a run's evidence chain.
Usage: python -m src.verify <memory_dir> [run_id]   (no run_id = verify all)"""
import sys
from pathlib import Path
from src.provenance import verify_run

def main():
    if len(sys.argv) < 2:
        print("usage: python -m src.verify <memory_dir> [run_id]"); return 2
    mem = Path(sys.argv[1])
    pdir = mem / "provenance"
    if len(sys.argv) >= 3:
        run_ids = [sys.argv[2]]
    else:
        run_ids = sorted({p.name.replace("_manifest.json","")
                          for p in pdir.glob("*_manifest.json")}) if pdir.exists() else []
    if not run_ids:
        print("no runs to verify"); return 0
    allok = True
    for rid in run_ids:
        r = verify_run(mem, rid)
        status = "VERIFIED" if r["verified"] else "FAILED"
        if not r["verified"]: allok = False
        print(f"[{status}] {rid}: {r.get('n_invocations','?')} invocations, {r['reason']}")
        if r.get("rehash_mismatches"):
            print(f"    tampered items: {r['rehash_mismatches']}")
    return 0 if allok else 1

if __name__ == "__main__":
    sys.exit(main())
