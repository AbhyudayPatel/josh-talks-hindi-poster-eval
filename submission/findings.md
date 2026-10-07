These findings come from my letter-by-letter audit of all 48 real outputs. The participant ratings will confirm or overturn them.

<div class="card"><div class="ch"><h3>F1 · English is solved. Hindi separates the models completely</h3><span class="pill audit">MY AUDIT</span></div><div class="cb">

| | |
|---|---|
| Observation | All three models got the English text exactly right on 6 of 6 posters. On the identical Hindi versions: Gemini 3.1 Flash Image Preview 6 of 6, GPT Image 1 2 of 6, Gemini 2.5 Flash Image 0 of 6. |
| Evidence | Hindi tax on exact text: **0 pp, 67 pp and 100 pp**. Across all 10 Hindi prompts: 9, 3 and 0 exactly right. Gemini 2.5 produced 4 unreadable posters; Gemini 3.1 produced none. |
| Interpretation | The pairs share everything except the language, so this gap is pure script rendering. An English-only benchmark would score these three models as roughly equal. |
| Implication | A "make my poster" feature tested in English could ship to Hindi users with a model that cannot spell a single Hindi poster correctly. |
| Recommendation | Measure and gate launches per script. On this sample, Hindi posters should go to Gemini 3.1, with an OCR check as a safety net. |

</div></div>

<div class="card"><div class="ch"><h3>F2 · One model generation closed the gap</h3><span class="pill audit">MY AUDIT</span></div><div class="cb">

| | |
|---|---|
| Observation | Within the same company, Gemini 2.5 Flash Image → Gemini 3.1 Flash Image Preview went from 0 of 10 to 9 of 10 exactly right in Hindi, while English stayed perfect. |
| Interpretation | India-specific quality moves fast and independently of English quality. A lab that tested last year's model would wrongly conclude that Hindi posters can't ship. |
| Recommendation | Treat this as a regression suite, not a one-off study: version every leaderboard entry and re-run the frozen prompts on every model release (the admin dashboard's "model version changed" alert). |

</div></div>

<div class="card"><div class="ch"><h3>F3 · Looking great is not the same as being usable</h3><span class="pill audit">MY AUDIT</span></div><div class="cb">

| | |
|---|---|
| Observation | All 48 posters look professional, with correct festival objects and Indian settings. Yet Gemini 2.5's chemist notice reads "हर रनिवार मुफ्टि शुमार जॉच्छ / श्री मडिजल स्तोष": every word is wrong, including the day of the free health check. |
| Interpretation | A preference vote by someone who doesn't read Hindi would rate this poster highly. For the shop, it is unusable, and on a health notice it is misleading. |
| Recommendation | India-focused evals need native-script raters and a "would you post it?" question, not just "which looks better?". |

</div></div>

<div class="card"><div class="ch"><h3>F4 · Same mistake, very different consequence</h3><span class="pill audit">MY AUDIT</span></div><div class="cb">

| | |
|---|---|
| Observation | Despite "ONLY the following text", models added text nobody asked for: GPT Image 1 on 4 of 16 posters, Gemini 2.5 on 5, Gemini 3.1 on 1. |
| Evidence | In English the extra shop name was readable (GPT, P09). In Hindi it became fake words: GPT's "अगरावी गसरलातो सोरर", Gemini 2.5's "मां तारा फ्रोट बन्दार, पतना, बेहार". Gemini 3.1 printed the instruction word "WhatsApp Status" as a heading. |
| Recommendation | Measure instruction-following per script; in product, strip or OCR-check any text that wasn't requested. |

</div></div>

<div class="card"><div class="ch"><h3>F5 · Culture is not the bottleneck. Text and brands are</h3><span class="pill audit">MY AUDIT</span></div><div class="cb">

| | |
|---|---|
| Observation | All three models got the visual culture right, even for Chhath Puja: soop with thekua, sugarcane, women offering arghya at a river ghat. Gujiya and pichkari for Holi, a brass thali of mithai for Diwali. |
| Evidence | Brands appeared on 6 of 48 posters: fake ones ("AASHIRAAD", "GUPIA ATTA") and real ones (Apple, USHA). |
| Interpretation | For this use case the frontier is spelling and restraint, not cultural knowledge. Fake or real brand logos put a trademark risk on a shop owner who won't notice. |
| Recommendation | Block logos in business templates; keep "fake brand" as a rating tag (already in the app). |

</div></div>

*An exploratory note:* GPT Image 1's errors clustered in less common words (मोबाइल → मोबाल, डिलीवरी → डिलेबरी) while its densest conjuncts were perfect, which suggests memorised greetings. Gemini 2.5 failed on common and rare words alike, so this pattern is model-specific. I noticed it after seeing the outputs, so it is a hypothesis, not a finding.
