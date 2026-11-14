"""/doctor: report a pest problem with buttons, get a plan that follows the pest policy, follow it up.

Callback data (each step carries what was chosen so far):
  d:new                         pick a pot        d:p:<n>                     pot chosen
  d:s:<n>:<pos|a>               plant chosen      d:y:<n>:<pos>:<pest>        symptom chosen
  d:z:<n>:<pos>:<pest>          pest confirmed    d:v:<n>:<pos>:<pest>:<l|m|h> severity
  d:o:<n>:<pos>:<pest>:<sev>:<0|1>  open the issue (flowering no/yes)
  d:i:<id> view   d:now:<id> did it   d:later:<id> remind   d:r:<id> resolved   d:x:<id> opened by mistake
  d:u:<n>  not sure what it is
  ph:<n>   send the latest photos of a pot
"""

from __future__ import annotations

from html import escape as _escape

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Kb
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from botnik import clock, doctor, editing, photos, tasks
from botnik.pests import CONFUSABLE, CONFUSION_TEXT, PESTS, SEVERITY_HE, SYMPTOMS
from botnik.treatment import confidor_refusal
from botnik.views import plant_summary

SEV_CODE = {"l": "light", "m": "medium", "h": "heavy"}
POT_KEY = "doctor_pot"  # last pot chosen in /doctor; a photo without a caption goes there


def escape(text: str) -> str:
    return _escape(text, quote=False)


