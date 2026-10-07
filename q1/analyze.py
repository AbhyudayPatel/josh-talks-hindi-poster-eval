"""Pre-registered analysis for the Hindi Local-Business Poster eval.

Written BEFORE any participant data existed. Reads every CSV in q1/ratings/ (one per participant, as exported
by rate.html, or one combined Google-Sheet export) + rating_app/key.json (blinding key).
Writes q1/out/results.json, q1/out/*.png and q1/out/results_fragment.md (pulled into the submission).

Design facts that drive the statistics:
  * fully crossed: every rater rates every image -> raters and prompts are crossed random factors
  * the real n for model comparisons is the number of PROMPTS (16), not the number of ratings (~500)
    -> CIs come from a two-level cluster bootstrap (resample prompts AND raters)
  * with 8-10 raters x 16 prompts we treat results as DIRECTIONAL unless the CI excludes 0 by a wide margin

Usage: python analyze.py [--ratings DIR] [--out DIR] [--synthetic-label]
"""
import argparse, json, pathlib, itertools
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import wilcoxon, binomtest

HERE = pathlib.Path(__file__).parent
MODEL_NAME = {"gpt1": "GPT Image 1", "g25": "Gemini 2.5 Flash Image", "g31": "Gemini 3.1 Flash Image Preview"}
COLOR = {"gpt1": "#2a78d6", "g25": "#eb6834", "g31": "#1baf7a"}  # validated categorical slots 1-3
TEXT_SCORE = {"Exactly correct": 3, "Small error": 2, "Major error": 1, "Gibberish / missing": 0}
USE_SCORE = {"Post as-is": 2, "Post after small fixes": 1, "Would not post": 0}
CULT_SCORE = {"Looks right": 2, "Something is a bit off": 1, "Clearly wrong / not Indian": 0}
MIN_SECONDS_PER_SCREEN = 15  # pre-registered speeder rule (median across screens)
B = 2000
rng = np.random.default_rng(7)


# ---------------------------------------------------------------- Krippendorff's alpha (nominal / ordinal / interval)
def kripp_alpha(units, level="ordinal", cats=None):
    """units: list of lists of values given by different raters to the same item (missing allowed)."""
    units = [[v for v in u if v is not None and not pd.isna(v)] for u in units]
    units = [u for u in units if len(u) >= 2]
    if not units:
        return np.nan
    cats = sorted({v for u in units for v in u}) if cats is None else cats
    idx = {c: i for i, c in enumerate(cats)}; K = len(cats)
    o = np.zeros((K, K))
    for u in units:
        m = len(u)
        for a, b in itertools.permutations(range(m), 2):
            o[idx[u[a]], idx[u[b]]] += 1 / (m - 1)
    n_c = o.sum(1); n = n_c.sum()
    if level == "nominal":
        d = 1 - np.eye(K)
    elif level == "interval":
        d = np.array([[(ci - cj) ** 2 for cj in cats] for ci in cats], float)
    else:  # ordinal
        d = np.zeros((K, K))
        for i in range(K):
            for j in range(K):
                lo, hi = min(i, j), max(i, j)
                d[i, j] = (n_c[lo:hi + 1].sum() - (n_c[lo] + n_c[hi]) / 2) ** 2
    Do = (o * d).sum() / n
    De = (np.outer(n_c, n_c) * d).sum() / (n * (n - 1))
    return 1 - Do / De if De > 0 else np.nan


def bradley_terry(wins, items, iters=500):
    """wins[(i,j)] = times i beat j. Returns strengths normalised to mean 1 (MM algorithm, Hunter 2004)."""
    p = {i: 1.0 for i in items}
    for _ in range(iters):
        new = {}
        for i in items:
            w = sum(wins.get((i, j), 0) for j in items if j != i)
            den = sum((wins.get((i, j), 0) + wins.get((j, i), 0)) / (p[i] + p[j]) for j in items if j != i)
            new[i] = w / den if den > 0 else p[i]
        s = np.mean(list(new.values())); p = {k: v / s for k, v in new.items()}
    return p


