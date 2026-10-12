"""The characterization oracle: what the original code does on a grid of inputs.

``record`` runs the grid against the original repository and writes what came back (value or
exception, and what the call changed in its arguments). ``verify`` runs the same grid against the
tree an arm delivered and lists the cases whose outcome is not the recorded one. The grid lives
here, outside the repositories, so no arm ever sees it.

    python oracle.py record <repo> <repo_path> <golden.json>
    python oracle.py verify <repo> <repo_path> <golden.json>
"""

import copy
import importlib
import itertools
import json
import random
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

Case = tuple[str, Callable[[], tuple[Callable[..., object], tuple[object, ...], list[object]]]]


def outcome(
    function: Callable[..., object], args: tuple[object, ...], watched: list[object]
) -> str:
    """What one call did: its value or its exception, and the arguments afterwards."""
    try:
        done = "ok " + repr(function(*args))
    except BaseException as error:  # noqa: BLE001 - the exception is the thing being recorded
        done = f"err {type(error).__name__}: {error}"
    return f"{done} | after {watched!r}"


# -- inventory ---------------------------------------------------------------------------------


def inventory_cases() -> Iterator[Case]:
    from inventory import classify, final_price, reserve  # noqa: PLC0415

    customers: list[object] = [
        {},
        {"kind": "retail"},
        {"kind": "retail", "loyal": True},
        {"kind": "retail", "loyal": True, "years": 2},
        {"kind": "retail", "loyal": True, "years": 5},
        {"kind": "retail", "loyal": True, "years": 9},
        {"kind": "wholesale"},
        {"kind": "staff"},
        {"kind": "staff", "probation": True},
        {"kind": "partner"},
        {"kind": "partner", "contract": "gold"},
        {"kind": "partner", "contract": "silver"},
        {"kind": "partner", "contract": "bronze"},
        {"kind": "alien"},
        {"kind": "retail", "blocked": True},
        {"kind": "alien", "blocked": True},
        None,
    ]
    grid = itertools.product(
        [0, 1, 9.99, 10, 33.333, -1],
        [1, 2, 9, 10, 49, 50, 99, 100, 101, 0, -3, True, 2.5, "3"],
        range(len(customers)),
        [None, "SAVE5", "HALF", "FREESHIP", "BOGUS"],
    )
    for index, (base, qty, who, coupon) in enumerate(grid):
        yield (
            f"final_price:{index}",
            lambda base=base, qty=qty, who=who, coupon=coupon: (
                final_price,
                (base, qty, copy.deepcopy(customers[who]), coupon),
                [],
            ),
        )

    stocks = [{}, {"a": 5, "b": 1}, {"a": 0, "b": 3}, {"a": 2, "b": 2, "c": 10}]
    item_lists: list[list[tuple[str, int]]] = [
        [],
        [("a", 1)],
        [("a", 5)],
        [("a", 9)],
        [("zzz", 1)],
        [("a", 1), ("b", 1)],
        [("a", 3), ("a", 3)],
        [("a", 0)],
        [("a", -2), ("b", 1)],
        [("b", 5), ("a", 1)],
        [("a", 1), ("zzz", 1), ("b", 1)],
        [("c", 7), ("a", 4), ("b", 9)],
    ]
    options = itertools.product(
        range(len(stocks)),
        range(len(item_lists)),
        ["strict", "partial", "skip", "bogus"],
        [None, {"a": 2}, {"c": 0, "b": 5}],
        [None, {"b"}, {"a", "zzz"}],
    )
    for index, (which, items, policy, caps, locked) in enumerate(options):
        yield (
            f"reserve:{index}",
            lambda which=which, items=items, policy=policy, caps=caps, locked=locked: _reserve_call(
                reserve, stocks[which], item_lists[items], policy, caps, locked
            ),
        )

    ids: list[object] = [..., "", 5, "X-1", "O-1"]
    lines: list[object] = [
        ...,
        [],
        [{"sku": "a", "qty": 1}],
        [{"sku": "a", "qty": 1}, {"sku": "a", "qty": 2}],
        [{"sku": "a", "qty": 0}, {"qty": 2}, "text"],
        [{"sku": "a", "qty": True}, {"sku": "b", "qty": 1001}, {"sku": "c", "qty": "3"}],
        [{"sku": "a", "qty": -1}],
        [{"sku": "a", "qty": 1000}, {"sku": "b", "qty": 2.5}],
    ]
    customers_of_orders: list[object] = [
        ...,
        None,
        {},
        {"blocked": True},
        {"kind": "alien"},
        {"kind": "partner"},
        "joe",
    ]
    totals: list[object] = [..., -1, "x", 5, 0.5, True, None]
    orders = itertools.product(ids, lines, customers_of_orders, totals)
    for index, (order_id, order_lines, customer, total) in enumerate(orders):
        order = {
            key: value
            for key, value in (
                ("id", order_id),
                ("lines", order_lines),
                ("customer", customer),
                ("total", total),
            )
            if value is not ...
        }
        yield (f"classify:{index}", lambda order=order: (classify, (copy.deepcopy(order),), []))
    yield ("classify:not-a-mapping-1", lambda: (classify, ([1, 2],), []))
    yield ("classify:not-a-mapping-2", lambda: (classify, (None,), []))


