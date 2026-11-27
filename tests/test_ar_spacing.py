from itertools import combinations
import json
from math import hypot
import random
import unittest

import config
from ar_soldier import ARSoldier
from collision import Rect, bodies_overlap
from enemy import Enemy
from enemy_spacing import place_ranged_spawns, ranged_half_width, resolve_ranged_spacing
from researcher import Researcher
from tests.helpers import advance, tap
from walkable import WalkableArea
from tests.helpers import ManualSpawnWorld as World


def crowd(count=9, side=1, *, index=10, distance=500, depth=None):
    world = World(rng=random.Random(42), item_rng=random.Random(5))
    world.select_stage(index)
    world.player.invincible = True
    depth = world.player.ground_y if depth is None else depth
    enemies = [ARSoldier(world.player.x + side * distance, -side, ground_y=depth,
                         run_speed=config.ENEMY_RUN_SPEEDS[i % 4]) for i in range(count)]
    for enemy in enemies:
        enemy.walkable = world.stage.walkable
    place_ranged_spawns(world.player, [], enemies)
    world.enemies = enemies
    return world, enemies


class ARSpacingTests(unittest.TestCase):
    def assert_separated(self, world, enemies=None, *, at_spawn=False):
        enemies = world.enemies if enemies is None else enemies
        active = [enemy for enemy in enemies if enemy.alive]
        for enemy in active:
            self.assertTrue(enemy.walkable.contains(enemy.x, enemy.ground_y, enemy.boundary_padding))
            self.assertFalse(bodies_overlap(enemy, world.player))
        for first, second in combinations(active, 2):
            if first.floor != second.floor or not first.body.overlaps_vertically(second.body):
                continue
            self.assertFalse(bodies_overlap(first, second))
            if at_spawn or all(e.state in ("ATTACK", "RELOAD") for e in (first, second)):
                self.assertTrue(
                    abs(first.x - second.x) >= ranged_half_width(first) + ranged_half_width(second) - 1e-8
                    or abs(first.ground_y - second.ground_y) >= config.AR_SOLDIER_SPACING_DEPTH - 1e-8)

    def test_identical_positions_are_separated_on_the_first_step_in_both_bosses_and_facings(self):
        for index in (10, 11):
            for side in (-1, 1):
                for count in (2, 5, 9):
                    with self.subTest(index=index, side=side, count=count):
                        world, enemies = crowd(count, side, index=index)
                        self.assert_separated(world, at_spawn=True)
                        world.step(config.FIXED_DT)
                        self.assert_separated(world)
                        self.assertTrue(all(enemy.ammo == 20 for enemy in enemies))

    def test_numeric_spawns_and_additional_waves_stay_separate_during_approach_fire_and_reload(self):
        for index in (10, 11):
            world, _ = crowd(0, index=index)
            seen_fire, seen_reload = set(), set()
            for wave in range(2):
                established = {e: (e.x, e.ground_y) for e in world.enemies}
                tap(world.controls, "spawn_9")
                world.step(config.FIXED_DT)
                for e, (x, y) in established.items():
                    self.assertLessEqual(hypot(e.x - x, e.ground_y - y), e.run_speed * config.FIXED_DT + 1e-8)
                self.assertEqual(len(world.enemies), (wave + 1) * 9)
                for _ in range(6 * 120):
                    before = [(e.x, e.ground_y) for e in world.enemies]
                    world.step(config.FIXED_DT)
                    self.assert_separated(world)
                    for e, (x, y) in zip(world.enemies, before):
                        speed = e.run_speed if e.running else config.ENEMY_SPEED
                        self.assertLessEqual(hypot(e.x - x, e.ground_y - y), speed * config.FIXED_DT + 1e-8)
                    seen_fire.update(enemy for enemy in world.enemies if enemy.ammo < 20)
                    seen_reload.update(enemy for enemy in world.enemies if enemy.state == "RELOAD")
            self.assertTrue(seen_fire)
            self.assertTrue(seen_reload)

    def test_spawn_sources_remain_the_original_random_map_edges_before_spacing(self):
        sides = set()
        for index in (10, 11):
            for seed in range(8):
                world, _ = crowd(0, index=index)
                world.spawner.rng = random.Random(seed)
                for enemy in world.spawner.spawn(9, 0):
                    side = enemy.spawn_source[1]
                    sides.add(side)
                    self.assertEqual(enemy.spawn_source[0], "edge")
                    self.assertEqual(enemy.x, enemy.boundary_padding if side < 0
                                     else config.WORLD_WIDTH - enemy.boundary_padding)
                    self.assertEqual(enemy.facing, -side)
        self.assertEqual(sides, {-1, 1})

    def test_stationary_firing_sprites_remain_separate_in_nine_and_eighteen_enemy_encounters(self):
        with (config.ROOT / "assets/frames.json").open(encoding="utf-8") as file:
            rows = json.load(file)[config.AR_SOLDIER_IMAGE]
        for index in (10, 11):
            for count in (9, 18):
                world, _ = crowd(0, index=index)
                world.enemies = world.spawner.spawn(count, 0)
                place_ranged_spawns(world.player, [], world.enemies)
                advance(world, 6)
                rectangles = []
                for enemy in world.enemies:
                    if enemy.state not in ("ATTACK", "RELOAD"):
                        continue
                    tile = rows[enemy.animation.row - 1][enemy.animation.frame]
                    width, height = (size * config.SPRITE_SCALE for size in tile["clip"][2:])
                    center = enemy.x + enemy.facing * tile["offset_x"] * config.SPRITE_SCALE
                    rectangles.append(Rect(center - width / 2, enemy.y,
                                           center + width / 2, enemy.y + height))
                self.assertGreaterEqual(len(rectangles), 2)
                for first, second in combinations(rectangles, 2):
                    self.assertFalse(first.overlaps(second), (index, count, first, second))

    def test_stationary_warning_burst_and_reload_are_not_moved_or_reset_by_an_approaching_peer(self):
        for side in (-1, 1):
            for phase in ("warning", "burst", "reload"):
                with self.subTest(side=side, phase=phase):
                    world, enemies = crowd(1, side, distance=550)
                    reference, controls = crowd(1, side, distance=550)
                    shooter, control = enemies[0], controls[0]
                    for scene, enemy in ((world, shooter), (reference, control)):
                        scene.step(config.FIXED_DT)
                        if phase == "reload":
                            enemy.ammo = 0
                            enemy.start_reload()
                        advance(scene, 1.2 if phase == "burst" else 0.2)
                    incoming = ARSoldier(shooter.x + side * (2 * ranged_half_width(shooter) + 1),
                                         -side, ground_y=shooter.ground_y, run_speed=540)
                    incoming.walkable = world.stage.walkable
                    world.enemies.append(incoming)
                    for _ in range(30):
                        world.step(config.FIXED_DT)
                        reference.step(config.FIXED_DT)
                        self.assertEqual(
                            (shooter.x, shooter.ground_y, shooter.state, shooter.ammo, shooter.aim_line,
                             shooter.aim_remaining, shooter.fire_remaining, shooter.animation.elapsed),
                            (control.x, control.ground_y, control.state, control.ammo, control.aim_line,
                             control.aim_remaining, control.fire_remaining, control.animation.elapsed))
                        self.assert_separated(world)

    def test_reinforcement_joins_a_live_burst_from_inside_and_outside_range(self):
        for side in (-1, 1):
            for front_gap, rear_gap in ((300, 550), (600, 1050)):
                with self.subTest(side=side, rear_gap=rear_gap):
                    world, (front,) = crowd(1, side, distance=front_gap)
                    advance(world, 0.65)
                    anchor = front.x, front.ground_y
                    self.assertLess(front.ammo, front.magazine_size)
                    rear = ARSoldier(world.player.x + side * rear_gap, -side, ground_y=front.ground_y)
                    world.enemies.append(rear)
                    start = rear.x, rear.ground_y
                    for _ in range(4 * 120):
                        world.step(config.FIXED_DT)
                        self.assert_separated(world)
                        if rear.ammo < rear.magazine_size:
                            break
                    self.assertLess(rear.ammo, rear.magazine_size)
                    self.assertNotEqual((rear.x, rear.ground_y), start)
                    self.assertEqual((front.x, front.ground_y), anchor)
                    self.assertIn(front.state, ("ATTACK", "RELOAD"))
                    self.assertTrue(any(bullet.ground_y == rear.ground_y for bullet in world.projectiles))

    def test_a_solo_edge_spawn_pursues_immediately_and_reacquires_a_distant_player(self):
        for index in (10, 11):
            world, _ = crowd(0, index=index)
            tap(world.controls, "spawn_1")
            world.step(config.FIXED_DT)
            enemy, = world.enemies
            self.assertGreater(abs(enemy.x - world.player.x), enemy.shoot_range)
            self.assertLess(abs(enemy.x - world.player.x), abs(enemy.previous_x - world.player.x))
            advance(world, 3)
            self.assertLess(enemy.ammo, enemy.magazine_size)
            side = 1 if enemy.x < world.player.x else -1
            world.player.x = enemy.x + side * 1000
            world.step(config.FIXED_DT)
            self.assertEqual(enemy.state, "RUN")
            self.assertGreater((enemy.x - enemy.previous_x) * side, 0)

    def test_riflemen_finish_their_warning_when_a_player_walks_away_at_the_range_boundary(self):
        for index, side in ((10, -1), (11, 1)):
            for count in (1, 2):
                with self.subTest(index=index, side=side, count=count):
                    world, enemies = crowd(count, side, index=index, distance=600)
                    for i, enemy in enumerate(enemies):
                        enemy.x = world.player.x + side * (600 + 200 * i)
                        enemy.run_speed = 480
                    world.controls.press("right" if side < 0 else "left")
                    world.player.vx = -side * config.WALK_SPEED
                    warnings = {}
                    for _ in range(3 * 120):
                        world.step(config.FIXED_DT)
                        for enemy in enemies:
                            if enemy.aiming:
                                anchor = (enemy.x, enemy.ground_y, enemy.aim_line, enemy.rounds_fired)
                                self.assertEqual(warnings.setdefault(enemy, anchor), anchor)
                            elif enemy in warnings:
                                self.assertGreater(enemy.rounds_fired, warnings.pop(enemy)[-1])
                    self.assertTrue(any(enemy.rounds_fired for enemy in enemies))

    def test_landing_at_a_wall_cancels_a_displaced_warning_before_firing(self):
        world, (enemy,) = crowd(1)
        player = world.player
        player.x = player.boundary_padding
        enemy.x = enemy.boundary_padding + 2
        player.jump_height, player.vy, player.jump_count = config.ENEMY_HEIGHT + 2, -150, 1
        world.step(config.FIXED_DT)
        self.assertTrue(enemy.aiming)
        enemy.aim_remaining = config.FIXED_DT
        x = enemy.x
        world.step(config.FIXED_DT)
        self.assertGreater(enemy.x, x)
        self.assertIsNone(enemy.aim_line)
        self.assertEqual(enemy.ammo, enemy.magazine_size)
        self.assertFalse(world.projectiles)
        world.step(config.FIXED_DT)
        self.assertEqual(enemy.aim_remaining, enemy.aim_duration)

    def test_every_summoned_rifleman_fires_when_more_arrive_than_fit_in_range(self):
        for index in (10, 11):
            world, _ = crowd(0, index=index)
            tap(world.controls, "spawn_9")
            world.step(config.FIXED_DT)
            fired = set()
            for _ in range(15 * 120):
                world.step(config.FIXED_DT)
                fired.update(enemy for enemy in world.enemies if enemy.ammo < enemy.magazine_size)
                if len(fired) == 9:
                    break
            self.assertEqual(len(fired), 9)

    def test_already_overlapping_riflemen_walk_or_run_apart_and_both_fire(self):
        world, enemies = crowd(2, distance=750)
        front, rear = enemies
        rear.x, rear.ground_y = front.x, front.ground_y
        self.assertTrue(bodies_overlap(front, rear))
        for _ in range(4 * 120):
            before = [(e.x, e.ground_y) for e in enemies]
            world.step(config.FIXED_DT)
            for e, (x, y) in zip(enemies, before):
                step = hypot(e.x - x, e.ground_y - y)
                if step > 1e-8:
                    self.assertIn(e.state, ("WALK", "RUN"))
                    speed = e.run_speed if e.state == "RUN" else config.ENEMY_SPEED
                    self.assertLessEqual(step, speed * config.FIXED_DT + 1e-8)
            if all(e.ammo < e.magazine_size for e in enemies):
                break
        self.assertTrue(all(e.ammo < e.magazine_size for e in enemies))
        self.assert_separated(world)

    def test_map_corners_and_player_movement_never_pack_riflemen_outside_the_floor(self):
        for index in (10, 11):
            for right in (False, True):
                for top in (False, True):
                    with self.subTest(index=index, right=right, top=top):
                        world, enemies = crowd(9, index=index)
                        left, bottom, high, upper = world.stage.walkable.bounds
                        world.player.x = high - 68 if right else left + 68
                        world.player.ground_y = upper if top else bottom
                        for enemy in enemies:
                            enemy.x = world.player.x + (-150 if right else 150)
                            enemy.ground_y = world.player.ground_y
                        place_ranged_spawns(world.player, [], enemies)
                        for key in (("right" if right else "left"), ("up" if top else "down")):
                            world.controls.press(key)
                        for _ in range(120):
                            world.step(config.FIXED_DT)
                            self.assert_separated(world)

    def test_list_order_changes_do_not_reshuffle_already_free_footprints(self):
        world, enemies = crowd()
        world.step(config.FIXED_DT)
        before = {enemy: (enemy.x, enemy.ground_y) for enemy in enemies}
        world.enemies.reverse()
        resolve_ranged_spacing(world.player, world.enemies)
        self.assertEqual({enemy: (enemy.x, enemy.ground_y) for enemy in enemies}, before)
        self.assert_separated(world)

    def test_packed_full_height_rows_keep_active_shooters_planted_while_reserves_reposition(self):
        world, enemies = crowd(18)
        advance(world, 6)
        self.assert_separated(world)
        for _ in range(120):
            before = {e: (e.x, e.ground_y) for e in enemies if e.state == "ATTACK" and e.ammo}
            self.assertTrue(before)
            world.step(config.FIXED_DT)
            self.assert_separated(world)
            for enemy, position in before.items():
                self.assertEqual((enemy.x, enemy.ground_y), position)

    def test_dead_other_floor_and_other_enemy_types_are_not_pushed(self):
        world, enemies = crowd(1, distance=300)
        anchor = enemies[0]
        excluded = []
        for kind in ("dead", "floor", "thug", "researcher"):
            cls = Enemy if kind == "thug" else Researcher if kind == "researcher" else ARSoldier
            enemy = cls(anchor.x, ground_y=anchor.ground_y)
            enemy.walkable = world.stage.walkable
            if kind == "dead":
                enemy.take_damage(enemy.hp)
            elif kind == "floor":
                enemy.floor = 1
            excluded.append(enemy)
        world.enemies.extend(excluded)
        before = {enemy: (enemy.x, enemy.ground_y, enemy.state) for enemy in world.enemies}
        resolve_ranged_spacing(world.player, world.enemies)
        self.assertEqual({enemy: (enemy.x, enemy.ground_y, enemy.state) for enemy in world.enemies}, before)

    def test_reload_hit_and_death_keep_their_existing_clocks_and_do_not_reserve_corpses(self):
        world, enemies = crowd(3, distance=300)
        world.step(config.FIXED_DT)
        reload, hit, dead = enemies
        reload.ammo = 0
        reload.start_reload()
        hit.take_damage(10)
        dead.take_damage(300)
        before = reload.animation.elapsed, hit.animation.elapsed, dead.x, dead.ground_y
        world.step(config.FIXED_DT)
        self.assertEqual((reload.state, reload.ammo), ("RELOAD", 0))
        self.assertAlmostEqual(reload.animation.elapsed, before[0] + config.FIXED_DT)
        self.assertAlmostEqual(hit.animation.elapsed, before[1] + config.FIXED_DT)
        self.assertEqual((dead.x, dead.ground_y), before[2:])
        self.assert_separated(world, [reload, hit])

    def test_single_rifleman_retains_original_walking_and_running_speeds(self):
        for gap, depth in ((200, 80), (800, 0), (800, 80)):
            for speed in config.ENEMY_RUN_SPEEDS:
                world, enemies = crowd(1, distance=gap, depth=100 - depth)
                enemy = enemies[0]
                enemy.run_speed = speed
                before = enemy.x, enemy.ground_y
                world.step(config.FIXED_DT)
                expected = speed if gap >= 360 else 120
                self.assertAlmostEqual(hypot(enemy.x - before[0], enemy.ground_y - before[1]),
                                       expected * config.FIXED_DT)

    def test_pursuit_changes_gait_and_actual_step_length_as_the_player_changes_distance(self):
        world, (enemy,) = crowd(1, distance=0)
        for gap, gait in ((800, "RUN"), (270, "RUN"), (140, "WALK"), (270, "WALK"), (800, "RUN")):
            world.player.x = enemy.x - gap
            world.player.ground_y = enemy.ground_y + (70 if enemy.ground_y < 140 else -70)
            x, y = enemy.x, enemy.ground_y
            world.step(config.FIXED_DT)
            self.assertEqual(enemy.state, gait)
            speed = enemy.run_speed if gait == "RUN" else config.ENEMY_SPEED
            self.assertAlmostEqual(hypot(enemy.x - x, enemy.ground_y - y), speed * config.FIXED_DT)

    def test_m_selected_ar_crowds_on_another_map_use_its_floor_and_do_not_overlap(self):
        world, _ = crowd(0, index=6)
        for _ in range(11):
            world.stage.cycle_spawn_enemy_type()
        self.assertIs(world.spawner.enemy_type, ARSoldier)
        tap(world.controls, "spawn_9")
        world.step(config.FIXED_DT)
        for _ in range(4 * 120):
            world.step(config.FIXED_DT)
            self.assert_separated(world)

    def test_inactive_maps_loading_and_f5_preserve_existing_lifecycle(self):
        world, enemies = crowd()
        advance(world, 0.5)
        snapshot = [(enemy.x, enemy.ground_y, enemy.ammo, enemy.animation.elapsed) for enemy in enemies]
        world.select_stage(9)
        advance(world, 1)
        world.select_stage(10)
        self.assertEqual([(enemy.x, enemy.ground_y, enemy.ammo, enemy.animation.elapsed) for enemy in enemies],
                         snapshot)
        world.pending_stage_index, world.stage_loading_remaining = 9, 2
        world.update(0.5)
        self.assertEqual([(enemy.x, enemy.ground_y, enemy.ammo, enemy.animation.elapsed) for enemy in enemies],
                         snapshot)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertFalse(any(stage.enemies for stage in world.stages))

    def test_spacing_handles_a_convex_floor_without_putting_feet_outside_it(self):
        world, enemies = crowd(5, distance=200)
        area = WalkableArea(((800, 0), (1750, 0), (1750, 250), (950, 250)))
        world.player.walkable = area
        for enemy in enemies:
            enemy.walkable = area
            enemy.x, enemy.ground_y = 1400, 100
        place_ranged_spawns(world.player, [], enemies)
        self.assert_separated(world)

    def test_moving_crowds_are_identical_at_all_render_frame_rates(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world, _ = crowd()
            advance(world, 1, fps)
            world.controls.press("up")
            advance(world, 0.5, fps)
            world.controls.release("up")
            advance(world, 2, fps)
            self.assert_separated(world)
            outcomes.append([(enemy.x, enemy.ground_y, enemy.state, enemy.ammo,
                              enemy.aim_remaining, enemy.fire_remaining, enemy.animation.elapsed)
                             for enemy in world.enemies])
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
