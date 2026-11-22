"""Melee formations and independent ranged-peer ground-plane separation."""

from functools import lru_cache
import json
from math import exp, hypot

import config
from combat import MOVES
from collision import same_floor
from physics import clamp


@lru_cache(maxsize=16)
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


def ranged_half_width(enemy):
    left, right = sprite_extents(enemy.image_name)
    return max(config.ENEMY_HALF_WIDTH, abs(left), abs(right)) + config.ENEMY_SPACING_MARGIN / 2


def _ranged_position_free(x, y, obstacles):
    return all(abs(x - ox) >= width - 1e-9 or abs(y - oy) >= depth - 1e-9
               for ox, oy, width, depth in obstacles)


def _ranged_obstacles(enemy, peers, player=None, positions=None):
    positions = {} if positions is None else positions
    obstacles = [(*positions.get(other, (other.x, other.ground_y)),
                  ranged_half_width(enemy) + ranged_half_width(other),
                  max(enemy.peer_spacing_depth, other.peer_spacing_depth))
                 for other in peers
                 if other is not enemy and same_floor(enemy, other)
                 and enemy.body.overlaps_vertically(other.body)]
    if player is not None and same_floor(enemy, player) and enemy.body.overlaps_vertically(player.body):
        obstacles.append((player.x, player.ground_y,
                          config.ENEMY_HALF_WIDTH + config.PLAYER_HALF_WIDTH,
                          config.BODY_DEPTH_TOLERANCE))
    return obstacles


def _nearest_ranged_position(enemy, obstacles):
    """Find the nearest free footprint without iterative pushes or wall escape."""
    x, y = enemy.x, enemy.ground_y
    if _ranged_position_free(x, y, obstacles):
        return x, y
    area, padding = enemy.walkable, enemy.boundary_padding
    lanes = {y, enemy.previous_ground_y, *(py for _, py in area.inset(padding))}
    for _, oy, _, depth in obstacles:
        lanes.update((oy - depth, oy + depth))
    candidates = []
    for lane in sorted(lanes):
        limits = area.x_limits(lane, padding)
        if limits is None:
            continue
        low, high = limits
        intervals = sorted((ox - width, ox + width) for ox, oy, width, depth in obstacles
                           if abs(lane - oy) < depth - 1e-9)
        merged = []
        for start, end in intervals:
            if merged and start < merged[-1][1] - 1e-9:
                merged[-1] = merged[-1][0], max(merged[-1][1], end)
            else:
                merged.append((start, end))
        target = clamp(x, low, high)
        options = (target,)
        for start, end in merged:
            if start + 1e-9 < target < end - 1e-9:
                options = tuple(edge for edge in (start, end) if low <= edge <= high)
                break
        for target in options:
            # Compare in footprint units, so sideways spacing is not sacrificed
            # just because belt depth is smaller than the visible sprite width.
            cost = ((target - x) / (2 * ranged_half_width(enemy))) ** 2
            cost += ((lane - y) / enemy.peer_spacing_depth) ** 2
            candidates.append((cost, abs(lane - y), target, lane))
    if not candidates:
        return None
    _, _, x, y = min(candidates)
    return x, y


def _place_ranged_actor(enemy, position):
    x, y = position
    moved_x, moved_y = abs(x - enemy.x) > 1e-9, abs(y - enemy.ground_y) > 1e-9
    if not (moved_x or moved_y):
        return
    enemy.x, enemy.ground_y = x, y
    if moved_x:
        enemy.vx = 0.0
    if moved_y:
        enemy.ground_vy = 0.0
    if enemy.state == "ATTACK":
        # Only a displaced shooter needs a fresh warning; unchanged neighbours
        # keep their clocks and already-fired rounds.
        enemy.stop()
    elif (enemy.state in ("WALK", "RUN")
          and hypot(x - enemy.previous_x, y - enemy.previous_ground_y) <= 1e-9):
        enemy.animation.set_state("IDLE")


def _reflow_ranged_peer(enemy, placed, player):
    """Open a second full-height row only when lateral space has run out."""
    # Prefer relocating the last arrival over an established front-line shooter.
    for other in reversed(placed):
        if not same_floor(enemy, other) or not enemy.body.overlaps_vertically(other.body):
            continue
        area = other.walkable
        _, bottom, _, top = area.bounds
        for lane in sorted((bottom, top), key=lambda y: abs(y - other.ground_y)):
            position = area.project(other.x, lane, other.boundary_padding)
            if not _ranged_position_free(*position, _ranged_obstacles(other, placed, player)):
                continue
            obstacles = _ranged_obstacles(enemy, placed, player, {other: position})
            destination = _nearest_ranged_position(enemy, obstacles)
            if destination is not None:
                _place_ranged_actor(other, position)
                return destination
    return None


