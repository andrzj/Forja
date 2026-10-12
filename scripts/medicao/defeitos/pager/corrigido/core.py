def paginate(items, page, size):
    """Return the items of page ``page`` (numbered from 1), ``size`` items per page."""
    if size < 1:
        raise ValueError("size must be at least 1")
    if page < 1:
        raise ValueError("page must be at least 1")
    start = (page - 1) * size
    return list(items[start : start + size])
