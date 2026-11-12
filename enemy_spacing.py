"""Stable, side-local attack slots and soft projected crowd separation."""

from functools import lru_cache
import json
from math import exp

import config
from combat import MOVES
from physics import approach, clamp


@lru_cache(maxsize=1)
def sprite_extents():
    """Reserve the occupied PNG envelope, including offsets and attack frames.

    Using one envelope rather than the current frame avoids breathing/jitter as
    the baton extends. Clip metadata is shared with rendering; Pillow is not used.
    """
    with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
        rows = json.load(file)[config.ENEMY_IMAGE]
    tiles = [tile for row in rows[:5] for tile in row]
    left = min(tile["offset_x"] - tile["clip"][2] / 2 for tile in tiles)
    right = max(tile["offset_x"] + tile["clip"][2] / 2 for tile in tiles)
    return left * config.SPRITE_SCALE, right * config.SPRITE_SCALE


def slot_cell(slot, columns=2):
    """Stagger the first arrivals across lanes before filling their second column."""
    if columns == 1:
        return slot, 0
    lanes = config.ENEMY_FORMATION_LANES
    block, cell = divmod(slot, lanes * 2)
    lane = block * lanes + cell % lanes
    column = (cell // lanes + lane % 2) % 2
    return lane, column


def prepare_enemy_spacing(player, enemies):
    """Assign persistent slots from a snapshot before any enemy moves."""
    groups = {-1: [], 1: []}
    for enemy in enemies:
        enemy.target_x = None
        enemy.target_depth = 0.0
        if not player.alive or not enemy.alive or enemy.knockback_started:
            enemy.formation_slot = None
            continue
        difference = enemy.x - player.x
        side = (1 if difference > 0 else -1) if difference else -enemy.facing
        limit = (config.ENEMY_FORMATION_RELEASE_DISTANCE if enemy.formation_slot is not None
                 else config.ENEMY_FORMATION_DISTANCE)
        if side != enemy.formation_side or abs(difference) > limit:
            enemy.formation_slot = None
        enemy.formation_side = side
        if abs(difference) <= limit:
            groups[side].append(enemy)

    left, right = sprite_extents()
    desired_gap = right - left + config.ENEMY_SPACING_MARGIN
    body_gap = config.PLAYER_HALF_WIDTH + config.ENEMY_HALF_WIDTH
    # Both sides can really connect: rear slots must remain counterable even
    # with the player's shortest basic attack, not just trigger enemy animation.
    reach = min(config.ENEMY_ATTACK_REACH + config.PLAYER_HALF_WIDTH,
                min(move.reach for move in MOVES.values()) + config.ENEMY_HALF_WIDTH)
    reach -= config.ENEMY_SPACING_MARGIN
    for side, group in groups.items():
        room = (player.x - config.ENEMY_HALF_WIDTH if side < 0 else
                config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH - player.x)
        far = min(reach, room)
        if len(group) < 2 or far < body_gap:
            for enemy in group:
                enemy.formation_slot = None
            continue
        used = {enemy.formation_slot for enemy in group if enemy.formation_slot is not None}
        # Existing assignments survive overtaking, animation changes and deaths.
        # Stable sorting breaks exact-coordinate ties in spawn/list order.
        for enemy in sorted(group, key=lambda actor: abs(actor.x - player.x)):
            if enemy.formation_slot is None:
                slot = 0
                while slot in used:
                    slot += 1
                enemy.formation_slot = slot
                used.add(slot)
        near = min(body_gap + config.ENEMY_SPACING_MARGIN, far)
        columns = 2 if far - near >= desired_gap * 0.3 else 1
        maximum_lane = max(slot_cell(slot, columns)[0] for slot in used)
        levels = max(1, (maximum_lane + 1) // 2)
        depth_step = min(config.ENEMY_DEPTH_STEP, config.ENEMY_DEPTH_LIMIT / levels)
        # Full sprite width cannot fit twice in the melee strip. Depth lanes
        # allow controlled silhouette overlap without extending attack reach.
        gap = min(desired_gap, far - near)
        for enemy in group:
            lane, column = slot_cell(enemy.formation_slot, columns)
            level = (lane + 1) // 2
            enemy.target_depth = level * depth_step * (1 if lane % 2 else -1)
            enemy.target_x = player.x + side * (near + column * gap)


def resolve_enemy_spacing(player, enemies, dt):
    """Ease depth and relieve severe attack overlap; never project/teleport x."""
    if not player.alive:
        return
    active = [enemy for enemy in enemies if enemy.alive and not enemy.knockback_started]
    for enemy in active:
        enemy.depth = approach(enemy.depth, enemy.target_depth, config.ENEMY_DEPTH_SPEED * dt)

    left, right = sprite_extents()
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
            if (abs(first.x - second.x) < gap - config.ENEMY_ATTACK_SEPARATION_SLOP
                    and abs(first.depth - second.depth) < config.ENEMY_DEPTH_STEP * 0.75):
                crowded.update((first, second))

    damping = 1 - exp(-config.ENEMY_SEPARATION_RATE * dt)
    for enemy in crowded:
        # Walking already steers to the slot at the enemy's original AI speed.
        # HIT and knockback keep their movement rules; only ATTACK needs relief.
        if enemy.state != "ATTACK":
            continue
        error = enemy.target_x - enemy.x
        maximum = config.ENEMY_ATTACK_SEPARATION_SPEED * dt
        correction = clamp(error * damping, -maximum, maximum)
        side = enemy.formation_side
        # A moving/jumping player may pass an attacker. Do not pull that enemy
        # across the player, or move farther than the remaining map space.
        distance = (enemy.x - player.x) * side
        minimum = config.PLAYER_HALF_WIDTH + config.ENEMY_HALF_WIDTH
        if side * correction < 0:
            correction = side * max(side * correction, min(0.0, minimum - distance))
        proposed = enemy.x + correction
        if config.ENEMY_HALF_WIDTH <= proposed <= config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH:
            enemy.x = proposed
