"""Telegram handlers for /garden, /missing and their inline buttons."""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from botnik import views


def _session(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["session_factory"]()


async def garden(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session(context) as s:
        text, keyboard = views.garden_overview(s, update.effective_user.id)
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def missing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session(context) as s:
        text, keyboard = views.missing_view(s, update.effective_user.id)
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline button navigation: edits the same message in place."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    parts = (query.data or "").split(":")

    with _session(context) as s:
        match parts:
            case ["g", "home"]:
                text, keyboard = views.garden_overview(s, user_id)
            case ["g", "a", area]:
                text, keyboard = views.area_view(s, user_id, area)
            case ["g", "m"]:
                text, keyboard = views.missing_view(s, user_id)
            case ["g", "c", number, back] if number.isdigit():
                text, keyboard = views.container_card(s, user_id, int(number), back)
            case _:
                return

    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():  # same button pressed twice
            raise
