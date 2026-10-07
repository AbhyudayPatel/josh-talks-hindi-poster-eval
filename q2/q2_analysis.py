"""Q2 - Low-quality transcriber detection: full, reproducible analysis.

Outputs -> q2/out/ : results.json (every number quoted in the report), CSV tables, PNG figures.
Run: python q2/q2_analysis.py   (reads work/q2.pkl, a pickle of 'Data Check.xlsx')
"""
import json, re, unicodedata, pathlib
import numpy as np, pandas as pd
from rapidfuzz.distance import Levenshtein
from scipy.stats import spearmanr, chisquare, mannwhitneyu
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "q2" / "out"; OUT.mkdir(parents=True, exist_ok=True)
R = {}  # every reported number goes here

src = ROOT / "work" / "q2.pkl"
df = pd.read_pickle(src) if src.exists() else pd.read_excel(ROOT / "Data Check.xlsx")

# ------------------------------------------------------------------ 0. normalisation helpers
PUNCT = re.compile(r"[।॥.,!?;:\"'()\[\]{}\-–—…‘’“”/\\|*#@&_~`^+=<>]")
ZW = re.compile(r"[​-‍﻿]")
BLANK_TOKENS = {"[blank]", "blank", "ब्लैंक", "खाली", "[ब्लैंक]"}


def norm(s):
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFC", s)
    s = ZW.sub("", s).lower()
    keep_blank = s.strip() in BLANK_TOKENS
    if keep_blank:
        return "[blank]"
    s = PUNCT.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def wer(ref, hyp):
    r, h = ref.split(), hyp.split()
    return Levenshtein.distance(r, h) / max(1, len(r))


def cer(ref, hyp):
    return Levenshtein.distance(ref, hyp) / max(1, len(ref))


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; m = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (float(max(0, c - m)), float(min(1, c + m)))


# ------------------------------------------------------------------ 1. structure & data audit
df["block"] = np.where(df.user_id < 1e7, "cohort10", "pool")
df["path"] = df.recording_url.str.replace(r"^https://storage.googleapis.com/[^/]+/", "", regex=True)
df["folder"] = df.path.str.rsplit("/", n=1).str[0]
df["w"] = df.whisper_text.map(norm)
df["u"] = df.user_text.map(norm)
df["whisper_missing"] = df.whisper_text.isna() | (df.w == "")
df["is_blank"] = df.u == "[blank]"
df["blank_misuse"] = df.user_text.astype(str).str.contains(r"\[blank\]", case=False) & ~df.is_blank
df["true_unedited"] = ~df.whisper_missing & (df.w == df.u)
df["cosmetic_edit"] = (df.is_edited == "Yes") & ~df.whisper_missing & (df.w == df.u)
df["edit_wer"] = np.where(df.whisper_missing, np.nan, [wer(a, b) if a else np.nan for a, b in zip(df.w, df.u)])
df["rtf"] = df.time_taken_by_user / df.duration
nchar = df.user_text.astype(str).str.replace(r"\s", "", regex=True).str.len()
has_letter = df.user_text.astype(str).str.contains(r"[ऀ-ॿa-zA-Z]")
# Junk = punctuation/whitespace only, a pasted URL, or letters from a script other than Devanagari/Latin.
# NOTE: repeated syllables ("ह ह ह", "आ आ आ") are deliberately NOT junk - laughter/hesitation is legitimate.
raw = df.user_text.astype(str)
wrong_script = raw.str.contains(r"[؀-ۿ઀-૿ঀ-৿஀-௿ఀ-౿]")
df["junk"] = (((~has_letter) & ~raw.str.contains(r"\d")) | raw.str.contains(r"https?://") | wrong_script) & ~df.is_blank

