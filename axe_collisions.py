"""Find the first midair clashes before applying axe damage for a simulation tick."""

from copy import copy
from dataclasses import dataclass
from itertools import combinations
from math import sqrt

import config


@dataclass(frozen=True)
class FlightLeg:
    start: float
    end: float
    x: float
    height: float
    vx: float
    vy: float
    gravity: float
    returning: bool

    def height_at(self, time):
        t = time - self.start
        return self.height + self.vy * t - self.gravity * t * t / 2


def flight_path(axe, dt, player):
    # Use the same sword contact, range, gravity and wall times as the live throw.
    # Only the parry changes its path. Character damage belongs to the live pass.
    probe = copy(axe)
    probe.hit_targets = set(axe.hit_targets)
    if player.state != "SWORD_PARRY":
        probe.hit_targets.add(player)
    legs = []

    def record(shot, start, duration, vx, vy, gravity):
        legs.append(FlightLeg(start, start + duration, shot.x, shot.height,
                              vx, vy, gravity, shot.deflected))

    probe.update(dt, player, on_travel=record)
    return legs


def contact_time(first, second, width, height, dt):
    if not (first.returning or second.returning):
        return None
    # A returned axe is level. The other axe can be level or descending.
    level, other = (first, second) if first.returning else (second, first)
    start, end = max(level.start, other.start), min(level.end, other.end)
    if end < start or (dt > 0 and end == start):
        return None
    closing_speed = level.vx - other.vx
    gap = (other.x + other.vx * (start - other.start)
           - level.x - level.vx * (start - level.start))
    if closing_speed == 0:
        return None
    entry, exit_time = sorted(((gap - width) / closing_speed, (gap + width) / closing_speed))
    entry, exit_time = max(start, start + entry), min(end, start + exit_time)
    if entry > exit_time:
        return None
    low, high = level.height - height, level.height + height
    if gap * closing_speed < 0 and low <= other.height_at(start) <= high:
        return None  # Already overlapping and moving apart.
    entry_height = other.height_at(entry)
    if entry_height < low or other.height_at(exit_time) > high:
        return None
    if entry_height <= high:
        return entry
    # The descending blade reaches the top of the level blade during their x overlap.
    speed_down = other.gravity * (entry - other.start) - other.vy
    distance = entry_height - high
    return entry + 2 * distance / (speed_down + sqrt(speed_down**2 + 2 * other.gravity * distance))


def axe_clash_times(axes, dt, player):
    if len(axes) < 2 or (player.state != "SWORD_PARRY" and not any(axe.deflected for axe in axes)):
        return {}
    paths = [flight_path(axe, dt, player) for axe in axes]
    events = []
    for i, j in combinations(range(len(axes)), 2):
        a, b = axes[i], axes[j]
        if ((a.shooter is not None and a.shooter is b.shooter)
                or a.floor != b.floor or abs(a.ground_y - b.ground_y) > config.BODY_DEPTH_TOLERANCE):
            continue
        for left in paths[i]:
            for right in paths[j]:
                t = contact_time(left, right, a.half_width + b.half_width, a.half_height + b.half_height, dt)
                if t is not None:
                    events.append((t, i, j))
    # A blade that already dropped cannot block a later throw. Ties can involve
    # more than two blades, regardless of the order enemies were spawned in.
    stops = {}
    for t, i, j in sorted(events):
        a, b = id(axes[i]), id(axes[j])
        if t <= min(stops.get(a, dt), stops.get(b, dt)) + 1e-12:
            stops[a] = min(t, stops.get(a, dt))
            stops[b] = min(t, stops.get(b, dt))
    return stops
