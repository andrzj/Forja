"""Runs one execution of the experiment of ``docs/medicao-2.md`` and judges what it delivered.

    python run.py plan                       the shuffled order of every execution
    python run.py one <repo> <arm> <rep>     one execution, judged, appended to results.jsonl
    python run.py batch                      every execution not yet done, in the planned order
    python run.py report                     the numbers so far

Arm ``A`` is the CLI with one fixed prompt; arm ``B`` is the Forja. Both get the same tools, the
same interpreter and the same ceiling of tokens. Everything is written under ``MEDICAO_DIR``
(default: the local application data of the user), never in the repository.
"""

import asyncio
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

import evaluate  # noqa: E402
import repos  # noqa: E402

from forja.core.adapters.common import build_spec  # noqa: E402
from forja.core.adapters.executor import (  # noqa: E402
    AGENT_DIR,
    AgentRequest,
    ErrorActivity,
    RolePermissions,
    UsageActivity,
    locate_in_path,
)
from forja.core.artifacts.models import Producer  # noqa: E402
from forja.core.isolation import git_blocking_environment  # noqa: E402
from forja.core.process import ProcessRunner  # noqa: E402
from forja.executors import ClaudeCodeAdapter  # noqa: E402

SEED = 20261012
REPETITIONS = 3
ARMS = ("A", "B")
FACADE = ("forja agente lint", "forja agente medir", "forja agente testar")
PROMPT = (
    "Reduza a complexidade ciclomática de toda função deste repositório que esteja acima de 15, "
    "sem mudar o comportamento: mesmos resultados, mesmos nomes públicos, mesmos efeitos. Não "
    "altere testes nem dependências. Você pode rodar `forja agente testar`, `forja agente lint` e "
    "`forja agente medir`. Rode os testes e o lint ao terminar e deixe tudo passando.\n"
)
DEFAULT_TOKENS = 200_000
TIMEOUT = 3600


def work_dir() -> Path:
    base = os.environ.get("MEDICAO_DIR") or str(
        Path(os.environ.get("LOCALAPPDATA", Path.home())) / "forja-medicao"
    )
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def environment() -> dict[str, str]:
    """The same for both arms: the interpreter of this project first, so `python` has pytest."""
    scripts = str(Path(sys.executable).parent)
    env = dict(os.environ)
    env["PATH"] = scripts + os.pathsep + env.get("PATH", "")
    return env


def plan() -> list[tuple[str, str, int]]:
    order = [(r, arm, n) for r in repos.ALL for arm in ARMS for n in range(1, REPETITIONS + 1)]
    random.Random(SEED).shuffle(order)
    return order


class Counting:
    """Reads the CLI's output as the Forja does: tokens sent and written, and any error."""

    def __init__(self, adapter: ClaudeCodeAdapter) -> None:
        self.adapter, self.tokens, self.error = adapter, 0, ""

    def intent(self, operation_id: str, details: object) -> None:
        pass

    def started(self, operation_id: str, identity: object) -> None:
        pass

    def effect(self, operation_id: str, details: object) -> None:
        pass

    def progress(self, operation_id: str, channel: str, line: str) -> None:
        if channel != "out":
            return
        activity = self.adapter.parse_event(line)
        if isinstance(activity, UsageActivity):
            self.tokens += (activity.input_tokens or 0) + (activity.output_tokens or 0)
        elif isinstance(activity, ErrorActivity):
            self.error = activity.message


async def arm_a(repo: Path, out: Path, env: dict[str, str], executable: Path) -> dict[str, object]:
    adapter = ClaudeCodeAdapter()
    permissions = RolePermissions(can_edit_files=True, allowed_commands=FACADE)
    work = out / "tree-a"
    shutil.copytree(repo, work, ignore=shutil.ignore_patterns(".git"))
    agent = work / AGENT_DIR
    agent.mkdir()
    setup = adapter.permission_setup(Producer.IMPLEMENTER, permissions)
    for name, data in setup.files.items():
        (agent / name).write_bytes(data)
    (agent / "package.md").write_text(PROMPT, encoding="utf-8", newline="\n")
    request = AgentRequest(Producer.IMPLEMENTER, agent / "package.md", work, permissions)
    plan_ = adapter.plan_invocation(request, setup, executable)
    plan_ = replace(plan_, env_set={**plan_.env_set, **git_blocking_environment(work)})
    python = locate_in_path("python", env["PATH"]) or sys.executable
    spec = build_spec(plan_, {**env, "FORJA_AGENT_PYTHON": str(python)}, timeout=TIMEOUT)
    counting = Counting(adapter)
    started = time.monotonic()
    result = await ProcessRunner(counting).run("arm-a", spec, out / "arm-a.log")  # type: ignore[arg-type]
    seconds = time.monotonic() - started
    shutil.rmtree(agent, ignore_errors=True)
    return {
        "tree": str(work), "tokens": counting.tokens, "seconds": round(seconds),
        "attempts": 1, "ended": result.outcome.value, "cli_error": counting.error,
    }  # fmt: skip


