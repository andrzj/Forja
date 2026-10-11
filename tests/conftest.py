"""Which tests run in which setting.

``slow`` and ``integration`` are marks on whole modules. ``FORJA_FAST=1`` leaves the integration
tests out, for mutation testing of the modules whose logic has its own fast tests; the default
run keeps them.
"""

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not os.environ.get("FORJA_FAST"):
        return
    dropped = [item for item in items if item.get_closest_marker("integration")]
    if dropped:
        items[:] = [item for item in items if item not in dropped]
        config.hook.pytest_deselected(items=dropped)
