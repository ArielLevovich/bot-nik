"""Bot entry point: python -m botnik.bot"""

from __future__ import annotations

import fcntl
import hashlib
import logging
import sys
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker
from telegram import BotCommand
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from botnik.config import PROJECT_ROOT, Settings, load_settings
from botnik.db import make_engine, make_session_factory
from botnik.handlers import basic, edit, garden, sun
from botnik.handlers.auth import GATE_GROUP, PRE_GATE_GROUP, make_gate

log = logging.getLogger(__name__)

COMMANDS = [
    BotCommand("garden", "כל הגינה"),
    BotCommand("missing", "עציצים שחסרים להם פרטים"),
    BotCommand("sun", "שעות שמש לפי אזור"),
    BotCommand("start", "מה הבוט יודע לעשות"),
    BotCommand("myid", "מספר המשתמש שלי"),
    BotCommand("cancel", "הפסקת שאלות"),
]


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands(COMMANDS)  # the "Menu" button in Telegram


def build_application(settings: Settings, session_factory: sessionmaker[Session] | None = None) -> Application:
    app = Application.builder().token(settings.telegram_bot_token).post_init(_post_init).build()
    app.bot_data["session_factory"] = session_factory or make_session_factory(make_engine())

    # Open to everyone, runs before the allow-list gate.
    app.add_handler(CommandHandler("myid", basic.myid), group=PRE_GATE_GROUP)
    # The one allow-list check. Everything below only runs for allowed users.
    app.add_handler(make_gate(settings.allowed_user_ids), group=GATE_GROUP)

    app.add_handler(CommandHandler("start", basic.start))
    app.add_handler(CommandHandler("garden", garden.garden))
    app.add_handler(CommandHandler("missing", garden.missing))
    app.add_handler(CallbackQueryHandler(garden.on_button, pattern=r"^g:"))
    app.add_handler(edit.build_conversation())
    app.add_handler(CallbackQueryHandler(edit.stale_button, pattern=r"^e:"))  # after the conversation
    app.add_handler(CommandHandler("sun", sun.overview))
    app.add_handler(sun.build_conversation())
    app.add_handler(CallbackQueryHandler(sun.stale_button, pattern=r"^sun:"))  # after the conversation
    app.add_handler(CommandHandler("cancel", basic.cancel_idle))  # after both conversations
    return app


def single_instance_lock():
    """Hold an exclusive lock for the life of the process; exit if another copy already holds it.

    Two copies polling with the same token steal each other's updates (old code answers some taps).
    """
    key = hashlib.sha1(str(PROJECT_ROOT).encode()).hexdigest()[:12]
    path = Path(tempfile.gettempdir()) / f"botnik-{key}.lock"
    handle = open(path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(
            "Bot-Nik is already running in another window, so this copy will not start.\n"
            "Stop the other copy (Ctrl+C in its window, or: pkill -f botnik.bot) and try again."
        )
    return handle  # keep a reference; the lock is released when the process ends


def main() -> None:
    lock = single_instance_lock()  # noqa: F841 (held until exit)
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its logs include the token in URLs
    settings = load_settings()
    if not settings.allowed_user_ids:
        log.warning("ALLOWED_USER_IDS is empty: the bot will only answer /myid.")
    app = build_application(settings)
    log.info("Bot-Nik is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