pool, coh = df[df.block == "pool"].copy(), df[df.block == "cohort10"].copy()
consec = pool.sort_values("user_id").folder.values
cps_dur = (nchar / df.duration)
cps_time = (nchar / df.time_taken_by_user)
R["audit"] = {
    "rows": len(df), "distinct_user_id": int(df.user_id.nunique()),
    "ids_with_history": int((df.user_id.value_counts() > 1).sum()),
    "cohort10_rows": len(coh), "pool_rows": len(pool),
    "pool_ids_unique_frac": float(pool.user_id.is_unique),
    "pool_consecutive_ids_same_folder": float((consec[1:] == consec[:-1]).mean()),
    "pool_median_id_gap": float(np.median(np.diff(np.sort(pool.user_id.values)))),
    "cps_matches_chars_per_duration": float(np.isclose(cps_dur, df.segment_character_per_second, rtol=1e-3).mean()),
    "cps_matches_chars_per_time": float(np.isclose(cps_time, df.segment_character_per_second, rtol=1e-3).mean()),
    "whisper_missing_frac": float(df.whisper_missing.mean()),
    "edited_yes_frac": float((df.is_edited == "Yes").mean()),
    "edited_yes_but_whisper_missing": int(((df.is_edited == "Yes") & df.whisper_missing).sum()),
    "edited_yes_cosmetic_only": int(df.cosmetic_edit.sum()),
    "time_missing": int(df.time_taken_by_user.isna().sum()),
    "time_zero": int((df.time_taken_by_user == 0).sum()),
    "time_gt_1h": int((df.time_taken_by_user > 3600).sum()),
    "blank_frac": float(df.is_blank.mean()),
    "blank_tag_variants": {k: int(v) for k, v in df.user_text.astype(str).str.strip()
                           .loc[lambda s: s.str.lower().isin(BLANK_TOKENS - {"[blank]"})].value_counts().items()},
    "blank_misuse_rows": int(df.blank_misuse.sum()),
    "junk_rows": int(df.junk.sum()),
    "tac_audios_rows": int(df.path.str.startswith("tac_audios").sum()),
}
# cohort10 timing looks synthetic
ct = coh.time_taken_by_user
vc = ct.round().value_counts().sort_index()
R["cohort10_timing"] = {
    "all_integer": bool((ct == ct.round()).all()),
    "min": float(ct.min()), "max": float(ct.max()),
    "values": {int(k): int(v) for k, v in vc.items()},
    "chisq_uniform_4_12_p": float(chisquare(vc.loc[4:12]).pvalue),
    "spearman_time_vs_duration_cohort": float(spearmanr(coh.time_taken_by_user, coh.duration).statistic),
    "spearman_time_vs_duration_pool": float(spearmanr(pool.time_taken_by_user, pool.duration, nan_policy="omit").statistic),
    "pool_integer_frac": float((pool.time_taken_by_user == pool.time_taken_by_user.round()).mean()),
    "duration_2dp_pool": float(((pool.duration * 100).round() - pool.duration * 100).abs().lt(1e-6).mean()),
    "duration_2dp_cohort": float(((coh.duration * 100).round() - coh.duration * 100).abs().lt(1e-6).mean()),
}

# ------------------------------------------------------------------ 2. population (task-level) baselines on pool
p = pool.dropna(subset=["time_taken_by_user"])
qs = [.01, .05, .10, .25, .5, .75, .9, .95, .99]
R["pool_dist"] = {
    "duration": {str(q): float(pool.duration.quantile(q)) for q in qs},
    "time_taken": {str(q): float(p.time_taken_by_user.quantile(q)) for q in qs},
    "rtf": {str(q): float(p.rtf.quantile(q)) for q in qs},
    "cps": {str(q): float(pool.segment_character_per_second.quantile(q)) for q in qs},
    "rtf_lt_1_frac": float((p.rtf < 1).mean()), "rtf_lt_0_5_frac": float((p.rtf < 0.5).mean()),
    "true_unedited_frac_when_whisper_present": float(pool.loc[~pool.whisper_missing, "true_unedited"].mean()),
    "edit_wer_median_when_edited": float(pool.loc[~pool.whisper_missing & ~pool.true_unedited, "edit_wer"].median()),
}
# RTF<1 by duration bucket (short clips make RTF<1 easier to hit innocently?)
pool["dur_bin"] = pd.cut(pool.duration, [0, 1, 3, 6, 10, 20], labels=["<1s", "1-3s", "3-6s", "6-10s", "10-20s"])
pool["rtf"] = pool.rtf
tab = pool.dropna(subset=["rtf"]).groupby("dur_bin", observed=True).agg(
    n=("rtf", "size"), median_rtf=("rtf", "median"), frac_rtf_lt1=("rtf", lambda x: (x < 1).mean()),
    median_time=("time_taken_by_user", "median"))
tab.to_csv(OUT / "pool_rtf_by_duration.csv"); R["pool_rtf_by_duration"] = tab.round(3).reset_index().to_dict("records")