def load(ratings_dir):
    files = sorted(pathlib.Path(ratings_dir).glob("*.csv"))
    if not files:
        raise SystemExit(f"no ratings CSVs in {ratings_dir}")
    df = pd.concat([pd.read_csv(f, encoding="utf-8-sig") for f in files], ignore_index=True)
    # Integrity gate: human rows must reproduce the app's email-seeded randomisation exactly (see verify_ratings.py).
    human = df[~df.build.astype(str).isin(["AI-PANEL", "SYNTH"])]
    if len(human):
        from verify_ratings import expected
        spec_ = json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))
        key_ = json.loads((HERE / "rating_app" / "key.json").read_text())
        for email, s in human.groupby("email"):
            pid, exp = expected(email, str(s.build.iloc[0]), spec_, key_)
            bad = sum(exp.get((int(r.screen_index), r.position)) != (r.prompt_id, r.image_id) for r in s.itertuples())
            if s.participant_id.iloc[0] != pid or bad:
                raise SystemExit(f"REJECTED: ratings for {email} were not produced by rate.html ({bad} rows off the app's layout).")
    key = json.loads((HERE / "rating_app" / "key.json").read_text())
    df["model"] = df.image_id.map(lambda i: key[i]["model"])
    df["key_prompt"] = df.image_id.map(lambda i: key[i]["prompt_id"])
    assert (df.key_prompt == df.prompt_id).all(), "blinding key mismatch"
    df = df.drop_duplicates(["participant_id", "screen_index", "image_id"], keep="last")
    df["is_repeat"] = df.is_repeat.astype(str).str.lower().eq("true")
    df["picked_this"] = df.picked_this.astype(str).str.lower().eq("true")
    df["text_score"] = df.text_accuracy.map(TEXT_SCORE)
    df["text_exact"] = df.text_score.eq(3).astype(float)
    df["text_readable"] = df.text_score.ge(2).astype(float)       # exact or small error
    df["use_score"] = df.would_post.map(USE_SCORE)
    df["post_asis"] = df.use_score.eq(2).astype(float)
    df["post_any"] = df.use_score.ge(1).astype(float)
    df["cult_ok"] = df.looks_right.map(CULT_SCORE).eq(2).astype(float)
    return df


