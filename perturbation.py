#!/usr/bin/env python3
"""perturbation.py — paired perturbation analysis (council #4).
Classifies whether each critic DISTINGUISHES clean vs corrupted versions of the
same problem. Reads LOCKED (deterministic) staged runs; writes scratch/perturbation.html.
Classifies observable verdicts, does NOT judge underlying reasoning."""
from __future__ import annotations
import html, json, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "scratch" / "critic_runs"
OUT = ROOT / "scratch" / "perturbation.html"

def load_locked(runs_dir):
    latest = {}
    for f in sorted(runs_dir.glob("batch_*.json")):
        try: d = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError: continue
        if d.get("options", {}).get("top_k") != 1: continue
        latest[(d.get("batch_file"), d.get("model"))] = d
    return list(latest.values())

def is_clean(v): return (v or "").startswith("clean")
def is_corrupt(v): return (v or "").startswith("corrupt")
def token_flawed(t): return (t or "").lower() in ("flawed", "unsound")
def token_sound(t): return (t or "").lower() == "sound"

def assemble(batches):
    problems = defaultdict(lambda: defaultdict(list))
    for d in batches:
        model = d.get("model")
        for r in d.get("rows", []):
            problems[r["id"]][model].append(
                (r.get("variant"), r.get("ground_truth_label"),
                 r.get("critic_verdict_token"), r.get("critic_full_response", "")))
    return problems

def classify(entries):
    cleans = [(v, t) for v, g, t, _ in entries if is_clean(v)]
    corrs = [(v, t) for v, g, t, _ in entries if is_corrupt(v)]
    if not cleans or not corrs: return "no_pair"
    clean_tokens = {token_sound(t) for _, t in cleans}
    corr_tokens = {token_flawed(t) for _, t in corrs}
    if len(clean_tokens) > 1 or len(corr_tokens) > 1: return "inconsistent"
    said_sound_on_clean = clean_tokens == {True}
    said_flawed_on_corr = corr_tokens == {True}
    if said_sound_on_clean and said_flawed_on_corr: return "discriminates"
    if not said_flawed_on_corr: return "blind"
    if not said_sound_on_clean: return "over_flags"
    return "inconsistent"

LABELS = {
    "discriminates": ("discriminates", "#2f6b4f", "accepts clean, rejects corrupted — reasons"),
    "blind": ("blind", "#7a2230", "said sound on a corrupted variant — missed the defect"),
    "over_flags": ("over-flags", "#a07a2a", "said flawed on a clean variant — can't distinguish"),
    "inconsistent": ("inconsistent", "#8a3d6b", "verdict varies within a label group — presentation-sensitive"),
    "no_pair": ("no pair", "#888", "only one side present — discrimination untestable"),
}

def esc(s): return html.escape(str(s if s is not None else ""))

def render(problems, models):
    tally = {m: defaultdict(int) for m in models}
    rows = []
    for pid in sorted(problems):
        cells = []
        for m in models:
            entries = problems[pid].get(m)
            if not entries:
                cells.append('<td class="cell na">—</td>'); continue
            cls = classify(entries); tally[m][cls] += 1
            label, color, _ = LABELS[cls]
            detail = " ".join(f"{esc(v).replace('clean-','c:').replace('corrupted-','x:').replace('clean','clean').replace('corrupted','corr')}={esc(t)}"
                              for v, g, t, _ in entries)
            cells.append(f'<td class="cell {cls}" style="--c:{color}"><span class="cls">{label}</span><span class="dtl">{detail}</span></td>')
        allvars = sorted({v for m in problems[pid] for v, *_ in problems[pid][m]})
        vsum = ", ".join(esc(v) for v in allvars)
        rows.append(f'<tr><td class="pid">{esc(pid)}<span class="vs">{vsum}</span></td>{"".join(cells)}</tr>')
    tally_cards = []
    for m in models:
        rowsm = "".join(f'<div class="tr"><span class="tn" style="--c:{LABELS[k][1]}">{tally[m].get(k,0)}</span><span class="tl">{LABELS[k][0]} — {LABELS[k][2]}</span></div>'
            for k in ("discriminates","blind","over_flags","inconsistent","no_pair"))
        tally_cards.append(f'<div class="tcard"><div class="tname">{esc(m)}</div>{rowsm}</div>')
    model_heads = "".join(f'<th>{esc(m)}</th>' for m in models)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Perturbation response</title>
