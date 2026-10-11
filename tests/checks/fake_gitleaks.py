"""A stand-in for gitleaks: reads stdin, calls any line holding FAKE-SECRET a leak.

It follows the documented interface: ``stdin`` subcommand, ``--exit-code`` for leaks, and a JSON
report with ``RuleID`` and ``StartLine`` written to ``--report-path``.
"""

import json
import sys


def main() -> int:
    args = sys.argv[1:]
    if args[0] != "stdin":
        return 1
    options = dict(zip(args[1::2], args[2::2], strict=False))
    exit_code = int(options.get("--exit-code", "1"))
    leaks = [
        {"RuleID": "fake-rule", "StartLine": number, "Secret": "REDACTED"}
        for number, line in enumerate(sys.stdin.read().split("\n"), start=1)
        if "FAKE-SECRET" in line
    ]
    if "--report-path" in options:
        with open(options["--report-path"], "w", encoding="utf-8") as report:
            json.dump(leaks, report)
    return exit_code if leaks else 0


if __name__ == "__main__":
    sys.exit(main())
