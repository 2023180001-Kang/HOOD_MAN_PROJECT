"""FIFO stairs: spaced enemy columns in one direction, exclusive player travel."""

from math import hypot

import config
from walkable import default_area


def can_use_stairs(actor):
    return (actor.alive and actor.staircase is None and actor.jump_height == 0
            and actor.vy == 0 and actor.counter_move is None
            and getattr(actor, "active_move", None) is None
            and not getattr(actor, "knockback_started", False)
            and actor.state in ("IDLE", "WALK", "RUN"))


class Staircase:
    def __init__(self, path, *, lower_area=None):
        self.path = tuple(path)
        self.lengths = tuple(hypot(bx - ax, by - ay)
                             for (ax, ay), (bx, by) in zip(self.path, self.path[1:]))
        self.length = sum(self.lengths)
        self.occupants = {}  # Actor -> distance travelled, in entry order.
        self.queue = []
        self.destination_floor = None
        self.lower_area = default_area() if lower_area is None else lower_area

    @property
    def occupant(self):
        """Leading actor, for inspection; all travellers are in occupants."""
        return next(iter(self.occupants), None)

    @property
    def progress(self):
        """Distance travelled by the leading actor."""
        return next(iter(self.occupants.values()), 0.0)

    def entrance(self, floor):
        return self.path[0 if floor == 0 else -1]

    def distance_to_entry(self, actor):
        x, y = self.entrance(actor.floor)
        return hypot(actor.x - x, actor.ground_y - y)

    def request(self, actor):
        if actor not in self.queue and actor not in self.occupants:
            self.queue.append(actor)

    def start_next(self):
        if not self.queue:
            return
        actor = self.queue[0]
        if not can_use_stairs(actor) or self.distance_to_entry(actor) > config.STAIR_ENTRY_RADIUS:
            return
        if self.occupants:
            # Never skip an older opposite-direction request or a waiting
            # player. The current column drains before that request enters.
            if (not actor.stair_following
                    or any(not traveller.stair_following for traveller in self.occupants)
                    or 1 - actor.floor != self.destination_floor
                    or min(self.occupants.values()) + 1e-9 < config.STAIR_FOLLOW_DISTANCE):
                return
        self.queue.pop(0)
        self.occupants[actor] = 0.0
        self.destination_floor = 1 - actor.floor
        actor.staircase = self
        actor.stair_arrival = False
        actor.x, actor.ground_y = self.entrance(actor.floor)
        actor.previous_x, actor.previous_ground_y = actor.x, actor.ground_y
        actor.vx = actor.ground_vy = actor.vy = actor.jump_height = 0.0
        actor.navigation_target = None
        actor.animation.set_state("WALK")

    def update(self, dt):
        moved = set(self.occupants)
        leader = None
        for actor in tuple(self.occupants):
            limit = (self.occupants[leader] - config.STAIR_FOLLOW_DISTANCE
                     if leader in self.occupants else self.length)
            self._update_actor(actor, dt, limit)
            leader = actor if actor in self.occupants else None
        return moved  # Include every actor that lands on this exact tick.

    def _update_actor(self, actor, dt, limit):
        actor.previous_x, actor.previous_ground_y = actor.x, actor.ground_y
        actor.previous_jump_height = 0.0
        if actor.state == "HIT":
            actor.animation.update(dt)
            if actor.animation.finished:
                actor.animation.set_state("WALK")
            return
        before = self.occupants[actor]
        progress = max(before, min(self.length, before + max(0.0, dt) * config.STAIR_SPEED, limit))
        self.occupants[actor] = progress
        remaining = progress if self.destination_floor == 1 else self.length - progress
        for (ax, ay), (bx, by), length in zip(self.path, self.path[1:], self.lengths):
            if remaining <= length + 1e-9:
                t = min(1.0, remaining / length)
                actor.x, actor.ground_y = ax + (bx - ax) * t, ay + (by - ay) * t
                break
            remaining -= length
        if abs(actor.x - actor.previous_x) > 1e-9:
            actor.facing = 1 if actor.x > actor.previous_x else -1
        actor.vx = actor.ground_vy = actor.vy = actor.jump_height = 0.0
        actor.animation.set_state("WALK" if progress > before else "IDLE")
        actor.animation.update(dt)
        if progress + 1e-9 >= self.length:
            self._land(actor, self.destination_floor, arrived=True)

    def release(self, actor):
        self.queue[:] = [waiting for waiting in self.queue if waiting is not actor]
        if actor in self.occupants:
            # Death/removal/tooling cannot strand a lock or leave feet in midair.
            destination = (self.destination_floor if self.occupants[actor] >= self.length / 2
                           else 1 - self.destination_floor)
            self._land(actor, destination)

    def detach(self, actor):
        """Leave the steps at the current position, without snapping to a landing."""
        self.queue[:] = [waiting for waiting in self.queue if waiting is not actor]
        self.occupants.pop(actor, None)
        actor.staircase = None
        actor.stair_arrival = False
        if not self.occupants:
            self.destination_floor = None

    def _land(self, actor, floor, *, arrived=False):
        actor.floor = floor
        actor.x, actor.ground_y = self.entrance(floor)
        actor.previous_x, actor.previous_ground_y = actor.x, actor.ground_y
        actor.staircase = None
        # Give a waiting actor the next tick to enter before body resolution
        # can push it off the shared landing.
        actor.stair_arrival = arrived
        actor.vx = actor.ground_vy = 0.0
        if actor.state in ("WALK", "RUN"):
            actor.animation.set_state("IDLE")
        self.detach(actor)
        actor.stair_arrival = arrived
