"""Render the leaderboard screen with REAL participant data (q1/ratings) instead of placeholders.

Every number is computed from the verified rating files: Hindi ship-ready rate with a two-level bootstrap
interval (prompts x raters), English-twin rate, Hindi tax, Hindi text-exact, looks-Indian, rating counts,
ship-ready by difficulty level, and rejection reasons. Writes q1/mockups/leaderboard_real.html.
"""
import json, pathlib, re
import numpy as np, pandas as pd

HERE = pathlib.Path(__file__).parent
Q1 = HERE.parent
spec = json.loads((Q1 / "prompts.json").read_text(encoding="utf-8"))
P = {p["id"]: p for p in spec["prompts"]}
key = json.loads((Q1 / "rating_app" / "key.json").read_text())
d = pd.concat([pd.read_csv(f, encoding="utf-8-sig") for f in sorted((Q1 / "ratings").glob("*.csv"))], ignore_index=True)
d = d[~d.is_repeat.astype(str).str.lower().eq("true")].copy()
d["model"] = d.image_id.map(lambda i: key[i]["model"])
d["lang"] = d.prompt_id.map(lambda x: P[x]["lang"])
d["level"] = d.prompt_id.map(lambda x: P[x]["level"].split()[0])
d["asis"] = d.would_post.eq("Post as-is").astype(float)
d["exact"] = d.text_accuracy.eq("Exactly correct").astype(float)
d["cult"] = d.looks_right.eq("Looks right").astype(float)
n_raters = d.participant_id.nunique()
NAME = {"gpt1": ("GPT Image 1", "OpenAI · gpt-image-1 · quality=high", "var(--series-1)"),
        "g25": ("Gemini 2.5 Flash Image", "Google · gemini-2.5-flash-image", "var(--series-2)"),
        "g31": ("Gemini 3.1 Flash Image Preview", "Google · gemini-3.1-flash-image-preview", "var(--series-3)")}
rng = np.random.default_rng(7)


def boot(sub):
    prompts, raters = sub.prompt_id.unique(), sub.participant_id.unique()
    cell = sub.groupby(["prompt_id", "participant_id"]).asis.mean()
    vals = []
    for _ in range(2000):
        ps, rs = rng.choice(prompts, len(prompts)), rng.choice(raters, len(raters))
        vals.append(np.nanmean([cell.get((p, r), np.nan) for p in ps for r in rs]))
    return np.percentile(vals, 2.5), np.percentile(vals, 97.5)


hi, en = d[d.lang != "EN"], d[d.lang == "EN"]
pairs = {p["pair"]: [] for p in spec["prompts"] if p["pair"]}
rows = []
for m in NAME:
    h, e = hi[hi.model == m], en[en.model == m]
    lo, up = boot(h)
    hi_twin = h[h.prompt_id.map(lambda x: P[x]["pair"] != "")].asis.mean()
    rows.append(dict(m=m, hi=h.asis.mean(), lo=lo, up=up, en=e.asis.mean(), tax=(e.asis.mean() - hi_twin) * 100,
                     exact=h.exact.mean(), cult=h.cult.mean(), n=len(d[d.model == m])))
rows.sort(key=lambda r: -r["hi"])
# rank bands: best possible rank = 1 + models clearly better; worst = 1 + models not clearly worse
for r in rows:
    others = [o for o in rows if o is not r]
    lo_rank = 1 + sum(o["lo"] > r["up"] for o in others)
    hi_rank = 1 + sum(o["up"] >= r["lo"] for o in others)
    r["band"] = f"{lo_rank}" if lo_rank == hi_rank else f"{lo_rank}–{hi_rank}"


def pct(x):
    return f"{x * 100:.0f}%"


def blue(v):  # sequential single-hue ramp, light -> dark
    steps = ["#f3f8fe", "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6"]
    c = steps[min(8, int(v * 8.999))]
    return f'style="background:{c};{"color:#fff;" if v > 0.62 else ""}"'


lb = ""
for r in rows:
    nm, sub, col = NAME[r["m"]]
    ci = f'<i style="left:{r["lo"] * 100:.0f}%;width:{max(1, (r["up"] - r["lo"]) * 100):.0f}%"></i><b style="left:{r["hi"] * 100:.0f}%;background:{col}"></b>'
    lb += (f'<tr><td class="rank">{r["band"]}</td><td><span class="sw" style="background:{col}"></span>{nm}<br><span class="note">{sub}</span></td>'
           f'<td><b>{pct(r["hi"])}</b></td><td><div class="ci">{ci}</div><span class="note">{pct(r["lo"])} to {pct(r["up"])}</span></td>'
           f'<td>{pct(r["en"])}</td><td>{"−" if r["tax"] >= 0 else "+"}{abs(r["tax"]):.0f} pp</td><td>{pct(r["exact"])}</td><td>{pct(r["cult"])}</td>'
           f'<td>{r["n"]}</td><td><span class="pill">provisional</span></td></tr>')

