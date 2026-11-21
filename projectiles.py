"""Stage-local researcher bullets with swept x/depth/height collision."""

from dataclasses import dataclass

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
    def finished(self):
        margin = config.RESEARCHER_BULLET_HALF_WIDTH
        return (self.spent or self.elapsed + 1e-9 >= config.RESEARCHER_BULLET_LIFETIME
                or self.x < -margin or self.x > config.WORLD_WIDTH + margin)

    def update(self, dt, player):
        if self.finished:
            return False
        start = self.x
        dt = max(0.0, dt)
        step = min(dt, config.RESEARCHER_BULLET_LIFETIME - self.elapsed)
        self.x += self.facing * config.RESEARCHER_BULLET_SPEED * step
        self.elapsed += step
        contact = self._contact_time(player, start, 0.0 if dt == 0 else step / dt)
        if contact is None:
            return False
        self.x = start + (self.x - start) * contact
        self.spent = True  # Also consume a bullet blocked by P/counter protection.
        return player.take_damage(self.damage)

    def _contact_time(self, player, start_x, time_fraction):
        if not player.alive or not same_floor(self, player):
            return None
        # A just-emitted bullet exists at the end of this simulation tick only.
        # Never sweep the player through a projectile that did not exist yet.
        if time_fraction == 0:
            px, py, height = player.x, player.ground_y, player.jump_height
            end_x, end_y, end_height = px, py, height
        else:
            px, py, height = player.previous_x, player.previous_ground_y, player.previous_jump_height
            end_x = px + (player.x - px) * time_fraction
            end_y = py + (player.ground_y - py) * time_fraction
            end_height = height + (player.jump_height - height) * time_fraction
        half_width = (player.body.right - player.body.left) / 2 + config.RESEARCHER_BULLET_HALF_WIDTH
        half_height = config.RESEARCHER_BULLET_HALF_HEIGHT
        axes = (
            (start_x - px, self.x - end_x, -half_width, half_width),
            (self.ground_y - py, self.ground_y - end_y,
             -config.ATTACK_DEPTH_TOLERANCE, config.ATTACK_DEPTH_TOLERANCE),
            (self.height - height, self.height - end_height,
             -half_height, player.body.top - player.body.bottom + half_height),
        )
        enter, leave = 0.0, 1.0
        for start, end, low, high in axes:
            delta = end - start
            if abs(delta) < 1e-12:
                if not low <= start <= high:
                    return None
                continue
            first, last = sorted(((low - start) / delta, (high - start) / delta))
            enter, leave = max(enter, first), min(leave, last)
            if enter > leave:
                return None
        return enter