# ------------------------------------------------------------------ 3. Whisper hallucination acceptance
# A whisper string that appears on many DIFFERENT audio folders with DIFFERENT durations is text that does not
# depend on the audio -> hallucination candidate. Confirm with the crowd: majority of humans mark [blank].
ww = pool[~pool.whisper_missing]
g = ww.groupby("w").agg(n=("w", "size"), folders=("folder", "nunique"), dur_sd=("duration", "std"),
                         blank_share=("is_blank", "mean"), accept_share=("true_unedited", "mean"))
halluc = g[(g.folders >= 10) & (g.dur_sd > 0.2) & (g.blank_share >= 0.4)].sort_values("n", ascending=False)
halluc.to_csv(OUT / "whisper_hallucinations.csv")
HALL = set(halluc.index)
df["whisper_halluc"] = df.w.isin(HALL)
df["halluc_accepted"] = df.whisper_halluc & df.true_unedited
pool = df[df.block == "pool"].copy(); coh = df[df.block == "cohort10"].copy()
R["hallucination"] = {"strings": [{"text": k, **{c: (round(float(v), 3) if isinstance(v, float) else int(v)) for c, v in r.items()}}
                                  for k, r in halluc.head(8).iterrows()],
                      "pool_rows_with_halluc": int(pool.whisper_halluc.sum()),
                      "pool_accept_rate": float(pool.loc[pool.whisper_halluc, "true_unedited"].mean()),
                      "pool_blank_rate": float(pool.loc[pool.whisper_halluc, "is_blank"].mean())}

# ------------------------------------------------------------------ 4. GOLD VALIDATION (crowd consensus)
# Same clip (identical whisper text + duration) transcribed independently by >=15 people -> the medoid
# transcription (min. total edit distance to all others) is a consensus reference. Lets us test whether
# behavioural signals actually predict error, instead of assuming it.
gold_rows = []
pg = pool[~pool.whisper_missing].groupby(["w", "duration"])
for (wtxt, dur), grp in pg:
    if len(grp) < 15:
        continue
    vals = grp.u.value_counts()
    texts, cnts = list(vals.index), vals.values
    if len(texts) == 1:
        med = texts[0]
    else:
        D = np.array([[Levenshtein.distance(a, b) for b in texts] for a in texts])
        med = texts[int(np.argmin((D * cnts[None, :]).sum(1)))]
    if med == "[blank]":
        continue  # silent clip; handled by hallucination analysis
    sub = grp.copy()
    sub["gold"] = med
    sub["cer"] = [1.0 if t == "[blank]" else min(1.5, cer(med, t)) for t in sub.u]
    sub["whisper_cer"] = cer(med, wtxt)
    sub["clip_id"] = f"{wtxt[:25]}|{dur}"
    gold_rows.append(sub)
gold = pd.concat(gold_rows)
gold["bad"] = gold.cer > 0.15  # >15% character error vs consensus = unusable for a 98-99% accuracy target
gold["whisper_needed_fix"] = gold.whisper_cer > 0.05
R["gold"] = {"clips": int(gold.clip_id.nunique()), "tasks": len(gold),
             "median_transcribers_per_clip": float(gold.groupby("clip_id").size().median()),
             "clips_where_consensus_differs_from_whisper": int((gold.groupby("clip_id").whisper_cer.first() > 0).sum()),
             "median_whisper_cer": float(gold.groupby("clip_id").whisper_cer.first().median()),
             "overall_bad_rate": float(gold.bad.mean()), "median_cer": float(gold.cer.median())}


def summarise(mask_name, mask, base=None):
    base = gold if base is None else base
    a, b = base[mask], base[~mask]
    ka, kb = int(a.bad.sum()), int(b.bad.sum())
    return {"signal": mask_name, "n_flagged": len(a), "share_flagged": len(a) / len(base),
            "bad_rate_flagged": ka / max(1, len(a)), "bad_ci_flagged": wilson(ka, len(a)),
            "bad_rate_rest": kb / max(1, len(b)), "bad_ci_rest": wilson(kb, len(b)),
            "lift": (ka / max(1, len(a))) / max(1e-9, kb / max(1, len(b))),
            "median_cer_flagged": float(a.cer.median()) if len(a) else np.nan,
            "median_cer_rest": float(b.cer.median())}


