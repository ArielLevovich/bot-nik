"""The pest policy (CLAUDE.md) as code: which treatment steps, in which order, and why.

Pure functions, no database. Every exclusion of a product comes with a reason the owner sees.

Tracks:
- strong:    hand removal / rinse -> neem (up to 3 rounds) -> Confidor only if it keeps coming back
- sensitive: Confidor soil drench + hand removal as the main treatment (e.g. the Hoya with mealybug)
- edible:    edible plants and herbs, shared soil included: never Confidor
Never Confidor while flowering (bees). Neem only in the evening. Confidor does nothing for mites or mildew.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from botnik.pests import PESTS

EDIBLE_GROUPS = ("edible", "herb")


@dataclass(frozen=True)
class Step:
    action: str  # remove / rinse / neem / confidor / leaves / airflow / stop_water / repot / monitor / nursery
    text_he: str
    product: str | None = None  # "neem" / "confidor"
    evening_only: bool = False
    check_days: int = 7
    event_type: str = "note"  # care_event type when done: spray / drench / remove / rinse / note


@dataclass
class Plan:
    track: str
    steps: list[Step]
    notes: list[str] = field(default_factory=list)


REMOVE = Step("remove", "הסרה ידנית של המושבות (מקלון עם אלכוהול) ושטיפה חזקה במים", event_type="remove")
NEEM = Step(
    "neem", "ריסוס שמן נים – בערב בלבד, לא בשמש ולא בחום; קודם לבדוק על עלה אחד", product="neem",
    evening_only=True, check_days=7, event_type="spray",
)
CONFIDOR = Step(
    "confidor", "קונפידור בהשקיה למצע, לפי המינון בתווית, יחד עם הסרה ידנית של מה שרואים", product="confidor",
    check_days=10, event_type="drench",
)
MITES_RINSE = Step("rinse", "שטיפת הצד התחתון של העלים במים והגברת לחות סביב הצמח", event_type="rinse")
LEAVES = Step("leaves", "הסרת העלים הפגועים ומעקב אחרי עלים חדשים", event_type="remove")
MILDEW_FIRST = Step(
    "airflow", "הסרת העלים הנגועים, הרחקה מעציצים צפופים לאוורור, והשקיה בבוקר בלבד", event_type="remove",
)
NURSERY_MILDEW = Step("nursery", "אין בבית חומר מתאים לקמחון מתקדם – כדאי לקנות תכשיר נגד קמחון במשתלה")
STOP_WATER = Step(
    "stop_water", "להפסיק להשקות עד שהמצע מתייבש, ולבדוק שחורי הניקוז פתוחים ושאין מים עומדים בתחתית",
    check_days=5,
)
REPOT = Step("repot", "להוציא מהעציץ, לחתוך שורשים חומים ורכים, ולשתול במצע חדש ויבש עם ניקוז טוב", check_days=7)
NURSERY = Step("nursery", "השלבים שבבית נגמרו – כדאי להראות לאגרונום או במשתלה (עם תמונה)")


def plan_for(pest_key: str, *, edible: bool, sensitive: bool, flowering: bool) -> Plan:
    pest = PESTS[pest_key]
    notes: list[str] = []
    track = "edible" if edible else ("sensitive" if sensitive else "strong")

    if pest.key == "root_rot":
        return Plan(track, [STOP_WATER, REPOT, NURSERY], ["תזכורות ההשקיה לעציץ הזה מושהות עד שזה נפתר."])
    if pest.key == "leafminer":
        return Plan(track, [LEAVES, LEAVES, NURSERY], ["אין צורך בריסוס – מסירים עלים ועוקבים אחרי גל הצמיחה."])
    if pest.key == "mildew":
        notes.append("קמחון הוא פטרייה – קונפידור לא משפיע עליו.")
        return Plan(track, [MILDEW_FIRST, NEEM, NURSERY_MILDEW], notes)
    if pest.key == "spider_mites":
        notes.append("אקריות אינן חרקים – קונפידור לא עובד עליהן.")
        return Plan(track, [MITES_RINSE, NEEM, NEEM, NURSERY], notes)

    # Sucking insects: mealybug, aphids, whitefly.
    confidor_allowed = pest.confidor_ok and not edible and not flowering
    if edible:
        notes.append("צמח מאכל או תבלין (או אדמה משותפת איתו) – בלי קונפידור.")
    if flowering and pest.confidor_ok and not edible:
        notes.append("פורח עכשיו – בלי קונפידור (מסוכן לדבורים). אחרי הפריחה אפשר לחזור אליו.")

    if track == "sensitive" and confidor_allowed:
        notes.append("מסלול רגיש – נים לבד לא מספיק לו, ולכן קונפידור הוא הטיפול העיקרי.")
        return Plan(track, [CONFIDOR, REMOVE, CONFIDOR, NURSERY], notes)
    steps = [REMOVE, NEEM, NEEM, NEEM]
    if confidor_allowed:
        notes.append("קונפידור רק אם זה חוזר אחרי 2–3 סבבי נים.")
        steps.append(CONFIDOR)
    steps.append(NURSERY)
    return Plan(track, steps, notes)


def start_step(plan: Plan, severity: str) -> int:
    """Heavy infestation on a strong plant: skip the removal-only step and go straight to neem."""
    if severity == "heavy" and plan.track == "strong" and plan.steps[0].action == "remove" and len(plan.steps) > 1:
        return 1
    return 0


def confidor_refusal(*, edible: bool, flowering: bool, pest_key: str) -> str | None:
    """Why Confidor must not be used here, or None if it may."""
    if edible:
        return "לא משתמשים בקונפידור על צמחי מאכל ותבלינים, וגם לא באדמה משותפת איתם."
    if flowering:
        return "לא משתמשים בקונפידור בזמן פריחה – מסוכן לדבורים."
    if not PESTS[pest_key].confidor_ok:
        return f"קונפידור לא עובד על {PESTS[pest_key].name_he}."
    return None
