"""A stand-in for a repository's E2E command: ``net`` in the mode knocks on the network through
the proxy the process was given; ``fail`` exits 1, ``gone`` exits 3 and anything else exits 0."""

import contextlib
import sys
import urllib.request

mode = sys.argv[1]
if "net" in mode:
    with contextlib.suppress(Exception):  # the trap answers 403; the point is that it was asked
        urllib.request.urlopen("http://blocked.test/p", timeout=5)  # noqa: S310
sys.exit(1 if "fail" in mode else 3 if "gone" in mode else 0)
