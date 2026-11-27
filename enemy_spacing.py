"""Melee formations and independent ranged-peer ground-plane separation."""

from functools import lru_cache
import json
from math import exp, hypot

import config
from combat import MOVES
from collision import same_floor
from physics import clamp
from sniper import Sniper


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


def _foot_obstacles(obstacles, margin=0.0):
    return [(x, y, min(width, 2 * config.ENEMY_HALF_WIDTH), config.BODY_DEPTH_TOLERANCE + margin)
            for x, y, width, _ in obstacles]


def _nearest_ranged_position(enemy, obstacles, origin, *, firing_at=None):
    """Find the nearest free footprint without iterative pushes or wall escape."""
    area, padding = enemy.walkable, enemy.boundary_padding
    x, y = area.project(*origin, padding)
    if firing_at is not None:
        fire_left, fire_right = enemy.firing_x_limits(firing_at)
    if (_ranged_position_free(x, y, obstacles) and (firing_at is None
            or (fire_left <= x <= fire_right
                and abs(y - firing_at.ground_y) < config.ATTACK_DEPTH_TOLERANCE))):
        return x, y
    lanes = {y, *(py for _, py in area.inset(padding))}
    for _, oy, _, depth in obstacles:
        lanes.update((oy - depth, oy + depth))
    if firing_at is not None:
        py = firing_at.ground_y
        band = config.ATTACK_DEPTH_TOLERANCE - config.ENEMY_SPACING_TOLERANCE
        lanes.update((py, py - band, py + band))
    candidates = []
    for lane in sorted(lanes):
        limits = area.x_limits(lane, padding)
        if limits is None:
            continue
        low, high = limits
        if firing_at is not None:
            if abs(lane - py) > band:
                continue
            low = max(low, fire_left)
            high = min(high, fire_right)
            if low > high:
                continue
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


def place_ranged_spawns(player, existing, spawned, *, include_snipers=False):
    """Separate new riflemen and, in the final boss room, snipers on arrival."""
    def spaces_on_entry(enemy):
        return enemy.uses_ranged_spacing or (include_snipers and isinstance(enemy, Sniper))

    placed = [e for e in existing if spaces_on_entry(e) and e.alive
              and e.staircase is None and not e.falling_from_upper]
    for enemy in spawned:
        if not spaces_on_entry(enemy):
            continue
        start = enemy.x, enemy.ground_y
        obstacles = _ranged_obstacles(enemy, placed, player)
        position = _nearest_ranged_position(enemy, obstacles, start)
        if position is None:
            # A full sprite row may not fit at the entrance. Use clear feet
            # for this arrival and leave the existing actors where they are.
            position = _nearest_ranged_position(enemy, _foot_obstacles(obstacles), start)
        if position is not None and position != start:
            enemy.x, enemy.ground_y = position
            enemy.previous_x, enemy.previous_ground_y = position
        placed.append(enemy)


def clear_route(enemy, goal, obstacles, waypoint_tolerance=1e-8):
    """Find a walkable first waypoint around the rectangles, using either axis for a detour."""
    x, y = enemy.x, enemy.ground_y
    gx, gy = goal
    if not (_ranged_position_free(x, y, obstacles) and _ranged_position_free(gx, gy, obstacles)):
        return None

    def clear(ax, ay, bx, by):
        # For axis-aligned detours this is the exact swept foot rectangle.
        return all(max(ax, bx) <= ox - w + 1e-8 or min(ax, bx) >= ox + w - 1e-8
                   or max(ay, by) <= oy - d + 1e-8 or min(ay, by) >= oy + d - 1e-8
                   for ox, oy, w, d in obstacles)

    if clear(x, y, gx, gy):
        return goal
    # A corridor may run above/below a rifleman, or left/right around a
    # vertical queue. Choose the shortest clear route on this floor.
    routes = []
    lanes = {y, gy, *(oy + offset for _, oy, _, d in obstacles for offset in (-d, d))}
    columns = {x, gx, *(ox + offset for ox, _, w, _ in obstacles for offset in (-w, w))}
    for lane in lanes:
        if clear(x, y, x, lane) and clear(x, lane, gx, lane) and clear(gx, lane, gx, gy):
            routes.append(((x, lane), (gx, lane)))
    for col in columns:
        if clear(x, y, col, y) and clear(col, y, col, gy) and clear(col, gy, gx, gy):
            routes.append(((col, y), (col, gy)))
    candidates = []
    for first, second in routes:
        if not all(enemy.walkable.contains(*p, enemy.boundary_padding) for p in (first, second)):
            continue
        length = hypot(first[0] - x, first[1] - y) + hypot(second[0] - first[0], second[1] - first[1])
        length += hypot(gx - second[0], gy - second[1])
        waypoint = next((p for p in (first, second, goal)
                         if hypot(p[0] - x, p[1] - y) > waypoint_tolerance), goal)
        candidates.append((length, waypoint))
    return min(candidates)[1] if candidates else None


def _approach_waypoint(enemy, goal, peers, player):
    if goal == (enemy.x, enemy.ground_y):
        return goal
    obstacles = _ranged_obstacles(enemy, peers, player)
    waypoint = clear_route(enemy, goal, obstacles)
    if waypoint is not None:
        return waypoint
    # A narrow floor may not fit a whole sprite above or below the front
    # shooter. Pass on a separate foot lane and spread out again at the goal.
    bodies = _foot_obstacles(obstacles, config.ENEMY_SPACING_MARGIN)
    return clear_route(enemy, goal, bodies) or goal


