"""Bot entry point: python -m botnik.bot"""

from __future__ import annotations

import logging

from telegram.ext import Application, CommandHandler

from botnik.config import Settings, load_settings
from botnik.handlers import basic
from botnik.handlers.auth import GATE_GROUP, PRE_GATE_GROUP, make_gate

log = logging.getLogger(__name__)


def build_application(settings: Settings) -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()

    # Open to everyone, runs before the allow-list gate.
    app.add_handler(CommandHandler("myid", basic.myid), group=PRE_GATE_GROUP)
    # The one allow-list check. Everything below only runs for allowed users.
    app.add_handler(make_gate(settings.allowed_user_ids), group=GATE_GROUP)

    app.add_handler(CommandHandler("start", basic.start))
    return app


def main() -> None:
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
