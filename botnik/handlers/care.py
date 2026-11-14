"""Care log from Telegram: card buttons, /water, /feed, the one-time starting point, /care."""

from __future__ import annotations

from datetime import timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from botnik import brief, carelog, clock, editing, rules, tasks, views
from botnik.care import fertilizers
from botnik.models import Product


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


def _card_with_note(s, user_id: int, number: int, note: str, batch: str | None = None):
    undo = [[InlineKeyboardButton("↩️ ביטול", callback_data=f"c:u:{batch}:{number}")]] if batch else None
    text, keyboard = views.container_card(s, user_id, number, top_rows=undo)
    return f"{note}\n\n{text}", keyboard


def _log_many(s, containers, kind: str) -> str:
    """Log water (kind 'w') or feed (kind 'f<product id>') for each container; returns the batch id."""
    batch = carelog.new_batch()
    for c in containers:
        if kind == "w":
            carelog.log(s, c, "water", source="button", batch=batch, amount_l=rules.suggested_amount_l(c), commit=False)
        else:
            carelog.log(s, c, "feed", source="button", batch=batch, product_id=int(kind[1:]), commit=False)
    s.commit()
    return batch


async def card_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """c:w:<n>  c:f:<n>  c:fp:<n>:<product>  c:u:<batch>:<n>"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    with _session(context) as s:
        if parts[1] == "u":
            batch, number = parts[2], int(parts[3])
            n = carelog.undo_batch(s, user_id, batch)
            if number:
                text, kb = _card_with_note(s, user_id, number, "↩️ בוטל." if n else "כבר בוטל.")
            else:
                text, kb = ("↩️ בוטל." if n else "כבר בוטל."), None
            await _show(update, text, kb)
            return

        number = int(parts[2])
        c = editing.find_container(s, user_id, number)
        if c is None:
            await _show(update, "העציץ לא נמצא.", None)
            return
        if parts[1] == "w":
            batch = _log_many(s, [c], "w")
            amount = rules.suggested_amount_l(c)
            note = f"✅ נרשמה השקיה ל־#{number}" + (f" (≈{amount:g} ל׳)" if amount else "")
            await _show(update, *_card_with_note(s, user_id, number, note, batch))
            return

        products = fertilizers(s, user_id)
        if parts[1] == "fp":
            product_id = int(parts[3])
        elif len(products) == 1:
            product_id = products[0].id
        elif not products:
            await _show(update, *_card_with_note(s, user_id, number, "אין דשן ברשימת החומרים בבית."))
            return
        else:
            rows = [[InlineKeyboardButton(p.name, callback_data=f"c:fp:{number}:{p.id}")] for p in products]
            await _show(update, "🌱 באיזה דשן השתמשת?", InlineKeyboardMarkup(rows))
            return
        batch = _log_many(s, [c], f"f{product_id}")
        product = s.get(Product, product_id)
        await _show(update, *_card_with_note(s, user_id, number, f"✅ נרשם דישון ל־#{number} ({product.name})", batch))


async def _baseline_or(update: Update, context: ContextTypes.DEFAULT_TYPE, then) -> None:
    with _session(context) as s:
        question = brief.baseline_question(s, update.effective_user.id)
        text, kb = question if question else then(s, update.effective_user.id)
    await _show(update, text, kb)


async def water_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _baseline_or(update, context, lambda s, uid: brief.water_menu(s, uid, "w"))


def _feed_start(s, user_id: int):
    products = fertilizers(s, user_id)
    if not products:
        return "אין דשן ברשימת החומרים בבית.", None
    if len(products) == 1:
        return brief.water_menu(s, user_id, f"f{products[0].id}")
    return brief.feed_product_picker(s, user_id)


async def feed_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _baseline_or(update, context, _feed_start)


async def water_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """w:<kind>:all | w:<kind>:a:<area> | w:<kind>:pick | w:<kind>:c:<n> | w:<kind>:menu"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    kind, action = parts[1], parts[2]
    with _session(context) as s:
        if action == "menu":
            await _show(update, *brief.water_menu(s, user_id, kind))
            return
        if action == "pick":
            await _show(update, *brief.water_pick(s, user_id, kind))
            return
        everything = tasks.containers_in_map_order(s, user_id)
        if action == "all":
            chosen = everything
        elif action == "a":
            chosen = [c for c in everything if c.slot and c.slot.area == parts[3]]
        else:
            chosen = [c for c in everything if c.number == int(parts[3])]
        if not chosen:
            await _show(update, "לא נמצאו עציצים.", None)
            return
        batch = _log_many(s, chosen, kind)
        await _show(update, *brief.logged_message("w" if kind == "w" else "f", chosen, batch))


async def baseline_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """b:<w|f>:<area>:<days ago or x>  |  b:skip"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    with _session(context) as s:
        if parts[1] != "skip":
            type = "water" if parts[1] == "w" else "feed"
            area, answer = parts[2], parts[3]
            in_area = [c for c in tasks.containers_in_map_order(s, user_id) if c.slot and c.slot.area == area]
            batch = carelog.new_batch()
            if answer == "x":
                if in_area:
                    carelog.log(s, in_area[0], "note", source="baseline", batch=batch,
                                note=f"{carelog.BASELINE_UNKNOWN}:{type}", commit=False)
            else:
                when = clock.utc_at_local(clock.today() - timedelta(days=int(answer)))
                products = fertilizers(s, user_id)
                for c in in_area:
                    carelog.log(
                        s, c, type, source="baseline", batch=batch, at=when, commit=False,
                        product_id=(products[0].id if products and type == "feed" else None),
                    )
            s.commit()
            question = brief.baseline_question(s, user_id)
            if question:
                await _show(update, *question)
                return
            text, kb = brief.water_menu(s, user_id, "w")
            await _show(update, "✅ נקודת ההתחלה נשמרה. מעכשיו התזכורות מחושבות ממנה.\n(לרישום דישון: /feed)\n\n" + text, kb)
            return
        await _show(update, *brief.water_menu(s, user_id, "w"))


async def care_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session(context) as s:
        text, kb = brief.care_overview(s, update.effective_user.id)
    await _show(update, text, kb)
