import os
import subprocess

from forja.core.process import ProcessIdentity, creation_token, kill_leftover
from tests.core.process.support import minimal_env, python, wait_until_dead


def _sleeper() -> subprocess.Popen[bytes]:
    return subprocess.Popen(python("import time; time.sleep(60)"), env=minimal_env())


def test_creation_token_is_stable_for_a_live_process_and_none_for_a_missing_one() -> None:
    token = creation_token(os.getpid())
    assert token is not None
    assert creation_token(os.getpid()) == token

    child = _sleeper()
    child.kill()
    child.wait()
    assert creation_token(child.pid) is None


def test_leftover_with_matching_identity_is_killed() -> None:
    child = _sleeper()
    try:
        identity = ProcessIdentity(child.pid, creation_token(child.pid))
        assert kill_leftover(identity) is True
        assert wait_until_dead(child.pid)
    finally:
        child.kill()
        child.wait()


def test_a_reused_pid_with_another_creation_time_is_left_alone() -> None:
    child = _sleeper()
    try:
        token = creation_token(child.pid)
        assert token is not None
        assert kill_leftover(ProcessIdentity(child.pid, token + 1)) is False
        assert creation_token(child.pid) == token
    finally:
        child.kill()
        child.wait()


def test_identity_without_a_token_never_matches() -> None:
    child = _sleeper()
    try:
        assert kill_leftover(ProcessIdentity(child.pid, None)) is False
        assert creation_token(child.pid) is not None
    finally:
        child.kill()
        child.wait()
