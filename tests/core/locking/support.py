import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from forja.core.events.models import canonical_json
from forja.core.locking import DirectoryLockSettings, LockOwner
from forja.core.locking.directory import OWNER_FILE
from forja.core.process import creation_token
from tests.core.process.support import minimal_env

NO_SLEEP = DirectoryLockSettings(sleep=lambda seconds: None)


def dead_owner(**changes: object) -> LockOwner:
    """An owner record whose process really existed and is really gone."""
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"], env=minimal_env()
    )
    try:
        deadline = time.monotonic() + 10
        token = None
        while token is None and time.monotonic() < deadline:
            token = creation_token(child.pid)
            time.sleep(0.02)
        pid = child.pid
    finally:
        child.kill()
        child.wait()
    data = {
        "pid": pid,
        "machine": platform.node() or "unknown",
        "started_at": "2026-10-10T00:00:00.000000Z",
        "creation_token": token,
        "run_id": "dead-run",
        "nonce": "dead-nonce",
    }
    data.update(changes)
    return LockOwner.model_validate(data)


def write_lock(directory: Path, owner: LockOwner) -> None:
    """Lay out a lock directory as if ``owner`` had taken it."""
    directory.mkdir(parents=True)
    (directory / OWNER_FILE).write_bytes(canonical_json(json.loads(owner.model_dump_json())))


def age(path: Path, seconds: float) -> None:
    """Make a file or directory look ``seconds`` old."""
    past = time.time() - seconds
    os.utime(path, (past, past))
