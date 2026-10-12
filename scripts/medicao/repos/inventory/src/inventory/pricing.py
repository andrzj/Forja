"""Prices for the shop."""

TIERS = ((100, 0.15), (50, 0.10), (10, 0.05))
COUPONS = {"SAVE5": ("flat", 5), "HALF": ("percent", 50), "FREESHIP": ("ship", 0)}


def final_price(base, qty, customer, coupon=None):
    """Price of ``qty`` units at ``base`` each, for a customer, with an optional coupon."""
    if not isinstance(qty, int) or isinstance(qty, bool):
        raise TypeError("qty must be an int")
    if qty <= 0:
        raise ValueError("qty must be positive")
    if base < 0:
        raise ValueError("base must not be negative")
    total = base * qty
    rate = 0.0
    for threshold, tier_rate in TIERS:
        if qty >= threshold:
            rate = tier_rate
            break
    kind = customer.get("kind", "retail")
    if kind == "wholesale":
        rate = max(rate, 0.20)
    elif kind == "staff":
        rate = 0.30 if not customer.get("probation") else 0.10
    elif kind == "retail":
        if customer.get("loyal") and customer.get("years", 0) >= 5:
            rate += 0.05
        elif customer.get("loyal"):
            rate += 0.02
    elif kind == "partner":
        if customer.get("contract") == "gold":
            rate = max(rate, 0.25)
        elif customer.get("contract") == "silver":
            rate = max(rate, 0.15)
    else:
        raise ValueError(f"unknown customer kind: {kind}")
    if customer.get("blocked"):
        raise PermissionError("customer is blocked")
    total = total * (1 - rate)
    if coupon is not None:
        if coupon not in COUPONS:
            raise KeyError(coupon)
        how, amount = COUPONS[coupon]
        if how == "flat":
            total = total - amount if total > amount else 0
        elif how == "percent":
            if kind != "staff":
                total = total * (1 - amount / 100)
        elif how == "ship":
            total = total
    if total < 0:
        total = 0
    return round(total, 2)
