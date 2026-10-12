def slugify(text):
    """Lowercase ``text`` and replace what is not a letter or a digit with a hyphen."""
    slug = "".join(char if char.isalnum() else "-" for char in text.lower())
    return "-".join(part for part in slug.split("-") if part)
