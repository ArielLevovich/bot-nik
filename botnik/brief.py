"""Texts and keyboards for reminders: morning brief, evening summary, /water, /feed, /care, /settings.

Callback data:
  t:d:<task>:<m|e>   done          t:p:<task>:<m|e>  tomorrow      t:n:<task>:<m|e>  not needed
  t:c:<task>:<c|l|w>:<m|e>  pest check: clean / less / worse
  t:all:<m|e>        all done (not checks)      t:dry             pick a dry pot t:dry:<n>         that pot is dry
  t:back             back to the evening summary
  w:<kind>:all | w:<kind>:a:<area> | w:<kind>:pick | w:<kind>:c:<n>   kind = w (water) or f<product id>
  b:<w|f>:<area>:<answer> | b:skip    one-time "when did you last ..." per area
  c:w:<n> c:f:<n> c:fp:<n>:<product>  card buttons     c:u:<batch>:<n>  undo (n = 0: no card)
  st:b | st:e | st:b:HHMM | st:e:HHMM   settings
"""

from __future__ import annotations

from datetime import date, time

from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Kb

from botnik import carelog, clock, doctor, rules, tasks
from botnik import labels as L
from botnik.care import FEED_GROUP_HE, WATER_NEED_HE, fertilizers
from botnik.models import Container, Issue, Product, Task, UserSettings
from botnik.pests import PESTS
from botnik.sun import area_label, areas
from botnik.views import escape, plant_summary

MAX_TASK_ROWS = 30  # Telegram keyboards get unwieldy beyond this
TYPE_EMOJI = {"water": "💧", "feed": "🌱", "check": "🔍", "treat": "🧴"}
STATUS_MARK = {"done": "✅", "not_needed": "✖️", "postponed": "⏭"}


def _area_of(c: Container) -> str:
    return c.slot.area if c.slot else L.NO_SLOT_KEY


def _task_line(session: Session, t: Task, open_ids: set[int]) -> str:
    c = t.container
    mark = "▫️" if t.id in open_ids else STATUS_MARK.get(t.status, "▫️")
    detail = ""
    if t.type == "water":
        amount = rules.suggested_amount_l(c)
        detail = f" · ≈{amount:g} ל׳" if amount else ""
    elif t.type == "feed":
        products = fertilizers(session, c.user_id)
        detail = f" · {escape(products[0].name)} לפי התווית" if products else ""
    elif t.type == "check":
        issue = session.get(Issue, t.issue_id)
        detail = f" – {escape(PESTS[issue.pest].name_he)}: איך זה נראה?" if issue else ""
    elif t.type == "treat":
        issue = session.get(Issue, t.issue_id)
        if issue:
            detail = f" – {escape(PESTS[issue.pest].name_he)}\n      {escape(doctor.current_step(issue).text_he)}"
    return f"{mark} {TYPE_EMOJI[t.type]} <b>#{c.number}</b> {escape(plant_summary(c))}{detail}"


def _grouped_lines(session: Session, items: list[Task], open_ids: set[int]) -> list[str]:
    lines, current = [], None
    for t in items:
        area = _area_of(t.container)
        if area != current:
            if current is not None:
                lines.append("")
            lines.append(f"<b>{escape(L.he(L.AREA_HE, area) if area != L.NO_SLOT_KEY else L.NO_SLOT_HE)}</b>")
            current = area
        lines.append(_task_line(session, t, open_ids))
    return lines


def _task_buttons(items: list[Task], mode: str) -> list[list[Btn]]:
    rows = []
    for t in items[:MAX_TASK_ROWS]:
        label = f"✓ {TYPE_EMOJI[t.type]} #{t.container.number}"
        if t.type == "check":
            rows.append([
                Btn(f"✅ #{t.container.number} נקי", callback_data=f"t:c:{t.id}:c:{mode}"),
                Btn("😐 פחות", callback_data=f"t:c:{t.id}:l:{mode}"),
                Btn("❌ עדיין", callback_data=f"t:c:{t.id}:w:{mode}"),
            ])
            continue
        rows.append([
            Btn(label, callback_data=f"t:d:{t.id}:{mode}"),
            Btn("⏭ מחר", callback_data=f"t:p:{t.id}:{mode}"),
            Btn("✗ לא צריך", callback_data=f"t:n:{t.id}:{mode}"),
        ])
    return rows


def _tomorrow_line(session: Session, user_id: int, today: date) -> str:
    items = tasks.tomorrow(session, user_id, today)
    if not items:
        return "מחר: אין משימות 🌿"
    parts = []
    for type in tasks.TYPES:
        nums = sorted({c.number for c, t in items if t == type})
        if nums:
            parts.append(f"{TYPE_EMOJI[type]} " + ", ".join(f"#{n}" for n in nums))
    return "מחר: " + " · ".join(parts)


