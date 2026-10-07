"""Verify that a ratings CSV was produced by rate.html.

The app derives everything random from the participant's email + the app BUILD id (see template.html):
participant_id, screen order and the A/B/C position of every model. This script re-implements that PRNG
exactly and checks the file against it, plus format checks (timestamps from JS toISOString carry milliseconds).
Usage: python q1/verify_ratings.py <csv>
"""
import json, pathlib, re, sys
import pandas as pd

HERE = pathlib.Path(__file__).parent
M32 = 0xFFFFFFFF


def imul(a, b):
    r = ((a & M32) * (b & M32)) & M32
    return r - (1 << 32) if r & 0x80000000 else r


def rng(seed):
    h = 1779033703 ^ len(seed)
    h = h - (1 << 32) if h & 0x80000000 else h
    for ch in seed:
        h = imul(h ^ ord(ch), 3432918353)
        u = h & M32
        h = ((u << 13) | (u >> 19)) & M32
        h = h - (1 << 32) if h & 0x80000000 else h

    def nxt():
        nonlocal h
        u = h & M32
        h = imul(h ^ (u >> 16), 2246822507)
        u = h & M32
        h = imul(h ^ (u >> 13), 3266489909)
        u = h & M32
        h = h ^ (u >> 16)
        return (h & M32) / 4294967296
    return nxt


def shuffle(a, r):
    a = list(a)
    for i in range(len(a) - 1, 0, -1):
        j = int(r() * (i + 1)); a[i], a[j] = a[j], a[i]
    return a


def expected(email, build, spec, key):
    rev = {(v["prompt_id"], v["model"]): k for k, v in key.items()}
    r = rng(email.strip().lower() + build)
    sids = [p["id"] for p in spec["prompts"]]
    main = shuffle(sids, r)
    order = [(pid, False, shuffle([0, 1, 2], r)) for pid in main] + [(spec["consistency_repeat"], True, shuffle([0, 1, 2], r))]
    pid = "R" + str(int(rng(email.lower())() * 1e6)).zfill(6)
    rows = {}
    for idx, (p, rep, pos) in enumerate(order):
        for j, k in enumerate(pos):
            rows[(idx + 1, "ABC"[j])] = (p, rev[(p, ["gpt1", "g25", "g31"][k])])
    return pid, rows


def main(path):
    spec = json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))
    key = json.loads((HERE / "rating_app" / "key.json").read_text())
    d = pd.read_csv(path, encoding="utf-8-sig")
    iso_ms = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
    ok_all = True
    for email, s in d.groupby("email"):
        pid, exp = expected(email, str(s.build.iloc[0]), spec, key)
        match = sum(exp.get((int(r.screen_index), r.position)) == (r.prompt_id, r.image_id) for r in s.itertuples())
        checks = {
            "participant_id matches app": s.participant_id.iloc[0] == pid,
            "screen order + positions match app": match == len(s) == 51,
            "timestamps in JS format": bool(iso_ms.match(str(s.consent_ts.iloc[0]))),
        }
        ok = all(checks.values()); ok_all &= ok
        print(f"{email}: expected id {pid}, file id {s.participant_id.iloc[0]}, rows matching app layout {match}/{len(s)} -> "
              + ("CONSISTENT" if ok else "NOT FROM APP: " + ", ".join(k for k, v in checks.items() if not v)))
    print("\nVERDICT:", "file is consistent with rate.html output" if ok_all else "file was NOT produced by rate.html")


if __name__ == "__main__":
    main(sys.argv[1])
