"""Persistent, side-local 2D melee slots with bounded ground-plane separation."""

from functools import lru_cache
import json
from math import exp, hypot

import config
from combat import MOVES
from physics import clamp


@lru_cache(maxsize=2)
def sprite_extents(image_name=config.ENEMY_IMAGE):
    """Reserve the occupied PNG envelope, including offsets and attack frames.

    Using one envelope rather than the current frame avoids breathing/jitter as
    the baton extends. Clip metadata is shared with rendering; Pillow is not used.
    """
    with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
        rows = json.load(file)[image_name]
    tiles = [tile for row in rows[:-1] for tile in row]
    left = min(tile["offset_x"] - tile["clip"][2] / 2 for tile in tiles)
    right = max(tile["offset_x"] + tile["clip"][2] / 2 for tile in tiles)
    return left * config.SPRITE_SCALE, right * config.SPRITE_SCALE


def encounter_envelope(enemies):
    images = {enemy.image_name for enemy in enemies} or {config.ENEMY_IMAGE}
    extents = [sprite_extents(name) for name in images]
    return (min(left for left, _ in extents), max(right for _, right in extents),
            max((enemy.boundary_padding for enemy in enemies), default=config.ENEMY_BOUNDARY_PADDING))


def slot_cell(slot, columns=2):
    """Stagger the first arrivals across lanes before filling their second column."""
    if columns == 1:
        return slot, 0
    lanes = config.ENEMY_FORMATION_LANES
    block, cell = divmod(slot, lanes * 2)
    lane = block * lanes + cell % lanes
    column = (cell // lanes + lane % 2) % 2
    return lane, column


def prepare_enemy_spacing(player, enemies, walkable=None):
    """Assign persistent slots from a snapshot before any enemy moves."""
    walkable = player.walkable if walkable is None else walkable
    groups = {-1: [], 1: []}
    for enemy in enemies:
        enemy.target_x = None
        enemy.target_ground_y = None
        if (not player.alive or not enemy.alive or enemy.knockback_started
                or enemy.counter_move is not None):
            enemy.formation_slot = None
            continue
        difference = enemy.x - player.x
        distance = hypot(difference, enemy.ground_y - player.ground_y)
        side = (1 if difference > 0 else -1) if difference else -enemy.facing
        limit = (config.ENEMY_FORMATION_RELEASE_DISTANCE if enemy.formation_slot is not None
                 else config.ENEMY_FORMATION_DISTANCE)
        if side != enemy.formation_side or distance > limit:
            enemy.formation_slot = None
        enemy.formation_side = side
        if distance <= limit:
            groups[side].append(enemy)

    left, right, padding = encounter_envelope(enemies)
    desired_gap = right - left + config.ENEMY_SPACING_MARGIN
    body_gap = config.PLAYER_HALF_WIDTH + config.ENEMY_HALF_WIDTH
    # Both sides can really connect: rear slots must remain counterable even
    # with the player's shortest basic attack, not just trigger enemy animation.
    reach = min(config.ENEMY_ATTACK_REACH + config.PLAYER_HALF_WIDTH,
                min(move.reach for move in MOVES.values()) + config.ENEMY_HALF_WIDTH)
    reach -= config.ENEMY_SPACING_MARGIN
    floor = walkable.inset(padding)
    band = max(0.0, config.ATTACK_DEPTH_TOLERANCE - config.ENEMY_SPACING_MARGIN)
    bottom = max(min(y for _, y in floor), player.ground_y - band)
    top = min(max(y for _, y in floor), player.ground_y + band)
    for side, group in groups.items():
        _, center_y = walkable.project(player.x, player.ground_y, padding)
        limits = walkable.x_limits(center_y, padding)
        room = player.x - limits[0] if side < 0 else limits[1] - player.x
        far = min(reach, room)
        if len(group) < 2 or far < body_gap or bottom > top:
            for enemy in group:
                enemy.formation_slot = None
            continue
        used = {enemy.formation_slot for enemy in group if enemy.formation_slot is not None}
        # Existing assignments survive overtaking, animation changes and deaths.
        # Stable sorting breaks exact-coordinate ties in spawn/list order.
        for enemy in sorted(group, key=lambda actor: hypot(actor.x - player.x,
                                                         actor.ground_y - player.ground_y)):
            if enemy.formation_slot is None:
                slot = 0
                while slot in used:
                    slot += 1
                enemy.formation_slot = slot
                used.add(slot)
        near = min(body_gap + config.ENEMY_SPACING_MARGIN, far)
        columns = 2 if far - near >= desired_gap * 0.3 else 1
        maximum_lane = max(slot_cell(slot, columns)[0] for slot in used)
        offsets = [((lane + 1) // 2) * (1 if lane % 2 else -1)
                   for lane in range(maximum_lane + 1)]
        low, high = min(offsets), max(offsets)
        depth_step = min(config.ENEMY_DEPTH_STEP, (top - bottom) / max(1, high - low))
        origin = clamp(player.ground_y, bottom - low * depth_step, top - high * depth_step)
        # Compress inside both the walkable floor and the real melee depth band.
        # A crowded wall never pushes targets outside, even with many enemies.
        gap = min(desired_gap, far - near)
        for enemy in group:
            lane, column = slot_cell(enemy.formation_slot, columns)
            ground_y = origin + offsets[lane] * depth_step
            target_x, target_y = walkable.project(player.x + side * (near + column * gap),
                                                  ground_y, padding)
            if (target_x - player.x) * side >= 0:
                enemy.target_ground_y = target_y
                enemy.target_x = target_x


def resolve_enemy_spacing(player, enemies, dt, walkable=None):
    """Ease severe overlap on the floor, then constrain every state and path."""
    walkable = player.walkable if walkable is None else walkable
    active = [enemy for enemy in enemies
              if player.alive and enemy.alive and not enemy.knockback_started
              and enemy.counter_move is None]
    left, right, _ = encounter_envelope(enemies)
    width = right - left + config.ENEMY_SPACING_MARGIN
    crowded = set()
    for index, first in enumerate(active):
        if first.target_x is None:
            continue
        for second in active[index + 1:]:
            if second.target_x is None or first.formation_side != second.formation_side:
                continue
            gap = min(width, abs(first.target_x - second.target_x))
            if gap <= config.ENEMY_SPACING_TOLERANCE:
                gap = min(width, config.ENEMY_ATTACK_REACH - config.ENEMY_HALF_WIDTH
                          - 2 * config.ENEMY_SPACING_MARGIN)
            depth_gap = abs(first.target_ground_y - second.target_ground_y)
            depth_gap = max(config.BODY_DEPTH_TOLERANCE, depth_gap)
            if (abs(first.x - second.x) < gap - config.ENEMY_ATTACK_SEPARATION_SLOP
                    and abs(first.ground_y - second.ground_y) < depth_gap * 0.75):
                crowded.update((first, second))

    damping = 1 - exp(-config.ENEMY_SEPARATION_RATE * dt)
    for enemy in crowded:
        # Walking already steers to the slot at the enemy's original AI speed.
        # HIT and knockback keep their movement rules; only ATTACK needs relief.
        if enemy.state != "ATTACK":
            continue
        error_x = (enemy.target_x - enemy.x) * damping
        error_y = (enemy.target_ground_y - enemy.ground_y) * damping
        maximum = config.ENEMY_ATTACK_SEPARATION_SPEED * dt
        length = hypot(error_x, error_y)
        if length > maximum:
            error_x, error_y = error_x / length * maximum, error_y / length * maximum
        side = enemy.formation_side
        # A moving/jumping player may pass an attacker. Do not pull that enemy
        # across the player, or move farther than the remaining map space.
        distance = (enemy.x - player.x) * side
        minimum = config.PLAYER_HALF_WIDTH + config.ENEMY_HALF_WIDTH
        if (side * error_x < 0
                and abs(enemy.ground_y - player.ground_y) < config.BODY_DEPTH_TOLERANCE):
            error_x = side * max(side * error_x, min(0.0, minimum - distance))
        enemy.x += error_x
        enemy.ground_y += error_y
    for enemy in enemies:
        walkable.constrain(enemy, config.ENEMY_HALF_WIDTH)
