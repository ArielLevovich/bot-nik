"""Daily reminders: morning brief and evening summary jobs, /today, task buttons, /settings."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, ContextTypes

from botnik import brief, clock, doctor, editing, tasks

log = logging.getLogger(__name__)


def _session(context_or_app):
    app = context_or_app if isinstance(context_or_app, Application) else context_or_app.application
    return app.bot_data["session_factory"]()


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


# --- scheduled jobs ---

async def brief_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = context.job.data
    today = clock.today()
    with _session(context) as s:
        tasks.generate(s, user_id, today)
        text, kb = brief.morning(s, user_id, today)
    await context.bot.send_message(user_id, text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def evening_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = context.job.data
    with _session(context) as s:
        text, kb = brief.evening(s, user_id, clock.today())
    await context.bot.send_message(user_id, text, parse_mode=ParseMode.HTML, reply_markup=kb)


def schedule_user(app: Application, user_id: int) -> None:
    """(Re)schedule this user's two daily messages at the times in their settings."""
    with _session(app) as s:
        settings = brief.get_settings(s, user_id)
        brief_time, evening_time = settings.brief_time, settings.evening_time
    for name, callback, at in (
        (f"brief-{user_id}", brief_job, brief_time),
        (f"evening-{user_id}", evening_job, evening_time),
    ):
        for job in app.job_queue.get_jobs_by_name(name):
            job.schedule_removal()
        app.job_queue.run_daily(callback, time=clock.parse_hhmm(at), data=user_id, name=name, chat_id=user_id, user_id=user_id)
    log.info("Scheduled user %s: brief %s, evening %s", user_id, brief_time, evening_time)


# --- commands and buttons ---

async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id, today = update.effective_user.id, clock.today()
    with _session(context) as s:
        tasks.generate(s, user_id, today)
        text, kb = brief.morning(s, user_id, today)
    await _show(update, text, kb)


async def task_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """t:<d|p|n>:<task>:<m|e>  t:c:<task>:<c|l|w>:<m|e>  t:all:<m|e>  t:dry  t:dry:<n>  t:back"""
    query = update.callback_query
    user_id, today = update.effective_user.id, clock.today()
    parts = query.data.split(":")
    note = ""
    with _session(context) as s:
        action = parts[1]
        mode = "e"
        if action in ("d", "p", "n"):
            mode = parts[3]
            task = tasks.get(s, user_id, int(parts[2]))
            if task is None or task.status not in tasks.ACTIVE:
                await query.answer("המשימה כבר טופלה.")
            else:
                if action == "d":
                    message = tasks.complete(s, task, today)
                    if message:
                        note = message + "\n\n"
                elif action == "p":
                    tasks.postpone(s, task, today)
                else:
                    tasks.not_needed(s, task)
                skipped = "✗ הבנתי, אחכה יותר בפעם הבאה" if task.type == "water" else "✗ סומן"
                await query.answer({"d": "✓ נרשם", "p": "⏭ עבר למחר", "n": skipped}[action])
        elif action == "c":
            mode = parts[4]
            task = tasks.get(s, user_id, int(parts[2]))
            issue = doctor.get(s, user_id, task.issue_id) if task and task.status in tasks.ACTIVE else None
            if issue is None:
                await query.answer("המשימה כבר טופלה.")
            else:
                result = {"c": "clean", "l": "less", "w": "worse"}[parts[3]]
                note = doctor.check_result(s, issue, result, today) + "\n\n"
                await query.answer()
        elif action == "all":
            mode = parts[2]
            for task in tasks.actionable(s, user_id, today, evening=mode == "e"):
                if task.type != "check":
                    tasks.complete(s, task, today)
            await query.answer("✓ הכל נרשם")
        elif action == "dry" and len(parts) == 2:
            await query.answer()
            await _show(update, *brief.dry_picker(s, user_id))
            return
        elif action == "dry":
            c = editing.find_container(s, user_id, int(parts[2]))
            if c:
                tasks.report_dry(s, c, today)
                note = f"🥀 רשמתי. #{c.number} יקבל מים מוקדם יותר מעכשיו, והוספתי השקיה להיום.\n\n"
            await query.answer()
        else:  # back
            await query.answer()
        text, kb = brief.morning(s, user_id, today) if mode == "m" else brief.evening(s, user_id, today)
    await _show(update, note + text, kb)


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session(context) as s:
        text, kb = brief.settings_view(s, update.effective_user.id)
    await _show(update, text, kb)


async def settings_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """st:b | st:e | st:b:HHMM | st:e:HHMM"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) == 2:
        await _show(update, *brief.time_picker(parts[1]))
        return
    value = f"{parts[2][:2]}:{parts[2][2:]}"
    allowed = brief.BRIEF_TIMES if parts[1] == "b" else brief.EVENING_TIMES
    if value not in allowed:
        return
    with _session(context) as s:
        settings = brief.get_settings(s, user_id)
        if parts[1] == "b":
            settings.brief_time = value
        else:
            settings.evening_time = value
        s.commit()
    schedule_user(context.application, user_id)
    with _session(context) as s:
        text, kb = brief.settings_view(s, user_id, note="✅ עודכן.")
    await _show(update, text, kb)
