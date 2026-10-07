"""AI-judge panel: Claude rates the same blinded screens a human participant sees.

This is NOT human data. It is a clearly-labelled AI panel used to (a) get an early read before the human study and
(b) test whether an automated judge agrees with careful human/expert labels (a key question for scaling).
Output: q1/ratings_AI/ratings_AI-<k>.csv in exactly the rate.html CSV format (so q1/analyze.py runs unchanged).

Usage: python q1/ai_judge.py [--runs 3]      (needs ANTHROPIC_API_KEY)
"""
import argparse, base64, io, json, pathlib, random, datetime, concurrent.futures as cf
from typing import Literal
import anthropic
from pydantic import BaseModel
from PIL import Image

HERE = pathlib.Path(__file__).parent
MODEL = "claude-opus-5"
spec = json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))
key = json.loads((HERE / "rating_app" / "key.json").read_text())
rev = {(v["prompt_id"], v["model"]): k for k, v in key.items()}
client = anthropic.Anthropic()

TextLabel = Literal["Exactly correct", "Small error", "Major error", "Gibberish / missing"]
LooksLabel = Literal["Looks right", "Something is a bit off", "Clearly wrong / not Indian"]
PostLabel = Literal["Post as-is", "Post after small fixes", "Would not post"]
Tag = Literal["Wrong festival / ritual items", "Not Indian-looking setting or people", "Wrong food / product",
              "Distorted objects, hands or faces", "Fake or misspelled brand / logo", "Extra unrequested text"]


class PosterRating(BaseModel):
    poster: Literal["A", "B", "C"]
    text_as_read: str  # the text the judge actually reads on the poster, transcribed letter by letter
    text_accuracy: TextLabel
    looks_right: LooksLabel
    problem_tags: list[Tag]
    would_post: PostLabel


class ScreenRating(BaseModel):
    posters: list[PosterRating]
    best_pick: Literal["A", "B", "C", "None"]
    comment: str


INSTRUCTIONS = """You are taking part in a blind evaluation as a rater. Imagine you own a small shop in a Hindi-speaking town and read Hindi fluently. You asked an AI tool to make a poster for your WhatsApp Status. Below is the exact text the shop owner asked for, followed by three posters (A, B, C) from different AI models. Model names are hidden.

For EACH poster:
1. First transcribe, letter by letter, exactly the text you see on the poster (do not correct it; copy any misspellings, missing nukta, wrong matras exactly as drawn).
2. Text accuracy, compared letter-by-letter with the requested text:
   - Exactly correct: every word, matra and number matches.
   - Small error: 1-2 letters/matras/nukta wrong, but a customer would still read it correctly.
   - Major error: wrong, missing or extra words, wrong number/price, or hard to read.
   - Gibberish / missing: fake letters that only look like Hindi, or the text is absent.
3. Looks right for this shop and occasion? (right festival items, Indian setting, real-looking food/products) plus any problem tags.
4. If it were your shop, would you post it?
Then pick the ONE poster you would post, or "None".

Shop: {business}
Requested text (must match exactly):
{lines}"""


def jpeg_b64(path):
    im = Image.open(path).convert("RGB"); im.thumbnail((1024, 1024))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=90)
    return base64.standard_b64encode(buf.getvalue()).decode()


def rate_screen(p, order, run):
    content = [{"type": "text", "text": INSTRUCTIONS.format(business=p["business"].split(",")[0], lines="\n".join(p["lines"]))}]
    for letter, m in zip("ABC", order):
        content += [{"type": "text", "text": f"Poster {letter}:"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": jpeg_b64(HERE / "images" / f"{p['id']}_{m}.png")}}]
    try:
        resp = client.messages.parse(model=MODEL, max_tokens=16000, thinking={"type": "adaptive"},
                                     messages=[{"role": "user", "content": content}], output_format=ScreenRating)
    except anthropic.APIStatusError as e:
        return p["id"], order, None, f"api error {e.status_code}"
    if resp.stop_reason == "refusal":
        return p["id"], order, None, "refusal"
    return p["id"], order, resp.parsed_output, resp.id


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", type=int, default=3); a = ap.parse_args()
    out = HERE / "ratings_AI"; out.mkdir(exist_ok=True)
    P = {p["id"]: p for p in spec["prompts"]}
    for run in range(1, a.runs + 1):
        rnd = random.Random(1000 + run)
        screens = [p["id"] for p in spec["prompts"]]; rnd.shuffle(screens); screens.append(spec["consistency_repeat"])
        jobs = [(i, pid, rnd.sample(["gpt1", "g25", "g31"], 3)) for i, pid in enumerate(screens)]
        rows, log = [], []
        with cf.ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(rate_screen, P[pid], order, run): (i, pid, order) for i, pid, order in jobs}
            for f in cf.as_completed(futs):
                i, pid, order = futs[f]
                _, _, r, rid = f.result()
                log.append({"run": run, "screen": i + 1, "prompt_id": pid, "order": order, "response_id": rid})
                if r is None:
                    continue
                by_letter = {x.poster: x for x in r.posters}
                best = "none" if r.best_pick == "None" else rev[(pid, order["ABC".index(r.best_pick)])]
                for letter, m in zip("ABC", order):
                    x = by_letter.get(letter)
                    if not x:
                        continue
                    iid = rev[(pid, m)]
                    rows.append(dict(build="AI-PANEL", participant_id=f"AI-{run}", name=f"{MODEL} (AI judge, run {run})", email="", age="",
                                     hindi_level="AI", state="", occupation="AI judge", consent=True, consent_ts="", practice_answer="",
                                     screen_index=i + 1, prompt_id=pid, is_repeat=(i == len(jobs) - 1), image_id=iid, position=letter,
                                     text_accuracy=x.text_accuracy, looks_right=x.looks_right, problem_tags="|".join(x.problem_tags),
                                     would_post=x.would_post, best_pick=best, picked_this=(best == iid), comment=(r.comment + " || read: " + x.text_as_read),
                                     seconds_on_screen=60, submitted_at=datetime.datetime.now(datetime.timezone.utc).isoformat()))
        import pandas as pd
        pd.DataFrame(rows).to_csv(out / f"ratings_AI-{run}.csv", index=False, encoding="utf-8-sig")
        (out / f"log_AI-{run}.json").write_text(json.dumps(sorted(log, key=lambda r: r["screen"]), indent=1))
        print(f"run {run}: {len(rows)} ratings, {sum(1 for l in log if not str(l['response_id']).startswith('msg'))} failed screens")


if __name__ == "__main__":
    main()
