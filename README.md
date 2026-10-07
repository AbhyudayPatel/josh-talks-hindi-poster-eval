# Does it spell Hindi right?

Josh Talks AI · Product Task (July 2026) · Abhyuday Patel

**Submission document:** submitted directly to Josh Talks (it contains participant names and emails, so it is not hosted here). Rebuild it with `python tools/build_submission.py`.

## Q1 · Hindi-text posters for India's local shops

A focused text-to-image eval: can AI models make a WhatsApp poster that a small Indian shop would post as-is, with the Hindi spelled exactly right? Six matched English/Hindi prompt pairs measure each model's "Hindi tax" directly.

| Path | What |
|---|---|
| `q1/prompts.json` | The 16 prompts (single source of truth) |
| `q1/generate.py` | Generation for GPT Image 1, Gemini 2.5 Flash Image, Gemini 3.1 Flash Image Preview (first output kept, every call logged) |
| `q1/images/` | All 48 generated images |
| `q1/generation_log.jsonl` | Model, exact prompt, platform, settings, request ID and timestamp for every call |
| `q1/researcher_audit.csv` | Letter-by-letter audit of every poster |
| `q1/rating_app/rate.html` | The blinded participant rating app (one file, works on a phone) |
| `q1/analyze.py` | Analysis written before any ratings were collected |
| `q1/ai_judge.py`, `q1/ratings_AI/` | AI-judge panel (Claude, clearly labelled, not human data) |
| `q1/mockups/` | Leaderboard / admin / failure explorer mockups |

## Q2 · Spotting low-quality transcribers

`q2/q2_analysis.py` reproduces every number in the document (validated against a crowd-consensus gold set found in the data). Outputs are in `q2/out/`. The provided dataset is not included in this repo because it is internal data; place `Data Check.xlsx` in the repo root to re-run.

## Rebuild the document

```
python q1/analyze.py --ratings q1/ratings --out q1/out          # human ratings, once collected
python q1/analyze.py --ratings q1/ratings_AI --out q1/out_AI    # AI-judge panel
python tools/build_submission.py                                # -> submission/Submission.pdf
```
