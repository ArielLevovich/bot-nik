"""/sun: ask the owner for sun hours per area (current season).

Overview buttons (entry points):  sun:go (all unanswered areas)  sun:a:<area> (one area)
While asking:  sun:h:<hour>  sun:none (no morning sun)  sun:pm:1|0  sun:skip  sun:cancel
"""

from __future__ import annotations

import warnings

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler

from botnik import sun, views

ASK = 0
TIMEOUT_SECONDS = 15 * 60


def _session(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["session_factory"]()


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


async def overview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/sun command."""
    with _session(context) as s:
        text, keyboard = views.sun_overview(s, update.effective_user.id)
    await _show(update, text, keyboard)


def _hour_buttons(hours: list[int]) -> list[list[InlineKeyboardButton]]:
    buttons = [InlineKeyboardButton(f"{h:02d}:00", callback_data=f"sun:h:{h}") for h in hours]
    return [buttons[i : i + 5] for i in range(0, len(buttons), 5)]


def question(state: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Text + keyboard for the current step (pure, for tests)."""
    head = f"☀️ <b>{sun.area_label(state['area'])}</b> · {sun.SEASON_HE[state['season']]}\n\n"
    end_row = [
        InlineKeyboardButton("⏭ דלג על האזור", callback_data="sun:skip"),
        InlineKeyboardButton("✖️ ביטול", callback_data="sun:cancel"),
    ]
    if state["step"] == "from":
        rows = _hour_buttons(sun.FROM_HOURS)
        rows.append([InlineKeyboardButton("🌑 אין שמש ישירה בבוקר", callback_data="sun:none")])
        text = head + "מאיזו שעה מגיעה <b>שמש ישירה</b> בבוקר לאזור הזה?"
    elif state["step"] == "to":
        rows = _hour_buttons(list(range(state["from"] + 1, sun.LAST_HOUR + 1)))
        text = head + f"שמש מ־{state['from']:02d}:00. <b>עד איזו שעה?</b>"
    else:
        rows = [[
            InlineKeyboardButton("☀️ יש", callback_data="sun:pm:1"),
            InlineKeyboardButton("🌥 אין", callback_data="sun:pm:0"),
        ]]
        text = head + "יש <b>שמש ישירה אחרי הצהריים</b> (אחרי 13:00)?"
    rows.append(end_row)
    return text, InlineKeyboardMarkup(rows)


async def _next_area(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    state = context.user_data["sun"]
    if not state["queue"]:
        context.user_data.pop("sun", None)
        with _session(context) as s:
            text, keyboard = views.sun_overview(s, update.effective_user.id)
        note = "✅ נשמר.\n\n" if state["saved"] else ""
        await _show(update, note + text, keyboard)
        return ConversationHandler.END
    state.update(area=state["queue"].pop(0), step="from", **{"from": None, "to": None})
    await _show(update, *question(state))
    return ASK


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    season = sun.season_for()
    with _session(context) as s:
        if query.data == "sun:go":
            queue = sun.unanswered(s, user_id, season)
        else:
            area = query.data.split(":", 2)[2]
            queue = [area] if area in sun.areas(s, user_id) else []
    context.user_data["sun"] = {"queue": queue, "season": season, "saved": 0}
    return await _next_area(update, context)


async def on_hour(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    state = context.user_data["sun"]
    hour = int(update.callback_query.data.split(":")[2])
    if state["step"] == "from":
        state.update(step="to", **{"from": hour})
    elif state["step"] == "to" and hour > state["from"]:
        state.update(step="pm", to=hour)
    await _show(update, *question(state))
    return ASK


async def on_no_morning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    state = context.user_data["sun"]
    state.update(step="pm", **{"from": None, "to": None})
    await _show(update, *question(state))
    return ASK


async def on_afternoon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    state = context.user_data["sun"]
    if state["step"] != "pm":
        return ASK
    with _session(context) as s:
        sun.save(
            s, update.effective_user.id, state["area"], state["season"],
            morning_from=state["from"], morning_to=state["to"],
            afternoon_sun=update.callback_query.data.endswith(":1"),
        )
    state["saved"] += 1
    return await _next_area(update, context)


async def on_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _next_area(update, context)


async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data.get("sun", {})["queue"] = []
    if "sun" not in context.user_data:
        return ConversationHandler.END
    return await _next_area(update, context)


async def stale_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer("השאלה הזו כבר לא פעילה. שלח /sun שוב.")


def build_conversation() -> ConversationHandler:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r".*per_message.*")
        return ConversationHandler(
            entry_points=[CallbackQueryHandler(start, pattern=r"^sun:(go|a:\w+)$")],
            states={
                ASK: [
                    CallbackQueryHandler(on_hour, pattern=r"^sun:h:\d+$"),
                    CallbackQueryHandler(on_no_morning, pattern=r"^sun:none$"),
                    CallbackQueryHandler(on_afternoon, pattern=r"^sun:pm:[01]$"),
                    CallbackQueryHandler(on_skip, pattern=r"^sun:skip$"),
                    CallbackQueryHandler(on_cancel, pattern=r"^sun:cancel$"),
                ],
            },
            fallbacks=[CommandHandler("cancel", on_cancel)],
            allow_reentry=True,
            conversation_timeout=TIMEOUT_SECONDS,
            name="sun_hours",
        )