def _prepare_ranged_approach(player, enemies):
    peers = [e for e in enemies if e.uses_ranged_spacing and e.alive and same_floor(e, player)
             and not e.falling_from_upper]
    moving = [e for e in peers if e.state in ("IDLE", "WALK", "RUN")
              and e.navigation_target is None and not e.knockback_started]
    if len(peers) < 2:
        for enemy in moving:
            enemy.ranged_goal = None
            enemy.has_firing_slot = True
        return
    reserved = {e: (e.x, e.ground_y) for e in peers if e not in moving}
    # After a reload, a soldier with more shots can give up its slot to a
    # waiting peer. Only the destinations change; both actors travel normally.
    moving.sort(key=lambda e: (e.rounds_fired, e.ranged_goal is None, abs(e.x - player.x)))
    band = config.ATTACK_DEPTH_TOLERANCE - config.ENEMY_SPACING_TOLERANCE
    for enemy in moving:
        obstacles = _ranged_obstacles(enemy, reserved, positions=reserved)
        muzzle_gap = enemy.muzzle_x + enemy.projectile_type.half_width
        obstacles.append((player.x, player.ground_y, muzzle_gap, band + 2))
        side = 1 if enemy.x >= player.x else -1
        # Preserve a valid approach on successive ticks. Pick a different
        # firing lane when another rifle already covers the player's depth.
        lane = player.ground_y
        if any((ox - player.x) * side > 0 and abs(oy - lane) < config.BODY_DEPTH_TOLERANCE
               for ox, oy in reserved.values()):
            _, bottom, _, top = enemy.walkable.bounds
            lane += band if top - lane >= lane - bottom else -band
        fire_left, fire_right = enemy.firing_x_limits(player)
        preferred_x = enemy.x
        if not fire_left <= preferred_x <= fire_right:
            # Aim inside the moving band so a squad can actually reach its reserved slot.
            preferred_x += player.vx * enemy.aim_duration
        gap = clamp(side * (preferred_x - player.x), muzzle_gap, enemy.shoot_range)
        preferred = (player.x + side * gap, lane)
        if enemy.ranged_goal is not None:
            gx, gy = enemy.ranged_goal
            if (fire_left <= gx <= fire_right and abs(gy - player.ground_y) <= band
                    and _ranged_position_free(gx, gy, obstacles)):
                preferred = enemy.ranged_goal
        goal = _nearest_ranged_position(enemy, obstacles, preferred, firing_at=player)
        enemy.has_firing_slot = goal is not None
        if goal is None:
            # Reserve a waiting footprint outside the firing band without
            # occupying a destination another rifleman is still approaching.
            origin = (player.x + side * (enemy.shoot_range + 2 * ranged_half_width(enemy)), enemy.ground_y)
            goal = _nearest_ranged_position(enemy, obstacles, origin)
            if goal is None:
                goal = _nearest_ranged_position(enemy, _foot_obstacles(obstacles), origin)
        if goal is None:
            goal = enemy.x, enemy.ground_y
        reserved[enemy] = enemy.ranged_goal = goal
        enemy.target_x, enemy.target_ground_y = _approach_waypoint(enemy, goal, peers, player)


def _allows_step(start, position, obstacles):
    # Hit reactions may already have put two feet inside each other. Allow a
    # step that reduces that overlap, without pushing either actor elsewhere.
    x, y = position
    for ox, oy, width, depth in obstacles:
        clearance = max(abs(x - ox) / width, abs(y - oy) / depth)
        if clearance < 1 - 1e-9:
            before = max(abs(start[0] - ox) / width, abs(start[1] - oy) / depth)
            if clearance <= before:
                return False
    return True


def resolve_ranged_spacing(player, enemies):
    """Yield a contested step without pushing another actor or adding movement."""
    active = [e for e in enemies if e.uses_ranged_spacing and e.alive and same_floor(e, player)
              and not e.falling_from_upper]
    previous = {e: (e.previous_x, e.previous_ground_y) for e in active}
    for enemy in active:
        start = previous.pop(enemy)
        # A landing against a wall can force the body solver to move a planted shooter.
        # Cancel before World emits a shot from a position the warning never showed.
        if enemy.state == "ATTACK" and hypot(enemy.x - start[0], enemy.ground_y - start[1]) > 1e-8:
            enemy.stop()
        if (enemy.x, enemy.ground_y) != start and enemy.state in ("WALK", "RUN"):
            obstacles = [(x, y, 2 * config.ENEMY_HALF_WIDTH, config.BODY_DEPTH_TOLERANCE)
                         for e, (x, y) in previous.items() if enemy.body.overlaps_vertically(e.body)]
            obstacles.append((player.x, player.ground_y, config.ENEMY_HALF_WIDTH + config.PLAYER_HALF_WIDTH,
                              config.BODY_DEPTH_TOLERANCE))
            if not _ranged_position_free(enemy.x, enemy.ground_y, obstacles):
                options = ((enemy.x, enemy.ground_y), (enemy.x, start[1]), (start[0], enemy.ground_y))
                enemy.x, enemy.ground_y = next((p for p in options if _allows_step(start, p, obstacles)), start)
                if enemy.x == start[0]:
                    enemy.vx = 0.0
                if enemy.ground_y == start[1]:
                    enemy.ground_vy = 0.0
                if not (enemy.vx or enemy.ground_vy):
                    enemy.animation.set_state("IDLE")
        previous[enemy] = enemy.x, enemy.ground_y


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
                or enemy.state == "STRONG_HIT"):
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

    if player.alive:
        _prepare_ranged_approach(player, enemies)
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
              and enemy.state != "STRONG_HIT"]
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
