"""Render the admin dashboard and failure explorer with REAL data (verified ratings, generation log, audit).
Writes q1/mockups/admin_real.html and q1/mockups/explorer_real.html."""
import json, pathlib, re
import pandas as pd

HERE = pathlib.Path(__file__).parent
Q1 = HERE.parent
key = json.loads((Q1 / "rating_app" / "key.json").read_text())
R = json.loads((Q1 / "out" / "results.json").read_text(encoding="utf-8"))
d = pd.concat([pd.read_csv(f, encoding="utf-8-sig") for f in sorted((Q1 / "ratings").glob("*.csv"))], ignore_index=True)
d["model"] = d.image_id.map(lambda i: key[i]["model"])
m = d[~d.is_repeat.astype(str).str.lower().eq("true")]
log = [json.loads(l) for l in (Q1 / "generation_log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
audit = pd.read_csv(Q1 / "researcher_audit.csv", encoding="utf-8-sig")
css = re.search(r"<style>(.*?)</style>", (HERE / "product.html").read_text(encoding="utf-8"), re.S).group(1)
NAME = {"gpt1": "GPT Image 1", "g25": "Gemini 2.5 Flash Image", "g31": "Gemini 3.1 Flash Image Preview"}

# ---------------- admin numbers
raters = sorted(m.participant_id.unique())
n = len(raters)
med_min = R["participants"]["median_minutes"]
alpha = R["alpha"]["text_ordinal"]
tr = R["test_retest"]["text_exact_agree"]
pos = R["position_bias"]
pos_dev = max(abs(v - 1 / 3) for v in pos.values())
piv = m.pivot_table(index="image_id", columns="participant_id", values="text_accuracy", aggfunc="first")
same = piv.nunique(axis=1).eq(1)
agree_by_prompt = m.assign(s=m.image_id.map(same)).groupby("prompt_id").s.mean().sort_values()
low = agree_by_prompt[agree_by_prompt == agree_by_prompt.min()]
ok_imgs = len({(l["prompt_id"], l["model_id"]) for l in log if l["status"] == "ok"})
empty = [l for l in log if l["status"] == "error" and str(l.get("error", "")).strip() == "'content'"]
quota = [l for l in log if l["status"] == "error" and "429" in str(l.get("error", ""))]
refusals = [l for l in log if l["status"] == "error" and "refus" in str(l.get("error", "")).lower()]

roster = ""
for pid in raters:
    s = d[d.participant_id == pid]
    calib = s.practice_answer.iloc[0] == "Small error"
    med = s.drop_duplicates("screen_index").seconds_on_screen.median()
    others = [c for c in piv.columns if c != pid]
    agr = (piv[pid] == piv[others[0]]).mean() if others else float("nan")
    speeder = med < 15
    roster += (f"<tr><td>{pid}</td><td>{s.hindi_level.iloc[0].split(' /')[0].replace(' reader', '')}</td>"
               f"<td>{'✓' if calib else '<span style=\"color:var(--warn)\">✗</span>'}</td>"
               f"<td{' style=\"color:var(--warn)\"' if speeder else ''}>{med:.0f}</td><td>{agr * 100:.0f}% same text label</td></tr>")


def alert(kind, title, body):
    sty = {"warn": ('border-color:#f3c7a6;background:#fff8f2', 'var(--warn)', '⚠ WARNING'),
           "crit": ('border-color:#f1b5b0;background:#fff5f4', 'var(--crit)', '■ INTEGRITY'),
           "info": ('', 'var(--series-1)', 'ⓘ INFO')}[kind]
    return f'<div class="alert" style="{sty[0]}"><div class="ic" style="color:{sty[1]}">{sty[2]}</div><div><b>{title}</b> {body}</div></div>'


alerts = alert("warn", f"Below target sample:", f"{n} of 8 to 10 raters. Every leaderboard entry stays provisional.")
if pos_dev > 0.08:
    lo_pos = min(pos, key=pos.get)
    alerts += alert("warn", "Position bias:", f"position {lo_pos} picked {pos[lo_pos] * 100:.0f}% of the time (expected ~33%, rule ±8 pp). Only {int(len(m) / 3)} picks so far, so likely noise; positions stay shuffled.")
alerts += alert("crit", "2 rating files rejected:", "their screen order did not match the app's randomisation for that email, so they were not produced by the rating app. Held out of all results.")
alerts += alert("info", f"Lowest rater agreement: {', '.join(low.index)}.", f"Raters gave the same text label on {low.iloc[0] * 100:.0f}% of these posters. Candidates for clearer guidelines or a zoom prompt.")
alerts += alert("info", f"Generation: {ok_imgs}/48 images, {len(refusals)} refusals.",
                f"{len(empty)} empty Gemini response retried; {len(quota)} quota errors from an unbilled key before switching keys. All logged. Model version strings stored as the baseline for regression alerts.")

admin = f"""<section class="view on" id="admin">
 <div class="top"><div class="logo">Bharat <span>Poster</span> Arena · <span style="color:var(--text-secondary);font-weight:600">Admin</span></div>
  <div class="tabs"><div class="a">Run health</div><div>Raters</div><div>Prompts</div><div>Models</div></div><div class="stamp real">REAL DATA · RUN 2026-10 · V1</div></div>
 <div class="grid3">
  <div class="card kpi"><div class="l">Completed raters</div><div class="v">{n} / 8-10</div><div class="d" style="color:var(--warn)">⚠ below target · median {med_min:.0f} min</div></div>
  <div class="card kpi"><div class="l">Rater agreement (text, Krippendorff α)</div><div class="v">{alpha:.2f}</div><div class="d" style="color:{'var(--good)' if alpha >= 0.6 else 'var(--warn)'}">{'✓ above' if alpha >= 0.6 else '⚠ below'} 0.60 target</div></div>
  <div class="card kpi"><div class="l">Test–retest (repeat screen)</div><div class="v">{tr * 100:.0f}%</div><div class="d" style="color:var(--text-secondary)">same text label on re-shown posters</div></div>
  <div class="card kpi"><div class="l">Position bias (pick share A/B/C)</div><div class="v">{'/'.join(f"{pos.get(k, 0) * 100:.0f}" for k in 'ABC')}</div><div class="d" style="color:{'var(--warn)' if pos_dev > 0.08 else 'var(--good)'}">{'⚠ outside' if pos_dev > 0.08 else '✓ within'} ±8 pp of 33%</div></div>
 </div>
 <div class="two">
  <div class="card"><h2>Alerts</h2><div class="sub">Rules evaluated on this run</div>{alerts}</div>
  <div class="card"><h2>Rater roster</h2><div class="sub">Calibration = practice item answered correctly ("Small error"). IDs only, no names.</div>
   <table><tr><th>Rater</th><th>Hindi</th><th>Calib.</th><th>Med s/screen</th><th>Agreement w/ other rater</th></tr>{roster}</table>
   <div class="note">Speeder rule: median under 15 s per screen. No rater flagged.</div></div>
 </div>
</section>"""

# ---------------- explorer: the same poster across all three models + one rater/audit disagreement
def labels(pid, mod):
    s = m[(m.prompt_id == pid) & (m.model == mod)]
    t = s.text_accuracy.value_counts()
    return ", ".join(f"{v}× {k.lower()}" for k, v in t.items())


def note(pid, mod):
    a = audit[(audit.prompt_id == pid) & (audit.model == mod)]
    return a.text_label.iloc[0] if len(a) else ""


cards = ""
for pid, mod, cap in [("P12", "g31", "All text correct, incl. मुफ़्त and जाँच"),
                      ("P12", "gpt1", "Nukta and chandrabindu missing (मुफ्त, जांच)"),
                      ("P12", "g25", "Every word wrong, incl. the day: 'हर रनिवार मुफ्टि शुमार जॉच्छ'"),
                      ("S15", "g25", "'श्री क्रूश्न जममताती की हादिक शुभफापाएँ'")]:
    cards += (f'<div><img src="../images/{pid}_{mod}.png"><div class="cap"><b style="color:var(--text-primary)">{pid} · {NAME[mod]}</b><br>'
              f'My audit: <b style="color:{"var(--good)" if note(pid, mod) == "Exactly correct" else "var(--crit)"}">{note(pid, mod).lower()}</b>. {cap}<br>Raters: {labels(pid, mod)}</div></div>')

explorer = f"""<section class="view on" id="explore">
 <div class="top"><div class="logo">Bharat <span>Poster</span> Arena</div>
  <div class="tabs"><div>Leaderboard</div><div class="a">Explore failures</div><div>Compare versions</div></div>
  <div class="stamp real">REAL OUTPUTS · AUDIT + {n} RATERS</div></div>
 <div class="filters"><div>Failure type: <b>Text in Hindi</b> ▾</div><div>Model: <b>All 3</b> ▾</div><div>Sort: <b>Rater vs audit disagreement</b> ▾</div></div>
 <div class="card"><h2>Same chemist's notice, three models, and where lay raters miss errors</h2><div class="sub">First three: P12 "हर रविवार मुफ़्त शुगर जाँच" from each model. Last: a broken greeting both raters called a "small error", which shows why text checks need zoom, OCR or expert raters.</div>
  <div class="thumbs">{cards}</div>
  <div class="note">Each card opens: the prompt, all three outputs, every rater's label and comment, and the generation log (request ID, timestamp, settings).</div>
 </div>
</section>"""

head = f'<!doctype html><html><head><meta charset="utf-8"><style>{css}\n.stamp.real{{color:#1a7f37;border-color:#1a7f37}}.thumbs .cap{{font-size:12px;line-height:1.4}}</style></head><body class="viz-root">'
(HERE / "admin_real.html").write_text(head + admin + "</body></html>", encoding="utf-8")
(HERE / "explorer_real.html").write_text(head + explorer + "</body></html>", encoding="utf-8")
print("built", n, "raters | alpha", round(alpha, 2), "| pos", pos, "| low agreement", list(low.index))
