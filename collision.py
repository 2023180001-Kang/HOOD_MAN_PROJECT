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

    def translated(self, dx=0.0, dy=0.0):
        return Rect(self.left + dx, self.bottom + dy, self.right + dx, self.top + dy)


def world_rect(rect, actor):
    return rect.translated(dy=actor.ground_y - config.GROUND_Y)


def transit_target(actor):
    return (getattr(actor, "staircase", None) is not None
            or getattr(actor, "falling_from_upper", False))


def attack_hits_body(attacker, target, box):
    if box is None:
        return False
    if transit_target(target):
        # Stairs change elevation, not melee depth. Compare the visible bodies
        # instead of rejecting the target merely because it is between floors.
        return (attacker.staircase is None
                and world_rect(box, attacker).overlaps(world_rect(target.body, target)))
    return (same_floor(attacker, target)
            and abs(attacker.ground_y - target.ground_y) <= config.ATTACK_DEPTH_TOLERANCE
            and box.overlaps(target.body))


def same_floor(first, second):
    return (getattr(first, "floor", 0) == getattr(second, "floor", 0)
            and getattr(first, "staircase", None) is None
            and getattr(second, "staircase", None) is None
            and not getattr(first, "stair_arrival", False)
            and not getattr(second, "stair_arrival", False))


def bodies_overlap(first, second):
    return (same_floor(first, second)
            and abs(first.ground_y - second.ground_y) < config.BODY_DEPTH_TOLERANCE - 1e-9
            and first.body.overlaps(second.body))


def body_contact_time(first, second, *, allow_transit=False):
    """First simultaneous x/depth/height body contact during the current step."""
    transit = allow_transit and first.staircase is None and transit_target(second)
    if not transit and not same_floor(first, second):
        return None
    half_width = (first.body.right - first.body.left + second.body.right - second.body.left) / 2
    first_height = first.body.top - first.body.bottom
    second_height = second.body.top - second.body.bottom
    depth = config.BODY_DEPTH_TOLERANCE - 1e-9
    axes = (
        (second.previous_x - first.previous_x, second.x - first.x, -half_width, half_width),
        (second.previous_ground_y - first.previous_ground_y,
         second.ground_y - first.ground_y, -depth, depth),
        (second.previous_jump_height - first.previous_jump_height,
         second.jump_height - first.jump_height, -second_height, first_height),
    )
    if transit:
        axes = (
            axes[0],
            (second.previous_ground_y + second.previous_jump_height
             - first.previous_ground_y - first.previous_jump_height,
             second.y - first.y, -second_height, first_height),
        )
    enter, leave = 0.0, 1.0
    for start, end, low, high in axes:
        delta = end - start
        if abs(delta) < 1e-12:
            if not low <= start <= high:
                return None
            continue
        first_time, last_time = sorted(((low - start) / delta, (high - start) / delta))
        enter, leave = max(enter, first_time), min(leave, last_time)
        if enter > leave:
            return None
    return enter


def resolve_bodies(player, enemies, walkable=None):
    """Constrain player motion, then let enemies yield; bounded, non-iterative."""
    if player.staircase is not None:
        return
    enemies = [enemy for enemy in enemies if same_floor(player, enemy)]
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