def cluster_boot(d, metric, by="model"):
    """Two-level bootstrap: resample prompts and raters with replacement. Returns {group: (lo, hi)}."""
    prompts, raters = d.prompt_id.unique(), d.participant_id.unique()
    piv = d.groupby([by, "prompt_id", "participant_id"])[metric].mean()
    groups = d[by].unique(); res = {g: [] for g in groups}
    for _ in range(B):
        ps = rng.choice(prompts, len(prompts)); rs = rng.choice(raters, len(raters))
        for g in groups:
            sub = piv.loc[g]
            vals = [sub.get((p, r), np.nan) for p in ps for r in rs]
            res[g].append(np.nanmean(vals))
    return {g: (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))) for g, v in res.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratings", default=str(HERE / "ratings")); ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--synthetic-label", action="store_true", help="stamp every figure ILLUSTRATIVE (pipeline test)")
    a = ap.parse_args(); OUT = pathlib.Path(a.out); OUT.mkdir(parents=True, exist_ok=True)
    stamp = "ILLUSTRATIVE – SYNTHETIC DATA" if a.synthetic_label else None
    spec = json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))
    P = {p["id"]: p for p in spec["prompts"]}
    df = load(a.ratings)
    R = {"data_label": "SYNTHETIC (pipeline test)" if a.synthetic_label else "REAL participant data"}

    # ---------- participants & exclusions (pre-registered)
    part = df.groupby("participant_id").agg(name=("name", "first"), email=("email", "first"), age=("age", "first"),
                                            hindi=("hindi_level", "first"), state=("state", "first"), consent=("consent", "first"),
                                            consent_ts=("consent_ts", "first"), med_sec=("seconds_on_screen", "median"),
                                            screens=("screen_index", "nunique"))
    part["excluded"] = (part.age < 18) | (~part.consent.astype(str).str.lower().eq("true")) | part.hindi.eq("Cannot read") | (part.med_sec < MIN_SECONDS_PER_SCREEN)
    part.to_csv(OUT / "participants.csv")
    R["participants"] = {"n_total": len(part), "n_included": int((~part.excluded).sum()),
                         "excluded": part[part.excluded].index.tolist(), "median_age": float(part.age.median()),
                         "hindi_levels": part.hindi.value_counts().to_dict(), "states": part.state.fillna("").value_counts().to_dict(),
                         "median_minutes": float(df.groupby("participant_id").seconds_on_screen.sum().median() / 60)}
    df = df[df.participant_id.isin(part[~part.excluded].index)]
    main_ = df[~df.is_repeat].copy()
    R["n_ratings"] = len(main_); R["n_prompts"] = main_.prompt_id.nunique()

    # ---------- 1. leaderboard (primary metric = Post as-is rate)
    metrics = ["post_asis", "post_any", "text_exact", "text_readable", "cult_ok"]
    lb = main_.groupby("model")[metrics].mean()
    ci = {m: cluster_boot(main_, m) for m in ["post_asis", "text_exact"]}
    picks = main_[main_.picked_this].groupby("model").size() / main_[["participant_id", "screen_index"]].drop_duplicates().shape[0]
    lb["best_pick_share"] = picks.reindex(lb.index).fillna(0)
    lb["none_share"] = float((main_.groupby(["participant_id", "screen_index"]).best_pick.first() == "none").mean())
    # Bradley-Terry from best-of-3 picks: the picked model beats each of the other two on that screen
    wins = {}
    for (_, _), s in main_.groupby(["participant_id", "screen_index"]):
        w = s[s.picked_this]
        if len(w) == 1:
            for l in s[~s.picked_this].model:
                wins[(w.model.iloc[0], l)] = wins.get((w.model.iloc[0], l), 0) + 1
    bt = bradley_terry(wins, list(MODEL_NAME))
    lb["bt_strength"] = pd.Series(bt)
    R["leaderboard"] = {m: {**{k: float(v) for k, v in lb.loc[m].items()},
                            "post_asis_ci": ci["post_asis"][m], "text_exact_ci": ci["text_exact"][m]} for m in lb.index}
    R["pairwise_wins"] = {f"{i}>{j}": n for (i, j), n in wins.items()}

    # ---------- 2. the Hindi tax: matched EN/HI pairs (A-F)
    pairs = main_[main_.prompt_id.map(lambda x: P[x]["pair"] != "")].copy()
    pairs["pair"] = pairs.prompt_id.map(lambda x: P[x]["pair"]); pairs["lang"] = pairs.prompt_id.map(lambda x: P[x]["lang"])
    tax = {}
    for m in MODEL_NAME:
        s = pairs[pairs.model == m]
        g = s.groupby(["pair", "lang"]).agg(asis=("post_asis", "mean"), exact=("text_exact", "mean")).unstack()
        d_asis = (g["asis"]["EN"] - g["asis"]["HI"]); d_exact = (g["exact"]["EN"] - g["exact"]["HI"])
        bs = [d_asis.sample(len(d_asis), replace=True, random_state=int(rng.integers(1e9))).mean() for _ in range(B)]
        tax[m] = {"EN_post_asis": float(g["asis"]["EN"].mean()), "HI_post_asis": float(g["asis"]["HI"].mean()),
                  "tax_post_asis_pp": float(d_asis.mean() * 100), "tax_ci_pp": [float(np.percentile(bs, 2.5) * 100), float(np.percentile(bs, 97.5) * 100)],
                  "EN_text_exact": float(g["exact"]["EN"].mean()), "HI_text_exact": float(g["exact"]["HI"].mean()),
                  "tax_text_exact_pp": float(d_exact.mean() * 100), "pairs_where_HI_worse": int((d_asis > 0).sum()), "n_pairs": int(len(d_asis))}
    R["hindi_tax"] = tax

    # ---------- 3. difficulty ladder & per-prompt table
    main_["level"] = main_.prompt_id.map(lambda x: P[x]["level"]); main_["lang"] = main_.prompt_id.map(lambda x: P[x]["lang"])
    pp = main_.groupby(["prompt_id", "model"]).agg(post_asis=("post_asis", "mean"), text_exact=("text_exact", "mean"),
                                                    text_score=("text_score", "mean"), cult_ok=("cult_ok", "mean"),
                                                    picked=("picked_this", "mean")).reset_index()
    pp.to_csv(OUT / "per_prompt_model.csv", index=False)
    R["per_prompt"] = pp.round(3).to_dict("records")
    hi = main_[main_.lang != "EN"]
    R["by_level_hindi"] = hi.groupby(["level", "model"]).post_asis.mean().unstack().round(3).to_dict()

    # ---------- 4. prompt-level paired tests (exploratory; n = 16 prompts)
    pv = pp.pivot(index="prompt_id", columns="model", values="post_asis")
    tests = {}
    for i, j in itertools.combinations(MODEL_NAME, 2):
        diff = (pv[i] - pv[j]).dropna()
        nz = diff[diff != 0]
        tests[f"{i}_vs_{j}"] = {"mean_diff_pp": float(diff.mean() * 100), "prompts_i_better": int((diff > 0).sum()),
                                "prompts_j_better": int((diff < 0).sum()), "ties": int((diff == 0).sum()),
                                "wilcoxon_p": float(wilcoxon(nz).pvalue) if len(nz) >= 6 else None,
                                "sign_test_p": float(binomtest(int((nz > 0).sum()), len(nz)).pvalue) if len(nz) else None}
    R["paired_tests"] = tests

    # ---------- 5. reliability
    items = main_.groupby("image_id")
    R["alpha"] = {"text_ordinal": kripp_alpha([g.text_score.tolist() for _, g in items], "ordinal", [0, 1, 2, 3]),
                  "post_ordinal": kripp_alpha([g.use_score.tolist() for _, g in items], "ordinal", [0, 1, 2]),
                  "culture_ordinal": kripp_alpha([g.looks_right.map(CULT_SCORE).tolist() for _, g in items], "ordinal", [0, 1, 2])}
    rep = df[df.is_repeat]; orig = main_[main_.prompt_id == spec["consistency_repeat"]]
    m = rep.merge(orig, on=["participant_id", "image_id"], suffixes=("_r", "_o"))
    R["test_retest"] = {"n": len(m), "text_exact_agree": float((m.text_score_r == m.text_score_o).mean()) if len(m) else None,
                        "text_within1": float(((m.text_score_r - m.text_score_o).abs() <= 1).mean()) if len(m) else None,
                        "post_agree": float((m.use_score_r == m.use_score_o).mean()) if len(m) else None,
                        "same_best_pick": float(m.groupby("participant_id").apply(lambda s: (s.picked_this_r == s.picked_this_o).all()).mean()) if len(m) else None}
    # position bias in best-pick
    pos = main_[main_.picked_this].position.value_counts(normalize=True)
    R["position_bias"] = {k: float(v) for k, v in pos.items()}

    # ---------- 6. failure taxonomy
    tags = main_.assign(tag=main_.problem_tags.fillna("").str.split("|")).explode("tag")
    tags = tags[tags.tag != ""]
    if len(tags):
        tt = tags.groupby(["model", "tag"]).size().unstack(fill_value=0).div(main_.groupby("model").size(), axis=0)
        R["tags_per_rating"] = tt.fillna(0).round(3).to_dict()
    else:
        R["tags_per_rating"] = {}
    R["comments"] = main_[main_.comment.fillna("").str.len() > 0][["prompt_id", "model", "comment"]].drop_duplicates().head(40).to_dict("records")

    # ---------- 7. researcher text audit agreement (if present)
    audit_f = HERE / "researcher_audit.csv"
    if audit_f.exists():
        au = pd.read_csv(audit_f, encoding="utf-8-sig")
        maj = main_.groupby(["prompt_id", "model"]).text_score.median().round().reset_index()
        au["score"] = au.text_label.map(TEXT_SCORE)
        j = au.merge(maj, on=["prompt_id", "model"], suffixes=("_aud", "_crowd"))
        R["audit_agreement"] = {"n": len(j), "exact": float((j.score == j.text_score).mean()), "within1": float(((j.score - j.text_score).abs() <= 1).mean())}

    # ---------- figures
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    order = sorted(MODEL_NAME, key=lambda k: -lb.loc[k, "post_asis"])

    fig, axs = plt.subplots(1, 2, figsize=(9, 2.8))
    for ax, met, ttl in ((axs[0], "post_asis", "Would post as-is"), (axs[1], "text_exact", "Text exactly correct")):
        for y, mdl in enumerate(order[::-1]):
            v = lb.loc[mdl, met] * 100; lo, hi_ = (np.array(ci[met][mdl]) * 100)
            ax.plot([lo, hi_], [y, y], color="#c3c2b7", lw=2, solid_capstyle="round")
            ax.plot(v, y, "o", color=COLOR[mdl], ms=9); ax.text(v, y + 0.22, f"{v:.0f}%", ha="center", fontsize=9)
        ax.set_yticks(range(len(order))); ax.set_yticklabels([MODEL_NAME[m] for m in order[::-1]]); ax.set_xlim(0, 100)
        ax.set_title(ttl + " (% of ratings, 95% CI)", loc="left", fontsize=10); ax.grid(axis="x", color="#eee")
    if stamp: fig.suptitle(stamp, color="#b42318", fontsize=12, y=1.02)
    fig.tight_layout(); fig.savefig(OUT / "fig_leaderboard.png", dpi=200, bbox_inches="tight"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.5, 2.6))
    for y, mdl in enumerate(order[::-1]):
        en, hi_ = tax[mdl]["EN_post_asis"] * 100, tax[mdl]["HI_post_asis"] * 100
        ax.plot([hi_, en], [y, y], color="#c3c2b7", lw=3, solid_capstyle="round")
        ax.plot(en, y, "o", color=COLOR[mdl], ms=9, mfc="white", mew=2); ax.plot(hi_, y, "o", color=COLOR[mdl], ms=9)
        ax.text(max(en, hi_) + 3, y, f"−{tax[mdl]['tax_post_asis_pp']:.0f} pp" if tax[mdl]['tax_post_asis_pp'] >= 0 else f"+{-tax[mdl]['tax_post_asis_pp']:.0f} pp", va="center", fontsize=9)
    ax.set_yticks(range(len(order))); ax.set_yticklabels([MODEL_NAME[m] for m in order[::-1]]); ax.set_xlim(0, 110)
    ax.set_xlabel("% rated 'Post as-is'   (○ English twin   ● Hindi twin, 6 matched pairs)")
    ax.set_title("The Hindi tax: same poster, same model – only the language changes", loc="left", fontsize=10)
    if stamp: fig.suptitle(stamp, color="#b42318", fontsize=12, y=1.04)
    fig.tight_layout(); fig.savefig(OUT / "fig_hindi_tax.png", dpi=200, bbox_inches="tight"); plt.close(fig)

    pv_ = pp.pivot(index="prompt_id", columns="model", values="post_asis")[order] * 100
    fig, ax = plt.subplots(figsize=(5.2, 6))
    ax.imshow(pv_.values, cmap="Blues", vmin=0, vmax=100, aspect="auto")
    for (r, c), v in np.ndenumerate(pv_.values):
        ax.text(c, r, f"{v:.0f}", ha="center", va="center", fontsize=8, color="white" if v > 60 else "#0b0b0b")
    ax.set_xticks(range(len(order))); ax.set_xticklabels([MODEL_NAME[m].replace(" Flash Image", "\nFlash Image") for m in order], fontsize=8)
    ax.set_yticks(range(len(pv_))); ax.set_yticklabels([f"{i} {P[i]['lang']} · {P[i]['category'][:24]}" for i in pv_.index], fontsize=7.5)
    ax.set_title("% 'Post as-is' by prompt", loc="left", fontsize=10)
    if stamp: ax.text(0.5, -0.12, stamp, transform=ax.transAxes, ha="center", color="#b42318")
    fig.tight_layout(); fig.savefig(OUT / "fig_prompt_heatmap.png", dpi=200, bbox_inches="tight"); plt.close(fig)

    (OUT / "results.json").write_text(json.dumps(R, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: R[k] for k in ["data_label", "participants", "leaderboard", "hindi_tax", "alpha", "test_retest", "position_bias", "paired_tests"]}, indent=1, default=float, ensure_ascii=False))


if __name__ == "__main__":
    main()
