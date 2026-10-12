"""Checking a configuration against what it must contain."""


def validate(config, schema):
    """The problems of ``config`` against ``schema``, in the order they are found.

    A key that is missing and has a default is filled in, so ``config`` is changed.
    """
    problems = []
    for section, rules in schema.items():
        if section not in config:
            if any(rule.get("required") for rule in rules.values()):
                problems.append(f"missing section {section}")
            continue
        values = config[section]
        for key, rule in rules.items():
            if key not in values:
                if rule.get("required"):
                    problems.append(f"{section}.{key} is required")
                elif "default" in rule:
                    values[key] = rule["default"]
                continue
            value = values[key]
            wanted = rule.get("type")
            if wanted == "int":
                if not isinstance(value, int) or isinstance(value, bool):
                    problems.append(f"{section}.{key} must be an int")
                    continue
            elif wanted == "bool":
                if not isinstance(value, bool):
                    problems.append(f"{section}.{key} must be a bool")
                    continue
            elif wanted == "list":
                if not isinstance(value, list):
                    problems.append(f"{section}.{key} must be a list")
                    continue
            elif wanted == "str" and not isinstance(value, str):
                problems.append(f"{section}.{key} must be text")
                continue
            if "min" in rule and isinstance(value, (int, float)) and value < rule["min"]:
                problems.append(f"{section}.{key} is below {rule['min']}")
            if "max" in rule and isinstance(value, (int, float)) and value > rule["max"]:
                problems.append(f"{section}.{key} is above {rule['max']}")
            if "choices" in rule and value not in rule["choices"]:
                problems.append(f"{section}.{key} is not one of {rule['choices']}")
        for key in values:
            if key not in rules and not schema.get("*open*", {}).get(section):
                problems.append(f"{section}.{key} is not known")
    return problems
