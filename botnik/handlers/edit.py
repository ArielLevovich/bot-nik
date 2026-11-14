"""Conversation: complete missing details / change status / move a container.

Entry buttons on the container card:  e:c:<n> (complete)  e:s:<n> (status)  e:m:<n> (move)
While asking:  e:v:<option index>  e:other  e:skip  e:cancel  and typed text.
State lives in context.user_data["edit"]; every answer is saved immediately.
"""

from __future__ import annotations

import warnings

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from botnik import editing, views

ASK = 0
TIMEOUT_SECONDS = 15 * 60


def _session(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["session_factory"]()


async def _show(update: Update, text: str, keyboard, edit: bool) -> None:
    if edit and update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            return
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
                return
            raise
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def _finish(update: Update, context: ContextTypes.DEFAULT_TYPE, note: str, edit: bool) -> int:
    state = context.user_data.pop("edit", None)
    if state:
        with _session(context) as s:
            text, keyboard = views.container_card(s, update.effective_user.id, state["n"], state.get("back", "a"))
        await _show(update, f"{note}\n\n{text}", keyboard, edit)
    return ConversationHandler.END


async def _ask_next(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool) -> int:
    """Move to the next key and ask it, or finish when nothing is left."""
    state = context.user_data["edit"]
    with _session(context) as s:
        c = editing.find_container(s, update.effective_user.id, state["n"])
        if c is None:
            context.user_data.pop("edit", None)
            await _show(update, "העציץ לא נמצא.", None, edit)
            return ConversationHandler.END
        state["key"] = editing.next_key(c, state["mode"], state["queue"], state["skipped"])
        state["other"] = False
        if state["key"] is None:
            done = "✅ נשמר." if state["answered"] else "לא נשמר שום שינוי."
            return await _finish(update, context, done, edit)
        q = editing.build_question(s, c, state["key"])
        state["options"] = [value for value, _ in q.options]
        text = editing.question_text(c, q)
    await _show(update, text, editing.question_keyboard(q), edit)
    return ASK


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, mode, number = query.data.split(":")
    context.user_data["edit"] = {
        "n": int(number),
        "mode": mode,
        "queue": list(editing.FIXED_KEYS.get(mode, [])),
        "skipped": [],
        "answered": 0,
        "key": None,
        "other": False,
        "options": [],
    }
    return await _ask_next(update, context, edit=True)


async def _save(update: Update, context: ContextTypes.DEFAULT_TYPE, value, edit: bool) -> int:
    state = context.user_data["edit"]
    with _session(context) as s:
        c = editing.find_container(s, update.effective_user.id, state["n"])
        editing.apply_answer(s, c, state["key"], value)
    state["answered"] += 1
    return await _ask_next(update, context, edit)


async def on_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    state = context.user_data.get("edit")
    index = int(query.data.split(":")[2])
    if not state or index >= len(state["options"]):
        return ConversationHandler.END
    return await _save(update, context, state["options"][index], edit=True)


async def on_other(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data["edit"]["other"] = True
    return await _reask(update, context)


async def _reask(update: Update, context: ContextTypes.DEFAULT_TYPE, error: str = "", edit: bool = True) -> int:
    """Show the current question again (after 'other' or bad input) without moving on."""
    state = context.user_data["edit"]
    with _session(context) as s:
        c = editing.find_container(s, update.effective_user.id, state["n"])
        q = editing.build_question(s, c, state["key"])
        text = editing.question_text(c, q, state["other"])
    if error:
        text = f"⚠️ {error}\n\n{text}"
    await _show(update, text, editing.question_keyboard(q, state["other"]), edit)
    return ASK


async def on_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    state = context.user_data["edit"]
    if state["key"]:
        state["skipped"].append(state["key"])
    return await _ask_next(update, context, edit=True)


async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    state = context.user_data.get("edit") or {}
    note = "✖️ הפסקתי. מה שכבר ענית נשמר." if state.get("answered") else "✖️ בוטל."
    return await _finish(update, context, note, edit=bool(update.callback_query))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    state = context.user_data["edit"]
    text = update.effective_message.text or ""
    with _session(context) as s:
        c = editing.find_container(s, update.effective_user.id, state["n"])
        kind = editing.build_question(s, c, state["key"]).kind
    if kind == "choice" and not state["other"]:
        return await _reask(update, context, "בחר אחת מהאפשרויות בכפתורים (או \"משהו אחר\").", edit=False)
    if kind == "number":
        try:
            value = editing.parse_number(text)
        except ValueError as exc:
            return await _reask(update, context, str(exc), edit=False)
        return await _save(update, context, value, edit=False)
    if not text.strip():
        return await _reask(update, context, "כתוב משהו, או לחץ דלג.", edit=False)
    return await _save(update, context, text.strip()[:500], edit=False)


async def stale_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A question button pressed after its conversation ended."""
    await update.callback_query.answer("השאלה הזו כבר לא פעילה. פתח את העציץ שוב.", show_alert=False)


def build_conversation() -> ConversationHandler:
    # PTB warns that per_message=False doesn't track each message; that's what we want here
    # (one question at a time per chat, answered by buttons or by typed text).
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r".*per_message.*")
        return _conversation()


def _conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start, pattern=r"^e:[csm]:\d+$")],
        states={
            ASK: [
                CallbackQueryHandler(on_choice, pattern=r"^e:v:\d+$"),
                CallbackQueryHandler(on_other, pattern=f"^{editing.CB_OTHER}$"),
                CallbackQueryHandler(on_skip, pattern=f"^{editing.CB_SKIP}$"),
                CallbackQueryHandler(on_cancel, pattern=f"^{editing.CB_CANCEL}$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_text),
            ],
        },
        fallbacks=[CommandHandler("cancel", on_cancel)],
        allow_reentry=True,
        conversation_timeout=TIMEOUT_SECONDS,
        name="edit_container",
    )
