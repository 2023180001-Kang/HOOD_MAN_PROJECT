"""World-space body and attack geometry; enemies never collide with each other."""

from dataclasses import dataclass

import config
from physics import clamp


@dataclass(frozen=True)
class Rect:
    left: float
    bottom: float
    right: float
    top: float

    def overlaps(self, other):
        return (self.left < other.right and self.right > other.left
                and self.bottom < other.top and self.top > other.bottom)

    def overlaps_vertically(self, other):
        return self.bottom < other.top and self.top > other.bottom


def resolve_bodies(player, enemies):
    """Constrain player motion, then let enemies yield; bounded, non-iterative."""
    low = config.PLAYER_HALF_WIDTH
    high = config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH
    separation = config.PLAYER_HALF_WIDTH + config.ENEMY_HALF_WIDTH
    colliders = []
    for enemy in enemies:
        if not enemy.alive:
            continue
        if not player.body.overlaps_vertically(enemy.body):
            continue
        difference = enemy.previous_x - player.previous_x
        side = (1 if difference > 0 else -1) if difference else -enemy.facing
        colliders.append((enemy, side))
        if side < 0:
            low = max(low, enemy.previous_x + separation)
        else:
            high = min(high, enemy.previous_x - separation)

    original_x = player.x
    if low <= high:
        player.x = clamp(player.x, low, high)
    # If a landing puts the player between overlapping enemies, move enemies
    # apart from the player instead of looping to resolve contradictory limits.
    for enemy, side in colliders:
        if player.body.overlaps(enemy.body):
            position = player.x + side * separation
            if not config.ENEMY_HALF_WIDTH <= position <= config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH:
                position = player.x - side * separation
            enemy.x = clamp(position, config.ENEMY_HALF_WIDTH,
                            config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH)
    if player.x != original_x:
        player.vx = 0.0
