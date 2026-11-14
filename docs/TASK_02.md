# Task 02 – Phase 1 essentials (complete the garden from Telegram)

Goal: the owner completes the garden **from Telegram**, without editing `garden.yaml` or sending measurements
to a developer. After this task the database, not the YAML, is the source of truth.
Kept short on purpose (owner chose "option B", 14.11.2026) so watering and fertilizing (Task 03) come sooner.

Source: the spec doc "בוט־ניק – אפיון וארכיטקטורה" (Claude Docs). Stack stays as in CLAUDE.md
(python-telegram-bot + JobQueue, not the aiogram/APScheduler/FastAPI listed as options in the spec).

## Steps

1. Protect the database from re-seeding
   - `python -m botnik.seed` refuses to run when the database already has containers for the owner,
     and explains why. `--reset` wipes the owner's garden data and loads the YAML again (asks "type yes" first).
   - Update the README: after the first seed, changes are made in the bot.
   - Tests: seed on a filled DB without `--reset` changes nothing; `--reset` reloads.

2. Compute `missing` instead of hand-writing it
   - One function `missing_fields(container)` returns the core fields that are still `None`:
     `slot`, `level`, `shape`, `material`, `color`, `condition`, and the dimensions the shape needs
     (round/roundish: diameter + height; rectangular/elliptical: length + width + height).
     Unknown shape → ask shape first, dimensions after.
   - Extra items that can't be derived (e.g. `outer_raw` "10 × 12" needs explaining) stay in a small
     `missing_extra` list on the container, removed when answered.
   - `/missing` and the card use this function. Tests per shape.

3. "Complete details" flow (one question at a time)
   - Card button `✏️ השלמת פרטים` (shown only when something is missing) starts a conversation
     (PTB `ConversationHandler`) that asks for each missing field in order.
   - Closed choices are buttons: level (מעקה / תלוי על המעקה / מדף / רצפה / תלוי), shape, material
     (plastic / ceramic / terracotta / fabric / metal / wood + "other" → text), color, slot (buttons of slot codes).
   - Numbers are typed: "30" or "30 ס״מ"; accept comma or dot; reject ≤ 0 or > 300 with a clear Hebrew message.
   - Every question has `⏭ דלג` (skip this field) and `✖️ ביטול` (stop, keep what was saved so far).
   - Each answer is saved immediately; at the end show the updated card with the new volume.
   - Tests: answer parsing (numbers, units, bad input), field order per shape, save + `missing` shrinks.

4. Quick actions on the card
   - `🔄 שינוי מצב`: 🟢🟡🔴⚪ buttons, then optional condition text (or skip).
   - `📍 הזזה`: choose new slot, then level. Just updates the container (the care log comes in Task 03).
   - Reuse the question screens from step 3.

5. Sun hours per area – asked in Telegram
   - Store per area: morning sun from–to, afternoon sun yes/no, for the current season (winter now;
     summer asked again in spring). Fields stay `None` until answered.
   - `/sun` walks the areas one by one with hour buttons (05–14) and `⏭ דלג` / `✖️ ביטול`;
     `/missing` adds a reminder line while any area is unanswered.
   - The container card shows its slot's area sun hours. Data only for now; calculations use it in Phase 4.

6. Tests and wrap-up
   - `pytest` passes; conversation steps tested on the pure functions (parsing, next-question logic, saving),
     not on Telegram itself.
   - The owner fills in containers 21–24 through the bot as the real-life check.

## Done when
- The owner completes containers 21–24 in Telegram and `/missing` says nothing is missing.
- The owner moves one pot and changes one status from the card, and `/garden` shows it.
- The owner answers sun hours for every area in `/sun`.
- Running `python -m botnik.seed` again does not overwrite anything.
- Tests pass.

## Decisions (owner, 14.11.2026)
- Option B: essentials only. Postponed to a later task: `/add` (new container/plant), `➕ צמח` on the card,
  `/plants`, the full "edit any field" menu, and editing plant names / Latin name / section / pest profile.
  Until then, new plants are sent to the developer in chat and added to the DB.
- Plant photos move to Phase 2 (with pest checks from photos and EXIF stripping).
- Sun hours are collected now, by the bot.
- Next priority: care information – watering and fertilizing (Task 03, Phase 2 care log and reminders).

Not in this task: photos, `/add`, `/plants`, care log, watering reminders, morning brief, weather, drip, LLM, hosting.
