"""Build the Hebrew texts and inline keyboards the bot shows.

Pure functions over the database (no Telegram calls), so they are easy to test.
Texts use Telegram HTML; every value from the database is escaped.
"""

from __future__ import annotations

from collections import Counter
from html import escape as _html_escape

from sqlalchemy import select
from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from botnik import labels as L
from botnik import carelog, clock, doctor, photos, rules, sun
from botnik.pests import PESTS
from botnik.care import FEED_GROUP_HE, WATER_NEED_HE
from botnik.editing import askable
from botnik.missing import missing_fields, missing_label
from botnik.models import Container, Slot
from botnik.volume import estimate_container

# Callback data (max 64 bytes):  g:home | g:a:<area> | g:m | g:c:<number>:<back>
#   <back> is "a" (back to the container's area) or "m" (back to /missing).
CB_HOME = "g:home"
CB_MISSING = "g:m"

START_TEXT = (
    "שלום! אני <b>בוט־ניק</b> 🌱\n"
    "אני מכיר כל עציץ וכל צמח במרפסת, ובהמשך אזכיר לך מה לעשות בכל יום.\n\n"
    "מה אפשר כבר עכשיו:\n"
    "/garden – כל הגינה לפי אזורים ומיקומים\n"
    "/missing – עציצים שחסרים להם פרטים\n"
    "/sun – שעות שמש לפי אזור\n\n"
    "טיפול ותזכורות:\n"
    "/today – מה לעשות היום (מגיע גם לבד כל בוקר)\n"
    "/water – רישום השקיה: כל הגינה, אזור או עציץ\n"
    "/feed – רישום דישון\n"
    "/care – כמה מים ואיזה דישון כל צמח צריך\n"
    "/doctor – משהו לא בסדר בצמח? (מזיקים ומחלות)\n"
    "📷 תמונה עם הכיתוב #21 נשמרת לעציץ 21\n"
    "/settings – שעות התדריך והסיכום\n"
    "/myid – מספר המשתמש שלך בטלגרם"
)


def escape(text: str) -> str:
    """Escape <, > and & for Telegram HTML; quotes can stay as they are."""
    return _html_escape(text, quote=False)


def _num(x: float | None) -> str:
    if x is None:
        return "?"
    return f"{x:g}"


def plant_summary(container: Container) -> str:
    """'רקפת ×3' / 'מנתור, לא מזוהה'."""
    counts = Counter(p.name_he for p in container.plants)
    parts = [name if n == 1 else f"{name} ×{n}" for name, n in counts.items()]
    return ", ".join(parts) or "ריק"


def container_line(c: Container) -> str:
    between = f" (בין {c.slot.code} ל־{c.between_slot.code})" if c.slot and c.between_slot else ""
    return f"{L.STATUS_EMOJI.get(c.status, '⚪')} <b>#{c.number}</b> {escape(plant_summary(c))}{between}"


def _button_label(c: Container) -> str:
    label = f"{L.STATUS_EMOJI.get(c.status, '⚪')} #{c.number} {plant_summary(c)}"
    return label if len(label) <= 32 else label[:31] + "…"


def _container_buttons(containers: list[Container], back: str) -> list[list[InlineKeyboardButton]]:
    buttons = [InlineKeyboardButton(_button_label(c), callback_data=f"g:c:{c.number}:{back}") for c in containers]
    return [buttons[i : i + 2] for i in range(0, len(buttons), 2)]


def _slots(session: Session, user_id: int) -> list[Slot]:
    return list(session.scalars(select(Slot).where(Slot.user_id == user_id).order_by(Slot.id)))


def _unplaced(session: Session, user_id: int) -> list[Container]:
    return list(
        session.scalars(
            select(Container)
            .where(Container.user_id == user_id, Container.slot_id.is_(None))
            .order_by(Container.number)
        )
    )


def _areas(session: Session, user_id: int) -> dict[str, list[Slot]]:
    """Areas in map order, each with its slots in map order."""
    areas: dict[str, list[Slot]] = {}
    for slot in _slots(session, user_id):
        areas.setdefault(slot.area, []).append(slot)
    return areas


