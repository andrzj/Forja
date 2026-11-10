"""Gera capturas PNG do terminal real da Forja (ConPTY + pyte + Pillow).

Uso: uv run --group capturas python scripts/capturas/terminal.py [cenario ...]
Sem argumentos, roda todos os cenários baratos (sem CLI de agente). O cenário
`execucao` roda a Forja de verdade com o claude-code num repositório descartável
e gasta cota da CLI: só roda se for pedido pelo nome.
Grava em docs/guia/imagens/. A execução real também grava o resumo.md em
docs/guia/imagens/resumo-execucao.md (texto, para colar no guia).
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pyte
from PIL import Image, ImageDraw, ImageFont
from winpty import PtyProcess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "guia" / "imagens"
FORJA = Path(sys.executable).parent / "forja.exe"
COLS = 170
FONT_PATHS = [r"C:\Windows\Fonts\CascadiaMono.ttf", r"C:\Windows\Fonts\consola.ttf"]
FONT_SIZE = 16
PAD = 12
DEFAULT_FG, DEFAULT_BG = "d4d4d4", "1e1e1e"
ANSI = {
    "black": "000000", "red": "cd3131", "green": "0dbc79", "brown": "e5e510",
    "yellow": "e5e510", "blue": "2472c8", "magenta": "bc3fbc", "cyan": "11a8cd",
    "white": "e5e5e5", "brightblack": "666666", "brightred": "f14c4c",
    "brightgreen": "23d18b", "brightbrown": "f5f543", "brightyellow": "f5f543",
    "brightblue": "3b8eea", "brightmagenta": "d670d6", "brightcyan": "29b8db",
    "brightwhite": "ffffff",
}
SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{10,}|api[_-]?key|token\s*[:=]\s*\S{12,}|ghp_\w+)", re.I)
HOME = str(Path.home())
USER = Path.home().name


def _color(name: str, default: str) -> str:
    if name == "default":
        return default
    if name in ANSI:
        return ANSI[name]
    return name if re.fullmatch(r"[0-9a-fA-F]{6}", name) else default


def _font() -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS:
        if Path(path).exists():
            return ImageFont.truetype(path, FONT_SIZE)
    raise SystemExit("nenhuma fonte monoespacada encontrada em C:\\Windows\\Fonts")


def _lines(screen: pyte.Screen) -> list[list[pyte.screens.Char]]:
    """Cells of each row, with the user name and home path hidden in place."""
    rows = []
    for y in range(screen.lines):
        cells = [screen.buffer[y][x] for x in range(screen.columns)]
        text = "".join(c.data or " " for c in cells)
        for secret in (HOME, USER):
            while (at := text.find(secret)) >= 0:
                new = "C:\\Users\\dev" if secret == HOME else "dev"
                cells[at : at + len(secret)] = (
                    [cells[at]._replace(data=ch) for ch in new]
                )
                cells += [cells[-1]._replace(data=" ")] * (len(secret) - len(new))
                text = "".join(c.data or " " for c in cells)
                if secret == USER and new in text and USER in new:
                    break
        rows.append(cells[: screen.columns])
    return rows


def render(screen: pyte.Screen, out: Path, rows: int | None = None) -> None:
    lines = _lines(screen)
    plain = "\n".join("".join(c.data or " " for c in line) for line in lines)
    if SECRET.search(plain):
        raise SystemExit(f"{out.name}: a tela parece conter segredo; captura recusada")
    while lines and not "".join(c.data for c in lines[-1]).strip():
        lines.pop()
    lines = lines[: rows or len(lines)] or lines[:1]
    font = _font()
    cw = round(font.getlength("M"))
    ch = FONT_SIZE + 6
    size = (cw * screen.columns + 2 * PAD, ch * len(lines) + 2 * PAD)
    img = Image.new("RGB", size, "#" + DEFAULT_BG)
    draw = ImageDraw.Draw(img)
    for y, line in enumerate(lines):
        for x, cell in enumerate(line):
            fg, bg = _color(cell.fg, DEFAULT_FG), _color(cell.bg, DEFAULT_BG)
            if cell.reverse:
                fg, bg = bg, fg
            px, py = PAD + x * cw, PAD + y * ch
            if bg != DEFAULT_BG:
                draw.rectangle([px, py, px + cw - 1, py + ch - 1], fill="#" + bg)
            if cell.data.strip():
                draw.text((px, py + 2), cell.data, font=font, fill="#" + fg)
                if cell.bold:
                    draw.text((px + 1, py + 2), cell.data, font=font, fill="#" + fg)
            if cell.underscore:
                draw.line([px, py + ch - 2, px + cw, py + ch - 2], fill="#" + fg)
    img.save(out)
    print(f"gravado {out.relative_to(ROOT)}")


def run(
    argv: list[str],
    cwd: Path,
    *,
    rows: int,
    timeout: float = 60,
    snapshot: tuple[Callable[[str], bool], Path] | None = None,
    final: Path | None = None,
    done: Callable[[str], bool] | None = None,
    env: dict[str, str] | None = None,
) -> pyte.Screen:
    """Runs ``argv`` in a ConPTY of COLS x rows; saves PNGs at the snapshot and at the end."""
    screen = pyte.Screen(COLS, rows)
    stream = pyte.Stream(screen)
    proc = PtyProcess.spawn(
        argv, cwd=str(cwd), dimensions=(rows, COLS), env={**os.environ, **(env or {})}
    )
    lock = threading.Lock()

    def pump() -> None:
        while True:
            try:
                data = proc.read(65536)
            except (EOFError, OSError):
                return
            if not data:
                return
            with lock:
                stream.feed(data)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    taken = snapshot is None
    finished = False
    deadline = time.monotonic() + timeout
    while proc.isalive() and time.monotonic() < deadline:
        time.sleep(0.5)
        with lock:
            text = "\n".join(screen.display)
        if done and done(text):
            time.sleep(2)
            finished = True
            break
        if not taken and snapshot and snapshot[0](text):
            with lock:
                render(screen, snapshot[1])
            taken = True
    timed_out = proc.isalive() and not finished
    with lock:
        if final:
            render(screen, final)
    if finished:
        proc.write("q")
        time.sleep(3)
    if proc.isalive():
        proc.terminate(force=True)
    reader.join(2)
    if timed_out:
        print(f"aviso: {argv[1:3]} passou do timeout de {timeout:.0f}s")
    return screen


def temp_repo(root: Path, files: dict[str, str]) -> Path:
    repo = root / "exemplo"
    repo.mkdir()
    for name, body in files.items():
        (repo / name).write_text(body, encoding="utf-8")
    git = ["git", "-c", "user.name=Exemplo", "-c", "user.email=exemplo@example.com"]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "inicio"], cwd=repo, check=True)
    return repo


BUG = {
    "pyproject.toml": (
        '[project]\nname = "exemplo"\nversion = "0.1.0"\nrequires-python = ">=3.12"\n'
    ),
    "calculadora.py": "def soma(a, b):\n    return a - b\n",
    "test_calculadora.py": (
        "from calculadora import soma\n\n\ndef test_soma():\n    assert soma(0, 0) == 0\n"
    ),
}


def ajuda(tmp: Path) -> None:
    run([str(FORJA), "--help"], tmp, rows=48, timeout=30, final=OUT / "terminal-ajuda.png")


def doctor(tmp: Path) -> None:
    repo = temp_repo(tmp, BUG)
    run([str(FORJA), "doctor"], repo, rows=22, timeout=180, final=OUT / "terminal-doctor.png")


def instalar_ajuda(tmp: Path) -> None:
    run(
        [str(FORJA), "instalar", "--help"],
        tmp,
        rows=20,
        timeout=30,
        final=OUT / "terminal-instalar-ajuda.png",
    )


def corrigir_plano(tmp: Path) -> None:
    repo = temp_repo(tmp, BUG)
    run(
        [str(FORJA), "corrigir", "soma(2, 3) devolve -1 em vez de 5", "--plano"],
        repo, rows=40, timeout=60, final=OUT / "terminal-corrigir-plano.png",
    )


def modo_ci_plano(tmp: Path) -> None:
    toml = (
        'objetivo = "corrigir"\ndescricao = "soma(2, 3) devolve -1 em vez de 5"\n'
        'tarefas = 1\n\n[interface]\nmodo = "texto"\nascii = true\n'
    )
    repo = temp_repo(tmp, {**BUG, "execucao.toml": toml})
    run(
        [str(FORJA), "--config", "execucao.toml", "--plano"],
        repo, rows=40, timeout=60, final=OUT / "terminal-modo-ci-plano.png",
    )


def execucao(tmp: Path) -> None:
    """Execução real e curta com o claude-code: gasta cota da CLI."""
    toml = (
        'objetivo = "corrigir"\ndescricao = "soma(2, 3) devolve -1 em vez de 5"\n'
        'cli = "claude-code"\ntokens = 400000\ntarefas = 1\n'
    )
    repo = temp_repo(tmp, {**BUG, "execucao.toml": toml})
    home = tmp / "forja-home"
    started = time.monotonic()
    screen = run(
        [str(FORJA), "--config", "execucao.toml"],
        repo, rows=44, timeout=1500,
        snapshot=(lambda t: time.monotonic() - started > 25 and bool(t.strip()),
                  OUT / "terminal-execucao-meio.png"),
        final=OUT / "terminal-execucao-fim.png",
        done=lambda t: "Fim da execução" in t,
        env={"FORJA_HOME": str(home)},
    )
    print("\n".join(line.rstrip() for line in screen.display if line.strip()))
    for resumo in home.rglob("resumo.md"):
        texto = resumo.read_text(encoding="utf-8").replace(USER, "dev")
        (OUT / "resumo-execucao.md").write_text(texto, encoding="utf-8")
        print(f"gravado resumo de {resumo}")
        break


CENARIOS = {
    "ajuda": ajuda,
    "doctor": doctor,
    "instalar-ajuda": instalar_ajuda,
    "corrigir-plano": corrigir_plano,
    "modo-ci-plano": modo_ci_plano,
}
CARO = {"execucao": execucao}


def main() -> None:
    nomes = sys.argv[1:] or list(CENARIOS)
    todos = {**CENARIOS, **CARO}
    OUT.mkdir(parents=True, exist_ok=True)
    for nome in nomes:
        tmp = Path(tempfile.mkdtemp(prefix="forja-captura-"))
        try:
            todos[nome](tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
