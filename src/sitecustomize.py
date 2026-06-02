"""
Runtime HTTP safeguards for Untappd scraping.

Python imports this module automatically at startup when running from the src/
directory. It keeps the existing scraper logic intact while making lightweight
requests less likely to trigger Untappd 429 rate limits.
"""

from __future__ import annotations

import os
import random
import threading
import time
from typing import Any

try:
    import requests
except Exception:  # pragma: no cover - requests may not be installed during metadata operations.
    requests = None


_PATCHED = False
_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _throttle_before_request():
    """Serialize requests enough to reduce bursts from ThreadPoolExecutor workers."""
    global _LAST_REQUEST_AT
    min_interval = _float_env("UNTAPPD_HTTP_MIN_INTERVAL", 0.45)
    jitter = _float_env("UNTAPPD_HTTP_JITTER", 0.25)

    with _LOCK:
        now = time.monotonic()
        wait_for = (_LAST_REQUEST_AT + min_interval) - now
        if wait_for > 0:
            time.sleep(wait_for)
        if jitter > 0:
            time.sleep(random.uniform(0, jitter))
        _LAST_REQUEST_AT = time.monotonic()


def _retry_after_seconds(response: Any, attempt: int) -> float:
    header = getattr(response, "headers", {}).get("Retry-After") if response is not None else None
    if header:
        try:
            return max(0.0, float(header))
        except ValueError:
            pass
    base = _float_env("UNTAPPD_HTTP_BACKOFF_BASE", 1.0)
    cap = _float_env("UNTAPPD_HTTP_BACKOFF_CAP", 12.0)
    return min(cap, base * (2 ** max(0, attempt - 1))) + random.uniform(0, 0.5)


def _patch_requests_get():
    global _PATCHED
    if requests is None or _PATCHED:
        return

    original_get = requests.get

    def guarded_get(*args, **kwargs):
        attempts = max(1, _int_env("UNTAPPD_HTTP_RETRIES", 4))
        last_response = None
        last_exc = None

        for attempt in range(1, attempts + 1):
            _throttle_before_request()
            try:
                response = original_get(*args, **kwargs)
                last_response = response
                if getattr(response, "status_code", None) != 429:
                    return response
                if attempt >= attempts:
                    return response
                wait_for = _retry_after_seconds(response, attempt)
                print(
                    "HTTP 429 from Untappd; backing off "
                    f"{wait_for:.1f}s before retry {attempt + 1}/{attempts}."
                )
                time.sleep(wait_for)
            except requests.RequestException as exc:
                last_exc = exc
                if attempt >= attempts:
                    raise
                wait_for = min(_float_env("UNTAPPD_HTTP_BACKOFF_CAP", 12.0), 0.75 * attempt)
                time.sleep(wait_for)

        if last_response is not None:
            return last_response
        if last_exc is not None:
            raise last_exc
        return original_get(*args, **kwargs)

    requests.get = guarded_get
    _PATCHED = True


_patch_requests_get()
