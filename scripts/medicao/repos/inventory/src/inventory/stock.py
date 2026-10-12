"""Taking goods out of stock."""


def reserve(stock, items, policy="strict", log=None, caps=None, locked=None):
    """Take ``items`` (pairs of sku and quantity) out of ``stock``.

    Returns what was reserved and what was not. ``stock`` and ``log`` are changed as it goes, so
    a failure in the middle leaves the earlier items taken.
    """
    if policy not in ("strict", "partial", "skip"):
        raise ValueError(f"unknown policy: {policy}")
    if log is None:
        log = []
    reserved = {}
    missing = {}
    for sku, qty in items:
        if locked and sku in locked:
            if policy == "strict":
                raise PermissionError(f"{sku} is locked")
            log.append(("locked", sku))
            continue
        if qty <= 0:
            if policy == "strict":
                raise ValueError(f"bad quantity for {sku}")
            log.append(("ignored", sku))
            continue
        cap = caps.get(sku) if caps else None
        if cap is not None and qty > cap:
            if policy == "strict":
                raise ValueError(f"{sku} is capped at {cap}")
            qty = cap
            log.append(("capped", sku, cap))
        have = stock.get(sku)
        if have is None:
            if policy == "strict":
                raise KeyError(sku)
            missing[sku] = missing.get(sku, 0) + qty
            log.append(("unknown", sku))
            continue
        if have >= qty:
            stock[sku] = have - qty
            reserved[sku] = reserved.get(sku, 0) + qty
            log.append(("reserved", sku, qty))
        elif policy == "partial" and have > 0:
            stock[sku] = 0
            reserved[sku] = reserved.get(sku, 0) + have
            missing[sku] = missing.get(sku, 0) + (qty - have)
            log.append(("partial", sku, have))
        elif policy == "strict":
            raise RuntimeError(f"not enough {sku}")
        else:
            missing[sku] = missing.get(sku, 0) + qty
            log.append(("short", sku, qty))
    return {"reserved": reserved, "missing": missing, "complete": not missing}
