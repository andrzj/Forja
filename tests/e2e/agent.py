"""Stand-in for a coding-agent CLI: writes one file in the current directory, then exits."""

import sys
import time
from pathlib import Path


def main() -> None:
    name, content, pause = sys.argv[1], sys.argv[2], float(sys.argv[3])
    Path(name).write_text(content, encoding="utf-8")
    print(f"wrote {name}", flush=True)
    time.sleep(pause)


if __name__ == "__main__":
    main()
