"""Tests for molexp's Logger subclass and get_logger factory."""

from __future__ import annotations

from typing import Any

import mollog
import pytest

import molexp
from molexp._logger import _reset_cache


@pytest.fixture(autouse=True)
def _isolate_logger_cache() -> Any:
    """Each test gets a fresh molexp logger cache."""
    _reset_cache()
    yield
    _reset_cache()


class _CapturingHandler(mollog.Handler):
    """Test handler that records every dispatched LogRecord."""

    def __init__(self) -> None:
        super().__init__(level=mollog.Level.TRACE)
        self.records: list[mollog.LogRecord] = []

    def emit(self, record: mollog.LogRecord) -> None:
        self.records.append(record)


def test_ice_emits_tagged_record() -> None:
    handler = _CapturingHandler()
    log = molexp.get_logger("molexp.test.ice")
    log.add_handler(handler)

    log.ice("agent step", agent_id="a-1", step=3)

    assert len(handler.records) == 1
    record = handler.records[0]
    assert record.level is mollog.Level.INFO
    assert record.message == "agent step"
    assert record.extra.get("verb") == "ice"
    assert record.extra.get("agent_id") == "a-1"
    assert record.extra.get("step") == 3