def resolve_ranged_spacing(player, enemies):
    """Reserve AR footprints, keeping stationary shooters ahead of incoming peers."""
    active = [enemy for enemy in enemies
              if enemy.uses_ranged_spacing and enemy.alive
              and enemy.staircase is None and not enemy.falling_from_upper
              and enemy.state != "RUSH_CARRIED"]
    if len(active) < 2 or not player.alive:
        return
    # Stable snapshot ordering: a moving rifleman yields to an established aim,
    # burst/reload or flinch, instead of dragging its neighbour's firing lane.
    active.sort(key=lambda enemy: (
        hypot(enemy.x - enemy.previous_x, enemy.ground_y - enemy.previous_ground_y) > 1e-9,
        enemy.state not in ("ATTACK", "RELOAD", "HIT"),
        enemy.spawned_at, enemy.previous_x, enemy.previous_ground_y))
    placed = []
    for index, enemy in enumerate(active):
        obstacles = _ranged_obstacles(enemy, placed, player)
        # A valid previous footprint is a reservation too. Otherwise two moving
        # rows can push one another across the map every tick instead of yielding.
        future = [other for other in active[index + 1:]
                  if (abs(enemy.previous_x - other.previous_x)
                      >= ranged_half_width(enemy) + ranged_half_width(other) - 1e-9
                      or abs(enemy.previous_ground_y - other.previous_ground_y)
                      >= max(enemy.peer_spacing_depth, other.peer_spacing_depth) - 1e-9)]
        previous = {other: (other.previous_x, other.previous_ground_y) for other in future}
        reserved = _ranged_obstacles(enemy, future, positions=previous)
        position = _nearest_ranged_position(enemy, obstacles + reserved)
        if position is None:
            position = _nearest_ranged_position(enemy, obstacles)
        if position is None:
            position = _reflow_ranged_peer(enemy, placed, player)
        if position is not None:
            _place_ranged_actor(enemy, position)
        placed.append(enemy)


def prepare_enemy_spacing(player, enemies, walkable=None):
    """Assign persistent slots from a snapshot before any enemy moves."""
    walkable = player.walkable if walkable is None else walkable
    groups = {-1: [], 1: []}
    for enemy in enemies:
        enemy.target_x = None
        enemy.target_ground_y = None
        if (not enemy.uses_melee_slots or not same_floor(player, enemy)
                or enemy.navigation_target is not None or enemy.falling_from_upper
                or not player.alive or not enemy.alive or enemy.knockback_started
                or enemy.leaping
                or enemy.state in ("STRONG_HIT", "RUSH_CARRIED", "RUSH_RELEASED")):
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
    # Both sides can really connect: rear slots must remain reachable even
    # with the player's shortest basic attack, not just trigger enemy animation.
    reach = min(config.ENEMY_ATTACK_REACH + config.PLAYER_HALF_WIDTH,
                min(move.reach for move in MOVES.values()) + config.ENEMY_HALF_WIDTH)
    reach -= config.ENEMY_SPACING_MARGIN
    floor = walkable.inset(padding)
    band = max(0.0, config.ATTACK_DEPTH_TOLERANCE - config.ENEMY_SPACING_MARGIN)
    band_bottom = max(min(y for _, y in floor), player.ground_y - band)
    top = min(max(y for _, y in floor), player.ground_y + band)
    for side, group in groups.items():
        preferred_bottom = max((enemy.formation_ground_min for enemy in group
                                if enemy.formation_ground_min is not None), default=band_bottom)
        # City formations use the pavement in front of the buildings, rather
        # than placing their front row below the curb just to spread out.
        # Following a player who actually enters the road remains possible.
        bottom = max(band_bottom, min(player.ground_y, preferred_bottom))
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
            ground_y = clamp(origin + offsets[lane] * depth_step, bottom, top)
            target_x, target_y = walkable.project(player.x + side * (near + column * gap),
                                                  ground_y, padding)
            if (target_x - player.x) * side >= 0:
                enemy.target_ground_y = target_y
                enemy.target_x = target_x


def resolve_enemy_spacing(player, enemies, dt, walkable=None):
    """Ease severe overlap on the floor, then constrain every state and path."""
    walkable = player.walkable if walkable is None else walkable
    active = [enemy for enemy in enemies
              if enemy.uses_melee_slots and same_floor(player, enemy)
              and enemy.navigation_target is None and not enemy.falling_from_upper
              and player.alive and enemy.alive and not enemy.knockback_started
              and not enemy.leaping
              and enemy.state not in ("STRONG_HIT", "RUSH_CARRIED", "RUSH_RELEASED")]
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
    resolve_ranged_spacing(player, enemies)
    for enemy in enemies:
        if enemy.staircase is None:
            area = walkable if same_floor(player, enemy) else enemy.walkable
            area.constrain(enemy, config.ENEMY_HALF_WIDTH)
