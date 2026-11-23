"""Ranged rounds with continuous collision and per-weapon flight/render profiles."""

from dataclasses import dataclass, field
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
    impact_target: object = field(default=None, init=False, repr=False)
    impact_damage: int = field(default=0, init=False)

    image_name = config.RESEARCHER_BULLET_IMAGE
    damage = config.RESEARCHER_DAMAGE
    half_width = config.RESEARCHER_BULLET_HALF_WIDTH
    half_height = config.RESEARCHER_BULLET_HALF_HEIGHT
    speed = config.RESEARCHER_BULLET_SPEED
    fps = config.RESEARCHER_BULLET_FPS
    straight_range = config.RESEARCHER_BULLET_STRAIGHT_RANGE
    gravity = config.RESEARCHER_BULLET_GRAVITY
    scale = config.RESEARCHER_BULLET_SCALE
    anchor_y = config.RESEARCHER_BULLET_ANCHOR_Y
    range_limited = False

    @property
    def y(self):
        return self.ground_y + self.height

    @property
    def frame(self):
        return int(self.elapsed * self.fps + 1e-9) % 8

    @property
    def impact_x(self):
        return self.x + self.facing * self.half_width

    @property
    def straight_duration(self):
        return self.straight_range / self.speed

    @property
    def falling(self):
        return not self.range_limited and self.elapsed + 1e-12 >= self.straight_duration

    @property
    def vy(self):
        return -self.gravity * max(0.0, self.elapsed - self.straight_duration) if self.falling else 0.0

    @property
    def finished(self):
        margin = self.half_width
        return (self.spent or self.height <= self.half_height
                or self.x < -margin or self.x > config.WORLD_WIDTH + margin
                or (self.range_limited and self.elapsed + 1e-12 >= self.straight_duration))

    def update(self, dt, player):
        if self.finished:
            return False
        dt = max(0.0, dt)
        offset = 0.0
        while True:
            gravity = self.gravity if self.falling else 0.0
            vy = self.vy
            step = dt - offset
            range_time = float("inf")
            if not self.falling:
                # Split exactly at the range boundary, including a large update.
                step = min(step, self.straight_duration - self.elapsed)
                if self.range_limited:
                    range_time = self.straight_duration - self.elapsed
            ground_time = float("inf")
            if gravity:
                clearance = self.height - self.half_height
                ground_time = 2 * clearance / (sqrt(vy * vy + 2 * gravity * clearance) - vy)
                step = min(step, ground_time)
            margin = self.half_width
            edge_gap = (config.WORLD_WIDTH + margin - self.x if self.facing > 0
                        else self.x + margin)
            edge_time = edge_gap / self.speed
            step = min(step, edge_time)
            terminal = min(ground_time, edge_time, range_time) <= step + 1e-12
            contact, target = self._first_contact(player, step, offset, dt, gravity)
            # Ground/world contact wins a simultaneous tie. Never hit after landing.
            hit = contact is not None and (not terminal or contact < step - 1e-12)
            travel = contact if hit else step
            self.x += self.facing * self.speed * travel
            self.height += vy * travel - gravity * travel * travel / 2
            self.elapsed += travel
            if hit:
                self.spent = True  # Also consume a bullet blocked by P invincibility.
                previous_hp = target.hp
                applied = target.take_damage(self.damage)
                self.impact_target = target
                self.impact_damage = previous_hp - target.hp
                return applied
            if terminal:
                if ground_time <= step + 1e-12:
                    self.height = self.half_height
                self.spent = True
                return False
            offset += step
            if offset >= dt:
                return False

    def _first_contact(self, target, duration, offset, tick_duration, gravity):
        return self._contact_time(target, duration, offset, tick_duration, gravity), target

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
        half_width = (player.body.right - player.body.left) / 2 + self.half_width
        half_height = self.half_height
        axes = (
            (self.x - px, self.facing * self.speed - vx, -half_width, half_width),
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


class PlayerPistolBullet(ResearcherBullet):
    """Same pistol flight profile, but hit only the first living enemy in the path."""

    damage = config.PLAYER_PISTOL_DAMAGE

    def _first_contact(self, enemies, duration, offset, tick_duration, gravity):
        first, target = None, None
        for enemy in enemies:
            contact = self._contact_time(enemy, duration, offset, tick_duration, gravity)
            if contact is not None and (first is None or contact < first):
                first, target = contact, enemy
        return first, target


class RifleBullet(ResearcherBullet):
    """AR round: level, range-limited flight; shared swept collision, no floor drop."""

    image_name = config.RIFLE_BULLET_IMAGE
    damage = config.AR_SOLDIER_DAMAGE
    half_width = config.RIFLE_BULLET_HALF_WIDTH
    half_height = config.RIFLE_BULLET_HALF_HEIGHT
    speed = config.RIFLE_BULLET_SPEED
    fps = config.RIFLE_BULLET_FPS
    straight_range = config.RIFLE_BULLET_RANGE
    scale = config.RIFLE_BULLET_SCALE
    anchor_y = config.RIFLE_BULLET_ANCHOR_Y
    range_limited = True