def morning(session: Session, user_id: int, today: date) -> tuple[str, Kb]:
    todo = tasks.actionable(session, user_id, today, evening=False)
    done = tasks.handled_today(session, user_id, today)
    head = f"☀️ <b>בוקר טוב</b> · {clock.date_he(today)}"
    if not todo and not done:
        lines = [head, "", "אין משימות היום 🌿", "", _tomorrow_line(session, user_id, today)]
        return "\n".join(lines + _baseline_hint(session, user_id)), Kb([])
    lines = [head, ""] + _grouped_lines(session, todo + done, {t.id for t in todo})
    if len(todo) > MAX_TASK_ROWS:
        lines += ["", f"מוצגים כפתורים ל־{MAX_TASK_ROWS} הראשונות; השאר ב־/today אחרי שתסמן."]
    if not todo:
        lines += ["", "✅ הכל בוצע להיום!"]
    lines += _baseline_hint(session, user_id)
    rows = _task_buttons(todo, "m")
    if len([t for t in todo if t.type != "check"]) > 1:
        rows.append([Btn("✓ הכל בוצע", callback_data="t:all:m")])
    return "\n".join(lines), Kb(rows)


def evening(session: Session, user_id: int, today: date) -> tuple[str, Kb]:
    todo = tasks.actionable(session, user_id, today)
    lines = [f"🌙 <b>סיכום ערב</b> · {clock.date_he(today)}", ""]
    if todo:
        lines += ["נשאר פתוח:"] + _grouped_lines(session, todo, {t.id for t in todo})
    else:
        lines.append("הכל סגור להיום ✅")
    lines += ["", _tomorrow_line(session, user_id, today)]
    rows = _task_buttons(todo, "e")
    if len([t for t in todo if t.type != "check"]) > 1:
        rows.append([Btn("✓ הכל בוצע", callback_data="t:all:e")])
    rows.append([Btn("🥀 משהו נראה יבש", callback_data="t:dry")])
    return "\n".join(lines), Kb(rows)


def dry_picker(session: Session, user_id: int) -> tuple[str, Kb]:
    containers = tasks.containers_in_map_order(session, user_id)
    buttons = [Btn(f"#{c.number} {plant_summary(c)}"[:30], callback_data=f"t:dry:{c.number}") for c in containers]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([Btn("⬅️ חזרה", callback_data="t:back")])
    return "🥀 איזה עציץ נראה יבש? אשקה אותו מוקדם יותר מעכשיו.", Kb(rows)


def _baseline_hint(session: Session, user_id: int) -> list[str]:
    if carelog.areas_without_history(session, user_id, "water"):
        return ["", "💡 עוד לא סימנת מתי השקית לאחרונה בכל אזור – שלח /water כדי שהתזכורות יהיו מדויקות."]
    return []


# --- /water and /feed ---

def water_menu(session: Session, user_id: int, kind: str) -> tuple[str, Kb]:
    """kind 'w' = water, 'f<product id>' = feed with that product."""
    if kind == "w":
        title = "💧 <b>מה השקית?</b>"
    else:
        product = session.get(Product, int(kind[1:]))
        title = f"🌱 <b>מה דישנת?</b> ({escape(product.name)})"
    rows = [[Btn("🪴 כל הגינה", callback_data=f"w:{kind}:all")]]
    area_buttons = [Btn(area_label(a), callback_data=f"w:{kind}:a:{a}") for a in _areas_with_containers(session, user_id)]
    rows += [area_buttons[i : i + 2] for i in range(0, len(area_buttons), 2)]
    rows.append([Btn("עציץ אחד…", callback_data=f"w:{kind}:pick")])
    return title + "\nכל הגינה, אזור שלם או עציץ אחד:", Kb(rows)


def water_pick(session: Session, user_id: int, kind: str) -> tuple[str, Kb]:
    containers = tasks.containers_in_map_order(session, user_id)
    buttons = [Btn(f"#{c.number} {plant_summary(c)}"[:30], callback_data=f"w:{kind}:c:{c.number}") for c in containers]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return "בחר עציץ:", Kb(rows)


def feed_product_picker(session: Session, user_id: int) -> tuple[str, Kb]:
    products = fertilizers(session, user_id)
    rows = [[Btn(p.name, callback_data=f"w:f{p.id}:menu")] for p in products]
    return "🌱 באיזה דשן השתמשת?", Kb(rows)


def _areas_with_containers(session: Session, user_id: int) -> list[str]:
    present = {c.slot.area for c in tasks.containers_in_map_order(session, user_id) if c.slot}
    return [a for a in areas(session, user_id) if a in present]


