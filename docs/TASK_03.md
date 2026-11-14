# Task 03 – Phase 2 start: watering & fertilizing reminders, on a server (Railway)

Goal: every morning at 05:50 the owner gets one message with what to water and fertilize today,
marks each task with one tap, and gets a short evening summary at 19:30 — even when the PC is off.

Source: spec doc "בוט־ניק – אפיון וארכיטקטורה" (Claude Docs): "שגרה יומית", "מנוע התזמון וההתראות",
"פקודות ותפריטים", "מלאי החומרים בבית", "אפשרויות אירוח", phase 2 in "תוכנית פיתוח בשלבים".
Phase 2 uses simple, deterministic rules by plant type and pot. Weather/ET0, distress and extreme alerts are Phase 4.

Owner decisions (14.11.2026): evening summary at 19:30; hosting on Railway Hobby ($5/month).

## Steps

1. Care log
   - `care_event` table (CLAUDE.md): `container_id` (and optional `plant_id`), `type` water / feed / move / note,
     `amount_l`, `product_id`, `at` (timezone Asia/Jerusalem), `source` button / command, `user_id`.
   - Card buttons `💧 השקיתי` and `🌱 דישנתי` (feed asks which product from `product`, fertilizers only).
     Every save answers with a confirmation and a `↩️ ביטול` (undo) button.
   - `/water` – water the whole garden, an area, or one pot (buttons). `/feed` – same, plus product.
   - Moving a pot (Task 02 `📍 הזזה`) now also logs a `move` event (starts the adjustment period, step 3).
   - The card shows "last watered / last fed" (e.g. "לפני 2 ימים").

2. Care profile per plant (deterministic inputs for the rules)
   - On `plant`: `water_need` low / medium / high and `feed_group`
     (flowering / edible / herb / succulent / foliage), default `None`.
   - A small built-in catalog by Latin genus fills defaults for the 29 current plants
     (e.g. Aloe → low/succulent, Ocimum → high/edible, Cyclamen → medium/flowering).
     Unknown plants stay `None` and appear in `/missing`, asked with buttons (reuse the Task 02 question engine).
   - `/care` lists all plants with their profile so the owner can review and change it once.

3. Rules: when to water, when to fertilize (pure functions + unit tests)
   - Watering interval in days = base by `water_need` and season × pot factors, rounded, minimum 1:
     - base, winter (Oct–Mar): low 14, medium 6, high 3; summer (Apr–Sep): low 10, medium 3, high 1.
     - pot factors: volume < 3 L ×0.7; > 20 L ×1.3; terracotta/fabric ×0.8; level railing / railing_hanging /
       hanging ×0.8; unknown volume → no factor.
     - a container with several plants (shared soil) uses the thirstiest plant.
     - per-container learned adjustment in days (step 5), limited to ±50% of the interval.
   - Suggested amount ≈ 20% of the estimated soil volume, at most 10 L at once, shown as approximate ("≈ 1.2 ל׳").
   - Fertilizing by `feed_group` and season (starting values, all per the product label):
     flowering every 14 days in season, every 28 days in winter while in bloom; edible every 14 days Apr–Oct;
     herbs every 28 days Apr–Sep, none in winter; succulents every 56 days Apr–Sep only; foliage every 21 days Apr–Oct.
   - No fertilizing during the adjustment period (21 days after planting or a move) or while status is 🔴.
   - Pest policy and Confidor are NOT part of this task (Task 04).
   - The card shows "next watering / next fertilizing" with the reason in one line.

4. Starting point
   - There is no care history yet. `/water` shows a one-time question per area:
     "When did you last water here?" today / yesterday / 2–3 days ago / don't know (= due today).
     The answer creates a back-dated `water` event (source `baseline`).

5. Tasks and the morning brief (05:50)
   - `task` table: `container_id`, `type` water / feed, `due_date`, `status` open / done / postponed / not_needed,
     `reason`, timestamps, `user_id`. Generated from the rules each morning; open tasks are not duplicated.
   - JobQueue `run_daily` at the owner's brief time (default 05:50, Asia/Jerusalem): one message,
     tasks grouped by area, each row with `✓` done · `⏭` tomorrow · `✗` not needed, plus `✓ הכל בוצע`.
   - `✓` closes the task and logs a `care_event` (source button). `⏭` moves it to tomorrow.
     `✗` closes it and teaches: that container's watering interval grows by 1 day (learned adjustment).
     Reported "too dry" (step 6) shrinks it by 1 day.
   - No tasks today → a one-line "nothing to do" message (no empty checklist).
   - `/today` shows the same checklist on demand.

6. Evening summary (19:30)
   - One short message: what is still open from today (with the same buttons), what is due tomorrow,
     and one button `🥀 משהו נראה יבש` (pick a pot → logs a note, shrinks its interval, adds a water task).
   - No other messages during the day (spec notification policy).

7. Personal times – `/settings`
   - `user_settings` table: `brief_time` (05:50), `evening_time` (19:30), `timezone` (Asia/Jerusalem).
   - `/settings` changes the two times with buttons (15-minute steps); jobs are rescheduled at once.

8. Move to Railway (Hobby plan; changed from PythonAnywhere on 14.11.2026 – its always-on plan is now $10/month)
   - Railway deploys from the private GitHub repo on every push (`railway.json`: start command, 1 replica,
     restart always, no overlap between old and new deploys). Python version from `.python-version`.
   - Variables in Railway (never in git): `TELEGRAM_BOT_TOKEN`, `ALLOWED_USER_IDS`, `BOTNIK_DB_PATH=/data/botnik.db`.
   - A volume mounted at `/data` keeps the database across deploys.
   - Moving the data: the owner sends `/backup` to the local bot (or takes `botnik.db`), stops the local bot,
     then sends `/restore` + the file to the Railway bot. The bot checks the file, saves a safety copy, restores.
   - Nightly backup job at 03:00 into `/data/backups/`, keeping 14 days; `/backup` any time sends a copy to Telegram.
   - Stop the local copy for good: two copies with the same token steal each other's messages.
     README: how updates reach the server (push to GitHub → Railway redeploys).

9. Tests and wrap-up
   - Unit tests for every rule (intervals per need/season/pot, learning limits, feed groups, adjustment period,
     baseline), task generation without duplicates, button handlers with fake updates, and the daily jobs
     with a fake clock.

## Done when
- The morning brief arrives at 05:50 from Railway while the owner's PC is off.
- Tapping `✓` on a watering task logs it, and the pot's card shows "last watered: today".
- The evening summary arrives at 19:30 with what is still open.
- `/water` and `/feed` work for a whole area and for one pot, with undo.
- Tests pass.

Phase 2 exit (spec, not this task alone): two weeks with no forgotten plant, and every pest treatment logged.

Not in this task: photos and pest triage (Task 04), weather/ET0, distress index, extreme alerts (Phase 4),
drip (Phase 3), free text and LLM, weekly report.
