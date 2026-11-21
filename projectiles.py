"""Researcher rounds: straight range, ballistic fall and continuous collision."""

from dataclasses import dataclass
from math import sqrt

import config
from collision import same_floor


@dataclass
class ResearcherBullet:
    x: float
    ground_y: float
    height: float
    facing: int
    floor: int = 0
    elapsed: float = 0.0
    spent: bool = False

    image_name = config.RESEARCHER_BULLET_IMAGE
    damage = config.RESEARCHER_DAMAGE

    @property
    def y(self):
        return self.ground_y + self.height

    @property
    def frame(self):
        return int(self.elapsed * config.RESEARCHER_BULLET_FPS + 1e-9) % 8

    @property
    def impact_x(self):
        return self.x + self.facing * config.RESEARCHER_BULLET_HALF_WIDTH

    @property
    def straight_duration(self):
        return config.RESEARCHER_BULLET_STRAIGHT_RANGE / config.RESEARCHER_BULLET_SPEED

    @property
    def falling(self):
        return self.elapsed + 1e-12 >= self.straight_duration

    @property
    def vy(self):
        return -config.RESEARCHER_BULLET_GRAVITY * max(0.0, self.elapsed - self.straight_duration)

    @property
    def finished(self):
        margin = config.RESEARCHER_BULLET_HALF_WIDTH
        return (self.spent or self.height <= config.RESEARCHER_BULLET_HALF_HEIGHT
                or self.x < -margin or self.x > config.WORLD_WIDTH + margin)

    def update(self, dt, player):
        if self.finished:
            return False
        dt = max(0.0, dt)
        offset = 0.0
        while True:
            gravity = config.RESEARCHER_BULLET_GRAVITY if self.falling else 0.0
            vy = self.vy
            step = dt - offset
            if not self.falling:
                # Split exactly at the range boundary, including a large update.
                step = min(step, self.straight_duration - self.elapsed)
            ground_time = float("inf")
            if gravity:
                clearance = self.height - config.RESEARCHER_BULLET_HALF_HEIGHT
                ground_time = 2 * clearance / (sqrt(vy * vy + 2 * gravity * clearance) - vy)
                step = min(step, ground_time)
            margin = config.RESEARCHER_BULLET_HALF_WIDTH
            edge_gap = (config.WORLD_WIDTH + margin - self.x if self.facing > 0
                        else self.x + margin)
            edge_time = edge_gap / config.RESEARCHER_BULLET_SPEED
            step = min(step, edge_time)
            terminal = min(ground_time, edge_time) <= step + 1e-12
            contact = self._contact_time(player, step, offset, dt, gravity)
            # Ground/world contact wins a simultaneous tie. Never hit after landing.
            hit = contact is not None and (not terminal or contact < step - 1e-12)
            travel = contact if hit else step
            self.x += self.facing * config.RESEARCHER_BULLET_SPEED * travel
            self.height += vy * travel - gravity * travel * travel / 2
            self.elapsed += travel
            if hit:
                self.spent = True  # Also consume a bullet blocked by P invincibility.
                return player.take_damage(self.damage)
            if terminal:
                if ground_time <= step + 1e-12:
                    self.height = config.RESEARCHER_BULLET_HALF_HEIGHT
                self.spent = True
                return False
            offset += step
            if offset >= dt:
                return False

    def _contact_time(self, player, duration, offset, tick_duration, gravity):
        if not player.alive or not same_floor(self, player):
            return None
        # A just-emitted bullet exists at the end of this simulation tick only.
        # Never sweep the player through a projectile that did not exist yet.
        if tick_duration == 0:
            px, py, height = player.x, player.ground_y, player.jump_height
            vx = ground_vy = jump_vy = 0.0
        else:
            vx = (player.x - player.previous_x) / tick_duration
            ground_vy = (player.ground_y - player.previous_ground_y) / tick_duration
            jump_vy = (player.jump_height - player.previous_jump_height) / tick_duration
            px = player.previous_x + vx * offset
            py = player.previous_ground_y + ground_vy * offset
            height = player.previous_jump_height + jump_vy * offset
        half_width = (player.body.right - player.body.left) / 2 + config.RESEARCHER_BULLET_HALF_WIDTH
        half_height = config.RESEARCHER_BULLET_HALF_HEIGHT
        axes = (
            (self.x - px, self.facing * config.RESEARCHER_BULLET_SPEED - vx, -half_width, half_width),
            (self.ground_y - py, -ground_vy,
              -config.ATTACK_DEPTH_TOLERANCE, config.ATTACK_DEPTH_TOLERANCE),
        )
        enter, leave = 0.0, duration
        for start, velocity, low, high in axes:
            if abs(velocity) < 1e-12:
                if not low <= start <= high:
                    return None
                continue
            first, last = sorted(((low - start) / velocity, (high - start) / velocity))
            enter, leave = max(enter, first), min(leave, last)
            if enter > leave:
                return None
        # Height is quadratic during the fall. A straight endpoint sweep could
        # miss a real mid-arc hit or report contact on the chord, off the arc.
        relative_height, relative_vy = self.height - height, self.vy - jump_vy
        low, high = -half_height, player.body.top - player.body.bottom + half_height
        candidates = [enter]
        for boundary in (low, high):
            difference = relative_height - boundary
            if gravity == 0:
                if abs(relative_vy) > 1e-12:
                    candidates.append(-difference / relative_vy)
            else:
                discriminant = relative_vy * relative_vy + 2 * gravity * difference
                if discriminant >= -1e-12:
                    root = sqrt(max(0.0, discriminant))
                    candidates.extend(((relative_vy - root) / gravity,
                                       (relative_vy + root) / gravity))
        for candidate in sorted(candidates):
            if enter - 1e-12 <= candidate <= leave + 1e-12:
                time = min(leave, max(enter, candidate))
                value = relative_height + relative_vy * time - gravity * time * time / 2
                if low - 1e-9 <= value <= high + 1e-9:
                    return time
        return None
