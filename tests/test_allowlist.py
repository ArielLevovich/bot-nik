import asyncio
from unittest.mock import MagicMock

import pytest
from telegram.ext import ApplicationHandlerStop

from botnik.config import ConfigError, parse_user_ids
from botnik.handlers.auth import is_allowed, make_gate


def test_parse_user_ids():
    assert parse_user_ids("123, 456,,789 ") == frozenset({123, 456, 789})
    assert parse_user_ids("") == frozenset()
    assert parse_user_ids(None) == frozenset()


def test_parse_user_ids_rejects_garbage():
    with pytest.raises(ConfigError):
        parse_user_ids("123,abc")


def test_is_allowed():
    allowed = frozenset({111})
    assert is_allowed(111, allowed)
    assert not is_allowed(222, allowed)
    assert not is_allowed(None, allowed)
    assert not is_allowed(111, frozenset())


def _update_from(user_id):
    update = MagicMock()
    update.effective_user = MagicMock(id=user_id) if user_id is not None else None
    return update


def test_gate_blocks_strangers_and_passes_owner():
    gate = make_gate(frozenset({111})).callback
    asyncio.run(gate(_update_from(111), MagicMock()))  # no exception = passes
    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(gate(_update_from(222), MagicMock()))
    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(gate(_update_from(None), MagicMock()))