def arm_b(
    repo: Path, out: Path, env: dict[str, str], executable: Path, tokens: int
) -> dict[str, object]:
    config = out / "forja-config.toml"
    config.write_text(
        'objetivo = "refatorar"\ndescricao = ""\narquivo = ""\ncli = "claude-code"\n'
        f"executavel = {json.dumps(str(executable))}\nescopo = []\ntokens = {tokens}\n"
        'agente_roda_testes = true\ntarefas = 5\nbase = ""\n\n[interface]\nmodo = "texto"\n'
        'tema = ""\nascii = false\nredimensionar = false\n',
        encoding="utf-8",
    )
    started = time.monotonic()
    try:
        done = subprocess.run(
            [sys.executable, "-m", "forja", "--config", str(config), "refatorar"],
            cwd=repo, env=env, capture_output=True, text=True, timeout=TIMEOUT,
            encoding="utf-8", errors="replace",
        )  # fmt: skip
        code, text = done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired as error:
        code, text = 124, str(error.stdout or "")
    seconds = time.monotonic() - started
    (out / "forja-output.txt").write_text(text, encoding="utf-8")
    branch = re.search(r"forja-run/[0-9a-f]+", text)
    summary = re.search(r"summary in (\S.*?resumo\.md)", text) or re.search(
        r"Resumo: (\S.*?resumo\.md)", text
    )
    spent = 0
    if summary:
        events = Path(summary.group(1)).with_name("events.jsonl")
        if events.exists():
            from forja.orchestrator.budget import read_consumption  # noqa: PLC0415

            spent = read_consumption(events).tokens
    info: dict[str, object] = {
        "tokens": spent, "seconds": round(seconds), "exit_code": code,
        "attempts": len(re.findall(r"^\S*\s*tentativa \d+/\d+", text, re.MULTILINE)),
        "branch": branch.group(0) if branch else "",
    }  # fmt: skip
    if branch and code in (0, 4):
        tree = out / "tree-b"
        repos.git(repo, "worktree", "add", "--detach", str(tree), branch.group(0))
        info["tree"] = str(tree)
    return info


def one(name: str, arm: str, rep: int, tokens: int = DEFAULT_TOKENS) -> dict[str, object]:
    out = work_dir() / f"{name}-{arm}{rep}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    initial = repos.materialize(name, out / "initial")
    env = environment()
    executable = locate_in_path("claude", env["PATH"])
    if executable is None:
        raise SystemExit("claude not found on PATH")
    if arm == "A":
        info = asyncio.run(arm_a(initial, out, env, executable))
    else:
        repo = repos.materialize(name, out / "repo-b")
        info = arm_b(repo, out, env, executable, tokens)
    base: dict[str, object] = {"repo": name, "arm": arm, "rep": rep, **info}
    tree = info.get("tree")
    if tree:
        verdict = evaluate.evaluate(name, initial, Path(str(tree)))
    else:
        verdict = {"accepted": False, "failed_criteria": ["nothing delivered"], "regression": False}
    over = int(str(info.get("tokens", 0))) > tokens
    base.update(verdict)
    base["over_budget"] = over
    base["accepted"] = bool(verdict["accepted"]) and not over
    with (work_dir() / "results.jsonl").open("a", encoding="utf-8") as results:
        results.write(json.dumps(base) + "\n")
    return base


def report() -> str:
    path = work_dir() / "results.jsonl"
    rows = (
        [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if path.exists()
        else []
    )
    lines = []
    for arm in ARMS:
        mine = [r for r in rows if r["arm"] == arm and r["rep"] >= 1]  # rep 0 is a pilot
        if not mine:
            continue
        accepted = sum(1 for r in mine if r["accepted"])
        regressions = sum(1 for r in mine if r.get("regression"))
        tokens = sum(int(r.get("tokens", 0)) for r in mine)
        seconds = sum(int(r.get("seconds", 0)) for r in mine)
        lines.append(
            f"arm {arm}: {len(mine)} runs, accepted {accepted}, with regression {regressions}, "
            f"tokens {tokens} (mean {tokens // len(mine)}), "
            f"seconds {seconds} (mean {seconds // len(mine)})"
        )
    return "\n".join(lines) or "no results yet"


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if command == "plan":
        for item in plan():
            print(*item)
    elif command == "one":
        budget = int(os.environ.get("MEDICAO_TOKENS", DEFAULT_TOKENS))
        print(json.dumps(one(sys.argv[2], sys.argv[3].upper(), int(sys.argv[4]), budget), indent=1))
    elif command == "batch":
        budget = int(os.environ.get("MEDICAO_TOKENS", DEFAULT_TOKENS))
        done = (
            {
                (r["repo"], r["arm"], r["rep"])
                for r in map(
                    json.loads, (work_dir() / "results.jsonl").read_text("utf-8").splitlines()
                )
            }
            if (work_dir() / "results.jsonl").exists()
            else set()
        )
        for item in plan():
            if item in done:
                continue
            row = one(*item, budget)
            print(item, "accepted" if row["accepted"] else row["failed_criteria"], flush=True)
    elif command == "report":
        print(report())
    else:
        raise SystemExit(__doc__)
