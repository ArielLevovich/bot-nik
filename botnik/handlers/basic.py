"""Basic commands: /myid (open to everyone) and a temporary /start."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.effective_message is None:
        return
    await update.effective_message.reply_text(
        f"מספר המשתמש שלך בטלגרם: {user.id}\n"
        "יש להוסיף אותו ל־ALLOWED_USER_IDS בקובץ ‎.env ולהפעיל את הבוט מחדש."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Temporary greeting; the full /start text comes in step 4.
    if update.effective_message is None:
        return
    await update.effective_message.reply_text("שלום! בוט־ניק פועל 🌱")
