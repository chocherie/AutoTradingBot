"""Exponential backoff for external API calls."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Optional, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


def with_backoff(
    fn: Callable[[], T],
    *,
    retries: int = 3,
    base_seconds: float = 2.0,
    operation: str = "request",
) -> T:
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt == retries - 1:
                break
            wait = base_seconds * (2**attempt)
            logger.warning(
                "retry_after_error",
                extra={"operation": operation, "attempt": attempt + 1, "wait_s": wait, "error": str(e)},
            )
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc
