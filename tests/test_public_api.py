"""The ``molab`` top-level surface re-exports mollog's logger, not a copy."""

from __future__ import annotations

import mollog

import molab


class TestLoggerReexport:
    def test_get_logger_is_mollogs(self):
        assert molab.get_logger is mollog.get_logger

    def test_logger_class_is_mollogs(self):
        assert molab.Logger is mollog.Logger

    def test_same_name_returns_same_object(self):
        assert molab.get_logger("molab.probe") is mollog.get_logger("molab.probe")
