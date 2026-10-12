def overlaps(a, b):
    """True when the closed intervals ``a`` and ``b``, each (start, end), share a point."""
    a_start, a_end = a
    b_start, b_end = b
    if a_start > a_end or b_start > b_end:
        raise ValueError("an interval starts after it ends")
    return a_start <= b_end and b_start <= a_end
