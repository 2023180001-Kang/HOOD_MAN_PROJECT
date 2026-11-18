from math import hypot
import random
import unittest

import config
from collision import bodies_overlap
from combat import MOVES
from controls import Controls
from enemy import Enemy
from enemy_spacing import prepare_enemy_spacing, resolve_enemy_spacing
from player import Player
from tests.helpers import advance, tap
from walkable import WalkableArea
from world import World


def ready(enemies):
    for enemy in enemies:
        enemy.animation.set_state("ATTACK")
        enemy.animation.elapsed = 4 / config.ENEMY_ANIMATIONS["ATTACK"][1]
        enemy.has_hit = False
        enemy.cooldown = 1.0


class BeltScrollTests(unittest.TestCase):
    def assert_inside(self, world):
        for actor, padding in ((world.player, config.PLAYER_BOUNDARY_PADDING),
                               *((enemy, config.ENEMY_BOUNDARY_PADDING) for enemy in world.enemies)):
            self.assertTrue(world.stage.walkable.contains(actor.x, actor.ground_y, padding),
                            (actor.state, actor.x, actor.ground_y, world.stage_index))
            self.assertGreaterEqual(actor.jump_height, 0.0)

    def test_eight_directions_use_one_normalized_walking_or_running_speed(self):
        area = WalkableArea.rectangle(0, -1000, config.WORLD_WIDTH, 1000)
        directions = (("right",), ("left",), ("up",), ("down",),
                      ("right", "up"), ("right", "down"), ("left", "up"), ("left", "down"))
        for running in (False, True):
            for keys in directions:
                with self.subTest(running=running, keys=keys):
                    player, controls = Player(), Controls()
                    for key in keys:
                        controls.press(key)
                    if running:
                        controls.press("left_shift")
                    speed = config.RUN_SPEED if running else config.WALK_SPEED
                    for _ in range(60):
                        player.update(config.FIXED_DT, controls, area)
                        self.assertLessEqual(hypot(player.vx, player.ground_vy), speed + 1e-8)
                    self.assertAlmostEqual(hypot(player.vx, player.ground_vy), speed)
                    dx, dy = controls.movement
                    self.assertAlmostEqual(player.vx, dx * speed)
                    self.assertAlmostEqual(player.ground_vy, dy * speed)
                    self.assertEqual(player.state, "RUN" if running else "WALK")
                    self.assertEqual(player.jump_height, 0)

    def test_opposite_vertical_keys_cancel_and_vertical_motion_preserves_facing(self):
        world = World()
        world.player.facing = -1
        for key in ("up", "down", "right_shift"):
            world.controls.press(key)
        advance(world, 0.2)
        self.assertEqual(world.player.ground_y, config.GROUND_Y)
        self.assertEqual(world.player.state, "IDLE")
        world.controls.release("down")
        advance(world, 0.05)
        self.assertGreater(world.player.ground_y, config.GROUND_Y)
        self.assertEqual(world.player.facing, -1)

    def test_changing_cardinal_diagonal_and_shift_input_never_exceeds_speed_cap(self):
        player, controls = Player(), Controls()
        area = WalkableArea.rectangle(0, -1000, config.WORLD_WIDTH, 1000)
        controls.press("right")
        controls.press("left_shift")
        for frame in range(180):
            if frame == 50:
                controls.press("up")
            elif frame == 80:
                controls.release("right")
                controls.press("left")
            elif frame == 100:
                controls.release("left_shift")
            player.update(config.FIXED_DT, controls, area)
            self.assertLessEqual(hypot(player.vx, player.ground_vy), config.RUN_SPEED + 1e-8)
        self.assertAlmostEqual(hypot(player.vx, player.ground_vy), config.WALK_SPEED)

    def test_jump_curve_is_identical_while_ground_position_moves_and_hits_a_boundary(self):
        for running in (False, True):
            with self.subTest(running=running):
                actual, reference = World(), World()
                actual.enemies.clear()
                reference.enemies.clear()
                actual.controls.press("up")
                reference.controls.press("right")
                if running:
                    actual.controls.press("left_shift")
                    reference.controls.press("left_shift")
                actual.controls.press("jump")
                reference.controls.press("jump")
                for frame in range(240):
                    if frame in (6, 12):
                        tap(actual.controls, "jump")
                        tap(reference.controls, "jump")
                    actual.step(config.FIXED_DT)
                    reference.step(config.FIXED_DT)
                    self.assertEqual((actual.player.jump_height, actual.player.vy, actual.player.jump_count),
                                     (reference.player.jump_height, reference.player.vy,
                                      reference.player.jump_count))
                    self.assert_inside(actual)
                self.assertTrue(actual.player.grounded)
                self.assertEqual(actual.player.ground_y, actual.stage.walkable.bounds[3])
                self.assertEqual(actual.player.y, actual.player.ground_y)

    def test_airborne_floor_motion_can_reverse_without_rewriting_jump_height(self):
        world = World()
        world.controls.press("up")
        world.controls.press("jump")
        advance(world, 0.1)
        height, velocity = world.player.jump_height, world.player.vy
        world.controls.release("up")
        world.controls.press("down")
        world.step(config.FIXED_DT)
        self.assertAlmostEqual(world.player.vy, velocity - config.GRAVITY * config.FIXED_DT)
        self.assertAlmostEqual(world.player.jump_height, height + world.player.vy * config.FIXED_DT)
        advance(world, 0.2)
        self.assertLess(world.player.ground_vy, 0)
        self.assert_inside(world)

    def test_attacks_hits_and_death_stop_both_floor_velocity_components(self):
        for state in ("attack", "hit", "death"):
            with self.subTest(state=state):
                world = World()
                world.player.vx, world.player.ground_vy = 200, 100
                world.controls.press("right")
                world.controls.press("up")
                if state == "attack":
                    world.controls.press("combat_s")
                else:
                    world.player.take_damage(20 if state == "hit" else 500)
                point = world.player.x, world.player.ground_y
                world.step(config.FIXED_DT)
                self.assertEqual((world.player.x, world.player.ground_y), point)
                self.assertEqual((world.player.vx, world.player.ground_vy), (0, 0))

    def test_world_player_bounds_cover_all_four_floor_corners_in_all_stages(self):
        for stage_index in range(len(config.STAGE_IMAGES)):
            for horizontal in ("left", "right"):
                for vertical in ("up", "down"):
                    with self.subTest(stage=stage_index, horizontal=horizontal, vertical=vertical):
                        world = World()
                        world.stage_index = stage_index
                        world.enemies.clear()  # Isolate the floor from enemy body blocking.
                        world.stage.traffic = None  # Isolate walking limits from lethal road hazards.
                        for key in (horizontal, vertical, "left_shift"):
                            world.controls.press(key)
                        for _ in range(5 * 120):
                            world.step(config.FIXED_DT)
                            self.assert_inside(world)
                        left, bottom, right, top = world.stage.walkable.bounds
                        padding = config.PLAYER_BOUNDARY_PADDING
                        self.assertEqual(world.player.x, left + padding if horizontal == "left" else right - padding)
                        self.assertEqual(world.player.ground_y, top if vertical == "up" else bottom)
                        self.assertEqual((world.player.vx, world.player.ground_vy), (0, 0))

    def test_both_actor_hit_directions_require_ground_depth_tolerance(self):
        for side in (-1, 1):
            for depth, expected in ((0, True), (32, True), (32.001, False), (-32, True), (-40, False)):
                with self.subTest(side=side, depth=depth):
                    player = Player()
                    enemy = Enemy(player.x + side * 80, -side, ground_y=player.ground_y + depth)
                    player.start_move(MOVES["combat_a"], side)
                    player.animation.elapsed = 3 / MOVES["combat_a"].fps
                    self.assertEqual(player.try_hit(enemy), expected)
                    self.assertEqual(enemy.hp, 190 if expected else 200)
                    ready([enemy])
                    self.assertEqual(enemy.try_hit(player), expected)
                    self.assertEqual(player.hp, 480 if expected else 500)

    def test_depth_miss_does_not_consume_player_target_or_enemy_swing(self):
        player = Player()
        enemy = Enemy(player.x + 80, -1, ground_y=140)
        player.start_move(MOVES["combat_s"], 1)
        player.animation.elapsed = 3 / MOVES["combat_s"].fps
        ready([enemy])
        self.assertFalse(player.try_hit(enemy))
        self.assertFalse(enemy.try_hit(player))
        self.assertFalse(enemy.has_hit)
        self.assertNotIn(enemy, player.hit_enemies)
        enemy.ground_y = 110
        self.assertTrue(player.try_hit(enemy))
        ready([enemy])
        self.assertTrue(enemy.try_hit(player))
        self.assertFalse(player.try_hit(enemy))
        self.assertFalse(enemy.try_hit(player))

    def test_jump_height_and_floor_depth_are_independent_hit_filters(self):
        player = Player()
        enemy = Enemy(player.x + 80, -1, ground_y=140)
        ready([enemy])
        self.assertFalse(enemy.try_hit(player))
        enemy.ground_y = 100
        player.jump_height = config.ENEMY_HEIGHT + 1
        self.assertFalse(enemy.try_hit(player))
        player.jump_height = 0
        self.assertTrue(enemy.try_hit(player))

    def test_vertical_body_approach_stops_at_feet_and_other_lanes_can_pass(self):
        world = World()
        world.player.ground_y = world.player.previous_ground_y = 70
        enemy = Enemy(world.player.x, ground_y=110)
        enemy.cooldown = 100
        world.enemies = [enemy]
        world.controls.press("up")
        for _ in range(120):
            world.step(config.FIXED_DT)
            self.assertFalse(bodies_overlap(world.player, enemy))
        self.assertLessEqual(world.player.ground_y, enemy.ground_y - config.BODY_DEPTH_TOLERANCE)
        world = World()
        enemy = Enemy(world.player.x + 60, -1, ground_y=130)
        enemy.cooldown = 100
        world.enemies = [enemy]
        world.controls.press("right")
        advance(world, 0.5)
        self.assertGreater(world.player.x, enemy.x)

    def test_ai_tracks_ground_depth_with_original_per_enemy_total_speed(self):
        for speed in config.ENEMY_RUN_SPEEDS:
            world = World()
            world.player.ground_y = 148
            enemy = Enemy(world.player.x - 600, run_speed=speed, ground_y=56)
            world.enemies = [enemy]
            world.step(config.FIXED_DT)
            self.assertGreater(enemy.vx, 0)
            self.assertGreater(enemy.ground_vy, 0)
            self.assertAlmostEqual(hypot(enemy.vx, enemy.ground_vy), speed)
            self.assertEqual(enemy.state, "RUN")

    def test_every_enemy_state_constrains_invalid_or_outward_floor_positions(self):
        for stage_index in range(len(config.STAGE_IMAGES)):
            area = World().stages[stage_index].walkable
            left, bottom, right, top = area.bounds
            for state in config.ENEMY_ANIMATIONS:
                for x, ground_y in ((left - 20, bottom - 20), (right + 20, top + 20)):
                    with self.subTest(stage=stage_index, state=state, x=x):
                        enemy = Enemy(x, ground_y=ground_y)
                        enemy.animation.set_state(state)
                        if state in ("DEAD", "DYING"):
                            enemy.hp = 0
                        if state == "KNOCKBACK":
                            enemy.knockback_started = True
                            enemy.vx, enemy.ground_vy = 450, 450
                        player = Player()
                        enemy.update(config.FIXED_DT, player, area)
                        self.assertTrue(area.contains(enemy.x, enemy.ground_y, enemy.boundary_padding))
                        resolve_enemy_spacing(player, [enemy], config.FIXED_DT, area)
                        self.assertTrue(area.contains(enemy.x, enemy.ground_y, enemy.boundary_padding))

    def test_2_5_10_enemies_at_all_corners_stay_inside_after_attack_separation_and_knockback(self):
        for stage_index in range(len(config.STAGE_IMAGES)):
            for count in (2, 5, 10):
                for corner in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
                    with self.subTest(stage=stage_index, count=count, corner=corner):
                        world = World()
                        world.stage_index = stage_index
                        left, bottom, right, top = world.stage.walkable.bounds
                        sx, sy = corner
                        world.player.x = left + 100 if sx < 0 else right - 100
                        world.player.ground_y = bottom if sy < 0 else top
                        world.player.invincible = True
                        world.enemies = [Enemy(world.player.x - sx * 80, sx,
                                               ground_y=world.player.ground_y) for _ in range(count)]
                        ready(world.enemies)
                        for frame in range(360):
                            if frame == 180:
                                for enemy in world.enemies[:2]:
                                    enemy.knockback(world.player.x, world.player.ground_y - sy * 50)
                            world.step(config.FIXED_DT)
                            self.assert_inside(world)
                        self.assertEqual(world.stage_index, stage_index)

    def test_ten_per_side_all_reach_attack_depth_and_twenty_can_hit_in_one_step(self):
        for stage_index in range(len(config.STAGE_IMAGES)):
            world = World()
            world.stage_index = stage_index
            world.stage.traffic = None  # All twenty must survive to exercise their melee attacks.
            world.player.invincible = True
            world.enemies = [Enemy(world.player.x + side * 500, -side, ground_y=56,
                                   run_speed=config.ENEMY_RUN_SPEEDS[index % 4])
                             for side in (-1, 1) for index in range(10)]
            hits = set()
            for _ in range(8 * 120):
                before = [enemy.has_hit for enemy in world.enemies]
                world.step(config.FIXED_DT)
                self.assert_inside(world)
                for enemy, was_hit in zip(world.enemies, before):
                    if enemy.state == "ATTACK" and enemy.has_hit and not was_hit:
                        hits.add(enemy)
            self.assertEqual(hits, set(world.enemies))
            self.assertTrue(all(abs(enemy.ground_y - world.player.ground_y) <= 32
                                for enemy in world.enemies))
            world.player.invincible = False
            ready(world.enemies)
            world.step(config.FIXED_DT)
            self.assertEqual(world.player.hp, 100)
            self.assertTrue(all(enemy.has_hit for enemy in world.enemies))

    def test_valid_corner_arrivals_never_teleport_the_player_or_attacking_enemies(self):
        for stage_index in range(len(config.STAGE_IMAGES)):
            for count in (2, 5, 10):
                for sx, sy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
                    world = World()
                    world.stage_index = stage_index
                    world.stage.traffic = None  # Measure AI movement without vehicle knockback.
                    _, bottom, right, top = world.stage.walkable.bounds
                    player = world.player
                    player.x = player.boundary_padding if sx < 0 else right - player.boundary_padding
                    player.ground_y = bottom if sy < 0 else top
                    player.invincible = True
                    point = player.x, player.ground_y
                    world.enemies = [Enemy(player.x - sx * 300, sx, ground_y=player.ground_y,
                                           run_speed=config.ENEMY_RUN_SPEEDS[index % 4])
                                     for index in range(count)]
                    for _ in range(360):
                        before = [(enemy.x, enemy.ground_y, enemy.state) for enemy in world.enemies]
                        world.step(config.FIXED_DT)
                        self.assert_inside(world)
                        self.assertEqual((player.x, player.ground_y), point)
                        for enemy, (x, y, state) in zip(world.enemies, before):
                            maximum = max(enemy.run_speed, config.ENEMY_SPEED) * config.FIXED_DT
                            if state == enemy.state == "ATTACK":
                                maximum = config.ENEMY_ATTACK_SEPARATION_SPEED * config.FIXED_DT
                            self.assertLessEqual(hypot(enemy.x - x, enemy.ground_y - y), maximum + 1e-8)

    def test_slot_targets_fit_floor_and_melee_depth_before_any_actor_moves(self):
        for stage_index in range(len(config.STAGE_IMAGES)):
            for count in (2, 5, 10):
                for ground_y in (56, 100, config.STAGE_WALKABLE_BOUNDS[stage_index][3]):
                    world = World()
                    world.stage_index = stage_index
                    world.player.ground_y = ground_y
                    world.enemies = [Enemy(world.player.x + 100, -1, ground_y=ground_y)
                                     for _ in range(count)]
                    prepare_enemy_spacing(world.player, world.enemies, world.stage.walkable)
                    for enemy in world.enemies:
                        self.assertIsNotNone(enemy.target_x)
                        self.assertTrue(world.stage.walkable.contains(enemy.target_x,
                                                                     enemy.target_ground_y, enemy.boundary_padding))
                        self.assertLessEqual(abs(enemy.target_ground_y - ground_y), 32)
                        self.assertGreater(enemy.target_x, world.player.x)

    def test_stage_transfer_preserves_jump_and_projects_floor_to_destination_region(self):
        world = World()
        world.stage.arrows_visible = True
        player = world.player
        player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
        player.ground_y = world.stage.walkable.bounds[3]
        player.jump_height, player.vy, player.jump_count = 120, 300, 2
        player.vx = 720
        self.assertTrue(world.try_stage_transition())
        self.assertIs(world.player, player)
        self.assertEqual(world.stage_index, 1)
        self.assertEqual(player.ground_y, 116)
        self.assertEqual((player.jump_height, player.vy, player.jump_count, player.vx), (120, 300, 2, 720))
        self.assertEqual(player.previous_ground_y, 116)
        self.assert_inside(world)
        self.assertEqual(world.camera.x, 0)
        world.stage.arrows_visible = True
        player.x, player.vx = 80, -720
        self.assertTrue(world.try_stage_transition())
        self.assertEqual(world.stage_index, 0)
        self.assertEqual(player.ground_y, 116)
        self.assert_inside(world)

    def test_camera_shake_never_changes_world_walkable_limits(self):
        world = World()
        top = world.stage.walkable.bounds[3]
        world.player.ground_y = top
        world.player.x = config.PLAYER_BOUNDARY_PADDING
        world.camera.shake()
        bounds = world.stage.walkable.bounds
        for _ in range(100):
            world.camera.update(config.FIXED_DT, 2500)
            world.stage.constrain_actor(world.player)
            self.assertEqual(world.stage.walkable.bounds, bounds)
            self.assertEqual((world.player.x, world.player.ground_y), (config.PLAYER_BOUNDARY_PADDING, top))

    def test_convex_polygon_foot_projection_is_idempotent_and_respects_padding(self):
        area = WalkableArea(((0, 56), (400, 56), (400, 100), (200, 148), (0, 148)))
        for point in ((-20, 0), (450, 200), (390, 145), (200, 100), (10, 140)):
            x, y = area.project(*point, 32)
            self.assertTrue(area.contains(x, y, 32))
            self.assertEqual(area.project(x, y, 32), (x, y))
            self.assertTrue(area.contains(x - 32, y))
            self.assertTrue(area.contains(x + 32, y))
        clockwise = WalkableArea(area.vertices[::-1])
        self.assertEqual(clockwise.project(450, 200, 32), area.project(450, 200, 32))
        with self.assertRaises(ValueError):
            WalkableArea(((0, 0), (100, 0), (30, 30), (100, 100), (0, 100)))

    def test_polygon_applies_to_live_world_movement_and_knockback(self):
        world = World()
        area = WalkableArea(((0, 56), (2560, 56), (2560, 100), (2200, 148), (0, 148)))
        world.stage.walkable = area
        world.player.x, world.player.ground_y = 2500, 90
        world.player.invincible = True
        for key in ("up", "right", "left_shift", "jump"):
            world.controls.press(key)
        world.enemies = [Enemy(2500, ground_y=100) for _ in range(10)]
        for enemy in world.enemies:
            enemy.knockback(2400, 56)
        for _ in range(480):
            world.step(config.FIXED_DT)
            self.assert_inside(world)

    def test_spawn_floor_positions_and_restart_are_stage_specific(self):
        world = World(rng=random.Random(17))
        for index in (0, 1):
            world.stage_index = index
            tap(world.controls, "spawn_9")
            world.step(config.FIXED_DT)
            self.assert_inside(world)
            self.assertGreater(len({enemy.ground_y for enemy in world.enemies}), 1)
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertEqual((world.player.ground_y, world.player.jump_height, world.player.ground_vy),
                         (config.GROUND_Y, 0, 0))
        self.assertTrue(all(not stage.enemies for stage in world.stages))

    def test_scripted_2d_world_is_independent_of_render_frame_rate(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world = World(rng=random.Random(901))
            world.player.invincible = True
            world.controls.press("spawn_5")
            world.update(config.FIXED_DT)
            for keys in (("right", "up", "left_shift", "jump"), ("right", "down", "combat_a"),
                         ("left", "up", "combat_f"), ("down",)):
                world.controls.held.clear()
                for key in keys:
                    world.controls.press(key)
                advance(world, 0.5, fps)
                self.assert_inside(world)
            outcomes.append((world.player.x, world.player.ground_y, world.player.jump_height,
                             world.player.vy, world.player.state,
                             [(enemy.x, enemy.ground_y, enemy.hp, enemy.state) for enemy in world.enemies]))
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
