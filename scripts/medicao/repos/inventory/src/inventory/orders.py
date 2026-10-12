"""Checking orders before they are accepted."""

KINDS = (None, "retail", "wholesale", "staff", "partner")


def classify(order):
    """Everything wrong with an order, in the order a clerk would fix it."""
    issues = []
    if not isinstance(order, dict):
        return ["order is not a mapping"]
    if "id" not in order or not order["id"]:
        issues.append("missing id")
    elif not isinstance(order["id"], str):
        issues.append("id is not text")
    elif not order["id"].startswith("O-"):
        issues.append("id has no O- prefix")
    lines = order.get("lines")
    if not lines:
        issues.append("no lines")
    else:
        seen = set()
        for number, line in enumerate(lines, start=1):
            if not isinstance(line, dict):
                issues.append(f"line {number} is not a mapping")
                continue
            sku = line.get("sku")
            if not sku:
                issues.append(f"line {number} has no sku")
            elif sku in seen:
                issues.append(f"line {number} repeats {sku}")
            else:
                seen.add(sku)
            qty = line.get("qty")
            if not isinstance(qty, int) or isinstance(qty, bool):
                issues.append(f"line {number} qty is not a whole number")
            elif qty <= 0:
                issues.append(f"line {number} qty must be positive")
            elif qty > 1000:
                issues.append(f"line {number} qty is too large")
    customer = order.get("customer")
    if customer is None:
        issues.append("no customer")
    elif customer.get("blocked"):
        issues.append("customer is blocked")
    elif customer.get("kind") not in KINDS:
        issues.append("unknown customer kind")
    total = order.get("total")
    if total is not None and (not isinstance(total, (int, float)) or total < 0):
        issues.append("total is invalid")
    return issues