def logged_message(kind: str, containers: list[Container], batch: str, number_for_card: int = 0) -> tuple[str, Kb]:
    what = "השקיה" if kind == "w" else "דישון"
    nums = ", ".join(f"#{c.number}" for c in containers)
    text = f"✅ נרשם {what} ל־{len(containers)} עציצים: {nums}" if len(containers) > 1 else f"✅ נרשם {what} ל־{nums}"
    return text, Kb([[Btn("↩️ ביטול", callback_data=f"c:u:{batch}:{number_for_card}")]])


# --- one-time starting point ---

WATER_BASELINE = [("0", "היום"), ("1", "אתמול"), ("3", "לפני 2–3 ימים"), ("x", "לא זוכר")]
FEED_BASELINE = [("3", "השבוע"), ("17", "לפני 2–3 שבועות"), ("35", "לפני יותר מחודש"), ("x", "לא זוכר / אף פעם")]


def baseline_question(session: Session, user_id: int) -> tuple[str, Kb] | None:
    """Next one-time question, or None when every area is answered."""
    for type, options, verb in (("water", WATER_BASELINE, "השקית"), ("feed", FEED_BASELINE, "דישנת")):
        left = carelog.areas_without_history(session, user_id, type)
        if left:
            area = left[0]
            code = "w" if type == "water" else "f"
            text = (
                "🧭 <b>נקודת התחלה</b> (פעם אחת)\n"
                f"מתי {verb} לאחרונה את <b>{escape(area_label(area))}</b>?\n"
                "מספיק בערך. ככה התזכורות יתחילו מהמקום הנכון."
            )
            buttons = [Btn(label, callback_data=f"b:{code}:{area}:{v}") for v, label in options]
            rows = [buttons[:2], buttons[2:], [Btn("⏭ דלג בינתיים", callback_data="b:skip")]]
            return text, Kb(rows)
    return None


# --- /care ---

def care_overview(session: Session, user_id: int) -> tuple[str, Kb]:
    lines = ["🌿 <b>פרופיל טיפול</b>", "כמה מים כל צמח צריך ואיך מדשנים אותו. אלה ערכי פתיחה – תקן מה שלא נראה לך.", ""]
    buttons = []
    for c in tasks.containers_in_map_order(session, user_id):
        parts = [
            f"{escape(p.name_he)}: {L.he(WATER_NEED_HE, p.water_need, '❓')} · {L.he(FEED_GROUP_HE, p.feed_group, '❓')}"
            for p in c.plants
        ]
        lines.append(f"<b>#{c.number}</b> " + " | ".join(parts))
        buttons.append(Btn(f"✏️ #{c.number}", callback_data=f"e:p:{c.number}"))
    rows = [buttons[i : i + 6] for i in range(0, len(buttons), 6)]
    return "\n".join(lines), Kb(rows)


# --- /settings ---

def get_settings(session: Session, user_id: int) -> UserSettings:
    row = session.get(UserSettings, user_id)
    if row is None:
        row = UserSettings(user_id=user_id, brief_time="05:50", evening_time="19:30", timezone="Asia/Jerusalem")
        session.add(row)
        session.commit()
    return row


def settings_view(session: Session, user_id: int, note: str = "") -> tuple[str, Kb]:
    s = get_settings(session, user_id)
    text = (
        (f"{note}\n\n" if note else "")
        + "⏰ <b>זמנים</b>\n"
        + f"🌅 תדריך בוקר: <b>{s.brief_time}</b>\n"
        + f"🌙 סיכום ערב: <b>{s.evening_time}</b>\n\n"
        + "בין התדריך לסיכום הבוט לא שולח הודעות."
    )
    return text, Kb([[Btn("🌅 שינוי שעת התדריך", callback_data="st:b"), Btn("🌙 שינוי שעת הסיכום", callback_data="st:e")]])


def _times(start: time, end: time) -> list[str]:
    out, minutes = [], start.hour * 60 + start.minute
    while minutes <= end.hour * 60 + end.minute:
        out.append(f"{minutes // 60:02d}:{minutes % 60:02d}")
        minutes += 15
    return out


BRIEF_TIMES = _times(time(4, 0), time(8, 0))
EVENING_TIMES = _times(time(17, 0), time(22, 0))


def time_picker(which: str) -> tuple[str, Kb]:
    options = BRIEF_TIMES if which == "b" else EVENING_TIMES
    buttons = [Btn(t, callback_data=f"st:{which}:{t.replace(':', '')}") for t in options]
    rows = [buttons[i : i + 4] for i in range(0, len(buttons), 4)]
    title = "🌅 באיזו שעה לשלוח את תדריך הבוקר?" if which == "b" else "🌙 באיזו שעה לשלוח את סיכום הערב?"
    return title, Kb(rows)
