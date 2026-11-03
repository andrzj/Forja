"""A stand-in for jscpd: two files that hold a line with FAKE-DUP are a clone of each other.

It follows the documented interface: ``--config <file>`` (keys ``minTokens``, ``minLines``,
``ignore``), ``-r json``, ``-o <dir>`` and ``--baseline-from-ref <ref>``, and a
``jscpd-report.json`` with ``duplicates[]``. With a ref, a clone is old when both files held the
marker there. It records what it was called with in ``argv.json`` next to the report. A file
``jscpd-fail`` in the working directory holds an exit code to end with; ``jscpd-garbage`` makes the
report unreadable and ``jscpd-silent`` writes none.
"""

import fnmatch
import json
import subprocess
import sys
from pathlib import Path

MARKER = "FAKE-DUP"


def held_at(ref: str, name: str) -> bool:
    shown = subprocess.run(["git", "show", f"{ref}:{name}"], capture_output=True, text=True)
    return shown.returncode == 0 and MARKER in shown.stdout


def main() -> int:
    args = sys.argv[1:]
    here = Path.cwd()
    config = json.loads(Path(args[args.index("--config") + 1]).read_text(encoding="utf-8"))
    out = Path(args[args.index("-o") + 1])
    ref = args[args.index("--baseline-from-ref") + 1] if "--baseline-from-ref" in args else None
    (out / "argv.json").write_text(json.dumps({"args": args, "config": config}), encoding="utf-8")
    if (here / "jscpd-fail").exists():
        return int((here / "jscpd-fail").read_text(encoding="utf-8"))
    if (here / "jscpd-silent").exists():
        return 0
    if (here / "jscpd-garbage").exists():
        (out / "jscpd-report.json").write_text("not json", encoding="utf-8")
        return 0
    holders = sorted(
        name
        for name in (p.relative_to(here).as_posix() for p in here.rglob("*") if p.is_file())
        if not name.startswith(".git/")
        and not any(fnmatch.fnmatch(name, glob) for glob in config["ignore"])
        and MARKER in (here / name).read_text(encoding="utf-8")
    )
    clones = []
    for index, first in enumerate(holders):
        for second in holders[index + 1 :]:
            old = ref is not None and held_at(ref, first) and held_at(ref, second)
            clones.append(
                {
                    "format": "python",
                    "kind": "exact",
                    "isNew": not old if ref is not None else False,
                    "lines": config["minLines"] + 1,
                    "tokens": config["minTokens"] + 1,
                    "firstFile": place(here, first),
                    "secondFile": place(here, second),
                }
            )
    report = {"duplicates": clones, "statistics": {}}
    (out / "jscpd-report.json").write_text(json.dumps(report), encoding="utf-8")
    return 0


def place(here: Path, name: str) -> dict[str, object]:
    text = (here / name).read_text(encoding="utf-8").split("\n")
    line = next(number for number, row in enumerate(text, start=1) if MARKER in row)
    return {
        "name": name,
        "start": line,
        "end": line + 5,
        "startLoc": {"line": line, "column": 1, "position": 0},
        "endLoc": {"line": line + 5, "column": 1, "position": 0},
    }


if __name__ == "__main__":
    sys.exit(main())
