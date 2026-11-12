"""Small deterministic physics helpers."""

from math import hypot


def clamp(value, lower, upper):
    return max(lower, min(value, upper))


def approach(value, target, amount):
    if value < target:
        return min(value + amount, target)
    return max(value - amount, target)


def approach_vector(x, y, target_x, target_y, amount):
    dx, dy = target_x - x, target_y - y
    distance = hypot(dx, dy)
    if distance <= amount:
        return target_x, target_y
    return x + dx / distance * amount, y + dy / distance * amount
