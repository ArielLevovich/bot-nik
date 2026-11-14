"""/backup (bot sends its database file), /restore (owner sends one back), and the nightly backup job."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from botnik import backup, clock
from botnik.care import fill_care_defaults

log = logging.getLogger(__name__)

AWAITING = "awaiting_restore"


def _engine(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["session_factory"].kw["bind"]


async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    engine = _engine(context)
    name = f"botnik-{clock.today():%Y-%m-%d}.db"
    with tempfile.TemporaryDirectory() as tmp:
        path = backup.snapshot(engine, Path(tmp) / name)
        with open(path, "rb") as f:
            await update.effective_message.reply_document(
                f, filename=name, caption="💾 גיבוי של כל נתוני הגינה. שמור אותו; לשחזור: /restore ואז שלח את הקובץ."
            )


async def restore_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data[AWAITING] = True
    await update.effective_message.reply_text(
        "📥 שלח לי עכשיו את קובץ botnik.db (כקובץ, דרך 📎).\n"
        "הוא יחליף את כל הנתונים כאן. לפני כן אשמור עותק של מה שיש עכשיו.\n"
        "לביטול: /cancel"
    )


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not context.user_data.get(AWAITING):
        await message.reply_text("קיבלתי קובץ, אבל לא ביקשת שחזור. כדי לשחזר: /restore ואז שלח את הקובץ.")
        return
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "incoming.db"
        telegram_file = await context.bot.get_file(message.document.file_id)
        await telegram_file.download_to_drive(path)
        ok, summary = backup.check(path)
        if not ok:
            await message.reply_text(f"⚠️ {summary}\nלא שיניתי כלום. נסה שוב, או /cancel.")
            return
        engine = _engine(context)
        safety = backup.restore(engine, path)
    context.user_data.pop(AWAITING, None)
    with context.application.bot_data["session_factory"]() as s:
        fill_care_defaults(s)
    log.info("Database restored from Telegram (%s); previous copy at %s", summary, safety)
    await message.reply_text(f"✅ שוחזר: {summary}.\nהעותק הקודם נשמר בגיבויים. נסה /garden.")


async def backup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    path = backup.daily_backup(_engine(context), clock.today())
    log.info("Daily backup: %s", path)
