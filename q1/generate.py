"""Generate images for the Hindi Local-Business Poster eval.

Fairness rules (enforced here, documented in the submission):
  * identical prompt string for every model (built from prompts.json template)
  * square 1:1 output, ~1024 px, for every model
  * exactly ONE generation per prompt per model; the first successful output is kept
    (no cherry-picking). Failures/refusals are logged and retried at most twice.
  * every call is logged to generation_log.jsonl with request id + UTC timestamp

Usage:
  python generate.py --model gpt-image-1                    (needs OPENAI_API_KEY)
  python generate.py --model gemini-2.5-flash-image         (needs GEMINI_API_KEY)
  python generate.py --model gemini-3.1-flash-image-preview (needs GEMINI_API_KEY)
"""
import argparse, base64, json, os, sys, time, datetime, pathlib, urllib.request, urllib.error

HERE = pathlib.Path(__file__).parent
IMG_DIR = HERE / "images"
LOG = HERE / "generation_log.jsonl"

MODELS = {
    "gpt-image-1": {"company": "OpenAI", "name": "GPT Image 1", "short": "gpt1"},
    "gemini-2.5-flash-image": {"company": "Google", "name": "Gemini 2.5 Flash Image", "short": "g25"},
    "gemini-3.1-flash-image-preview": {"company": "Google", "name": "Gemini 3.1 Flash Image Preview", "short": "g31"},
}


def build_prompt(spec, p):
    lines = "\n".join(f'Line {i+1}: "{l}"' for i, l in enumerate(p["lines"]))
    return spec["template"].format(business=p["business"], visual=p["visual"],
                                   language_spec=p["language_spec"], lines=lines)


def gen_openai(model, prompt):
    from openai import OpenAI
    client = OpenAI()
    raw = client.images.with_raw_response.generate(
        model=model, prompt=prompt, size="1024x1024", quality="high", n=1,
        output_format="png", moderation="auto")
    resp = raw.parse()
    settings = {"endpoint": "POST https://api.openai.com/v1/images/generations", "size": "1024x1024",
                "quality": "high", "n": 1, "output_format": "png", "moderation": "auto"}
    return base64.b64decode(resp.data[0].b64_json), raw.headers.get("x-request-id"), settings, \
        {"usage": resp.usage.model_dump() if getattr(resp, "usage", None) else None}


def gen_gemini(model, prompt):
    key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "1:1"}}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    parts = data["candidates"][0]["content"]["parts"]
    img = next(p for p in parts if "inlineData" in p or "inline_data" in p)
    inline = img.get("inlineData") or img.get("inline_data")
    settings = {"endpoint": f"POST {url}", "responseModalities": ["IMAGE"], "aspectRatio": "1:1",
                "imageSize": "default (1K)"}
    return base64.b64decode(inline["data"]), data.get("responseId"), settings, \
        {"modelVersion": data.get("modelVersion"), "usage": data.get("usageMetadata")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=list(MODELS))
    ap.add_argument("--only", nargs="*", help="prompt ids to run (default: all)")
    a = ap.parse_args()
    spec = json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))
    meta = MODELS[a.model]
    IMG_DIR.mkdir(exist_ok=True)
    fn = gen_openai if a.model.startswith("gpt") else gen_gemini
    for p in spec["prompts"]:
        if a.only and p["id"] not in a.only:
            continue
        out = IMG_DIR / f"{p['id']}_{meta['short']}.png"
        if out.exists():  # never regenerate -> no cherry-picking
            print("skip (exists)", out.name); continue
        prompt = build_prompt(spec, p)
        for attempt in range(1, 4):
            ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
            rec = {"prompt_id": p["id"], "company": meta["company"], "model_name": meta["name"],
                   "model_id": a.model, "prompt": prompt, "attempt": attempt, "timestamp_utc": ts,
                   "platform": "OpenAI Image API" if fn is gen_openai else "Google Gemini API (generateContent)"}
            try:
                t0 = time.time()
                png, rid, settings, extra = fn(a.model, prompt)
                out.write_bytes(png)
                rec.update(status="ok", request_id=rid, settings=settings, latency_s=round(time.time()-t0, 1),
                           file=f"images/{out.name}", **extra)
            except Exception as e:  # refusals / API errors are data too
                msg = e.read().decode()[:500] if isinstance(e, urllib.error.HTTPError) else str(e)[:500]
                rec.update(status="error", error=msg)
            with LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(p["id"], a.model, rec["status"], rec.get("latency_s", rec.get("error", ""))[:120] if isinstance(rec.get("error"), str) else rec.get("latency_s"))
            if rec["status"] == "ok":
                break
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