def _reserve_call(
    function: Callable[..., object],
    stock: dict[str, int],
    items: list[tuple[str, int]],
    policy: str,
    caps: object,
    locked: object,
) -> tuple[Callable[..., object], tuple[object, ...], list[object]]:
    stock, log = dict(stock), []
    return function, (stock, list(items), policy, log, copy.deepcopy(caps), locked), [stock, log]


# -- scanner -----------------------------------------------------------------------------------

LINE_POOL = [
    "",
    "   ",
    "# a comment",
    "; another",
    "[core]",
    "[ spaced ]",
    "[]",
    "[open",
    "[core]  ",
    "x = 1",
    "x=1",
    "y = 'quoted'",
    'z = "double"',
    "k = ",
    "= nothing",
    "two words = 1",
    "no equals",
    "v = a \\",
    "tail",
    "mid \\",
    'q = "unbalanced',
    "r = '",
    "s = ''",
    "t = a=b",
    "x = 2",
]


def scanner_cases() -> Iterator[Case]:
    from scanner import convert, parse_line, validate  # noqa: PLC0415

    sequences: list[tuple[str, ...]] = [(line,) for line in LINE_POOL]
    sequences += list(itertools.product(LINE_POOL, repeat=2))
    generator = random.Random(20261012)
    sequences += [tuple(generator.choice(LINE_POOL) for _ in range(3)) for _ in range(1500)]
    for index, (sequence, strict) in enumerate(itertools.product(sequences, [False, True])):
        yield (
            f"parse_line:{index}",
            lambda sequence=sequence, strict=strict: _read_call(parse_line, sequence, strict),
        )

    texts: list[object] = [
        "", " ", "true", "TRUE", "Yes", "on", "false", "No", "OFF", "none", "null", "None",
        "0", "7", "-7", "+7", "-", "+", "--3", "3.5", "-3.5", "+0.25", "1.2.3", ".5", "5.",
        "0x1f", "0X1F", "0xZZ", "0x", "[]", "[ ]", "[1,2]", "[1, two, 3.5]", "[[1],[2]]", "[a,",
        "2kb", "2KB", "10mb", "-1gb", "kb", "1tb", "abc", "a b", " 12 ", "'q'", "1e5", "٣",
        None, 5, 2.5, [1], True,
    ]  # fmt: skip
    for index, text in enumerate(texts):
        yield (f"convert:{index}", lambda text=text: (convert, (text,), []))

    values: list[object] = [1, "1", True, None, [1], 5.5, -1, 100, "b", []]
    rule_parts = itertools.product(
        [None, "int", "bool", "list", "str", "float"],
        [None, 0],
        [None, 10],
        [None, [1, 2]],
        ["none", "required", "default"],
    )
    index = 0
    for wanted, low, high, choices, mode in rule_parts:
        rule: dict[str, object] = {}
        if wanted:
            rule["type"] = wanted
        if low is not None:
            rule["min"] = low
        if high is not None:
            rule["max"] = high
        if choices:
            rule["choices"] = choices
        if mode == "required":
            rule["required"] = True
        if mode == "default":
            rule["default"] = 3
        for value in [*values, ...]:
            config = {"a": {} if value is ... else {"x": value}, "extra": {"k": 1}}
            for schema in ({"a": {"x": rule}}, {"a": {"x": rule}, "b": {"y": rule}}):
                yield (
                    f"validate:{index}",
                    lambda config=config, schema=schema: _validate_call(validate, config, schema),
                )
                index += 1
    yield (
        "validate:no-section",
        lambda: _validate_call(validate, {}, {"a": {"x": {"required": True}}}),
    )
    yield (
        "validate:open",
        lambda: _validate_call(validate, {"a": {"q": 1}}, {"a": {}, "*open*": {"a": True}}),
    )


def _read_call(
    parse_line: Callable[..., object], sequence: tuple[str, ...], strict: bool
) -> tuple[Callable[..., object], tuple[object, ...], list[object]]:
    state: dict[str, object] = {"data": {}}
    if strict:
        state["strict"] = True

    def feed(*_: object) -> list[object]:
        done: list[object] = []
        for line in sequence:
            try:
                done.append(parse_line(line, state))
            except ValueError as error:
                done.append(f"ValueError: {error}")
        return done

    return feed, (), [state]


def _validate_call(
    validate: Callable[..., object], config: dict[str, object], schema: dict[str, object]
) -> tuple[Callable[..., object], tuple[object, ...], list[object]]:
    config = copy.deepcopy(config)
    return validate, (config, copy.deepcopy(schema)), [config]


CASES: dict[str, Callable[[], Iterator[Case]]] = {
    "inventory": inventory_cases,
    "scanner": scanner_cases,
}


def run(repo: str, path: Path) -> dict[str, str]:
    sys.path.insert(0, str(path / "src"))
    importlib.invalidate_caches()
    results: dict[str, str] = {}
    for case_id, make in CASES[repo]():
        function, args, watched = make()
        results[case_id] = outcome(function, args, watched)
    return results


def main(argv: list[str]) -> int:
    mode, repo, path, golden = argv[0], argv[1], Path(argv[2]), Path(argv[3])
    results = run(repo, path)
    if mode == "record":
        golden.write_text(json.dumps(results, indent=0, sort_keys=True), encoding="utf-8")
        print(json.dumps({"cases": len(results)}))
        return 0
    recorded: dict[str, str] = json.loads(golden.read_text(encoding="utf-8"))
    failed = sorted(case_id for case_id in recorded if results.get(case_id) != recorded[case_id])
    print(json.dumps({"cases": len(recorded), "failed": failed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
