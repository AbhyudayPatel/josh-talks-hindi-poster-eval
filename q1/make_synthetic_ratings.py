"""PIPELINE TEST ONLY. Generates fake ratings in the exact rate.html CSV format so analyze.py can be
tested end-to-end before real participants exist. Output goes to ratings_SYNTHETIC/ (never ratings/),
and analyze.py must be run with --synthetic-label so every figure is stamped ILLUSTRATIVE.
These numbers are random and MUST NOT appear in the submission as findings."""
import json, pathlib, random
import pandas as pd

HERE = pathlib.Path(__file__).parent
OUT = HERE / "ratings_SYNTHETIC"; OUT.mkdir(exist_ok=True)
spec = json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))
key = json.loads((HERE / "rating_app" / "key.json").read_text())
rev = {(v["prompt_id"], v["model"]): k for k, v in key.items()}
TEXT = ["Exactly correct", "Small error", "Major error", "Gibberish / missing"]
USE = ["Post as-is", "Post after small fixes", "Would not post"]
CULT = ["Looks right", "Something is a bit off", "Clearly wrong / not Indian"]
random.seed(1)
for r in range(9):
    rows, pid = [], f"SYN{r:03d}"
    order = [p["id"] for p in spec["prompts"]]; random.shuffle(order); order.append(spec["consistency_repeat"])
    for si, pid_ in enumerate(order):
        ims = [rev[(pid_, m)] for m in ["gpt1", "g25", "g31"]]; random.shuffle(ims)
        best = random.choice(ims + ["none"])
        for j, iid in enumerate(ims):
            t = random.choice(TEXT)
            rows.append(dict(build="SYNTH", participant_id=pid, name=f"Synthetic {r}", email=f"syn{r}@example.invalid", age=25 + r,
                             hindi_level="Fluent reader", state="", occupation="", consent=True, consent_ts="", practice_answer="Small error",
                             screen_index=si + 1, prompt_id=pid_, is_repeat=si == len(order) - 1, image_id=iid, position="ABC"[j],
                             text_accuracy=t, looks_right=random.choice(CULT), problem_tags="", would_post=USE[min(2, TEXT.index(t))] if random.random() < .7 else random.choice(USE),
                             best_pick=best, picked_this=best == iid, comment="", seconds_on_screen=random.randint(30, 120), submitted_at=""))
    pd.DataFrame(rows).to_csv(OUT / f"ratings_{pid}.csv", index=False, encoding="utf-8-sig")
print("synthetic ratings written to", OUT)
