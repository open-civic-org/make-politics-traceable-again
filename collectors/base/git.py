from __future__ import annotations

import os
import subprocess
from functools import lru_cache


def get_git_commit_sha(*, override: str | None = None) -> str:
    """
    Return current HEAD SHA, an explicit override, or 'UNKNOWN'.

    Never raises solely because Git is unavailable.
    Set MPTA_GIT_COMMIT_SHA to force a value (tests / CI).
    """
    if override is not None:
        return override or "UNKNOWN"
    env = os.environ.get("MPTA_GIT_COMMIT_SHA")
    if env is not None:
        return env or "UNKNOWN"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            sha = result.stdout.strip()
            if sha:
                return sha
    except (OSError, subprocess.SubprocessError):
        pass
    return "UNKNOWN"


def get_git_dirty(*, override: bool | None = None) -> bool | None:
    """Return whether the working tree is dirty, or None if unknown."""
    if override is not None:
        return override
    env = os.environ.get("MPTA_GIT_DIRTY")
    if env is not None:
        return env.lower() in {"1", "true", "yes"}
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return None


@lru_cache
def cached_git_commit_sha() -> str:
    return get_git_commit_sha()
