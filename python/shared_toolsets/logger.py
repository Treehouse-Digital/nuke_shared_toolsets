"""Logger and timing routines for shared toolsets."""

from __future__ import annotations

import contextlib
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ("LOG", "Timed")

LOG = logging.getLogger("SharedToolSets")
"""Logger for shared toolsets."""
if not any(isinstance(handler, logging.NullHandler) for handler in LOG.handlers):
    LOG.addHandler(logging.NullHandler())


class Timed(contextlib.ContextDecorator, contextlib.AbstractContextManager):
    """Context manager and decorator for timing code execution."""

    def __init__(self, msg: str, level: int = logging.DEBUG) -> None:
        """Initialize with exit message and optional level to log at."""
        self.msg = msg
        self.level = level
        self.stacklevel = 2
        self._started_at: list[float] = []

    def __call__(self, func: Callable) -> Callable:
        """Extend to set stacklevel for decorator usage."""
        self.stacklevel = 3
        return super().__call__(func)

    def _recreate_cm(self) -> Timed:
        timer = type(self)(self.msg, self.level)
        timer.stacklevel = self.stacklevel
        return timer

    def __enter__(self) -> None:
        """Enter the context and start timing."""
        self._started_at.append(time.perf_counter())

    def __exit__(self, *_: object) -> None:
        """Exit the context, log the elapsed time."""
        elapsed = time.perf_counter() - self._started_at.pop()
        msg = f"took {elapsed:>7.2f}s for {self.msg}"
        LOG.log(self.level, msg, stacklevel=self.stacklevel)
