"""A stand-in for the CLI. It does what a JSON script says: record how it was called, write files,
print lines, wait, exit. The script is named by FAKE_CLAUDE_SCRIPT.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

script = json.loads(Path(os.environ["FAKE_CLAUDE_SCRIPT"]).read_text(encoding="utf-8"))
package = sys.stdin.buffer.read().decode("utf-8")
Path(script["record"]).write_text(
    json.dumps(
        {"argv": sys.argv[1:], "cwd": os.getcwd(), "env": sorted(os.environ), "stdin": package}
    ),
    encoding="utf-8",
)
for name, content in script.get("writes", {}).items():
    target = Path(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
if "saida" in script:
    saida = script["saida"]
    text = saida if isinstance(saida, str) else json.dumps(saida)
    Path(".forja-agent").mkdir(exist_ok=True)
    Path(".forja-agent/saida.json").write_text(text, encoding="utf-8")
ran = []
for item in script.get("run", []):
    done = subprocess.run(item["cmd"], capture_output=True, text=True, check=False)
    ran.append({"cmd": item["cmd"], "code": done.returncode, "out": done.stdout + done.stderr})
if "run" in script:
    Path(script["ran"]).write_text(json.dumps(ran), encoding="utf-8")
for text in script.get("lines", []):
    print(text, flush=True)
if script.get("stderr"):
    print(script["stderr"], file=sys.stderr, flush=True)
time.sleep(script.get("sleep", 0))
sys.exit(script.get("exit", 0))
