"""Build the single-file, blinded participant rating app.

* Every image gets an opaque random id (e.g. 'i7f3a9c'); the id->model key is written to
  rating_app/key.json and is NEVER embedded in the participant file (blinding).
* Images are re-encoded as 900 px JPEG (q=88) and embedded as base64 so the app is one file
  that can be shared over WhatsApp/email and opened offline on a phone.
* Usage:  python build_rating_app.py [--endpoint URL] [--allow-missing]
"""
import argparse, base64, io, json, pathlib, secrets, datetime
from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).parent
APP = HERE / "rating_app"
MODELS = ["gpt1", "g25", "g31"]


def placeholder(pid, m):
    im = Image.new("RGB", (900, 900), (235, 233, 228)); d = ImageDraw.Draw(im)
    d.text((40, 430), f"PENDING GENERATION  {pid} / {m}", fill=(90, 90, 90))
    return im


def b64(im):
    im = im.convert("RGB"); im.thumbnail((900, 900))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=88, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--endpoint", default=""); ap.add_argument("--allow-missing", action="store_true")
    a = ap.parse_args()
    spec = json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))
    keyf = APP / "key.json"
    key = json.loads(keyf.read_text()) if keyf.exists() else {}
    rev = {(v["prompt_id"], v["model"]): k for k, v in key.items()}
    screens, missing = [], []
    for p in spec["prompts"]:
        imgs = []
        for m in MODELS:
            f = HERE / "images" / f"{p['id']}_{m}.png"
            if (p["id"], m) not in rev:
                iid = "i" + secrets.token_hex(3); key[iid] = {"prompt_id": p["id"], "model": m}; rev[(p["id"], m)] = iid
            if f.exists():
                src = b64(Image.open(f))
            else:
                missing.append(f.name); src = b64(placeholder(p["id"], m))
            imgs.append({"iid": rev[(p["id"], m)], "src": src})
        screens.append({"sid": "s" + p["id"], "prompt_id": p["id"], "business": p["business"].split(",")[0],
                        "lines": p["lines"], "lang": p["lang"], "images": imgs})
    if missing and not a.allow_missing:
        raise SystemExit(f"{len(missing)} images missing (e.g. {missing[:3]}). Generate them or pass --allow-missing for a preview build.")
    keyf.write_text(json.dumps(key, indent=1))
    build = ("PREVIEW-" if missing else "") + datetime.datetime.now().strftime("%Y%m%d%H%M")
    html = (APP / "template.html").read_text(encoding="utf-8")
    html = html.replace("__SCREENS__", json.dumps(screens, ensure_ascii=False)).replace("__REPEAT__", spec["consistency_repeat"]) \
               .replace("__ENDPOINT__", a.endpoint).replace("__BUILD__", build)
    out = APP / ("rate_PREVIEW.html" if missing else "rate.html")
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB), build={build}, missing={len(missing)}")


if __name__ == "__main__":
    main()
