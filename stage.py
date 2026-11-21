"""Independent street scenes and world-space backgrounds/exit markers."""

from math import ceil, floor, sin, sqrt, tau
import random

import config
from axe_enemy import AxeEnemy
from doors import StageDoor
from drop_items import spawn_drop_items
from enemy import Enemy
from enemy02 import Enemy02
from physics import clamp
from researcher import Researcher
from spawn_manager import SpawnManager, SpawnPoint
from stairs import Staircase, can_use_stairs
from walkable import WalkableArea, for_stage


class Stage:
    def __init__(self, index=0, *, rng=None, attack_sequence=None, traffic_rng=None, item_rng=None):
        self.index = index
        self.arrows_visible = False
        self.enemies = []
        self.effects = []
        self.afterimages = []
        self.damage_numbers = []
        self.projectiles = []
        self.doors = [StageDoor(kind, rect)
                      for kind, rect in config.STAGE_DOOR_SPECS.get(self.image_name, ())]
        self.walkable = for_stage(index)
        self.route_rng = random.Random()
        if rng is not None:
            # Navigation decisions never consume spawn or combat randomness.
            self.route_rng.setstate(rng.getstate())
        upper_bounds = config.STAGE_UPPER_FLOOR_BOUNDS.get(self.image_name)
        self.upper_walkable = (WalkableArea.rectangle(*upper_bounds) if upper_bounds else None)
        self.stairs = [Staircase(path, lower_area=self.walkable)
                       for path in config.STAGE_STAIR_PATHS.get(self.image_name, ())]
        drop_bounds = config.STAGE_DROP_ITEM_SPAWN_BOUNDS.get(self.image_name)
        self.drop_spawn_area = (WalkableArea.rectangle(*drop_bounds) if drop_bounds is not None
                                else self.walkable)
        self.drop_items = spawn_drop_items(self.drop_spawn_area, rng=item_rng,
                                          upper_walkable=self.upper_walkable)
        spawn_bounds = config.STAGE_ENEMY_SPAWN_BOUNDS.get(self.image_name)
        self.spawn_area = (WalkableArea.rectangle(*spawn_bounds) if spawn_bounds is not None
                           else self.walkable)
        enemy_type = Enemy
        if self.image_name == config.FACTORY_OUTSIDE_IMAGE:
            enemy_type = AxeEnemy
        elif self.image_name in config.ENEMY02_STAGE_IMAGES:
            enemy_type = Enemy02
        elif self.image_name in config.FACTORY_INSIDE_IMAGES:
            enemy_type = Researcher
        self.spawner = SpawnManager(rng=rng, walkable=self.walkable, spawn_area=self.spawn_area,
                                    attack_sequence=attack_sequence,
                                    enemy_type=enemy_type, extra_sources=self.open_door_spawns)
        self.traffic = None  # Road traffic is retired; no stage creates cars.

    def constrain_actor(self, actor):
        if actor.staircase is not None:
            return
        if not 0 <= actor.floor < len(self.floor_areas):
            actor.floor = 0
        actor.walkable = self.area_for(actor)
        half_width = (actor.body.right - actor.body.left) / 2
        actor.walkable.constrain(actor, half_width)

    @property
    def floor_areas(self):
        return (self.walkable, self.upper_walkable) if self.upper_walkable else (self.walkable,)

    def area_for(self, actor):
        return self.floor_areas[actor.floor]

    @property
    def camera_y_bounds(self):
        anchor = config.STAGE_GROUND_ANCHORS.get(self.image_name, config.STAGE_GROUND_Y)
        bottom = config.GROUND_Y - anchor * config.STAGE_SCALE
        # Include the complete artwork and the highest possible running double
        # jump, not just the lower floor or the original 720px viewport.
        jump = (config.JUMP_SPEED ** 2 + config.RUN_DOUBLE_JUMP_SPEED ** 2) / (2 * config.GRAVITY)
        player_top = (max(area.bounds[3] for area in self.floor_areas) + jump
                      + config.CAMERA_PLAYER_HEIGHT + config.CAMERA_TOP_MARGIN
                      + config.PLAYER_HIT_SHAKE_STRENGTH)
        top = max(bottom + config.STAGE_IMAGE_HEIGHT * config.STAGE_SCALE, player_top)
        return min(0.0, bottom), max(0.0, top - config.SCREEN_HEIGHT)

    def open_door_spawns(self):
        if not self.doors:
            return ()
        width, height = config.TWO_FLOOR_MAP_SIZE
        scale = config.STAGE_SCALE
        anchor = config.STAGE_GROUND_ANCHORS.get(self.image_name, config.STAGE_GROUND_Y)
        bottom = config.GROUND_Y - anchor * scale
        points = []
        floors = config.STAGE_DOOR_FLOORS[self.image_name]
        for tile in range(ceil(config.WORLD_WIDTH / (width * scale))):
            for index, door in enumerate(self.doors):
                if door.state != "OPEN":
                    continue
                left, top, door_width, door_height = door.source_rect
                center = left + door_width / 2
                x = (tile * width + (width - center if tile % 2 else center)) * scale
                # Do not project off-map copies into a fake spawn at the edge.
                if not 0 <= x <= config.WORLD_WIDTH:
                    continue
                area = self.floor_areas[floors[index]]
                y = bottom + (height - top - door_height - 12) * scale
                x, y = area.project(x, y, self.spawner.enemy_type.boundary_padding)
                points.append(SpawnPoint(x, y, floors[index], area, ("door", index, tile)))
        return points

    def release_actor(self, actor):
        for stair in self.stairs:
            stair.release(actor)
        actor.navigation_target = None

    def exit_player_stairs(self, player, controls):
        """Fresh Space/left/right detaches without changing the visible feet."""
        if player.staircase is None:
            return False
        lateral = controls.take_latest_press(("left", "right"))
        jumping = controls.take_press("jump")
        if (not player.alive or player.state not in ("IDLE", "WALK")
                or not (jumping or (lateral is not None and controls.direction))):
            return False
        feet = player.y
        player.staircase.detach(player)
        player.floor = int(self.upper_walkable is not None and feet >= self.upper_walkable.bounds[1])
        area = self.area_for(player)
        _, bottom, _, top = area.bounds
        player.ground_y = clamp(feet, bottom, top)
        player.previous_x = player.x
        player.previous_ground_y = player.ground_y
        player.jump_height = player.previous_jump_height = max(0.0, feet - player.ground_y)
        player.walkable = area
        player.vx = player.ground_vy = 0.0
        player.vy = config.JUMP_SPEED if jumping else 0.0
        player.jump_count = 1 if jumping else 2
        player.air_kicks_used = 0
        player.upper_landing_requested = False
        player.falling_from_upper = not jumping and player.jump_height > 0
        player.stair_regrab_remaining = config.STAIR_REGRAB_DELAY
        player.animation.set_state("JUMP" if jumping or not player.grounded else "IDLE")
        player.animation.elapsed = 0.0
        return True

    def try_player_stair_catch(self, player):
        if (not player.alive or player.staircase is not None or player.stair_regrab_remaining > 0
                or player.jump_count != 1 or player.vy > 0
                or player.jump_height < config.STAIR_JUMP_CATCH_MIN_HEIGHT
                or player.falling_from_upper or player.counter_move is not None
                or player.active_move is not None or player.state != "JUMP"):
            return False
        return any(stair.catch_player(player) for stair in self.stairs)

    def prepare_player_double_jump(self, player):
        """Reach the upper ledge even with an early second Space press."""
        if (self.upper_walkable is None or player.floor != 0 or player.falling_from_upper
                or player.staircase is not None or player.active_move is not None):
            return
        # Base this on the entire lower floor, not the current depth. Steering
        # up/down must not alter the jump curve or put the apex off-screen.
        target = (self.upper_walkable.bounds[1] - self.walkable.bounds[1]
                  + config.UPPER_PLATFORM_JUMP_CLEARANCE)
        remaining = max(0.0, target - player.jump_height)
        # Compensate for the semi-implicit, fixed-step gravity integrator.
        minimum_speed = sqrt(2 * config.GRAVITY * remaining) + config.GRAVITY * config.FIXED_DT / 2
        player.vy = max(player.vy, minimum_speed)

    def resolve_player_platforms(self, player, controls):
        """One-way upper landing and a gravity-driven drop from its front edge."""
        if (self.upper_walkable is None or player.staircase is not None
                or not player.alive or player.counter_move is not None
                or player.active_move is not None):
            return
        front = self.upper_walkable.bounds[1]
        if player.floor == 1:
            if (controls.depth_direction < 0 and player.ground_y <= front + 1e-9
                    and player.state in ("IDLE", "WALK", "RUN", "JUMP")):
                feet, previous_feet = player.y, player.previous_ground_y + player.previous_jump_height
                self.release_actor(player)
                player.floor = 0
                player.walkable = self.walkable
                player.x, player.ground_y = self.walkable.project(
                    player.x, self.walkable.bounds[3], player.boundary_padding)
                # Rebase height, preserving the displayed feet and vertical
                # momentum. Falling is not an instant jump down to the street.
                player.jump_height = feet - player.ground_y
                player.previous_ground_y = player.ground_y
                player.previous_jump_height = max(0.0, previous_feet - player.ground_y)
                player.jump_count = 2  # No extra mid-fall jump or immediate recatch.
                player.falling_from_upper = True
                player.upper_landing_requested = False
                player.animation.set_state("JUMP")
            return
        if player.falling_from_upper or player.jump_count != 2 or player.grounded:
            return
        if controls.depth_direction > 0:
            player.upper_landing_requested = True
        elif controls.depth_direction < 0:
            player.upper_landing_requested = False
        previous_feet = player.previous_ground_y + player.previous_jump_height
        if (player.upper_landing_requested and player.vy <= 0
                and previous_feet >= front and player.y <= front
                and self.upper_walkable.contains(player.x, front, player.boundary_padding)):
            self.release_actor(player)
            player.floor = 1
            player.walkable = self.upper_walkable
            player.ground_y = player.previous_ground_y = front
            player.jump_height = player.vy = 0.0
            player.previous_jump_height = max(0.0, previous_feet - front)
            player.jump_count = player.air_kicks_used = 0
            player.upper_landing_requested = False
            player.animation.set_state("IDLE")

    def update_navigation(self, dt, player, controls):
        """Route cross-floor enemies and grant stair entry in arrival order."""
        if not self.stairs:
            return set()
        actors = [player, *self.enemies]
        for stair in self.stairs:
            for actor in tuple(stair.occupants):
                if actor not in actors or not actor.alive or not player.alive:
                    stair.release(actor)
        if player.staircase is not None:
            # Route enemies toward the new destination on the reversal tick.
            player.staircase.set_player_direction(player, controls.depth_direction)
        destination = (player.staircase.destination_floor if player.staircase else player.floor)
        if player.alive:
            self.assign_descent_routes(destination)
        requests = {stair: [] for stair in self.stairs}
        for enemy in self.enemies:
            enemy.navigation_target = None
            if not player.alive or not can_use_stairs(enemy):
                continue
            if enemy.floor == destination and player.staircase is None:
                continue
            if enemy.floor == 1 and destination == 0 and enemy.descent_route == "DROP":
                enemy.formation_slot = None
                if enemy.descent_delay > 0:
                    enemy.descent_delay = max(0.0, enemy.descent_delay - dt)
                    enemy.navigation_target = (enemy.x, enemy.ground_y)
                else:
                    enemy.navigation_target = (enemy.x, self.upper_walkable.bounds[1])
                continue
            stair = min(self.stairs, key=lambda candidate: candidate.distance_to_entry(enemy))
            enemy.navigation_target = stair.entrance(enemy.floor)
            enemy.formation_slot = None
            if enemy.floor != destination and (
                    enemy in stair.queue or stair.distance_to_entry(enemy) <= config.STAIR_QUEUE_RADIUS):
                requests[stair].append(enemy)
        if (can_use_stairs(player) and player.stair_regrab_remaining <= 0
                and controls.direction == 0):
            direction = 1 if player.floor == 0 else -1
            if controls.depth_direction == direction:
                for stair in self.stairs:
                    if stair.distance_to_entry(player) <= config.STAIR_ENTRY_RADIUS:
                        requests[stair].append(player)
                        break
        for stair, wanted in requests.items():
            stair.queue[:] = [actor for actor in stair.queue if actor in wanted]
            for actor in wanted:
                stair.request(actor)
            ranks = {0: 0, 1: 0}
            for actor in stair.queue:
                rank = ranks[actor.floor]
                ranks[actor.floor] += 1
                if actor is player:
                    continue
                x, y = stair.entrance(actor.floor)
                actor.navigation_target = self.area_for(actor).project(
                    x + rank * config.STAIR_QUEUE_GAP, y - (24 if rank else 0),
                    actor.boundary_padding)
            stair.start_next()
        moved = set()
        for stair in self.stairs:
            moved.update(stair.update(dt, player=player, direction=controls.depth_direction))
        for actor in moved:
            self.constrain_actor(actor)
        return moved

    def assign_descent_routes(self, destination):
        if self.upper_walkable is None:
            return
        candidates = []
        for enemy in self.enemies:
            if not enemy.falling_from_upper and (destination != 0 or enemy.floor == 0):
                enemy.descent_route = None
                enemy.descent_delay = 0.0
            if (destination == 0 and enemy.floor == 1 and can_use_stairs(enemy)
                    and enemy.descent_route is None):
                candidates.append(enemy)
        # A lone arrival can still use the stairs. Leave it undecided so that
        # another arrival before entry can form a new randomly split group.
        if len(candidates) < 2:
            return
        count = self.route_rng.randint(1, len(candidates) - 1)
        dropping = set(self.route_rng.sample(candidates, count))
        for enemy in candidates:
            enemy.descent_route = "DROP" if enemy in dropping else "STAIRS"
            enemy.descent_delay = (self.route_rng.uniform(*config.ENEMY_DROP_DELAY_RANGE)
                                   if enemy in dropping else 0.0)

    def resolve_enemy_drop(self, enemy, player):
        destination = player.staircase.destination_floor if player.staircase else player.floor
        if (self.upper_walkable is not None and destination == 0 and player.alive
                and enemy.floor == 1 and enemy.descent_route == "DROP" and can_use_stairs(enemy)
                and enemy.descent_delay <= 0
                and enemy.ground_y <= self.upper_walkable.bounds[1] + 1e-9):
            self.release_actor(enemy)
            enemy.begin_floor_fall(self.walkable, ground_y=player.ground_y)

    @property
    def image_name(self):
        return config.STAGE_IMAGES[self.index]

    @property
    def arrow_sides(self):
        if not self.arrows_visible:
            return ()
        return (1,) if self.index == 0 else (-1, 1)

    def destination(self, side):
        target = self.index + side
        if side in self.arrow_sides and 0 <= target < len(config.STAGE_IMAGES):
            return target
        return None

    def toggle_doors(self):
        for door in self.doors:
            door.toggle()

    def update_doors(self, dt):
        for door in self.doors:
            door.update(dt)

    def draw(self, assets, camera_x=0.0, camera_y=0.0, *, elapsed=0.0):
        # Keep the supplied character/building scale instead of enlarging the
        # artwork to the full world width. Mirrored tiles join without a cut.
        image = assets.images[self.image_name]
        scale = config.STAGE_SCALE
        width = image.w * scale
        height = image.h * scale
        anchor = config.STAGE_GROUND_ANCHORS.get(self.image_name, config.STAGE_GROUND_Y)
        bottom = config.GROUND_Y - anchor * scale - camera_y
        bottom = min(0.0, bottom)
        roof = bottom + height
        headroom = max(0.0, config.SCREEN_HEIGHT - roof)
        first = max(0, floor(camera_x / width))
        last = min(ceil(config.WORLD_WIDTH / width),
                   ceil((camera_x + config.SCREEN_WIDTH) / width))
        for index in range(first, last):
            image.composite_draw(
                0, "h" if index % 2 else "",
                index * width + width / 2 - camera_x,
                bottom + height / 2, width, height,
            )
            if headroom:
                # The jump can rise above the supplied artwork. Extend only
                # its top edge; keep the actual map/floors at their world y.
                image.clip_composite_draw(
                    0, image.h - 1, image.w, 1, 0, "h" if index % 2 else "",
                    index * width + width / 2 - camera_x, roof + headroom / 2,
                    width, headroom,
                )
            for door in self.doors:
                assets.draw_stage_door(door, image, index * width - camera_x, bottom,
                                       scale, mirrored=bool(index % 2))
        # Flat floor props stay underneath characters, vehicles and exit markers.
        for item in self.drop_items:
            if item.grounded:
                assets.draw_drop_item(item, camera_x, camera_y)
        sway = (sin(tau * elapsed / config.STAGE_ARROW_SWAY_PERIOD)
                * config.STAGE_ARROW_SWAY_AMPLITUDE)
        for side in self.arrow_sides:
            arrow = assets.images[config.STAGE_ARROW_IMAGES[side]]
            x = (config.STAGE_EXIT_MARGIN if side < 0 else
                 config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN)
            arrow.draw(x + side * sway - camera_x, config.STAGE_ARROW_Y - camera_y,
                       config.STAGE_ARROW_WIDTH, config.STAGE_ARROW_WIDTH * arrow.h / arrow.w)
