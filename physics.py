"""Small deterministic physics helpers."""


def clamp(value, lower, upper):
    return max(lower, min(value, upper))


def approach(value, target, amount):
    if value < target:
        return min(value + amount, target)
    return max(value - amount, target)
