# Task 05 – "Ask Nik": talk to the bot in free text and photos (Claude API)

Goal: the owner writes to the bot the way he'd write to a gardener friend – a question, a report of what he did,
or a photo with "מה זה?" – and Nik answers in Hebrew from the real garden data, and turns reports into care-log
entries **after one confirmation tap**.

Source: spec doc "בוט־ניק – אפיון וארכיטקטורה" (Claude Docs): "שאל את ניק" (core feature), "טקסט חופשי",
"ארכיטקטורה טכנית" (Claude API with tool use, structured JSON), "ניתוח תמונה"; Task 04 step 7 (photo identification,
postponed then). CLAUDE.md hard rule: **an LLM only translates free text/photos into structured data – it never decides
quantities or treatments.** Everything the agent says about amounts, schedules or products comes from tools that call
the existing tested code (`rules.py`, `treatment.py`, `tasks.py`).

## Design in one picture

```
owner text / photo ──► agent (Claude, tool use) ──► read tools ──► garden DB + rules/treatment code
                               │
                               └──► "propose" tools ──► bot shows ONE confirmation with buttons ──► owner taps ✓ ──► DB
```
The model can read anything about the garden, but can only **propose** changes. Nothing is written without a tap.

## Steps

1. Setup (needs owner approval – see questions)
   - Dependency: the official Anthropic Python SDK (`anthropic`).
   - `ANTHROPIC_API_KEY` as a Railway variable (never in git or `.env.example` values).
   - Model from a variable `BOTNIK_MODEL`, default `claude-opus-5-5`; adaptive thinking, effort `low` for chat
     (raise only if answers are weak). Server-side refusal fallback enabled (`fallbacks: "default"`).
   - Without a key the bot works exactly as today and answers free text with a short "Nik isn't connected" note.

2. Read tools (deterministic code, unit tested)
   - `garden_overview` – areas, slots, pots, plants, statuses, missing details.
   - `pot_details(number)` – the pot card data: measurements, volume, plants, care profile, condition, sun hours.
   - `care_schedule(number)` – last / next watering and fertilizing **as computed by `rules.py`**, with the reasons.
   - `care_log(number, days)` – recent events (water, feed, treatments, moves, notes).
   - `open_issues()` and `treatment_plan(number, pest, flowering)` – **from `treatment.py`**, including exclusions
     (no Confidor on edible / flowering, not for mites or mildew).
   - `products()` – what's at home and its usage rules. `today_tasks()` – today's brief.

3. Propose tools → one confirmation message
   - `propose_care_entries([{pot, type: water|feed|note|status|move, …}])` – e.g. "השקיתי את כל המעקה וריססתי נים
     על הרוזמרין" → a list the bot renders as one message with `✓ לשמור הכל` / `✏️ לא נכון` / `✖️ ביטול`.
   - `propose_issue(pot, pest, severity)` – shows the plan from `treatment.py` with a button that opens it in `/doctor`.
   - Amounts are never taken from the model: watering uses `rules.suggested_amount_l`, products use the home list.
   - Pot references are validated (unknown number / area → the bot asks instead of guessing).

4. Chat in Telegram
   - Any free text that is not a command and not an answer to an open question goes to Nik.
   - Short memory per chat: the last 20 turns, stored in the DB (`chat_turn`), so it survives restarts;
     `/new` starts a fresh conversation. Typing indicator while Nik thinks; long answers split under Telegram's limit.
   - Hebrew, short, practical answers; says "לא בטוח" instead of inventing; marks general knowledge
     that isn't from the garden data as "להערכה" (spec: sources and reliability).

5. Photos to Nik
   - A photo with a question ("מה זה?", "למה העלים מצהיבים?") goes to Nik as an image (EXIF already stripped).
   - Nik describes what it sees and may **suggest** a pest via `propose_issue`; the owner confirms or picks another
     in `/doctor`. A photo captioned only `#21` keeps today's behavior (saved), with a button `🔎 לשאול את ניק`.

6. Safety and honesty rules (in code, not only in the prompt)
   - The system prompt states the CLAUDE.md rule and the pest policy; the tools enforce it anyway
     (`treatment_plan` never returns Confidor where it's excluded; propose tools reject unknown pots/products).
   - Refusal stop reason → a friendly "I can't help with that one" message, never a crash.
   - The garden data sent to the model has no address (city only) and no Telegram IDs.

7. Cost control
   - Every call's token usage is saved; `/settings` shows this month's estimated cost.
   - A monthly cap (owner decides, e.g. $10): when reached, Nik pauses until next month and says so;
     the rest of the bot keeps working.
   - Prompt caching for the fixed parts (system prompt, tool definitions) to cut the cost of each question.

8. Tests and wrap-up
   - Read tools return exactly what the card / rules return; propose tools validate and never write.
   - The agent loop runs in tests against a **fake client** (no network, no cost): a scripted reply that
     calls tools, a refusal, the cap being reached.
   - One optional live smoke test (a few cents), run only when the owner says so.

## Done when
- "למה העלים התחתונים של הגרניום האדום מצהיבים?" gets a Hebrew answer that uses #7's real data
  (where it stands, last watering, open issues) and marks general advice as such.
- "השקיתי את כל המעקה וריססתי נים על הרוזמרין" → one confirmation listing the waterings and the neem treatment;
  `✓ לשמור הכל` logs them and closes today's matching tasks.
- A phone photo + "מה זה?" → a description, a suggested pest, and a button into `/doctor`.
- Nik never states an amount or treatment that didn't come from a tool.
- The monthly cap pauses Nik and the rest of the bot keeps working. Tests pass.

## Questions for the owner (before starting)
1. May I add the Anthropic SDK (`anthropic`)? (CLAUDE.md requires asking for new dependencies.)
2. Model: the default is Claude Opus 5.5 (best answers). My rough estimate is a few cents per question, so
   ~10 questions a day is around $10 a month. A cheaper model (Claude Haiku 5.5) is possible – your choice.
3. Monthly spending cap for Nik: how much?
4. The API key: create it at console.anthropic.com (prepaid credit) and put it in Railway's Variables
   as `ANTHROPIC_API_KEY` yourself – don't paste it in a chat.

Not in this task: weather/ET0 (Phase 4), drip (Phase 3), weekly report, voice messages.
