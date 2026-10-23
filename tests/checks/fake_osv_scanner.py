"""A stand-in for osv-scanner: every ``-L`` file lists packages, one per line, as
``name version [vulns=ID,ID] [licenses=MIT,GPL-3.0]`` (`_` in a license is a space);
a file that says ``fail:N`` ends with N.

It follows the documented interface: ``scan``, ``--format json``, ``--output-file``, ``--licenses``
(licenses are reported only with it), ``-L``, and the exit codes 0 (nothing found), 1 (something
found) and 128 (no package). The JSON has ``results[].source.path`` and ``.packages[]`` with
``package{name,version,ecosystem}``, ``vulnerabilities[].id`` and ``licenses[]``.
"""

import json
import sys
from pathlib import Path
from typing import Any

FAILED = "fail:"


def main() -> int:
    args = sys.argv[1:]
    if args[0] != "scan":
        return 127
    output = Path(args[args.index("--output-file") + 1])
    licenses = any(arg.startswith("--licenses") for arg in args)
    files = [args[i + 1] for i, arg in enumerate(args) if arg == "-L"]
    results: list[dict[str, Any]] = []
    found = False
    counts: dict[str, int] = {}
    for name in files:
        text = Path(name).read_text(encoding="utf-8")
        if text.startswith(FAILED):
            return int(text.removeprefix(FAILED))
        packages = []
        for line in text.splitlines():
            fields = line.split()
            if len(fields) < 2:
                continue
            options = dict(field.split("=", 1) for field in fields[2:])
            vulns = [{"id": v} for v in options.get("vulns", "").split(",") if v]
            entry = {
                "package": {"name": fields[0], "version": fields[1], "ecosystem": "PyPI"},
                "vulnerabilities": vulns,
            }
            if licenses:
                entry["licenses"] = [
                    x.replace("_", " ") for x in options.get("licenses", "").split(",") if x
                ]
            found = found or bool(vulns)
            for license_name in options.get("licenses", "").split(","):
                if license_name:
                    counts[license_name.replace("_", " ")] = (
                        counts.get(license_name.replace("_", " "), 0) + 1
                    )
            if "unlisted" not in options:  # a package the scanner leaves out of its list
                packages.append(entry)
        results.append({"source": {"path": str(Path(name).resolve()), "type": "lockfile"},
                        "packages": packages})  # fmt: skip
    if not any(result["packages"] for result in results) and not counts:
        return 128
    document: dict[str, Any] = {"results": results}
    if licenses:
        document["license_summary"] = [{"name": n, "count": c} for n, c in counts.items()]
    output.write_text(json.dumps(document), encoding="utf-8")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