def _session(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["session_factory"]()


def _engine(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["session_factory"].kw["bind"]


async def _show(update: Update, text: str, keyboard) -> None:
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            return
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
                return
            raise
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


# --- screens (pure: session in, text + keyboard out) ---

def home_view(s, user_id: int) -> tuple[str, Kb]:
    issues = doctor.open_issues(s, user_id)
    if not issues:
        return pot_picker(s, user_id)
    lines = ["🩺 <b>בעיות פתוחות</b>", ""]
    rows = []
    for issue in issues:
        lines.append(f"#{issue.container.number} {escape(plant_summary(issue.container))}: {escape(doctor.summary_he(issue))}")
        rows.append([Btn(f"#{issue.container.number} {PESTS[issue.pest].name_he}", callback_data=f"d:i:{issue.id}")])
    rows.append([Btn("🆕 בעיה חדשה", callback_data="d:new")])
    return "\n".join(lines), Kb(rows)


def pot_picker(s, user_id: int) -> tuple[str, Kb]:
    pots = tasks.containers_in_map_order(s, user_id)
    buttons = [Btn(f"#{c.number} {plant_summary(c)}"[:30], callback_data=f"d:p:{c.number}") for c in pots]
    return "🩺 <b>באיזה עציץ יש בעיה?</b>", Kb([buttons[i : i + 2] for i in range(0, len(buttons), 2)])


def plant_picker(c) -> tuple[str, Kb]:
    rows = [[Btn((p.name_he + (f" ({p.note})" if p.note else ""))[:40], callback_data=f"d:s:{c.number}:{p.position}")]
            for p in c.plants]
    rows.append([Btn("כל העציץ", callback_data=f"d:s:{c.number}:a")])
    return f"🩺 #{c.number}: <b>על איזה צמח?</b>", Kb(rows)


def symptom_picker(number: int, pos: str) -> tuple[str, Kb]:
    rows = [[Btn(label, callback_data=f"d:y:{number}:{pos}:{key}")] for key, label in SYMPTOMS]
    rows.append([Btn("❓ לא בטוח", callback_data=f"d:u:{number}")])
    return "🔎 <b>מה רואים?</b>", Kb(rows)


def unsure_view(number: int) -> tuple[str, Kb]:
    lines = ["❓ <b>איך מזהים</b>", ""] + [f"• <b>{p.name_he}</b>: {p.signs_he}" for p in PESTS.values()]
    lines += ["", f"📷 אפשר גם לשלוח לי תמונה עם הכיתוב #{number} – היא תישמר להשוואה בהמשך."]
    return "\n".join(lines), Kb([[Btn("⬅️ חזרה לבחירה", callback_data=f"d:s:{number}:a")]])


def confusion_view(number: int, pos: str) -> tuple[str, Kb]:
    return CONFUSION_TEXT, Kb([
        [Btn("🐑 צמר דביק / חרקים – כנימה קמחית", callback_data=f"d:z:{number}:{pos}:mealybug")],
        [Btn("🌫 אבקה שנמחקת – קמחון", callback_data=f"d:z:{number}:{pos}:mildew")],
    ])


def severity_picker(number: int, pos: str, pest: str) -> tuple[str, Kb]:
    rows = [[Btn(SEVERITY_HE[SEV_CODE[code]], callback_data=f"d:v:{number}:{pos}:{pest}:{code}")] for code in "lmh"]
    return f"<b>{PESTS[pest].name_he}</b> – כמה זה חמור?", Kb(rows)


def flowering_question(number: int, pos: str, pest: str, sev: str) -> tuple[str, Kb]:
    base = f"d:o:{number}:{pos}:{pest}:{sev}"
    return "🌸 <b>הצמח פורח עכשיו?</b>\n(זה קובע אם מותר קונפידור – הוא מסוכן לדבורים)", Kb(
        [[Btn("🌸 כן, פורח", callback_data=f"{base}:1"), Btn("לא", callback_data=f"{base}:0")]]
    )


def issue_view(issue, note: str = "") -> tuple[str, Kb]:
    c = issue.container
    p = doctor.plan(issue)
    track_he = {"strong": "צמח חזק", "sensitive": "מסלול רגיש", "edible": "צמח מאכל / תבלין"}[p.track]
    who = f" · {escape(issue.plant.name_he)}" if issue.plant else ""
    lines = [f"🩺 <b>#{c.number} {escape(plant_summary(c))}</b>{who}",
             f"{PESTS[issue.pest].name_he} · {SEVERITY_HE[issue.severity].split(' –')[0]} · {track_he}", ""]
    lines += [f"ℹ️ {escape(n)}" for n in p.notes]
    lines += ["", "<b>תוכנית:</b>"]
    for i, step in enumerate(p.steps):
        mark = "▶️" if i == issue.step else ("✔️" if i < issue.step else "▫️")
        lines.append(f"{mark} {i + 1}. {escape(step.text_he)}")
    if issue.status == "resolved":
        lines += ["", "✅ נפתר."]
        return (f"{note}\n\n" if note else "") + "\n".join(lines), Kb([])
    lines += ["", f"<b>מצב:</b> {escape(doctor.summary_he(issue))}"]
    rows = [
        [Btn(f"✓ עשיתי את שלב {issue.step + 1}", callback_data=f"d:now:{issue.id}"),
         Btn("⏰ תזכיר לי", callback_data=f"d:later:{issue.id}")],
        [Btn("✅ נפתר", callback_data=f"d:r:{issue.id}"), Btn("🗑 נפתח בטעות", callback_data=f"d:x:{issue.id}")],
    ]
    return (f"{note}\n\n" if note else "") + "\n".join(lines), Kb(rows)


# --- handlers ---

async def doctor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session(context) as s:
        text, kb = home_view(s, update.effective_user.id)
    await _show(update, text, kb)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id, today = update.effective_user.id, clock.today()
    parts = query.data.split(":")
    action = parts[1]
    with _session(context) as s:
        if action == "new":
            await _show(update, *pot_picker(s, user_id))
            return
        if action in ("i", "now", "later", "r", "x"):
            issue = doctor.get(s, user_id, int(parts[2]))
            if issue is None:
                await _show(update, "הבעיה הזו כבר לא קיימת.", None)
                return
            note = ""
            if action == "now":
                _, note = doctor.do_step(s, issue, today)
            elif action == "later":
                doctor.remind_step(s, issue, today)
                when = "בסיכום הערב" if doctor.current_step(issue).evening_only else "בתדריך ובסיכום הערב"
                note = f"⏰ יופיע {when} של היום."
            elif action == "r":
                doctor.resolve(s, issue)
                note = "✅ סגרתי את הבעיה."
            elif action == "x":
                doctor.delete_issue(s, issue)
                await _show(update, "🗑 נמחק.", None)
                return
            await _show(update, *issue_view(issue, note))
            return

        number = int(parts[2])
        c = editing.find_container(s, user_id, number)
        if c is None:
            await _show(update, "העציץ לא נמצא.", None)
            return
        context.user_data[POT_KEY] = number
        if action == "p":
            view = plant_picker(c) if len(c.plants) > 1 else symptom_picker(number, str(c.plants[0].position) if c.plants else "a")
        elif action == "s":
            view = symptom_picker(number, parts[3])
        elif action == "u":
            view = unsure_view(number)
        elif action == "y":
            pos, pest = parts[3], parts[4]
            view = confusion_view(number, pos) if pest in CONFUSABLE else severity_picker(number, pos, pest)
        elif action == "z":
            view = severity_picker(number, parts[3], parts[4])
        elif action == "v":
            pos, pest, sev = parts[3], parts[4], parts[5]
            # Flowering only matters where Confidor could be used at all.
            if confidor_refusal(edible=doctor.is_edible(c), flowering=False, pest_key=pest) is None:
                view = flowering_question(number, pos, pest, sev)
            else:
                view = _open(s, c, pos, pest, sev, flowering=False)
        elif action == "o":
            view = _open(s, c, parts[3], parts[4], parts[5], flowering=parts[6] == "1")
        else:
            return
    await _show(update, *view)


def _open(s, c, pos: str, pest: str, sev: str, flowering: bool) -> tuple[str, Kb]:
    plant = None if pos == "a" else next((p for p in c.plants if p.position == int(pos)), None)
    issue, note = doctor.open_issue(s, c, plant, pest, SEV_CODE[sev], flowering)
    tip = f"📷 אפשר לשלוח עכשיו תמונה (היא תישמר לעציץ #{c.number})."
    return issue_view(issue, "\n".join(x for x in (f"🔁 {note}" if note else "", tip) if x))


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user_id = update.effective_user.id
    number = photos.container_from_caption(message.caption) or context.user_data.get(POT_KEY)
    if number is None:
        await message.reply_text("📷 לאיזה עציץ? שלח את התמונה שוב עם כיתוב כמו #21.")
        return
    with _session(context) as s:
        c = editing.find_container(s, user_id, number)
        if c is None:
            await message.reply_text(f"אין עציץ #{number}.")
            return
        file_id = message.photo[-1].file_id if message.photo else message.document.file_id
        data = bytes(await (await context.bot.get_file(file_id)).download_as_bytearray())
        issues = doctor.open_issues(s, user_id, c.id)
        photos.add(s, _engine(context), c, data, issue_id=issues[-1].id if issues else None)
    linked = f" ולבעיה הפתוחה ({PESTS[issues[-1].pest].name_he})" if issues else ""
    await message.reply_text(f"📷 נשמר לעציץ #{number}{linked}, בלי נתוני מיקום.")


async def on_photos_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ph:<n> – send the latest two photos of a pot, newest last, for comparing."""
    query = update.callback_query
    user_id = update.effective_user.id
    number = int(query.data.split(":")[1])
    with _session(context) as s:
        c = editing.find_container(s, user_id, number)
        latest = photos.latest(s, c.id) if c else []
        files = [(photos.file_for(_engine(context), p), clock.local_date(p.taken_at)) for p in reversed(latest)]
    if not files:
        await query.answer(f"אין עדיין תמונות של #{number}. שלח תמונה עם הכיתוב #{number}.", show_alert=True)
        return
    await query.answer()
    for path, day in files:
        with open(path, "rb") as f:
            await query.message.reply_photo(f, caption=f"#{number} · {day:%d.%m.%Y}")
