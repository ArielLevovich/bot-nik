# Task 02 – Finish Phase 1 (garden intake from Telegram)

Goal: the owner completes and maintains the garden **from Telegram**, without editing `garden.yaml`
or sending measurements to a developer. After this task the database, not the YAML, is the source of truth.

Phase 1 exit criterion (spec): every plant is registered and assigned to a container and a slot.

Source: the spec doc "בוט־ניק – אפיון וארכיטקטורה" (Claude Docs), sections "מודל העציץ", "מפת מיקומים",
"שלב 3: עציצים וצמחים" and "תוכנית פיתוח בשלבים". Stack stays as in CLAUDE.md (python-telegram-bot + JobQueue,
not the aiogram/APScheduler/FastAPI listed as options in the spec).

## Steps

1. Protect the database from re-seeding
   - `python -m botnik.seed` refuses to run when the database already has containers for the owner,
     and explains why. `--reset` wipes the owner's garden data and loads the YAML again (asks "type yes" first).
   - Update the README: after the first seed, changes are made in the bot.
   - Tests: seed on a filled DB without `--reset` changes nothing.

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

4. Edit any field, not only missing ones
   - Card button `✏️ עריכה` → list of editable fields → same question screens as step 3.
   - Quick actions on the card: `🔄 שינוי מצב` (🟢🟡🔴⚪ buttons, then optional condition text),
     `📍 הזזה` (choose new slot + level; moving keeps history for later phases – log a `move` care_event
     only if `care_event` exists by then, otherwise just update).
   - Plant level: edit names, `section` (A / B / center), Latin name + `latin_verified`, pest profile.

5. Add a new container and plant – `/add`
   - Questions: slot → level → shape → dimensions → material → color → plant Hebrew name
     (+ optional English/Latin) → section if the container has sections → status.
   - Skippable fields simply stay `None` and show up in `/missing`.
   - "Add another plant to this container?" at the end. Container number = next free number.
   - Also a card button `➕ צמח` to add a plant to an existing container.

6. Plant list – `/plants`
   - Plants grouped by area (spec command), each opens the plant's container card.
   - Register the new commands in the Telegram menu.

7. Tests and wrap-up
   - `pytest` passes; conversation steps tested on the pure functions (parsing, next-question logic, saving),
     not on Telegram itself.
   - The owner fills in containers 21–24 through the bot as the real-life check.

## Done when
- The owner completes containers 21–24 in Telegram and `/missing` says nothing is missing.
- The owner moves one pot to another slot and changes one status from the card, and `/garden` shows it.
- The owner adds one new plant with `/add` and sees it in `/garden` and `/plants`.
- Running `python -m botnik.seed` again does not overwrite anything.
- Tests pass.

## Open questions for the owner (ask before or during the task)
- Photos per plant: the spec's Phase 1 says "every plant with a photo". Saving photos needs EXIF stripping,
  which needs a new dependency (Pillow). Do it in this task, or leave photos for Phase 2 (pest checks from photos)?
- Sun hours per area (spec "שלב 2: אזורים" table is empty): record them now (simple buttons per area:
  morning from–to, afternoon yes/no), or wait for Phase 4 where they are used?

Not in this task: care log, watering reminders, morning brief, weather, drip, LLM, hosting.
