import contextlib
import inspect
import logging
import re
from unittest.mock import patch

import pytest
from shared_toolsets.logger import LOG, Timed


def test_context_manager_logs_once_at_requested_level(caplog):
    with contextlib.ExitStack() as stack:
        stack.enter_context(
            patch("shared_toolsets.logger.time.perf_counter", side_effect=[10.0, 11.25])
        )
        stack.enter_context(caplog.at_level(logging.INFO, logger=LOG.name))
        stack.enter_context(Timed("work", level=logging.INFO))

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.INFO
    assert caplog.records[0].message == "took    1.25s for work"


def test_decorator_logs_at_the_call_site(caplog):
    @Timed("decorated", level=logging.INFO)
    def operation() -> str:
        return "done"

    with contextlib.ExitStack() as stack:
        stack.enter_context(
            patch("shared_toolsets.logger.time.perf_counter", side_effect=[1.0, 1.5])
        )
        stack.enter_context(caplog.at_level(logging.INFO, logger=LOG.name))
        call_line = inspect.currentframe().f_lineno + 1
        result = operation()

    record = caplog.records[0]
    assert result == "done"
    assert record.funcName == "test_decorator_logs_at_the_call_site"
    assert record.lineno == call_line
    assert re.search(r"took\s+\d+\.\d{2}s for decorated", record.message)


def test_exception_is_logged_and_propagates(caplog):
    failure = RuntimeError("failed")
    with contextlib.ExitStack() as stack:
        stack.enter_context(
            patch("shared_toolsets.logger.time.perf_counter", side_effect=[0.0, 2.0])
        )
        stack.enter_context(caplog.at_level(logging.WARNING, logger=LOG.name))
        stack.enter_context(pytest.raises(RuntimeError, match="failed"))
        stack.enter_context(Timed("failing", level=logging.WARNING))
        raise failure

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert caplog.records[0].message == "took    2.00s for failing"


def test_same_decorated_function_can_be_reentered(caplog):
    @Timed("nested", level=logging.INFO)
    def nested(depth: int) -> None:
        if depth:
            nested(depth - 1)

    with contextlib.ExitStack() as stack:
        stack.enter_context(
            patch(
                "shared_toolsets.logger.time.perf_counter",
                side_effect=[0.0, 1.0, 2.0, 3.0],
            )
        )
        stack.enter_context(caplog.at_level(logging.INFO, logger=LOG.name))
        nested(1)

    assert len(caplog.records) == 2
    assert [record.message for record in caplog.records] == [
        "took    1.00s for nested",
        "took    3.00s for nested",
    ]
