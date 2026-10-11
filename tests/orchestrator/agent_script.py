"""Stand-in for an agent CLI: writes the files it is told to, in the current directory."""

import json
import sys
import time
from pathlib import Path


def main() -> None:
    files = json.loads(sys.argv[1])
    for name, content in files.items():
        target = Path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    print(f"wrote {len(files)} file(s)", flush=True)
    time.sleep(float(sys.argv[2]))


if __name__ == "__main__":
    main()
