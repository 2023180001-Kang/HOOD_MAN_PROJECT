"""x/height-plane hit rectangles and depth-aware ground body constraints."""

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


def bodies_overlap(first, second):
    return (abs(first.ground_y - second.ground_y) < config.BODY_DEPTH_TOLERANCE - 1e-9
            and first.body.overlaps(second.body))


def resolve_bodies(player, enemies, walkable=None):
    """Constrain player motion, then let enemies yield; bounded, non-iterative."""
    walkable = player.walkable if walkable is None else walkable
    walkable.constrain(player, config.PLAYER_HALF_WIDTH)
    for enemy in enemies:
        walkable.constrain(enemy, config.ENEMY_HALF_WIDTH)
    if player.counter_move is not None:
        # Keep the choreographed pair fixed; other actors yield to the player.
        separation = config.PLAYER_HALF_WIDTH + config.ENEMY_HALF_WIDTH
        for enemy in enemies:
            if not enemy.blocks_movement or enemy.counter_move is not None or not bodies_overlap(player, enemy):
                continue
            side = (1 if enemy.x > player.x else -1) if enemy.x != player.x else -enemy.facing
            enemy.x = player.x + side * separation
            walkable.constrain(enemy, config.ENEMY_HALF_WIDTH)
        return
    # A vertical approach should stop at the footprint edge, rather than turn
    # into a horizontal wall or allow walking through a different floor lane.
    for enemy in enemies:
        if not enemy.blocks_movement or not bodies_overlap(player, enemy):
            continue
        previous_depth = enemy.previous_ground_y - player.previous_ground_y
        if abs(previous_depth) >= config.BODY_DEPTH_TOLERANCE - 1e-9:
            side = 1 if previous_depth > 0 else -1
            if player.ground_y != player.previous_ground_y:
                player.ground_y = enemy.previous_ground_y - side * config.BODY_DEPTH_TOLERANCE
                player.ground_vy = 0.0
                walkable.constrain(player, config.PLAYER_HALF_WIDTH)
            if bodies_overlap(player, enemy):
                enemy.ground_y = player.ground_y + side * config.BODY_DEPTH_TOLERANCE
                enemy.ground_vy = 0.0
                walkable.constrain(enemy, config.ENEMY_HALF_WIDTH)

    low, high = walkable.x_limits(player.ground_y, player.boundary_padding)
    separation = config.PLAYER_HALF_WIDTH + config.ENEMY_HALF_WIDTH
    room_low, room_high = low, high
    colliders = []
    for enemy in enemies:
        if not enemy.blocks_movement:
            continue
        if not player.body.overlaps_vertically(enemy.body):
            continue
        if abs(player.ground_y - enemy.ground_y) >= config.BODY_DEPTH_TOLERANCE - 1e-9:
            continue
        difference = enemy.previous_x - player.previous_x
        side = (1 if difference > 0 else -1) if difference else -enemy.facing
        colliders.append((enemy, side))
        if side < 0:
            low = max(low, enemy.previous_x + separation)
            edge, _ = walkable.x_limits(enemy.ground_y, enemy.boundary_padding)
            room_low = max(room_low, edge + separation)
        else:
            high = min(high, enemy.previous_x - separation)
            _, edge = walkable.x_limits(enemy.ground_y, enemy.boundary_padding)
            room_high = min(room_high, edge - separation)

    original_x = player.x
    low, high = max(low, room_low), min(high, room_high)
    if low <= high:
        player.x = clamp(player.x, low, high)
    else:
        # A crowded landing at a wall must leave space on the original sides.
        # Moving the player just inside that feasible interval avoids flipping
        # an enemy through the player to the opposite side.
        player.x = clamp(player.x, room_low, room_high)
    # If a landing puts the player between overlapping enemies, move enemies
    # apart from the player instead of looping to resolve contradictory limits.
    for enemy, side in colliders:
        walkable.constrain(enemy, config.ENEMY_HALF_WIDTH)
        if bodies_overlap(player, enemy) or (enemy.x - player.x) * side < separation:
            position = player.x + side * separation
            enemy.x = position
            walkable.constrain(enemy, config.ENEMY_HALF_WIDTH)
    if player.x != original_x:
        player.vx = 0.0
    walkable.constrain(player, config.PLAYER_HALF_WIDTH)
