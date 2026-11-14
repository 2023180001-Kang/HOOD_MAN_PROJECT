"""Stage-local road traffic, swept collisions and fatal vehicle reactions."""

import random

import config
from animation import Animation
from physics import approach


class Car:
    def __init__(self, x, facing, speed):
        self.x = self.previous_x = x
        self.facing = facing
        self.speed = speed
        self.ground_y = config.CAR_GROUND_Y
        self.animation = Animation({"DRIVE": (1, config.CAR_FPS, True)}, "DRIVE")

    def update(self, dt):
        self.previous_x = self.x
        self.x += self.facing * self.speed * dt
        self.animation.update(dt)

    @property
    def off_stage(self):
        return (self.x > config.WORLD_WIDTH + config.CAR_SPAWN_MARGIN if self.facing > 0
                else self.x < -config.CAR_SPAWN_MARGIN)

    def hits(self, actor):
        if not actor.alive:
            return False
        # Intersect all three motion intervals at the SAME time. Testing only
        # the final AABBs tunnels through fast cars and crossing actors.
        half_width = (actor.body.right - actor.body.left) / 2 + config.CAR_HALF_WIDTH
        height = actor.body.top - actor.body.bottom
        axes = (
            (actor.previous_x - self.previous_x, actor.x - self.x, -half_width, half_width),
            (actor.previous_ground_y - self.ground_y, actor.ground_y - self.ground_y,
             -config.CAR_DEPTH_TOLERANCE, config.CAR_DEPTH_TOLERANCE),
            (actor.previous_jump_height, actor.jump_height, -height, config.CAR_HEIGHT),
        )
        enter, leave = 0.0, 1.0
        for start, end, low, high in axes:
            delta = end - start
            if abs(delta) < 1e-12:
                if not low <= start <= high:
                    return False
                continue
            first, last = sorted(((low - start) / delta, (high - start) / delta))
            enter, leave = max(enter, first), min(leave, last)
            if enter > leave:
                return False
        return True


class Traffic:
    def __init__(self, *, rng=None):
        # Keep traffic randomness independent from enemy spawn/attack profiles.
        self.rng = random.Random() if rng is None else rng
        self.car = None
        self.spawn_remaining = config.CAR_INITIAL_DELAY

    def update(self, dt):
        if self.car is None:
            self.spawn_remaining = max(0.0, self.spawn_remaining - dt)
            if self.spawn_remaining > 1e-9:
                return None
            facing = self.rng.choice((-1, 1))
            x = (-config.CAR_SPAWN_MARGIN if facing > 0 else
                 config.WORLD_WIDTH + config.CAR_SPAWN_MARGIN)
            self.car = Car(x, facing, self.rng.uniform(*config.CAR_SPEED_RANGE))
        car = self.car
        car.update(dt)
        if car.off_stage:
            self.car = None
            self.spawn_remaining = self.rng.uniform(*config.CAR_PASS_DELAY)
        return car


def start_car_hit(actor, direction):
    """HP reaches zero at impact, before the non-looping death presentation."""
    actor.hp = 0
    actor.car_hit = True
    actor.facing = direction
    actor.vx = direction * config.CAR_HIT_SPEED
    actor.ground_vy = actor.vy = 0.0
    actor.animation.definitions["DEAD"] = (1, config.CAR_HIT_FPS, False)
    actor.animation.set_state("CAR_HIT")


def update_car_hit(actor, dt):
    actor.x += actor.vx * dt
    actor.vx = approach(actor.vx, 0.0, config.CAR_HIT_FRICTION * dt)
    if actor.jump_height > 0:
        actor.vy -= config.GRAVITY * dt
        actor.jump_height = max(0.0, actor.jump_height + actor.vy * dt)
        if actor.jump_height == 0:
            actor.vy = 0.0
    actor.animation.update(dt)
    if actor.animation.finished:
        actor.vx = 0.0
        actor.animation.set_state("DEAD")
        actor.animation.elapsed = 8 / config.CAR_HIT_FPS