needfix = gold[gold.whisper_needed_fix]
sig = [
    summarise("RTF < 1 (submitted faster than audio length)", gold.rtf < 1),
    summarise("RTF < 0.5", gold.rtf < 0.5),
    summarise("Unedited when Whisper was wrong", needfix.true_unedited, needfix),
    summarise("Unedited (any clip)", gold.true_unedited),
    summarise("RTF < 1 AND unedited", (gold.rtf < 1) & gold.true_unedited),
    summarise("RTF >= 1 AND unedited", (gold.rtf >= 1) & gold.true_unedited),
    summarise("Blank on a speech clip", gold.is_blank),
    summarise("Text density < 50% of consensus", gold.u.str.replace(" ", "").str.len() < 0.5 * gold.gold.str.replace(" ", "").str.len()),
]
sig_df = pd.DataFrame(sig); sig_df.to_csv(OUT / "gold_signal_validation.csv", index=False)
R["gold_signals"] = json.loads(sig_df.to_json(orient="records"))

gold["rtf_bin"] = pd.cut(gold.rtf, [0, 0.5, 1, 2, 4, 8, 1e9], labels=["<0.5", "0.5-1", "1-2", "2-4", "4-8", ">8"], right=False)
rb = gold.groupby("rtf_bin", observed=True).agg(n=("cer", "size"), bad_rate=("bad", "mean"), median_cer=("cer", "median"),
                                                unedited=("true_unedited", "mean"))
rb.to_csv(OUT / "gold_by_rtf.csv"); R["gold_by_rtf"] = rb.round(3).reset_index().to_dict("records")
R["gold_spearman_rtf_cer"] = float(spearmanr(gold.rtf, gold.cer, nan_policy="omit").statistic)
R["gold_spearman_editwer_cer_needfix"] = float(spearmanr(needfix.edit_wer, needfix.cer, nan_policy="omit").statistic)

# ------------------------------------------------------------------ 5. per-user scorecard for the 10 real users
POOL_REF = {
    "true_unedited_rate": pool.loc[~pool.whisper_missing, "true_unedited"].mean(),
    "blank_rate": pool.is_blank.mean(),
    "halluc_accept_rate": pool.loc[pool.whisper_halluc, "true_unedited"].mean(),
    "junk_rate": pool.junk.mean(),
    "blank_misuse_rate": pool.blank_misuse.mean(),
}
rows = []
for uid, s in coh.groupby("user_id"):
    wp = s[~s.whisper_missing]
    k_un, n_un = int(wp.true_unedited.sum()), len(wp)
    hl = s[s.whisper_halluc]
    rows.append({
        "user_id": uid, "tasks": len(s), "audio_min": s.duration.sum() / 60,
        "whisper_present": n_un, "true_unedited": k_un, "true_unedited_rate": k_un / max(1, n_un),
        "unedited_ci_lo": wilson(k_un, n_un)[0], "unedited_ci_hi": wilson(k_un, n_un)[1],
        "unedited_long_clips_rate": wp[wp.duration >= 5].true_unedited.mean(),
        "median_edit_wer": wp.loc[~wp.true_unedited, "edit_wer"].median(),
        "blank_rate": s.is_blank.mean(), "blank_on_whisper_speech": (s.is_blank & ~s.whisper_missing & ~s.whisper_halluc).sum(),
        "blank_misuse": int(s.blank_misuse.sum()), "junk": int(s.junk.sum()),
        "halluc_seen": len(hl), "halluc_accepted": int(hl.true_unedited.sum()),
        "dup_text_long": int(s[s.duration >= 3].u.duplicated().sum()),
        "median_cps": s.segment_character_per_second.median(),
        "cps_gt_25": int((s.segment_character_per_second > 25).sum()),
        "rtf_lt1_rate_UNRELIABLE": (s.rtf < 1).mean(),
    })
users = pd.DataFrame(rows).sort_values("true_unedited_rate", ascending=False)
users.to_csv(OUT / "cohort10_scorecard.csv", index=False)
R["cohort10"] = json.loads(users.round(4).to_json(orient="records"))
R["pool_ref"] = {k: float(v) for k, v in POOL_REF.items()}

