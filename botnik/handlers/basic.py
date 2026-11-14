"""Basic commands: /myid (open to everyone) and /start."""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from botnik.views import START_TEXT


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.effective_message is None:
        return
    await update.effective_message.reply_text(
        f"מספר המשתמש שלך בטלגרם: {user.id}\n"
        "יש להוסיף אותו ל־ALLOWED_USER_IDS בקובץ ‎.env ולהפעיל את הבוט מחדש."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None:
        return
    await update.effective_message.reply_text(START_TEXT, parse_mode=ParseMode.HTML)


async def cancel_idle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/cancel when no question is open (an open conversation handles /cancel itself first)."""
    if update.effective_message is None:
        return
    if context.user_data.pop("awaiting_restore", None):
        await update.effective_message.reply_text("✖️ השחזור בוטל. לא שיניתי כלום.")
    else:
        await update.effective_message.reply_text("אין כרגע שאלות פתוחות.")
