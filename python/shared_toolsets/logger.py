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


class Timed(contextlib.ContextDecorator, contextlib.AbstractContextManager):
    """Context manager and decorator for timing code execution."""

    def __init__(self, msg: str, level: int = logging.DEBUG) -> None:
        """Initialize with exit message and optional level to log at."""
        self.msg = msg
        self.level = level
        self.stacklevel = 2

    def __call__(self, func: Callable) -> Callable:
        """Extend to set stacklevel for decorator usage."""
        self.stacklevel = 3
        return super().__call__(func)

    def __enter__(self) -> None:
        """Enter the context and start timing."""
        self.start = time.time()

    def __exit__(self, *_: object) -> None:
        """Exit the context, log the elapsed time."""
        msg = f"took {time.time() - self.start:7> .2f}s for {self.msg}"
        LOG.log(self.level, msg, stacklevel=self.stacklevel)
