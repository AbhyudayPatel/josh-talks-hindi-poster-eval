# Finishing the submission (about 1 evening + participants' time)

Everything rebuilds with one command: `python tools/build_submission.py` → `submission/Submission.pdf` (upload this file).
The build prints what is still unfilled. Never edit numbers by hand. They come from the data files.

1. **Generate the Gemini images.** Your key works, but Google gives image models no free API quota.
   - **Option A (fast):** enable billing on the key at https://aistudio.google.com/apikey, then run the two commands below (about $2).
   - **Option B (free):** open `q1/prompt_sheet.html`, generate each prompt once in the AI Studio web app (aspect 1:1), save as
     `q1/manual/g25/P01.png` etc., add one screenshot per model to `q1/manual/screens/`, then run `python q1/import_manual.py`.
   ```
   set GEMINI_API_KEY=...            (PowerShell: $env:GEMINI_API_KEY="...")
   python q1/generate.py --model gemini-2.5-flash-image
   python q1/generate.py --model gemini-3.1-flash-image-preview
   ```
   If the preview ID has been retired, use the ID listed in Google's docs and record it. Screenshot your AI Studio /
   OpenAI usage pages as extra proof and drop them in `submission/assets/`.
2. **Refresh**: `python tools/refresh_shots.py`. **Audit the Gemini images**: add 32 rows to `q1/researcher_audit.csv` (same format).
3. **Build the participant app**: `python q1/build_rating_app.py` → `q1/rating_app/rate.html` (one file; share it on WhatsApp or by email).
   Optional auto-collection: deploy `q1/rating_app/apps_script.gs`, then rebuild with `--endpoint <URL>`.
4. **Run 8-10 Hindi-reading adults** (~20 min each). Put every returned CSV in `q1/ratings/`.
5. **Analyse**: `python q1/analyze.py` → `q1/out/results.json` + figures (they flow into §2.9.2 automatically).
6. **Write the findings** from the real results: create `submission/findings.md` (replaces the audit-only §2.10) and
   `submission/reflection_learned.md`. Update the one-page "Key findings" bullets and the video findings line in
   `tools/build_submission.py` (search for `[UPDATE`).
7. **Fill `submission/config.json`** (name, email, video link, materials link), record the ≤2-min video from §5, rebuild.

Do NOT put anything from `q1/ratings_SYNTHETIC/` or `q1/out_SYNTHETIC/` in the submission. That data is fake, used only to test the pipeline.