def garden_overview(session: Session, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    areas = _areas(session, user_id)
    unplaced = _unplaced(session, user_id)
    if not areas and not unplaced:
        return "הגינה עדיין ריקה. צריך להריץ את טעינת הנתונים (seed).", InlineKeyboardMarkup([])

    lines = ["🪴 <b>הגינה</b>", ""]
    total = 0
    buttons = []
    for area, slots in areas.items():
        containers = [c for s in slots for c in s.containers]
        total += len(containers)
        lines.append(f"<b>{escape(L.he(L.AREA_HE, area))}</b>")
        for slot in slots:
            if not slot.containers:
                lines.append(f"  {slot.code}: {'פנוי' if slot.free else 'ריק'}")
            for c in slot.containers:
                lines.append(f"  {slot.code} · {container_line(c)}")
        lines.append("")
        if containers:
            buttons.append(
                InlineKeyboardButton(f"{L.he(L.AREA_HE, area)} ({len(containers)})", callback_data=f"g:a:{area}")
            )
    if unplaced:
        total += len(unplaced)
        lines.append(f"<b>{L.NO_SLOT_HE}</b>")
        lines += [f"  {container_line(c)}" for c in unplaced]
        lines.append("")
        buttons.append(InlineKeyboardButton(f"{L.NO_SLOT_HE} ({len(unplaced)})", callback_data=f"g:a:{L.NO_SLOT_KEY}"))

    lines.append(f"סה״כ {total} מיכלים. 🟢 טוב · 🟡 במעקב · 🔴 צריך טיפול · ⚪ לא ידוע")
    lines.append("לבחירת עציץ – בחר אזור:")
    keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


def area_view(session: Session, user_id: int, area: str) -> tuple[str, InlineKeyboardMarkup]:
    if area == L.NO_SLOT_KEY:
        title, containers = L.NO_SLOT_HE, _unplaced(session, user_id)
        lines = [f"<b>{title}</b>", ""] + [container_line(c) for c in containers]
    else:
        slots = _areas(session, user_id).get(area, [])
        title = L.he(L.AREA_HE, area)
        lines = [f"<b>{escape(title)}</b>", ""]
        containers = []
        for slot in slots:
            note = f" – {escape(slot.note)}" if slot.note else ""
            lines.append(f"<b>{slot.code}</b>{note}")
            if not slot.containers:
                lines.append("  (פנוי)" if slot.free else "  (ריק)")
            for c in slot.containers:
                lines.append(f"  {container_line(c)}")
                containers.append(c)
    lines += ["", "בחר עציץ לכרטיס המלא:"]
    keyboard = _container_buttons(containers, "a")
    keyboard.append([InlineKeyboardButton("⬅️ לכל הגינה", callback_data=CB_HOME)])
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


def _dimensions(c: Container) -> str | None:
    if c.shape in ("round", "roundish") or c.outer_diameter_cm is not None:
        if c.outer_diameter_cm is None and c.outer_height_cm is None:
            return None
        return f"קוטר {_num(c.outer_diameter_cm)} × גובה {_num(c.outer_height_cm)} ס״מ"
    if c.outer_length_cm is None and c.outer_width_cm is None and c.outer_height_cm is None:
        return None
    return (
        f"אורך {_num(c.outer_length_cm)} × רוחב {_num(c.outer_width_cm)} × "
        f"גובה {_num(c.outer_height_cm)} ס״מ"
    )


def care_lines(session: Session, c: Container, today) -> list[str]:
    """Last/next watering and fertilizing for the card."""
    last_w = carelog.last_date(session, c.id, "water")
    last_f = carelog.last_date(session, c.id, "feed")
    last_m = carelog.last_date(session, c.id, "move")
    due_w, plan_w = rules.next_water(c, last_w, today)
    pests = {i.pest for i in doctor.open_issues(session, c.user_id, c.id)}
    lines = []
    if "root_rot" in pests:
        lines.append(f"💧 <b>השקיה:</b> אחרונה {clock.ago_he(last_w, today)} · <b>מושהית</b> – עובש שורשים")
    elif plan_w is None:
        lines.append(f"💧 <b>השקיה:</b> אחרונה {clock.ago_he(last_w, today)} · חסר פרופיל טיפול לצמחים")
    else:
        amount = rules.suggested_amount_l(c)
        amount_txt = f" · ≈{amount:g} ל׳" if amount else ""
        lines.append(
            f"💧 <b>השקיה:</b> אחרונה {clock.ago_he(last_w, today)} · הבאה {clock.when_he(due_w, today)}{amount_txt}"
        )
        lines.append(f"   כל {plan_w.days} ימים: {escape(plan_w.reason)}")
    due_f, plan_f = rules.next_feed(c, last_f, today, last_m)
    if pests:
        due_f, plan_f = None, rules.Plan(None, "לא מדשנים כשיש בעיה פתוחה")
    nxt = clock.when_he(due_f, today) if due_f else escape(plan_f.reason)
    lines.append(f"🌱 <b>דישון:</b> אחרון {clock.ago_he(last_f, today)} · הבא {nxt}")
    if due_f and plan_f.reason.startswith("תקופת"):
        lines.append(f"   {escape(plan_f.reason)}")
    return lines


def container_card(
    session: Session, user_id: int, number: int, back: str = "a", top_rows: list | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    c = session.scalars(select(Container).where(Container.user_id == user_id, Container.number == number)).one_or_none()
    if c is None:
        return f"לא מצאתי עציץ #{number}.", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ לכל הגינה", callback_data=CB_HOME)]])

    lines = [f"{L.STATUS_EMOJI.get(c.status, '⚪')} <b>עציץ #{c.number}</b> – {escape(plant_summary(c))}", ""]

    if c.slot:
        place = f"{c.slot.code} ({escape(L.he(L.AREA_HE, c.slot.area))})"
        if c.between_slot:
            place += f", בין {c.slot.code} ל־{c.between_slot.code}"
    else:
        place = "לא ידוע"
    lines.append(f"📍 <b>מיקום:</b> {place}")
    lines.append(f"↕️ <b>הצבה:</b> {escape(L.he(L.LEVEL_HE, c.level, 'לא ידוע'))}")
    if c.stand_height_cm is not None:
        lines.append(f"   על מעמד בגובה {_num(c.stand_height_cm)} ס״מ")
    if c.hang_height_cm is not None or c.hang_note:
        hang = f"בגובה {_num(c.hang_height_cm)} ס״מ" if c.hang_height_cm is not None else ""
        lines.append(f"   תלייה: {' – '.join(x for x in (hang, escape(c.hang_note or '')) if x)}")
    if c.position_note:
        lines.append(f"   {escape(c.position_note)}")
    if c.sun_note:
        lines.append(f"☀️ {escape(c.sun_note)}")
    if c.slot:
        season = sun.season_for()
        row = sun.get(session, user_id, c.slot.area, season)
        lines.append(f"☀️ <b>שמש באזור ({sun.SEASON_HE[season]}):</b> {sun.describe(row)}")

    lines.append("")
    if c.type_code:
        lines.append(f"🪣 <b>סוג:</b> {escape(L.he(L.TYPE_HE, c.type_code))}")
    lines.append(
        f"🪣 <b>מיכל:</b> {escape(L.he(L.SHAPE_HE, c.shape, 'צורה לא ידועה'))}, "
        f"{escape(L.he(L.MATERIAL_HE, c.material, 'חומר לא ידוע'))}, "
        f"{escape(L.he(L.COLOR_HE, c.color, 'צבע לא ידוע'))}"
    )
    dims = _dimensions(c)
    if dims:
        lines.append(f"📏 <b>מידות חיצוניות:</b> {dims}")
    if c.outer_raw:
        lines.append(f"📏 <b>מידה שנרשמה:</b> {escape(c.outer_raw)}")
    est = estimate_container(c)
    if est:
        lines.append(f"🧮 <b>נפח מצע משוער:</b> {est.volume_l:.1f} ליטר · שטח פני המצע {est.surface_cm2:.0f} סמ״ר")
    else:
        lines.append("🧮 <b>נפח מצע:</b> אי אפשר לחשב – חסרות מידות")
    if c.substrate:
        lines.append(f"🟫 <b>מצע:</b> {escape(L.he(L.SUBSTRATE_HE, c.substrate))}")
    if c.sections:
        lines.append(f"↔️ <b>צדדים:</b> {' / '.join(c.sections)} (חוצץ מעל המעקה)")

    lines += ["", "🌿 <b>צמחים:</b>"]
    for p in c.plants:
        latin = ""
        if p.latin:
            latin = f" · <i>{escape(p.latin)}</i>" + ("" if p.latin_verified else " (לאימות)")
        en = f" ({escape(p.name_en)})" if p.name_en and p.name_en != "unknown" else ""
        section = f" [{L.he(L.SECTION_HE, p.section)}]" if p.section else ""
        lines.append(f"• {escape(p.name_he)}{en}{latin}{section}")
        if p.note:
            lines.append(f"   {escape(p.note)}")
        if p.pest_profile == "sensitive":
            lines.append("   🐛 מסלול מזיקים רגיש")
        if p.pests_history:
            lines.append(f"   היסטוריית מזיקים: {escape(', '.join(p.pests_history))}")
        if p.planted_on:
            lines.append(f"   נשתל ב־{p.planted_on:%d.%m.%Y}")
        if p.water_need or p.feed_group:
            lines.append(
                f"   טיפול: {L.he(WATER_NEED_HE, p.water_need, '? מים')} · דישון: {L.he(FEED_GROUP_HE, p.feed_group, '?')}"
            )

    lines += [""] + care_lines(session, c, clock.today())
    issues = doctor.open_issues(session, user_id, c.id)
    for issue in issues:
        lines.append(f"🐛 <b>בעיה פתוחה:</b> {escape(doctor.summary_he(issue))}")
    n_photos = photos.count(session, c.id)

    lines += ["", f"<b>מצב:</b> {L.STATUS_EMOJI.get(c.status, '⚪')} {L.he(L.STATUS_HE, c.status)}"]
    lines.append(f"   {escape(c.condition)}" if c.condition else "   לא נרשם")

    missing = missing_fields(c)
    if missing:
        lines += ["", "❓ <b>חסר:</b> " + ", ".join(escape(missing_label(c, m)) for m in missing)]

    if back == "m":
        back_btn = InlineKeyboardButton("⬅️ לרשימת החסרים", callback_data=CB_MISSING)
    else:
        area = c.slot.area if c.slot else L.NO_SLOT_KEY
        back_btn = InlineKeyboardButton("⬅️ חזרה לאזור", callback_data=f"g:a:{area}")
    keyboard = list(top_rows or [])
    keyboard.append([
        InlineKeyboardButton("💧 השקיתי", callback_data=f"c:w:{c.number}"),
        InlineKeyboardButton("🌱 דישנתי", callback_data=f"c:f:{c.number}"),
    ])
    pest_buttons = [InlineKeyboardButton(f"🐛 {PESTS[i.pest].name_he}", callback_data=f"d:i:{i.id}") for i in issues]
    pest_buttons.append(InlineKeyboardButton("🐛 בעיה חדשה" if issues else "🐛 בעיה", callback_data=f"d:p:{c.number}"))
    if n_photos:
        pest_buttons.append(InlineKeyboardButton(f"📷 תמונות ({n_photos})", callback_data=f"ph:{c.number}"))
    keyboard.append(pest_buttons[:3])
    if any(askable(m) for m in missing):
        keyboard.append([InlineKeyboardButton("✏️ השלמת פרטים", callback_data=f"e:c:{c.number}")])
    keyboard.append([
        InlineKeyboardButton("🔄 שינוי מצב", callback_data=f"e:s:{c.number}"),
        InlineKeyboardButton("📍 הזזה", callback_data=f"e:m:{c.number}"),
    ])
    keyboard.append([back_btn, InlineKeyboardButton("🪴 כל הגינה", callback_data=CB_HOME)])
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


def missing_view(session: Session, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    containers = [
        c
        for c in session.scalars(select(Container).where(Container.user_id == user_id).order_by(Container.number))
        if missing_fields(c)
    ]
    sun_left = len(sun.unanswered(session, user_id, sun.season_for()))
    sun_line = f"☀️ עוד לא סימנת שעות שמש ל־{sun_left} אזורים – /sun" if sun_left else ""
    if not containers:
        text = "✅ אין פרטים חסרים בעציצים. כל העציצים מלאים!"
        return (f"{text}\n\n{sun_line}" if sun_line else text), InlineKeyboardMarkup([])
    lines = ["❓ <b>עציצים שחסרים להם פרטים</b>", ""]
    for c in containers:
        lines.append(container_line(c))
        lines.append("   חסר: " + ", ".join(escape(missing_label(c, m)) for m in missing_fields(c)))
    lines += ["", "בחר עציץ, ובכרטיס שלו לחץ ✏️ השלמת פרטים."]
    if sun_line:
        lines += ["", sun_line]
    return "\n".join(lines), InlineKeyboardMarkup(_container_buttons(containers, "m"))


def sun_overview(session: Session, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    season = sun.season_for()
    lines = [f"☀️ <b>שעות שמש לפי אזור</b> · {sun.SEASON_HE[season]}", ""]
    buttons = []
    for area in sun.areas(session, user_id):
        row = sun.get(session, user_id, area, season)
        mark = "✅" if sun.is_answered(row) else "❓"
        lines.append(f"{mark} <b>{escape(sun.area_label(area))}</b>: {sun.describe(row)}")
        buttons.append(InlineKeyboardButton(f"✏️ {sun.area_label(area)}", callback_data=f"sun:a:{area}"))
    lines += ["", "שמש ישירה = השמש עצמה מגיעה לעציצים (לא רק אור). מספיק בערך, לפי שעה עגולה."]
    keyboard = []
    left = sun.unanswered(session, user_id, season)
    if left:
        keyboard.append([InlineKeyboardButton(f"▶️ לענות על מה שחסר ({len(left)})", callback_data="sun:go")])
    keyboard += [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)
