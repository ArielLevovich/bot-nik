# Task 04 – Phase 2 continued: pest check ("doctor"), treatments and photos

Goal: when something looks wrong on a plant, the owner taps `/doctor` (or `🐛` on the card), answers a few
button questions, and gets a treatment plan that follows the pest policy, uses what is at home,
is logged, and comes back as a follow-up check until the problem is gone.

Source: spec doc "בוט־ניק – אפיון וארכיטקטורה" (Claude Docs): "מזיקים ומחלות נפוצים במישור החוף",
"מלאי החומרים בבית", "הטיפול לפי חוזק הצמח", "תגובה לאירועים", phase 2 exit ("every pest treatment logged");
CLAUDE.md "Pest policy (encode as rules, not prose)".
Treatment decisions are deterministic Python with unit tests. An LLM may only turn a photo into structured
data (step 7, optional) – never choose a product or amount.

## Steps

1. Pest knowledge as data (`botnik/pests.py`)
   - The spec's table: aphids, mealybug, spider mites, whitefly, citrus leafminer, powdery mildew, root rot.
     For each: Hebrew name, kind (insect / mite / fungus / rot), signs in plain Hebrew, first-line actions,
     and which home products work on it (neem: insects, mites, mildew prevention; Confidor: sucking insects only –
     aphids, whitefly, mealybug; not mites, not mildew).
   - Symptom buttons that lead to a pest, with the two confusions asked explicitly:
     white cotton, sticky, in leaf joints = mealybug (insect) vs. white powder on the leaf surface = mildew (fungus);
     tiny dots + fine webs = spider mites.

2. Treatment policy engine (`botnik/treatment.py`, pure functions + tests)
   - Input: the plants in the container (edible/herb from `feed_group`, `pest_profile`), the pest, "flowering now?",
     the issue's history. Output: ordered steps, each with action, product (or none), timing rules, and the
     reason it was chosen or a product was excluded.
   - Rules (CLAUDE.md, encoded):
     - strong plant: hand removal / water rinse → neem → Confidor only after 2–3 neem rounds that didn't work.
     - sensitive or repeatedly infested: Confidor as the main treatment, soil drench per label, plus hand removal.
     - edible plants and herbs: never Confidor – removal, rinse, neem.
     - never Confidor while flowering (bees); neem only in the evening, not in sun or heat; test on one leaf first.
     - Confidor does nothing for mildew or spider mites; mildew: airflow, remove leaves, morning-only watering, neem as prevention.
     - root rot: stop watering, check drainage, consider repotting.
   - The same pest coming back on a plant (2nd issue within 90 days) switches it to `pest_profile = sensitive`
     automatically, with a one-line explanation.
   - Shared soil: a container with any edible/herb plant never gets a Confidor drench.

3. Issues and the `/doctor` flow
   - `issue` table: `container_id`, optional `plant_id`, `pest`, `severity` light / medium / heavy, `status` open / resolved,
     `step` (index in the plan), `flowering`, `opened_at`, `next_check`, `resolved_at`, `user_id`.
   - `/doctor` and card button `🐛 בעיה`: pick pot → (plant, if several) → symptom buttons → pest confirmed →
     severity → "flowering now?" → the plan, with the first step's buttons: `✓ עשיתי עכשיו` / `⏰ אזכיר` / `✖️ ביטול`.
   - The card shows open issues and a short history ("כנימה קמחית · שלב 2 מתוך 3 · בדיקה ב־21.11").
   - `/doctor` also lists open issues to update.

4. Follow-ups in the daily messages
   - A `check` task type: "🔍 #21 הויה – כנימה קמחית: איך זה נראה?" with `✅ נקי` (resolve) · `😐 פחות` (repeat step) ·
     `❌ עדיין / יותר` (next step). Next check 7 days after neem or a rinse, 10 days after a Confidor drench.
   - Neem tasks go to the **evening** summary only (evening-only rule); others to the morning brief.
   - Open root rot pauses watering tasks for that container until resolved (the brief says why).
   - No fertilizing while an issue is open on the container (stress).

5. Treatment log
   - `care_event` types `spray` / `drench` / `remove` / `rinse` with `product_id`; every treatment links to its issue.
   - Warnings, not silent rules: if the owner logs Confidor on a flowering or edible plant from anywhere, the bot
     refuses and explains; neem logged before 17:00 gets a reminder about sun and heat.

6. Photos (needs approval: Pillow – see questions)
   - The owner can send a photo during `/doctor`, or any photo with the caption `#21`; it is saved on the Railway volume
     (`/data/photos/<container>/<date>-<id>.jpg`) with EXIF removed (location!) and resized to max 1600 px.
   - `photo` table: `container_id`, optional `plant_id` and `issue_id`, file path, taken date.
   - Card button `📷 תמונות` sends the latest photo and the one before it, for comparing.
   - `/backup` stays the database only; photos are covered by Railway's volume backups.

7. Optional – photo identification with the Claude API (only if the owner approves cost and a key)
   - A photo during `/doctor` is sent to Claude with a tool schema that returns `{pest, confidence, signs_seen}` only.
   - The bot shows it as a suggestion ("נראה כמו כנימה קמחית – נכון?") and the owner confirms with a button;
     the plan still comes from step 2. Key in Railway variables (`ANTHROPIC_API_KEY`), never in git.

8. Tests and wrap-up
   - Policy table tests: every pest × strong / sensitive / edible × flowering / not; escalation; auto-sensitive;
     shared soil; Confidor never for mildew/mites/edible/flowering.
   - Flow tests with fake updates for `/doctor`, check buttons, evening neem task, root rot pause.
   - Real check: the Hoya (#21) mealybug.

## Done when
- `/doctor` on the Hoya (#21) with mealybug gives: hand removal + Confidor soil drench (sensitive profile), unless it is flowering.
- The same flow on rosemary (#11) gives removal / rinse → neem in the evening, and no Confidor.
- A follow-up check appears in the brief on the right day, and `❌ עדיין` moves to the next step.
- Every treatment is logged and visible on the card.
- Tests pass.

## Owner decisions (14.11.2026)
- Pillow approved.
- Step 7 (Claude photo identification) postponed – not built in this task.

Not in this task: weather/ET0, distress index, extreme alerts (Phase 4), drip (Phase 3), free-text "ask Nik", weekly report.
