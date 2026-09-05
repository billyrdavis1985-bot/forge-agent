#!/usr/bin/env python3
"""build_dashboard.py — assemble staged critic verdicts into a review surface.
Reads batch_*.json in scratch/critic_runs/, writes scratch/audit.html.
Surfaces disagreements, shared blind spots, and per-critic failure SHAPE
(false alarms vs misses) WITHOUT scoring — token-vs-label matching is the proxy
this research exists to expose."""
from __future__ import annotations
import html, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "scratch" / "critic_runs"
OUT = ROOT / "scratch" / "audit.html"

def load_batches(runs_dir):
    latest = {}
    for f in sorted(runs_dir.glob("batch_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        latest[(data.get("batch_file"), data.get("model"))] = (f.name, data)
    return [d for _, d in latest.values()]

def assemble(batches):
    models = sorted({b.get("model") for b in batches if b.get("model")})
    items = {}
    for b in batches:
        model = b.get("model"); batch = b.get("batch_file", "")
        for row in b.get("rows", []):
            iid = row.get("id")
            if iid is None: continue
            key = f"{batch}::{iid}::{row.get('variant')}"
            if key not in items:
                items[key] = {"id": iid, "batch": batch, "variant": row.get("variant"),
                    "ground_truth": row.get("ground_truth_label"),
                    "error_type": row.get("error_type"), "verdicts": {}}
            items[key]["verdicts"][model] = {
                "token": (row.get("critic_verdict_token") or "").strip(),
                "full": row.get("critic_full_response") or ""}
    meta = {"n_items": len(items), "n_batches": len({i["batch"] for i in items.values()})}
    return items, models, meta

def flags_for(item, models):
    tokens = [item["verdicts"].get(m, {}).get("token", "") for m in models]
    present = [t for t in tokens if t and t != "(none)"]
    gt = (item["ground_truth"] or "").strip().lower()
    disagree = len(set(present)) > 1
    def aligns(tok):
        if not tok or tok == "(none)": return None
        t = tok.lower()
        if gt == "sound": return t == "sound"
        if gt in ("flawed", "unsound"): return t in ("flawed", "unsound")
        return None
    alignments = {m: aligns(item["verdicts"].get(m, {}).get("token", "")) for m in models}
    both_diverge = len(present) >= 2 and all(
        alignments[m] is False for m in models if alignments[m] is not None)
    def mode(tok):
        if not tok or tok == "(none)": return None
        t = tok.lower()
        if gt == "sound": return "aligns" if t == "sound" else "false_alarm"
        if gt in ("flawed", "unsound"): return "aligns" if t in ("flawed","unsound") else "miss"
        return None
    modes = {m: mode(item["verdicts"].get(m, {}).get("token", "")) for m in models}
    return {"disagree": disagree, "both_diverge": both_diverge,
            "alignments": alignments, "modes": modes}

def failure_shapes(items, models):
    shape = {m: {"false_alarm": 0, "miss": 0, "aligns": 0} for m in models}
    for i in items.values():
        modes = flags_for(i, models)["modes"]
        for m in models:
            md = modes.get(m)
            if md in shape[m]: shape[m][md] += 1
    return shape

def esc(s): return html.escape(str(s if s is not None else ""))

def render(items, models, meta):
    ordered = sorted(items.values(), key=lambda i: (i["batch"], i["id"], i["variant"] or ""))
    n_disagree = sum(1 for i in ordered if flags_for(i, models)["disagree"])
    n_both = sum(1 for i in ordered if flags_for(i, models)["both_diverge"])
    shapes = failure_shapes(items, models)
    shape_cards = []
    for m in models:
        s = shapes[m]
        shape_cards.append(f'<div class="shape"><div class="shape-name">{esc(m)}</div>'
            f'<div class="shape-row"><span class="sm miss">{s["miss"]}</span>'
            f'<span class="sl">misses — said sound on a corrupted item (read first)</span></div>'
            f'<div class="shape-row"><span class="sm fa">{s["false_alarm"]}</span>'
            f'<span class="sl">false alarms — said flawed on a sound item</span></div>'
            f'<div class="shape-row"><span class="sm al">{s["aligns"]}</span>'
            f'<span class="sl">token aligns with truth</span></div></div>')
    shape_panel = "".join(shape_cards)
    rows_html = []
    for i in ordered:
        fl = flags_for(i, models)
        gt = esc(i["ground_truth"]); variant = esc(i["variant"])
        marks = []
        if fl["both_diverge"]:
            marks.append('<span class="mark mark-both" title="Both critics diverge from truth — a shared blind spot">both diverge</span>')
        elif fl["disagree"]:
            marks.append('<span class="mark mark-dis" title="Critics gave different verdicts">critics disagree</span>')
        if any(fl["modes"].get(m) == "miss" for m in models):
            marks.append('<span class="mark mark-miss" title="A critic said sound on a corrupted item — read first">miss</span>')
        if any(fl["modes"].get(m) == "false_alarm" for m in models):
            marks.append('<span class="mark mark-fa" title="A critic said flawed on a sound item">false alarm</span>')
        marks_html = "".join(marks) or '<span class="mark mark-quiet">aligned</span>'
        cells = []
        for m in models:
            v = i["verdicts"].get(m)
            if not v:
                cells.append('<td class="verdict none"><span class="tok">—</span><span class="note">not run</span></td>'); continue
            align = fl["alignments"].get(m)
            state = "aligns" if align is True else ("diverges" if align is False else "na")
            cells.append(f'<td class="verdict {state}"><span class="tok">{esc(v["token"]) or "—"}</span>'
                f'<details><summary>reasoning</summary><pre>{esc(v["full"])}</pre></details></td>')
        err = f'<div class="err">planted: {esc(i["error_type"])}</div>' if i["error_type"] else ""
        rows_html.append(f'<tr class="{"row-both" if fl["both_diverge"] else ""}">'
            f'<td class="idc"><span class="iid">{esc(i["id"])}</span>'
            f'<span class="bvar">{esc(i["batch"]).replace("candidates_","").replace(".jsonl","")} · {variant}</span>{err}</td>'
            f'<td class="gt"><span class="gt-label">{gt}</span><span class="gt-cap">ground truth</span></td>'
            f'{"".join(cells)}<td class="flags">{marks_html}</td></tr>')
    model_heads = "".join(f'<th class="mh">{esc(m)}</th>' for m in models)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Critic audit surface</title>
<style>
:root{{--paper:#f7f6f3;--ink:#1c1e22;--faint:#6b6f76;--line:#dcdad3;--anchor:#2f3640;
--amber:#b07a1e;--rose:#a63f52;--slate:#556070;--both-bg:#fbf1f2;
--mono:"SFMono-Regular",Consolas,Menlo,monospace;--sans:Inter,-apple-system,"Segoe UI",Roboto,sans-serif;}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.5}}
.wrap{{max-width:1180px;margin:0 auto;padding:56px 28px 120px}}
header{{border-bottom:2px solid var(--ink);padding-bottom:24px;margin-bottom:8px}}
h1{{font-size:30px;font-weight:640;letter-spacing:-.015em;margin:0 0 6px}}
.sub{{color:var(--faint);max-width:64ch;margin:0}}
.thesis{{margin:22px 0 34px;padding:16px 18px;border-left:3px solid var(--slate);background:#efeee9;color:#333;font-size:14px;max-width:78ch}}
.thesis b{{color:var(--ink)}}
.counts{{display:flex;gap:34px;margin:0 0 26px;flex-wrap:wrap}}
.count .n{{font-size:34px;font-weight:660;letter-spacing:-.02em;display:block;line-height:1}}
.count .l{{color:var(--faint);font-size:13px;display:block;margin-top:3px;max-width:22ch}}
.count.both .n{{color:var(--rose)}}.count.dis .n{{color:var(--amber)}}
.shapes{{margin:0 0 38px;padding:20px 20px 8px;border:1px solid var(--line);background:#fff;border-radius:2px}}
.shapes-head{{font-size:13px;font-weight:600;color:var(--ink);margin-bottom:16px}}
.shapes-note{{color:var(--faint);font-weight:400}}
.shapes-grid{{display:flex;gap:44px;flex-wrap:wrap}}
.shape{{min-width:230px}}
.shape-name{{font-family:var(--mono);font-weight:600;font-size:14px;color:var(--anchor);margin-bottom:10px}}
.shape-row{{display:flex;align-items:baseline;gap:10px;margin-bottom:7px}}
.sm{{font-size:22px;font-weight:660;font-variant-numeric:tabular-nums;min-width:1.4em;text-align:right}}
.sm.miss{{color:#7a2230}}.sm.fa{{color:#a07a2a}}.sm.al{{color:var(--slate)}}
.sl{{font-size:12.5px;color:var(--faint);line-height:1.35}}
table{{width:100%;border-collapse:collapse;margin-top:6px}}
th{{text-align:left;font-size:12px;font-weight:600;color:var(--faint);padding:0 12px 10px;border-bottom:1px solid var(--line);vertical-align:bottom}}
th.mh{{color:var(--anchor);font-family:var(--mono);font-size:13px}}
td{{padding:14px 12px;border-bottom:1px solid var(--line);vertical-align:top}}
tr.row-both{{background:var(--both-bg)}}
.idc .iid{{font-family:var(--mono);font-weight:600;font-size:14px;display:block}}
.idc .bvar{{color:var(--faint);font-size:12px;display:block;margin-top:2px}}
.idc .err{{color:var(--rose);font-size:11.5px;margin-top:6px;max-width:26ch;line-height:1.35}}
.gt{{white-space:nowrap}}.gt-label{{font-weight:600;display:block}}.gt-cap{{color:var(--faint);font-size:11px}}
.verdict .tok{{font-family:var(--mono);font-weight:600;display:block}}
.verdict.aligns .tok{{color:var(--slate)}}.verdict.diverges .tok{{color:var(--rose)}}
.verdict.na .tok,.verdict.none .tok{{color:var(--faint)}}.verdict .note{{color:var(--faint);font-size:12px}}
details{{margin-top:6px}}summary{{cursor:pointer;color:var(--slate);font-size:12.5px;user-select:none}}
summary:hover{{color:var(--ink)}}
pre{{font-family:var(--mono);font-size:12px;line-height:1.55;white-space:pre-wrap;background:#fff;border:1px solid var(--line);border-radius:2px;padding:12px;margin:8px 0 0;max-width:62ch;color:#2a2c30}}
.flags{{white-space:nowrap}}
.mark{{display:inline-block;font-size:11.5px;font-weight:600;padding:2px 8px;border-radius:2px;margin:0 4px 4px 0}}
.mark-both{{background:var(--rose);color:#fff}}.mark-dis{{background:#f0e2c4;color:var(--amber)}}
.mark-miss{{background:#7a2230;color:#fff}}.mark-fa{{background:#e7d6b8;color:#7a5a12}}
.mark-quiet{{color:var(--faint);font-weight:500}}
.legend{{margin-top:40px;color:var(--faint);font-size:12.5px;max-width:80ch;line-height:1.6}}
.legend b{{color:var(--ink)}}
@media (max-width:760px){{table,thead,tbody,tr,td,th{{display:block}}th{{display:none}}td{{border:none;padding:4px 0}}tr{{border-bottom:1px solid var(--line);padding:14px 0}}.shapes-grid{{gap:24px}}}}
</style></head><body><div class="wrap">
<header><h1>Critic audit surface</h1>
<p class="sub">Fine-tuned reasoning critics, verdicts placed next to ground truth. A review surface for reading — not a scoreboard.</p></header>
<div class="thesis">This page <b>does not score the critics</b>. Verdict-token vs. label matching is a proxy, and matching the label does not mean the diagnosis was genuine. The markers point to <b>where to read</b>: cases the critics diverge on, cases where every critic diverges from truth, and the <b>shape</b> of each critic's failures. Judging whether a verdict reflects real understanding is the reader's work.</div>
<div class="counts">
<div class="count both"><span class="n">{n_both}</span><span class="l">items where every critic diverges from truth — shared blind spots</span></div>
<div class="count dis"><span class="n">{n_disagree}</span><span class="l">items the critics disagree on</span></div>
<div class="count"><span class="n">{meta['n_items']}</span><span class="l">items across {meta['n_batches']} batches</span></div></div>
<div class="shapes"><div class="shapes-head">Failure shape by critic — <span class="shapes-note">what kind of reading each needs, not a score</span></div>
<div class="shapes-grid">{shape_panel}</div></div>
<table><thead><tr><th>item</th><th>truth</th>{model_heads}<th>read</th></tr></thead><tbody>
{''.join(rows_html)}</tbody></table>
<p class="legend"><b>miss</b> (dark red) means a critic said sound on a corrupted item — the highest-stakes failure for a verification gate, so read these first. <b>false alarm</b> means it said flawed on a sound item. <b>aligns</b> means the token matches the label — a neutral fact, not a checkmark, because a matching token can still sit on a spurious diagnosis. <b>both diverge</b> highlights rows where every critic missed the same way. Open <b>reasoning</b> to read the full verdict — that reading, not the token, is where genuine vs. spurious is decided.</p>
</div></body></html>"""

def main():
    if not RUNS_DIR.exists():
        print(f"No staged runs at {RUNS_DIR}", file=sys.stderr); return 1
    batches = load_batches(RUNS_DIR)
    if not batches:
        print(f"No batch_*.json in {RUNS_DIR}", file=sys.stderr); return 1
    items, models, meta = assemble(batches)
    OUT.write_text(render(items, models, meta), encoding="utf-8")
    print(f"Wrote {OUT}  ({meta['n_items']} items, {len(models)} critics: {', '.join(models)})")
    if "--open" in sys.argv: print(f"Open: file://{OUT}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