<style>
:root{{--paper:#f7f6f3;--ink:#1c1e22;--faint:#6b6f76;--line:#dcdad3;--anchor:#2f3640;
--mono:"SFMono-Regular",Consolas,Menlo,monospace;--sans:Inter,-apple-system,"Segoe UI",Roboto,sans-serif;}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.5}}
.wrap{{max-width:1120px;margin:0 auto;padding:56px 28px 120px}}
header{{border-bottom:2px solid var(--ink);padding-bottom:24px;margin-bottom:26px}}
h1{{font-size:29px;font-weight:640;letter-spacing:-.015em;margin:0 0 6px}}
.sub{{color:var(--faint);max-width:70ch;margin:0}}
.thesis{{margin:20px 0 30px;padding:15px 17px;border-left:3px solid var(--anchor);background:#efeee9;color:#333;font-size:14px;max-width:80ch}}
.thesis b{{color:var(--ink)}}
.tally{{display:flex;gap:40px;flex-wrap:wrap;margin-bottom:34px}}
.tcard{{min-width:320px}}
.tname{{font-family:var(--mono);font-weight:600;font-size:14px;color:var(--anchor);margin-bottom:10px}}
.tr{{display:flex;align-items:baseline;gap:10px;margin-bottom:6px}}
.tn{{font-size:20px;font-weight:660;font-variant-numeric:tabular-nums;min-width:1.4em;text-align:right;color:var(--c)}}
.tl{{font-size:12.5px;color:var(--faint)}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;font-size:12px;font-weight:600;color:var(--faint);padding:0 10px 10px;border-bottom:1px solid var(--line)}}
th:first-child{{width:230px}}
td{{padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
.pid{{font-family:var(--mono);font-weight:600;font-size:13px}}
.pid .vs{{display:block;font-family:var(--sans);font-weight:400;color:var(--faint);font-size:11px;margin-top:3px;max-width:210px}}
.cell{{border-left:3px solid var(--c,#ccc);padding-left:10px}}
.cell.na{{border:none;color:var(--faint)}}
.cell .cls{{display:block;font-weight:600;font-size:13px;color:var(--c)}}
.cell .dtl{{display:block;font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:3px}}
.legend{{margin-top:34px;color:var(--faint);font-size:12.5px;max-width:82ch;line-height:1.6}}
.legend b{{color:var(--ink)}}
</style></head><body><div class="wrap">
<header><h1>Perturbation response</h1>
<p class="sub">Does each critic <b>distinguish</b> the clean and corrupted versions of the same problem? The pair — not the item — is the unit that measures reasoning sensitivity.</p></header>
<div class="thesis">A critic that says the right thing on isolated items may still be unable to tell a sound proof from its corrupted twin. This view classifies each critic's behavior across a problem's variants. It classifies observable verdicts — it does <b>not</b> judge whether the underlying reasoning was genuine; open the audit surface and read for that.</div>
<div class="tally">{''.join(tally_cards)}</div>
<table><thead><tr><th>problem · variants</th>{model_heads}</tr></thead><tbody>
{''.join(rows)}</tbody></table>
<p class="legend"><b>discriminates</b> — sound on clean, flawed on corrupted: the critic tracks the actual defect. <b>blind</b> — said sound on a corrupted variant: missed the planted error. <b>over-flags</b> — said flawed on a clean variant: cannot separate clean from corrupted. <b>inconsistent</b> — verdict changed across variants that share a truth label: reacting to surface form, not substance. <b>no pair</b> — the grid has only one side of this problem, so discrimination cannot be tested; shown rather than hidden.</p>
</div></body></html>"""

def main():
    if not RUNS.exists():
        print(f"No staged runs at {RUNS}", file=sys.stderr); return 1
    batches = load_locked(RUNS)
    if not batches:
        print("No LOCKED runs found. Re-run the grid under the determinism lock first.", file=sys.stderr); return 1
    problems = assemble(batches)
    models = sorted({b.get("model") for b in batches if b.get("model")})
    OUT.write_text(render(problems, models), encoding="utf-8")
    print(f"Wrote {OUT}  ({len(problems)} problems, {len(models)} critics)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
