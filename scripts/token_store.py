#!/usr/bin/env python3
"""Shared helpers for safely reading and writing EVE token state."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager

if os.name == "nt":
    import msvcrt

    def _lock(file_obj):
        msvcrt.locking(file_obj.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock(file_obj):
        msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(file_obj):
        fcntl.flock(file_obj, fcntl.LOCK_EX)

    def _unlock(file_obj):
        fcntl.flock(file_obj, fcntl.LOCK_UN)


def get_tokens_file() -> str:
    return os.path.join(
        os.environ.get("OPENCLAW_STATE_DIR", os.path.expanduser("~/.openclaw")),
        "eve-tokens.json",
    )


def _get_lock_file() -> str:
    return get_tokens_file() + ".lock"


def _ensure_state_dir():
    os.makedirs(os.path.dirname(get_tokens_file()), exist_ok=True)


@contextmanager
def token_file_lock():
    """Serialize all token file mutations across scripts/processes."""
    _ensure_state_dir()
    lock_file = open(_get_lock_file(), "a+")
    try:
        _lock(lock_file)
        yield
    finally:
        _unlock(lock_file)
        lock_file.close()


def load_tokens() -> dict:
    """Load the token file if present, otherwise return an empty structure."""
    tokens_file = get_tokens_file()
    if os.path.exists(tokens_file):
        with open(tokens_file, encoding="utf-8") as handle:
            return json.load(handle)
    return {"characters": {}}


def save_tokens_unlocked(data: dict):
    """Atomically persist token data. Caller must already hold the lock."""
    tokens_file = get_tokens_file()
    _ensure_state_dir()
    tmp_file = tokens_file + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    os.chmod(tmp_file, 0o600)
    os.replace(tmp_file, tokens_file)


def save_tokens(data: dict):
    """Lock and atomically persist token data."""
    with token_file_lock():
        save_tokens_unlocked(data)
