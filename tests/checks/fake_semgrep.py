"""A stand-in for semgrep: reports a finding for each line holding FAKE-FINDING (rule fake-rule)
or FAKE-OTHER (rule other-rule) in the files it is given.

It follows the documented interface: ``scan``, ``--config``, ``--json-output=<file>``, and a JSON
report with ``results[].check_id``, ``path``, ``start`` and ``end``. A config file whose text is
``fail:N`` makes it end with code N before reporting.
"""

import json
import sys
from pathlib import Path

RULES = {"FAKE-FINDING": "fake-rule", "FAKE-OTHER": "other-rule"}


def main() -> int:
    args = sys.argv[1:]
    if args[0] != "scan":
        return 2
    config = Path(args[args.index("--config") + 1]).read_text(encoding="utf-8")
    if config.startswith("fail:"):
        return int(config.removeprefix("fail:"))
    output = next(a for a in args if a.startswith("--json-output=")).split("=", 1)[1]
    files = args[args.index("--quiet") + 1 :]
    results = []
    for path in files:
        text = Path(path).read_text(encoding="utf-8")
        for number, line in enumerate(text.split("\n"), start=1):
            for marker, rule in RULES.items():
                if marker in line:
                    place = {"line": number, "col": 1, "offset": 0}
                    results.append(
                        {
                            "check_id": rule,
                            "path": path,
                            "start": place,
                            "end": place,
                            "extra": {"message": "fake", "severity": "WARNING"},
                        }
                    )
    with open(output, "w", encoding="utf-8") as report:
        json.dump({"results": results, "errors": []}, report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
