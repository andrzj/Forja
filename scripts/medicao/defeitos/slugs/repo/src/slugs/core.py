def slugify(text):
    """Lowercase ``text`` and replace what is not a letter or a digit with a hyphen."""
    return "".join(char if char.isalnum() else "-" for char in text.lower())
