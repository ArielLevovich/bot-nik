"""Allow-list gate: the single place that decides who the bot answers.

The gate runs in handler group -1, before every regular handler (group 0+).
For a user who is not allowed it raises ApplicationHandlerStop, so no other
handler runs and the bot sends nothing. The only exception is /myid, which is
registered in group -2 (before the gate) so the owner can learn their ID.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes, TypeHandler

log = logging.getLogger(__name__)

GATE_GROUP = -1
PRE_GATE_GROUP = -2  # handlers that must work for everyone (only /myid)


def is_allowed(user_id: int | None, allowed_ids: frozenset[int]) -> bool:
    return user_id is not None and user_id in allowed_ids


def make_gate(allowed_ids: frozenset[int]) -> TypeHandler:
    async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        user_id = user.id if user else None
        if not is_allowed(user_id, allowed_ids):
            log.info("Ignoring update from non-allowed user %s", user_id)
            raise ApplicationHandlerStop

    return TypeHandler(Update, gate)
