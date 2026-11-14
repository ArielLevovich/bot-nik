# Bot-Nik (בוט־ניק) – Telegram garden bot

A personal Telegram bot that manages a single balcony garden in Kfar Saba, Israel.
It knows every plant and container, logs care actions, and tells the owner what to do each day.
It deals ONLY with the garden: watering, fertilizing, pests, plant health, seasons, quantities.

The owner speaks Hebrew. **Talk to the owner in Hebrew.** All bot text shown in Telegram is Hebrew (RTL).
Code, identifiers, comments and commit messages are in English.

Full product spec: `docs/SPEC.md`. Garden data: `data/garden.yaml`. Current task: `docs/TASK_01.md`.

## Stack (decided – don't change without asking)
- Python 3.12
- python-telegram-bot v21+ (async), polling during development; its built-in JobQueue for scheduling
- SQLite via SQLAlchemy 2.x (single file `botnik.db`); migrate to Postgres later only if needed
- PyYAML for the seed file
- pytest for tests
- Config from `.env` (python-dotenv): `TELEGRAM_BOT_TOKEN`, `ALLOWED_USER_IDS`
- Later phases only: Open-Meteo (weather/ET0), Claude API (free text + photos), hosting on PythonAnywhere

## Hard rules
- **Allow-list**: the bot answers only Telegram user IDs in `ALLOWED_USER_IDS`. Everyone else is ignored. Check this in one place (a decorator/filter), not per handler.
- Never commit secrets. `.env` is in `.gitignore`; provide `.env.example`.
- Never store an exact address. Location is city-level only.
- Strip EXIF from photos when photos are added (later phase).
- Care calculations are deterministic Python code with unit tests. An LLM is only ever used to translate free text/photos into structured data, never to decide quantities.
- Single user for now, but every table that belongs to a user has `user_id` so more users can be added later.

## Data model (core)
`slot` (fixed map location: M1–M5, P1, N1–N3, G1–G2, K1–K2, H1, E1)
→ `container` (pot/planter; `slot_id`, optional `between_slot_id`, `level`: railing / railing_hanging / shelf / floor / hanging; shape, material, color, outer dimensions in cm, substrate, optional `sections`)
→ `plant` (`container_id`, optional `section`, Hebrew/English/Latin name, `latin_verified`, status, condition text, `pest_profile`: normal / sensitive)
→ `care_event` (plant_id or container_id, type: water / feed / prune / spray / repot / move / note, amount, product_id, timestamp, source: button / text / drip)

Also: `product` (fertilizers and pest treatments at home, with usage rules), `observation`, `task`, `issue` – add when the phase needs them, not before.

Key ideas:
- **Slots are fixed, containers move.** Moving a pot = changing its `slot_id`. Conditions belong to the slot.
- Dimensions are **outer** cm, measured with plants inside. Estimate inner volume/area in code (subtract ~1 cm wall; ellipse/roundish handled by shape). Elliptical red planters have unknown width – store null, ask the user later.
- Red railing planters straddle the railing: two planting `sections` (A/B) separated by a raised divider; plants in the same section share soil.
- `null` = not provided yet. Keep a `missing` list so the bot can ask for it.

## Development phases
0. Infrastructure – bot answers only the owner, DB exists, runs locally. ← **current**
1. Garden intake – load `garden.yaml`, browse slots/containers/plants in Telegram, edit missing fields.
2. Health & watering – care log with buttons, simple watering reminders by plant type + pot, pest triage, morning brief (05:50) and evening summary. Move to PythonAnywhere.
3. Drip system – manifolds (4 outlets, 70 cm tubes, 2.3 L/h unregulated), tube allocation, timer duration, placement suggestions.
4. Smart model – Open-Meteo ET0, pot/zone coefficients, plant tolerances, distress index (מדד מצוקה), extreme-weather alerts.
5. Extras – "ask Nik" free text, weekly report, seasonal calendar, vacation mode, time-lapse, calculators.

Do one phase at a time. Each phase ends with working code the owner actually uses, plus tests.

## Pest policy (encode as rules, not prose)
- Strong plants: hand removal / water rinse → neem oil → Confidor only if infestation returns after 2–3 neem rounds.
- Sensitive or repeatedly infested plants (e.g. the Hoya with mealybug): Confidor as the main treatment, applied as a soil drench per label, plus manual removal.
- Edible plants and herbs: never Confidor. Hand removal, rinse, neem.
- Never Confidor while the plant is flowering (bees). Neem only in the evening, not in sun or heat.
- Mealybug (כנימה קמחית, insect) ≠ powdery mildew (קמחון, fungus). Confidor does nothing against mildew or spider mites.

## Working style
- Small steps. Run the bot and tests after each step. Explain to the owner in plain Hebrew what changed and how to try it.
- Ask before adding a dependency not listed above.
