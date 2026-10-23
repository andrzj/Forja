"""Gate 6: a proxy on loopback that refuses every request and remembers where it was headed.

Forja creates no sandbox, so it cannot cut the network. It points the proxy variables of the
process under test here instead: a client that honours them and tries to leave loopback lands in
the trap, which keeps only the destination (host and port, never the path) and answers 403.
A client that ignores the proxy is not seen; that limit belongs in the summary.
"""

import asyncio
from types import TracebackType
from typing import Self
from urllib.parse import urlsplit

MAX_REQUEST_LINE = 2048
READ_TIMEOUT = 2.0
UNKNOWN = "unknown"
_REFUSAL = b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
_DEFAULT_PORTS = {"http": 80, "https": 443}


def destination_of(line: str) -> str:
    """``host:port`` a proxy request line asks for, or ``unknown`` when it cannot be read.

    The line is ``CONNECT host:port HTTP/1.1`` or ``GET http://host[:port]/path HTTP/1.1``.
    """
    parts = line.split()
    if len(parts) < 2:
        return UNKNOWN
    method, target = parts[0].upper(), parts[1]
    try:
        if method == "CONNECT":
            parsed = urlsplit("//" + target)
            host, port = parsed.hostname, parsed.port
        else:
            parsed = urlsplit(target)
            host = parsed.hostname
            port = parsed.port or _DEFAULT_PORTS.get(parsed.scheme)
    except ValueError:
        return UNKNOWN
    if not host or port is None:
        return UNKNOWN
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


class NetworkTrap:
    """Use as ``async with NetworkTrap() as trap``; ``trap.url`` is the proxy to hand out."""

    def __init__(self) -> None:
        self._server: asyncio.Server | None = None
        self._seen: list[str] = []
        self._port = 0

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    @property
    def destinations(self) -> tuple[str, ...]:
        """Where the clients were headed, in order of first attempt, without repeats."""
        return tuple(dict.fromkeys(self._seen))

    async def __aenter__(self) -> Self:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        self._port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            try:
                raw = await asyncio.wait_for(reader.read(MAX_REQUEST_LINE), READ_TIMEOUT)
            except (TimeoutError, ConnectionError):
                raw = b""
            line = raw.split(b"\n", 1)[0].decode("latin-1").strip()
            self._seen.append(destination_of(line))
            writer.write(_REFUSAL)
            await writer.drain()
        except ConnectionError:
            pass
        finally:
            writer.close()
