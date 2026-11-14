"""Question-by-question editing of a container: the logic, without Telegram.

A conversation asks a series of keys. In "complete" mode the keys come from
missing_fields() (so answering one may add others, e.g. shape -> its dimensions);
in the quick-action modes the list is fixed (status, move).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from botnik import labels as L
from botnik.missing import FIELD_ATTR, missing_fields
from botnik.models import Container, Slot

MAX_CM = 300

# Modes: "c" complete missing, "s" status (+ condition), "m" move (slot + level)
FIXED_KEYS = {"s": ["status", "condition_update"], "m": ["slot", "level"]}

CB_SKIP = "e:skip"
CB_CANCEL = "e:cancel"
CB_OTHER = "e:other"


@dataclass
class Question:
    key: str
    kind: str  # "choice" | "number" | "text"
    prompt: str
    options: list[tuple[str, str]] = field(default_factory=list)  # (value, Hebrew label)
    allow_other: bool = False  # a "something else" button that switches to typing
    per_row: int = 2
    skip_label: str = "⏭ דלג"


def _choice(table: dict[str, str], values: list[str]) -> list[tuple[str, str]]:
    return [(v, table[v]) for v in values]


SHAPES = ["round", "rectangular", "elliptical", "roundish"]
MATERIALS = ["plastic", "ceramic", "terracotta", "fabric", "metal", "wood"]
COLORS = ["white", "black", "red", "terracotta", "grey", "dark grey", "blue", "green", "brown", "pink"]
STATUSES = ["good", "watch", "needs_care", "unknown"]

DIMENSION_PROMPTS = {
    "outer.diameter": "📏 מה <b>הקוטר</b> החיצוני של הפתח למעלה, בס״מ?",
    "outer.length": "📏 מה <b>האורך</b> החיצוני, בס״מ?",
    "outer.width": "📏 מה <b>הרוחב</b> החיצוני בנקודה הרחבה, בס״מ?",
    "outer.height": "📏 מה <b>הגובה</b> של המיכל, בס״מ?",
}
NUMBER_HINT = "\nכתוב מספר, למשל 30."


def askable(key: str) -> bool:
    return key in DIMENSION_PROMPTS or key in {
        "slot", "level", "shape", "material", "color", "condition", "condition_update", "status", "outer_raw_meaning",
    }


def build_question(session: Session, c: Container, key: str) -> Question:
    if key == "slot":
        slots = session.scalars(select(Slot).where(Slot.user_id == c.user_id).order_by(Slot.id))
        current = f"\nעכשיו: {c.slot.code}" if c.slot else ""
        return Question(
            key, "choice", f"📍 איפה העציץ עומד? בחר מיקום מהמפה.{current}",
            [(s.code, f"{s.code} · {L.he(L.AREA_HE, s.area)}") for s in slots], per_row=3,
        )
    if key == "level":
        current = f"\nעכשיו: {L.he(L.LEVEL_HE, c.level)}" if c.level else ""
        return Question(key, "choice", f"↕️ באיזה גובה הוא נמצא?{current}", _choice(L.LEVEL_HE, list(L.LEVEL_HE)))
    if key == "shape":
        return Question(key, "choice", "🪣 מה צורת המיכל?", _choice(L.SHAPE_HE, SHAPES))
    if key in DIMENSION_PROMPTS:
        return Question(key, "number", DIMENSION_PROMPTS[key] + NUMBER_HINT)
    if key == "material":
        return Question(key, "choice", "🪣 ממה המיכל עשוי?", _choice(L.MATERIAL_HE, MATERIALS), allow_other=True)
    if key == "color":
        return Question(key, "choice", "🎨 מה צבע המיכל?", _choice(L.COLOR_HE, COLORS), allow_other=True, per_row=3)
    if key == "condition":
        return Question(key, "text", "🌿 איך הצמח נראה עכשיו? כתוב משפט קצר (למשל: \"עלים ירוקים, צמיחה חדשה\").")
    if key == "condition_update":
        current = f"\nעכשיו כתוב: \"{c.condition}\"" if c.condition else ""
        return Question(
            key, "text", f"🌿 רוצה לעדכן גם את התיאור? כתוב משפט קצר, או השאר כמו שהוא.{current}",
            skip_label="⏭ השאר כמו שהוא",
        )
    if key == "status":
        current = f"\nעכשיו: {L.STATUS_EMOJI[c.status]} {L.STATUS_HE[c.status]}"
        options = [(s, f"{L.STATUS_EMOJI[s]} {L.STATUS_HE[s]}") for s in STATUSES]
        return Question(key, "choice", f"🔄 מה המצב של העציץ?{current}", options)
    if key == "outer_raw_meaning":
        raw = c.outer_raw or "?"
        return Question(key, "text", f"📏 נרשם \"{raw}\". מה המשמעות? (למשל: \"קוטר 10, גובה 12\")")
    raise KeyError(key)


def question_text(c: Container, q: Question, typing_other: bool = False) -> str:
    from botnik.views import escape, plant_summary  # local import: views imports this module's callers

    header = f"✏️ <b>עציץ #{c.number}</b> – {escape(plant_summary(c))}\n\n"
    if typing_other:
        return header + "כתוב במילים:"
    return header + q.prompt


def question_keyboard(q: Question, typing_other: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if q.kind == "choice" and not typing_other:
        buttons = [InlineKeyboardButton(label, callback_data=f"e:v:{i}") for i, (_, label) in enumerate(q.options)]
        rows = [buttons[i : i + q.per_row] for i in range(0, len(buttons), q.per_row)]
        if q.allow_other:
            rows.append([InlineKeyboardButton("✍️ משהו אחר", callback_data=CB_OTHER)])
    rows.append([InlineKeyboardButton(q.skip_label, callback_data=CB_SKIP), InlineKeyboardButton("✖️ ביטול", callback_data=CB_CANCEL)])
    return InlineKeyboardMarkup(rows)


_NUMBER_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(?:ס[\"״']?מ|cm|סנטימטר)?\s*\.?\s*$", re.IGNORECASE)


def parse_number(text: str) -> float:
    """'30', '30.5', '30,5', '30 ס"מ', '30cm' -> float. Raises ValueError with a Hebrew message."""
    m = _NUMBER_RE.match(text or "")
    if not m:
        raise ValueError("לא הבנתי את המספר. כתוב רק מספר בס״מ, למשל 30.")
    value = float(m.group(1).replace(",", "."))
    if value <= 0 or value > MAX_CM:
        raise ValueError(f"המספר צריך להיות בין 1 ל־{MAX_CM} ס״מ.")
    return value


def find_container(session: Session, user_id: int, number: int) -> Container | None:
    return session.scalars(select(Container).where(Container.user_id == user_id, Container.number == number)).one_or_none()


def next_key(c: Container, mode: str, queue: list[str], skipped: list[str]) -> str | None:
    """The next key to ask, or None when done. Pops from `queue` in fixed modes."""
    if mode == "c":
        for key in missing_fields(c):
            if key not in skipped and askable(key):
                return key
        return None
    while queue:
        key = queue.pop(0)
        if askable(key):
            return key
    return None


def apply_answer(session: Session, c: Container, key: str, value: str | float) -> None:
    """Save one answer and commit."""
    if key == "slot":
        slot = session.scalars(select(Slot).where(Slot.user_id == c.user_id, Slot.code == value)).one()
        if c.slot_id != slot.id:
            c.between_slot_id = None  # "between X and Y" no longer true after a move
        c.slot_id = slot.id
    elif key == "status":
        c.status = str(value)
        for p in c.plants:  # plants started with the container's status; keep them in step
            p.status = str(value)
    elif key in ("condition", "condition_update"):
        text = str(value).strip()
        c.condition = text
        for p in c.plants:
            p.condition = text
    elif key == "outer_raw_meaning":
        c.outer_raw = f"{c.outer_raw or ''} – {str(value).strip()}".strip(" –")
        c.missing_extra = [m for m in (c.missing_extra or []) if m != "outer_raw_meaning"]
    elif key in FIELD_ATTR:
        setattr(c, FIELD_ATTR[key], float(value) if key.startswith("outer.") else str(value).strip())
    else:
        raise KeyError(key)
    session.commit()
