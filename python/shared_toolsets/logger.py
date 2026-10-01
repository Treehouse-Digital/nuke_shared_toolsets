"""Logger and timing routines for shared toolsets."""

from __future__ import annotations

import contextlib
import logging
import time

__all__ = ("LOG", "timed")

LOG = logging.getLogger("SharedToolSets")
"""Logger for shared toolsets."""


class timed(contextlib.ContextDecorator, contextlib.AbstractContextManager):
    """Context manager and decorator for timing code execution."""

    def __init__(self, msg: str, level=logging.DEBUG):
        """Initialize with exit message and optional level to log at."""
        self.msg = msg
        self.level = level
        self.stacklevel = 2

    def __call__(self, func):
        self.stacklevel = 3
        return super().__call__(func)

    def __enter__(self):
        self.start = time.time()

    def __exit__(self, *_):
        msg = f"took {time.time() - self.start:7> .2f}s for {self.msg}"
        LOG.log(self.level, msg, stacklevel=self.stacklevel)
