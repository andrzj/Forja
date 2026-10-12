def split(total_cents, parts):
    """Divide ``total_cents`` into ``parts`` shares of whole cents."""
    if parts < 1:
        raise ValueError("parts must be at least 1")
    if total_cents < 0:
        raise ValueError("the total cannot be negative")
    share, extra = divmod(total_cents, parts)
    return [share + 1 if index < extra else share for index in range(parts)]
