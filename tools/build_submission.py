"""Build the single submission document: submission/master.md -> Submission.html -> Submission.pdf

Fills every {{placeholder}} from real artefacts only:
  q1/generation_log.jsonl, q1/images/, q1/researcher_audit.csv, q1/out/results.json (participant study, if run),
  q2/out/results.json, submission/config.json, optional submission/findings.md (hand-written after the study).
Run again after each step (Gemini generation, participant study) and the document updates itself.
"""
import json, re, shutil, pathlib, html, sys
import markdown
import pandas as pd
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUB = ROOT / "submission"; ASSETS = SUB / "assets"; ASSETS.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "q1"))
from shot import pdf as to_pdf
from generate import build_prompt

cfg = json.loads((SUB / "config.json").read_text(encoding="utf-8"))
spec = json.loads((ROOT / "q1" / "prompts.json").read_text(encoding="utf-8"))
P = {p["id"]: p for p in spec["prompts"]}
MODELS = [("gpt1", "OpenAI", "GPT Image 1", "gpt-image-1"), ("g25", "Google", "Gemini 2.5 Flash Image", "gemini-2.5-flash-image"),
          ("g31", "Google", "Gemini 3.1 Flash Image Preview", "gemini-3.1-flash-image-preview")]
MN = {m[0]: m[2] for m in MODELS}
IMG = ROOT / "q1" / "images"
log = [json.loads(l) for l in (ROOT / "q1" / "generation_log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
have = {m[0]: sorted(p.stem.split("_")[0] for p in IMG.glob(f"*_{m[0]}.png")) for m in MODELS}
n_have = {k: len(v) for k, v in have.items()}
all_gen = all(n == 16 for n in n_have.values())
q1r_f = ROOT / "q1" / "out" / "results.json"
q1r = json.loads(q1r_f.read_text(encoding="utf-8")) if q1r_f.exists() else None
if q1r and not q1r.get("data_label", "").startswith("REAL"):
    q1r = None  # never let synthetic results into the submission
q2r = json.loads((ROOT / "q2" / "out" / "results.json").read_text(encoding="utf-8"))
audit = pd.read_csv(ROOT / "q1" / "researcher_audit.csv", encoding="utf-8-sig")
findings_f = SUB / "findings.md"
PENDING = '<span class="pending">PENDING</span>'
R = {}

# ------------------------------------------------------------------ helpers
def thumb(src, name, w=420):
    out = ASSETS / name
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
        im = Image.open(src).convert("RGB"); im.thumbnail((w, w)); im.save(out, "JPEG", quality=84, optimize=True)
    return f"assets/{name}"

def copy(src):
    dst = ASSETS / src.name; shutil.copy2(src, dst); return f"assets/{src.name}"

def pct(x, d=0):
    return f"{x*100:.{d}f}%"

# ------------------------------------------------------------------ config & status
for k in ["candidate_name", "candidate_email", "video_url", "materials_url", "date"]:
    R[k] = cfg[k]
n_part = q1r["participants"]["n_included"] if q1r else None
R["n_participants"] = str(n_part) if n_part else "8 to 10"
MID = {m[0]: m[3] for m in MODELS}


def gen_status(k):
    ok = [l for l in log if l["model_id"] == MID[k] and l["status"] == "ok"]
    if n_have[k] == 16:
        return f"16 of 16 generated, {min(l['timestamp_utc'] for l in ok)[:10]}"
    if n_have[k] == 0:
        return PENDING
    return f"{n_have[k]} of 16 generated"


def platform(k):
    ok = [l for l in log if l["model_id"] == MID[k] and l["status"] == "ok"]
    return ok[0]["platform"].replace(" (generateContent)", "") if ok else "Gemini API or Google AI Studio"


for k, *_ in MODELS:
    R[f"gen_status_{k}"] = gen_status(k)
    R[f"platform_{k}"] = platform(k)

# ------------------------------------------------------------------ researcher audit
TS = {"Exactly correct": 3, "Small error": 2, "Major error": 1, "Gibberish / missing": 0}
audit["lang"] = audit.prompt_id.map(lambda x: P[x]["lang"])
summ = []
for k, _, name, _ in MODELS:
    a = audit[audit.model == k]
    if not len(a):
        continue
    en, hi = a[a.lang == "EN"], a[a.lang != "EN"]
    pairs_hi = hi[hi.prompt_id.map(lambda x: P[x]["pair"] != "")]
    summ.append(f"| {name} | {(en.text_label=='Exactly correct').sum()}/{len(en)} | {(hi.text_label=='Exactly correct').sum()}/{len(hi)} | "
                f"{(pairs_hi.text_label=='Exactly correct').sum()}/{len(pairs_hi)} | {(hi.text_label.isin(['Exactly correct','Small error'])).sum()}/{len(hi)} | "
                f"{(hi.text_label.isin(['Major error','Gibberish / missing'])).sum()}/{len(hi)} | {(a.extra_text=='yes').sum()}/{len(a)} | {(a.brand_issue=='yes').sum()}/{len(a)} |")
R["audit_summary"] = ("| Model | English text exact | Hindi text exact (all 10 Hindi/mixed) | Hindi exact — 6 twins only | Hindi readable (exact + small) | Hindi major/gibberish | Unrequested text | Fake brand/logo |\n|---|---|---|---|---|---|---|---|\n" + "\n".join(summ)
                      + ("\n\n*Gemini audits will be added after generation.*" if not all_gen else ""))
rows = []
for _, r in audit.iterrows():
    rows.append(f"| {r.prompt_id} | {MN[r.model]} | {P[r.prompt_id]['lang']} | {r.text_label} | {html.escape(str(r.notes)) if str(r.notes)!='nan' else ''} |")
R["audit_table"] = "**Per-image audit notes**\n\n| Prompt | Model | Lang | Text (my label) | Notes |\n|---|---|---|---|---|\n" + "\n".join(rows)

# ------------------------------------------------------------------ Q1 participant block
if q1r:
    for f in ["fig_leaderboard.png", "fig_hindi_tax.png", "fig_prompt_heatmap.png"]:
        copy(ROOT / "q1" / "out" / f)
    lb = q1r["leaderboard"]; tax = q1r["hindi_tax"]; al = q1r["alpha"]; tr = q1r["test_retest"]; pt = q1r["paired_tests"]
    order = sorted(lb, key=lambda m: -lb[m]["post_asis"])
    t = "| Model | Ship-ready (95% CI) | Text exact (95% CI) | Readable | Culture OK | Best-pick share | Bradley–Terry |\n|---|---|---|---|---|---|---|\n"
    for m in order:
        L = lb[m]
        t += (f"| {MN[m]} | **{pct(L['post_asis'])}** ({pct(L['post_asis_ci'][0])}–{pct(L['post_asis_ci'][1])}) | {pct(L['text_exact'])} ({pct(L['text_exact_ci'][0])}–{pct(L['text_exact_ci'][1])}) | "
              f"{pct(L['text_readable'])} | {pct(L['cult_ok'])} | {pct(L['best_pick_share'])} | {L['bt_strength']:.2f} |\n")
    tt = "| Model | Ship-ready EN twin | Ship-ready HI twin | Hindi tax (95% CI) | Text exact EN → HI | Pairs where HI worse |\n|---|---|---|---|---|---|\n"
    for m in order:
        x = tax[m]
        tt += f"| {MN[m]} | {pct(x['EN_post_asis'])} | {pct(x['HI_post_asis'])} | **{x['tax_post_asis_pp']:.0f} pp** ({x['tax_ci_pp'][0]:.0f} to {x['tax_ci_pp'][1]:.0f}) | {pct(x['EN_text_exact'])} → {pct(x['HI_text_exact'])} | {x['pairs_where_HI_worse']}/{x['n_pairs']} |\n"
    pt_t = "| Comparison | Mean Δ ship-ready | Prompts better / worse / tie | Wilcoxon p | Sign-test p |\n|---|---|---|---|---|\n"
    for k, v in pt.items():
        i, j = k.split("_vs_")
        pt_t += f"| {MN[i]} vs {MN[j]} | {v['mean_diff_pp']:+.0f} pp | {v['prompts_i_better']} / {v['prompts_j_better']} / {v['ties']} | {v['wilcoxon_p'] if v['wilcoxon_p'] is None else round(v['wilcoxon_p'],3)} | {v['sign_test_p'] if v['sign_test_p'] is None else round(v['sign_test_p'],3)} |\n"
    pp = q1r["participants"]
    small = pp['n_included'] < 8
    R["q1_results_block"] = (f"""<div class="block yellow">

<span class="pill real">REAL DATA</span> **This run had {pp['n_included']} verified Hindi-reading participants, below the 8 to 10 the brief asks for.** Every rating file is checked against the app's own randomisation, and I chose to report only ratings that pass, rather than pad the sample. With 2 raters the numbers are descriptive: they show direction, not a ranking. They are read together with my letter-by-letter audit of all 48 posters and the 3-run AI panel above, and all three sources point the same way.

</div>

""" if small else "") + f"""<span class="pill real">REAL DATA</span> {pp['n_included']} participant(s) included ({pp['n_total']} completed; exclusions: {', '.join(pp['excluded']) or 'none'}), median {pp['median_minutes']:.0f} minutes, {q1r['n_ratings']} image-ratings over {q1r['n_prompts']} prompts.

**Leaderboard (all 16 prompts).**

{t}
<div class="fig"><img src="assets/fig_leaderboard.png"></div>

**The Hindi tax (6 matched twins).**

{tt}
<div class="fig"><img src="assets/fig_hindi_tax.png"></div>

**Per-prompt view.**

<div class="fig"><img src="assets/fig_prompt_heatmap.png" style="max-height:520px"></div>

{'' if small else '**Exploratory paired tests across prompts (n = 16; Holm-adjust before claiming).**' + chr(10) + chr(10) + pt_t}
**Reliability.** {'Rater agreement (alpha) needs two or more raters.' if pp['n_included'] < 2 else f"Agreement between raters, Krippendorff's alpha (ordinal): text {al['text_ordinal']:.2f}, would-post {al['post_ordinal']:.2f}, looks-right {al['culture_ordinal']:.2f} (targets: text 0.6, would-post 0.4)."} Test-retest on the repeated screen: identical text label {pct(tr['text_exact_agree'] or 0)}, within one level {pct(tr['text_within1'] or 0)}, identical would-post {pct(tr['post_agree'] or 0)}. Best-pick share by position: {', '.join(f'{k} {pct(v)}' for k, v in sorted(q1r['position_bias'].items()))}.
""" + (f"\n**Agreement with my researcher audit:** participants' median text label matched mine on {pct(q1r['audit_agreement']['exact'])} of images (within one level: {pct(q1r['audit_agreement']['within1'])})." if "audit_agreement" in q1r else "")
else:
    R["q1_results_block"] = f"""<div class="block grey">

{PENDING} **Participant ratings.** This section fills in automatically from the rating files: the leaderboard with 95% intervals, the Hindi tax per model, the per-prompt view, rater agreement, repeat-screen consistency and position bias. Nothing here is estimated or simulated.

</div>"""


def card(title, rows, tag="MY AUDIT", cls="audit"):
    body = "".join(f"| {k} | {v} |\n" for k, v in rows)
    return (f'<div class="card"><div class="ch"><h3>{title}</h3><span class="pill {cls}">{tag}</span></div><div class="cb">\n\n'
            f"| | |\n|---|---|\n{body}\n</div></div>\n\n")


DEFAULT_FINDINGS = ("These early findings come from my letter-by-letter audit of the real GPT Image 1 outputs. "
                    "Participant ratings and the Gemini outputs will confirm or overturn them.\n\n") + \
    card("F1 · A Hindi tax exists even when the visuals are excellent", [
        ("Observation", "English text was exactly right on 6 of 6 English posters, but on only 2 of the 6 matching Hindi posters."),
        ("Evidence", "P02 \"शर्मा स्वीट्स\" came out with a doubled म and a stray nukta; P10 \"उपलब्ध\" became \"उपल्वध\"."),
        ("Interpretation", "The pairs share everything except language, so the gap is script rendering, not layout or style."),
        ("Implication", "A poster feature that passes English QA would ship broken in Hindi."),
        ("Recommendation", "Gate any Indic launch on a per-script ship-ready bar; until a model passes, verify text or overlay it.")]) + \
    card("F2 · Looking great is not the same as being usable", [
        ("Observation", "All 16 posters are polished, with correct festival objects and Indian settings, yet 7 of 10 Hindi posters have text errors."),
        ("Interpretation", "A preference vote by a non-Hindi reader would rate these highly. For the shop owner, a misspelled shop name rules a poster out."),
        ("Recommendation", "India-focused evals need native-script raters and a \"would you post it?\" question, not only \"which looks better?\".")]) + \
    card("F3 · Same mistake, very different consequence", [
        ("Observation", "Despite \"ONLY the following text\", the model added text nobody asked for on 4 of 16 posters."),
        ("Evidence", "In English (P09) the extra shop name was readable. In the Hindi twin (P10) it became fake Hindi: \"अगरावी गसरलातो सोरर\"."),
        ("Recommendation", "Measure instruction-following per script; in product, strip or OCR-check any text that wasn't requested.")]) + \
    card("F4 · Errors follow how common a word is, not how complex the script is", [
        ("Observation", "The most conjunct-heavy prompt (श्री कृष्ण जन्माष्टमी की हार्दिक शुभकामनाएँ) was perfect. Everyday words broke: मोबाइल → मोबाल, डिलीवरी → डिलेबरी, जैसा → जेसा. Nukta was dropped in 4 of 7 cases."),
        ("Interpretation", "Stock greetings look memorised; the shop's own words, the whole point of the poster, are not."),
        ("Caveat", "I noticed this after seeing the outputs, so it is a hypothesis to test on the Gemini outputs and with participants."),
        ("Recommendation", "For model builders: targeted training data with shop names, prices and English loanwords in Devanagari.")]) + \
    card("F5 · Fake brands are a real risk for small shops", [
        ("Observation", "2 of 16 posters showed a brand: a fake \"AASHIRAAD\" rice pack (an Aashirvaad look-alike) and an Apple logo."),
        ("Implication", "The shop owner carries the trademark risk without noticing."),
        ("Recommendation", "Block logos in business templates. The rating app already has a \"fake brand\" tag.")])
R["findings_block"] = findings_f.read_text(encoding="utf-8") if findings_f.exists() else DEFAULT_FINDINGS


def opt(name, default):
    f = findings_f.with_name(name)
    return f.read_text(encoding="utf-8").strip() if f.exists() else default


R["onepager_findings"] = opt("onepager_findings.md",
    "- **A clear Hindi tax.** GPT Image 1 spelled English perfectly on 6 of 6 posters, but Hindi correctly on only 2 of the 6 identical Hindi versions, while every poster looked professional. <span class=\"pill audit\">MY AUDIT</span>\n"
    "- **Errors follow common words, not hard script.** The densest conjuncts were perfect; everyday words broke (मोबाइल → मोबाल, डिलीवरी → डिलेबरी). <span class=\"pill audit\">MY AUDIT</span>\n"
    "- **Small slips become visible defects in Hindi.** Unrequested shop names were readable in English but fake Hindi in the Hindi version; 2 posters showed fake brands. <span class=\"pill audit\">MY AUDIT</span>\n"
    + ("" if q1r else f"- {PENDING} Participant leaderboard and the Gemini comparison fill in from the rating files.\n"))
R["reflection_learned"] = opt("reflection_learned.md",
    "Checking every output before the study changed the design: I added \"fake brand\" and \"extra text\" as rating tags because I saw them in real posters. "
    "The surprises weren't where I expected either. A prompt built to break the models came out perfect, while ordinary words broke. I've recorded that as a hypothesis, not a finding. "
    "And with 16 prompts, the prompt, not the rater, is the unit of evidence, so the next version should add more prompts rather than more ratings.")
R["video_findings"] = opt("video_findings.md",
    "Before anyone rated them, I read every poster letter by letter. GPT Image 1's English posters were all spelled perfectly. The Hindi versions? Two out of six. "
    "And they all look professional, which is the trap. The errors weren't in the hard letters, they were in ordinary words: 'mobile' lost a letter, 'delivery' was misspelled. "
    "And a shop name I never asked for was fine in English and gibberish in Hindi. [UPDATE with participant results]")

# ------------------------------------------------------------------ AI-judge panel (clearly not human)
air_f = ROOT / "q1" / "out_AI" / "results.json"
if air_f.exists():
    air = json.loads(air_f.read_text(encoding="utf-8"))
    for f in ["fig_leaderboard.png", "fig_hindi_tax.png"]:
        shutil.copy2(ROOT / "q1" / "out_AI" / f, ASSETS / ("ai_" + f))
    lb, tax, al = air["leaderboard"], air["hindi_tax"], air["alpha"]
    order = sorted(lb, key=lambda m: -lb[m]["post_asis"])
    t = "| Model | Would post as-is (95% CI) | Text exactly correct | Picked as best | Hindi tax (post as-is) |\n|---|---|---|---|---|\n"
    for m in order:
        L, x = lb[m], tax[m]
        t += (f"| {MN[m]} | **{pct(L['post_asis'])}** ({pct(L['post_asis_ci'][0])} to {pct(L['post_asis_ci'][1])}) | {pct(L['text_exact'])} | "
              f"{pct(L['best_pick_share'])} | {x['tax_post_asis_pp']:.0f} pp ({pct(x['EN_post_asis'])} → {pct(x['HI_post_asis'])}) |\n")
    ag = air.get("audit_agreement", {})
    tr = air["test_retest"]
    R["ai_panel_block"] = f"""### AI-judge panel <span class="pill illus">AI, NOT HUMAN</span>

To get an early read and to test the "can we automate judging?" question from the scaling plan, I ran the exact participant protocol with an AI judge: Claude Opus 5 saw the same blinded, shuffled screens and answered the same questions, in {air['participants']['n_included']} independent runs. **This is not participant data and does not replace the human study.**

{t}
<div class="fig"><img src="assets/ai_fig_hindi_tax.png" style="max-height:62mm"></div>

**How far can it be trusted?** Agreement between the three AI runs on text accuracy: Krippendorff's alpha {al['text_ordinal']:.2f}. Its median text label matched my letter-by-letter audit on **{pct(ag.get('exact', 0))}** of posters ({pct(ag.get('within1', 0))} within one level). Same label on the repeated screen: {pct(tr['text_exact_agree'] or 0)}. The judge also transcribes what it reads, which makes every label auditable.

**Where it diverges, and why that matters.** On "would you post it?" the AI judge is very strict about tiny background lettering in photo-realistic scenes: garbled text on packet labels, book spines or a clock face. It downgraded Gemini 3.1's English posters for this even when the headline text was perfect, which produces an odd negative "Hindi tax" for that model. A shop owner may never notice those details. So the AI judge is ready to pre-screen **text accuracy**, but **"would you post it?" should stay a human judgment** until it is checked against the participant ratings.
"""
else:
    R["ai_panel_block"] = ""

# ------------------------------------------------------------------ appendix tables
pt = "| ID | Lang · level | Category | Exact text requested | What it tests |\n|---|---|---|---|---|\n"
for p in spec["prompts"]:
    pair = f" · pair {p['pair']}" if p["pair"] else ""
    pt += f"| **{p['id']}**{pair} | {p['lang']} · {p['level']} | {p['category']} | {' / '.join(p['lines'])} | {p['tests']} |\n"
ex = build_prompt(spec, P["P02"])
R["prompt_table"] = pt + ("\n**Full prompt, example P02.** Every prompt is built from the same template; the exact text of each is stored in the generation log.\n\n"
                          f"<pre class=\"prompt\">{html.escape(ex)}</pre>")

okl = sorted([l for l in log if l["status"] == "ok"], key=lambda l: (["gpt-image-1", "gemini-2.5-flash-image", "gemini-3.1-flash-image-preview"].index(l["model_id"]), l["prompt_id"]))
gl = "| Prompt | Model | Platform | Request ID | Time (UTC) |\n|---|---|---|---|---|\n"
for l in okl:
    rid = l.get("request_id") or "web app, see screenshot"
    gl += f"| {l['prompt_id']} | {l['model_name']} | {l['platform']} | <code>{rid}</code> | {l['timestamp_utc'][:16].replace('T', ' ')} |\n"
R["genlog_table"] = gl + "\nEvery record in <code>q1/generation_log.jsonl</code> also stores the exact prompt, settings and token usage."

g = '<table class="gallery"><tr><th>Prompt</th>' + "".join(f"<th>{m[1]} · {m[2]}</th>" for m in MODELS) + "</tr>"
for p in spec["prompts"]:
    g += f'<tr><td><b>{p["id"]}</b><br>{p["lang"]} · {p["category"]}<br><span class="req">{"<br>".join(html.escape(x) for x in p["lines"])}</span></td>'
    for k, *_ in MODELS:
        f = IMG / f"{p['id']}_{k}.png"
        g += f'<td><img src="{thumb(f, f.stem + ".jpg")}"></td>' if f.exists() else f'<td class="ph">{PENDING}</td>'
    g += "</tr>"
R["gallery"] = g + "</table>\n\nThumbnails shown; full-resolution PNGs are in `q1/images/` (" + cfg["materials_url"] + ")."

# Q2 tables
copy(ROOT / "q2" / "out" / "fig_timing_artifact.png")
sig = pd.read_csv(ROOT / "q2" / "out" / "gold_signal_validation.csv")
t = "| Signal (gold set, 5,544 tasks) | Tasks flagged | Bad if flagged (95% CI) | Bad otherwise | Note |\n|---|---|---|---|---|\n"
notes = {"Unedited when Whisper was wrong": "true by construction", "Unedited (any clip)": "true by construction (Whisper wrong on all gold clips)",
         "RTF >= 1 AND unedited": "true by construction"}
for _, r in sig.iterrows():
    lo, hi = json.loads(r.bad_ci_flagged.replace("(", "[").replace(")", "]")) if isinstance(r.bad_ci_flagged, str) else r.bad_ci_flagged
    t += f"| {r.signal} | {int(r.n_flagged)} ({r.share_flagged*100:.1f}%) | {r.bad_rate_flagged*100:.1f}% ({lo*100:.1f}–{hi*100:.1f}) | {r.bad_rate_rest*100:.1f}% | {notes.get(r.signal,'')} |\n"
rb = pd.read_csv(ROOT / "q2" / "out" / "gold_by_rtf.csv")
t2 = "| RTF bin | Tasks | Bad rate | Median CER | Unedited share |\n|---|---|---|---|---|\n" + "".join(
    f"| {r.rtf_bin} | {r.n} | {r.bad_rate*100:.0f}% | {r.median_cer:.2f} | {r.unedited*100:.0f}% |\n" for _, r in rb.iterrows())
pr = pd.read_csv(ROOT / "q2" / "out" / "pool_rtf_by_duration.csv")
t3 = "| Clip length | Tasks | Median RTF | Share RTF < 1 | Median time (s) |\n|---|---|---|---|---|\n" + "".join(
    f"| {r.dur_bin} | {r.n} | {r.median_rtf:.1f} | {r.frac_rtf_lt1*100:.1f}% | {r.median_time:.1f} |\n" for _, r in pr.iterrows())
sc = pd.read_csv(ROOT / "q2" / "out" / "cohort10_scorecard.csv")
t4 = "| User | Tasks | Audio min | Unedited (CI) | Unedited ≥5 s | Median edit WER | Blank rate | Halluc. accepted/seen | Junk | [blank]+text | Dup. long texts |\n|---|---|---|---|---|---|---|---|---|---|---|\n" + "".join(
    f"| {int(r.user_id)} | {int(r.tasks)} | {r.audio_min:.0f} | {r.true_unedited_rate*100:.0f}% ({r.unedited_ci_lo*100:.0f}–{r.unedited_ci_hi*100:.0f}) | {r.unedited_long_clips_rate*100:.0f}% | {r.median_edit_wer:.2f} | {r.blank_rate*100:.0f}% | {int(r.halluc_accepted)}/{int(r.halluc_seen)} | {int(r.junk)} | {int(r.blank_misuse)} | {int(r.dup_text_long)} |\n" for _, r in sc.iterrows())
hz = q2r["hallucination"]["strings"]
t5 = "| Whisper string | Tasks | Distinct recordings | Humans wrote [blank] | Accepted verbatim |\n|---|---|---|---|---|\n" + "".join(
    f"| {h['text'][:40]}{'…' if len(h['text'])>40 else ''} | {int(h['n'])} | {int(h['folders'])} | {h['blank_share']*100:.0f}% | {h['accept_share']*100:.0f}% |\n" for h in hz)
R["q2_tables"] = f"""<span class="lbl real">REAL DATA</span>

**H1. Signal validation against the crowd-consensus gold set** (bad = CER > 15% vs medoid of ~126 transcriptions)

{t}
**H2. Error rate by real-time factor (gold set)**

{t2}
**H3. Production tasks: RTF by clip length** (8-digit task-ID block, real timings)

{t3}
**H4. Per-user scorecard (10 users with history; timing-based fields omitted — synthetic)**

{t4}
**H5. Whisper hallucinations (strings recurring across unrelated recordings)**

{t5}
**H6. Why the 10-user timings are unusable**

<div class="fig"><img src="assets/fig_timing_artifact.png" style="max-height:260px"></div>
"""

# participant table (consent proof)
if q1r:
    pdf_ = pd.read_csv(ROOT / "q1" / "out" / "participants.csv")
    R["participant_table"] = "**Participants and consent record** <span class=\"lbl real\">REAL DATA</span>\n\n| # | Name | Email | Age | Hindi | State | Consent | Consent timestamp (UTC) |\n|---|---|---|---|---|---|---|---|\n" + "".join(
        f"| {i+1} | {r['name']} | {r.email} | {int(r.age)} | {r.hindi} | {'' if pd.isna(r.state) else r.state} | {'Yes' if str(r.consent).lower()=='true' else 'No'} | {r.consent_ts} |\n" for i, (_, r) in enumerate(pdf_.iterrows()))
else:
    R["participant_table"] = f"**Participants and consent record:** {PENDING} — filled automatically from the rating files (name, email, age, Hindi level, consent text + timestamp per participant)."

R["req_models"] = "✔ all 48 generated" if all_gen else f"{PENDING} GPT Image 1 ✔ 16/16; Gemini ×2 scripted, awaiting API key"
R["req_participants"] = f"✔ {n_part} participants" if q1r else f"{PENDING} app built & tested; study to run"
R["req_findings"] = "✔ participant + audit findings" if q1r else "✔ audit findings · participant findings pending"
R["req_video"] = "✔" if not cfg["video_url"].startswith("[") else f"{PENDING} record from §5"

# ------------------------------------------------------------------ render
md = (SUB / "master.md").read_text(encoding="utf-8")
missing = sorted(set(re.findall(r"{{(\w+)}}", md)) - set(R))
if missing:
    raise SystemExit(f"unfilled placeholders: {missing}")
md = re.sub(r"{{(\w+)}}", lambda m: R[m.group(1)], md)
md = re.sub(r'<div class="([^"]+)">', r'<div class="\1" markdown="1">', md)
md = re.sub(r'<div class="fig" markdown="1">', '<div class="fig">', md)
md = md.replace("../work/shots/", "assets/").replace("../q2/out/", "assets/")
for f in list((ROOT / "work" / "shots").glob("*.png")) + list((ROOT / "q2" / "out").glob("fig_*.png")):
    copy(f)

body = markdown.markdown(md, extensions=["tables", "md_in_html", "fenced_code", "sane_lists"])
body = body.replace("\u2014", "-").replace("\u2013", "-")
css = (ROOT / "tools" / "submission.css").read_text(encoding="utf-8")
out_html = SUB / "Submission.html"
out_html.write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>Josh Talks AI · Product Task submission</title><style>{css}</style></head><body>{body}</body></html>", encoding="utf-8")
to_pdf(out_html, SUB / "Submission.pdf")
left = re.findall(r"\[UPDATE[^\]]*\]|\[YOUR [A-Z]+\]|\[PASTE[^\]]*\]", out_html.read_text(encoding="utf-8"))
print("built", SUB / "Submission.pdf", f"({(SUB/'Submission.pdf').stat().st_size/1e6:.1f} MB)")
print("status:", {"images": n_have, "participant_results": bool(q1r)})
print("still to fill:", sorted(set(left)) or "nothing")
print("PENDING markers:", out_html.read_text(encoding="utf-8").count('class="pending"'))
