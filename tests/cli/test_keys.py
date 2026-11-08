"""The terminal keys a run understands, by the character the terminal sends."""

import asyncio

import pytest

from forja.cli.keys import TerminalKeys


@pytest.mark.parametrize(
    ("char", "name"),
    [("\x0b", "ctrl+k"), ("\x03", "ctrl+c"), ("q", "q"), ("Q", "q"), ("t", "t"), ("T", "t")],
)
def test_a_known_character_reaches_the_run_by_its_name(char: str, name: str) -> None:
    async def go() -> str:
        keys = TerminalKeys()
        keys._loop = asyncio.get_running_loop()
        keys._put(char)
        return await asyncio.wait_for(keys._queue.get(), 1)

    assert asyncio.run(go()) == name


def test_an_unknown_character_is_ignored() -> None:
    async def go() -> bool:
        keys = TerminalKeys()
        keys._loop = asyncio.get_running_loop()
        keys._put("x")
        await asyncio.sleep(0)
        return keys._queue.empty()

    assert asyncio.run(go())
