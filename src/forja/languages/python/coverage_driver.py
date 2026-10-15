"""Runs pytest under coverage.py and writes one JSON report, in a single process.

It is run as a script by the repository's own interpreter, which has pytest and coverage.py but
not Forja, so it imports nothing of Forja's. Usage:

    python coverage_driver.py --report <path> -- <pytest arguments>

Coverage is recorded per test (the context is the test's node id), so the report says which
tests ran each line. The report is written even when tests fail: coverage of a failing run is
still coverage. The exit code is pytest's.
"""

import os
import sys
from pathlib import Path
from typing import Any


class _PerTest:
    """Names the coverage context after the test's node id (``tests/test_a.py::test_x``).

    coverage.py's own ``test_function`` context says ``test_a.test_x``, with no directory: it
    cannot tell which file to run. The node id can.
    """

    def __init__(self, recorder: Any) -> None:
        self._recorder = recorder

    def pytest_runtest_setup(self, item: Any) -> None:
        self._recorder.switch_context(item.nodeid)


def main(argv: list[str]) -> int:
    if len(argv) < 4 or argv[0] != "--report" or argv[2] != "--":
        sys.stderr.write("usage: coverage_driver.py --report <path> -- <pytest arguments>\n")
        return 2
    report = Path(argv[1])
    pytest_arguments = argv[3:]

    import coverage
    import pytest

    # "python -m pytest" puts the working directory first on the path; a script does not
    sys.path.insert(0, os.getcwd())
    recorder = coverage.Coverage(data_file=None, config_file=True)
    recorder.start()
    try:
        code = int(pytest.main(pytest_arguments, plugins=[_PerTest(recorder)]))
    finally:
        recorder.stop()
        report.parent.mkdir(parents=True, exist_ok=True)
        recorder.json_report(outfile=str(report), show_contexts=True, ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