order = ["gpt1", "g25", "g31"]
lv = ""
for code, label in [("L1", "L1 short greeting"), ("L2", "L2 offer / price"), ("L3", "L3 multi-line / code-mixed / festival"), ("L4", "L4 long / dense conjuncts")]:
    sub = hi[hi.level == code]
    lv += f"<tr><td>{label}</td>" + "".join(f'<td {blue(v)}>{pct(v)}</td>' for v in [sub[sub.model == m].asis.mean() for m in order]) + "</tr>"

nope = d[d.would_post.eq("Would not post")]
reasons = [("Misspelled / gibberish text", lambda s: s.text_accuracy.isin(["Major error", "Gibberish / missing"])),
           ("Extra unrequested text", lambda s: s.problem_tags.fillna("").str.contains("Extra unrequested")),
           ("Fake brand / logo", lambda s: s.problem_tags.fillna("").str.contains("brand")),
           ("Distorted objects, hands or faces", lambda s: s.problem_tags.fillna("").str.contains("Distorted"))]
rj = ""
for label, f in reasons:
    cells = []
    for m in order:
        s = nope[nope.model == m]
        cells.append(f"{pct(f(s).mean())}" if len(s) else "n/a")
    rj += f"<tr><td>{label}</td>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"
rej_n = " · ".join(f"{NAME[m][0].split(' Flash')[0].replace('Gemini ', 'Gem ')} n={len(nope[nope.model == m])}" for m in order)

css = re.search(r"<style>(.*?)</style>", (HERE / "product.html").read_text(encoding="utf-8"), re.S).group(1)
html = f"""<!doctype html><html><head><meta charset="utf-8"><style>{css}
.stamp.real{{color:#1a7f37;border-color:#1a7f37}} .ci{{display:inline-block}} td .note{{display:block}}</style></head>
<body class="viz-root"><section class="view on" id="lb">
 <div class="top"><div class="logo">Bharat <span>Poster</span> Arena</div>
  <div class="tabs"><div class="a">Leaderboard</div><div>Explore failures</div><div>Compare versions</div><div>Methodology</div></div>
  <div class="stamp real">REAL DATA · {n_raters} HUMAN RATERS · PROVISIONAL</div></div>
 <div class="filters"><div>Script: <b>Devanagari (Hindi)</b> ▾</div><div>Business: <b>All 8</b> ▾</div><div>Difficulty: <b>All</b> ▾</div><div>Rater pool: <b>Hindi readers, 18+</b> ▾</div><div>Eval run: <b>2026-10 · v1</b> ▾</div></div>
 <div class="card">
  <h2>Which model makes posters a local Indian shop would post as-is?</h2>
  <div class="sub">Ranked by <b>Ship-ready rate</b> (% of ratings "Post as-is") on the 10 Hindi prompts. Models whose 95% intervals overlap share a rank band. All models are <i>provisional</i>: fewer than 300 ratings each.</div>
  <table><tr><th>Rank</th><th>Model</th><th>Ship-ready (Hindi)</th><th>95% interval</th><th>English twin</th><th>Hindi tax</th><th>Text exact (Hindi)</th><th>Looks Indian (Hindi)</th><th>Ratings</th><th>Status</th></tr>{lb}</table>
  <div class="note">Hindi tax = change in ship-ready rate from the English twin to the Hindi twin on the 6 matched pairs (− = worse in Hindi, + = better in Hindi). Interval = two-level bootstrap over prompts and raters. Ratings = all 16 prompts per model, repeat screen excluded.</div>
 </div>
 <div class="two">
  <div class="card"><h2>Where each model breaks (Hindi)</h2><div class="sub">Ship-ready rate by difficulty level</div>
   <table class="heat"><tr><th>Level</th><th>GPT Image 1</th><th>Gemini 2.5</th><th>Gemini 3.1</th></tr>{lv}</table></div>
  <div class="card"><h2>Why posters get rejected</h2><div class="sub">Share of "Would not post" ratings with each reason ({rej_n})</div>
   <table><tr><th>Reason</th><th>GPT 1</th><th>Gem 2.5</th><th>Gem 3.1</th></tr>{rj}</table></div>
 </div>
</section></body></html>"""
(HERE / "leaderboard_real.html").write_text(html, encoding="utf-8")
for r in rows:
    print(r["band"], NAME[r["m"]][0], f"HI {pct(r['hi'])} [{pct(r['lo'])},{pct(r['up'])}] EN {pct(r['en'])} tax {r['tax']:.0f} exact {pct(r['exact'])} n={r['n']}")