# examples for the report
ex = {}
u632 = coh[(coh.user_id == 632098) & coh.true_unedited & (coh.duration >= 8)].head(3)
ex["632098_unedited_long"] = u632[["whisper_text", "user_text", "duration"]].to_dict("records")
ex["junk"] = coh[coh.junk][["user_id", "user_text", "duration"]].head(6).to_dict("records")
ex["blank_misuse"] = coh[coh.blank_misuse][["user_id", "user_text"]].head(5).to_dict("records")
tac = gold[gold.clip_id.str.startswith("हमने सुना है कि बालाजी")]
ex["gold_clip"] = {"whisper": tac.whisper_text.iloc[0] if len(tac) else None, "consensus": tac.gold.iloc[0] if len(tac) else None,
                   "n": len(tac), "unedited_share": float(tac.true_unedited.mean()) if len(tac) else None}
R["examples"] = ex

# ------------------------------------------------------------------ 6. alert-volume simulation on pool tasks
R["volume"] = {
    "pool_tasks_rtf_lt1_and_unedited": float(((pool.rtf < 1) & pool.true_unedited).mean()),
    "pool_tasks_rtf_lt0.5": float((pool.rtf < 0.5).mean()),
    "pool_tasks_halluc_accepted": float(pool.halluc_accepted.mean()),
}

# ------------------------------------------------------------------ 7. figures
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "font.family": "DejaVu Sans"})
ink, accent, muted = "#1f2937", "#eb6834", "#b8b6ae"

fig, ax = plt.subplots(figsize=(6.4, 3.2))
x = rb.index.astype(str); y = rb.bad_rate.values * 100
bars = ax.bar(x, y, color=[accent if s in ("<0.5", "0.5-1") else muted for s in x])
for b_, v, n in zip(bars, y, rb.n.values):
    ax.text(b_.get_x() + b_.get_width() / 2, v + 1, f"{v:.0f}%\n(n={n})", ha="center", fontsize=8, color=ink)
ax.set_ylabel("% transcripts >15% CER\nvs crowd consensus"); ax.set_xlabel("Real-time factor = time spent / audio length")
ax.set_title("Gold set: tasks finished faster than the audio are far more often wrong", fontsize=10, loc="left")
ax.set_ylim(0, 118); ax.set_yticks(range(0, 101, 20)); fig.tight_layout(); fig.savefig(OUT / "fig_gold_rtf.png", dpi=200); plt.close(fig)

fig, ax = plt.subplots(figsize=(6.4, 3.0))
uu = users.sort_values("true_unedited_rate")
lbl = uu.user_id.astype(str)
ax.errorbar(uu.true_unedited_rate * 100, lbl, xerr=[(uu.true_unedited_rate - uu.unedited_ci_lo) * 100, (uu.unedited_ci_hi - uu.true_unedited_rate) * 100],
            fmt="o", color=ink, ecolor=muted, capsize=2)
ax.axvline(POOL_REF["true_unedited_rate"] * 100, color=accent, ls="--", lw=1)
ax.text(POOL_REF["true_unedited_rate"] * 100 + 1, 0, "population rate", color=accent, fontsize=8, va="bottom")
ax.set_xlabel("% of Whisper-transcribed tasks submitted with zero real edits (95% Wilson CI)")
ax.set_title("Blind-acceptance rate per user", fontsize=10, loc="left")
fig.tight_layout(); fig.savefig(OUT / "fig_users_unedited.png", dpi=200); plt.close(fig)

fig, ax = plt.subplots(figsize=(6.4, 2.8))
for blk, col in (("pool", ink), ("cohort10", accent)):
    v = df[df.block == blk].time_taken_by_user.dropna(); v = v[v < 60]
    ax.hist(v, bins=np.arange(0, 60, 0.5), density=True, alpha=0.6, color=col, label=f"{blk} (n={len(df[df.block==blk])})")
ax.set_xlabel("time_taken_by_user (s, <60 s shown)"); ax.set_ylabel("density"); ax.legend(frameon=False)
ax.set_title("10-user block: time is integer 4-12 s, unrelated to clip length -> unusable", fontsize=10, loc="left")
fig.tight_layout(); fig.savefig(OUT / "fig_timing_artifact.png", dpi=200); plt.close(fig)

(OUT / "results.json").write_text(json.dumps(R, ensure_ascii=False, indent=1, default=lambda o: o if not isinstance(o, (np.floating, np.integer)) else o.item()), encoding="utf-8")
print(json.dumps({k: R[k] for k in ["audit", "gold", "hallucination", "volume", "pool_ref"]}, ensure_ascii=False, indent=1, default=str))
print(sig_df.round(3).to_string())
print(rb.round(3).to_string())
print(users.round(3).to_string())
