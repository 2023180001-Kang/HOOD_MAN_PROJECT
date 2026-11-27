import hashlib
import json
from math import hypot
import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pico2d
from PIL import Image, ImageChops

import config
from ar_soldier import ARSoldier
from assets import Assets
from combat import STRONG_MOVES
from game import Game
from player import Player
from projectiles import ResearcherBullet, RifleBullet
from researcher import Researcher
from tests.helpers import advance, enter_kick_wait, tap
from tests.test_strong_attacks import strike
from ui import UI
from tests.helpers import ManualSpawnWorld as World


def encounter(index=10, side=1, gap=300, speed=1.0, invincible=True):
    world = World(rng=random.Random(23), item_rng=random.Random(5))
    world.select_stage(index)
    world.player.invincible = invincible
    world.player.facing = side
    enemy = ARSoldier(world.player.x + side * gap, -side,
                      ground_y=world.player.ground_y, attack_speed=speed)
    enemy.walkable = world.stage.walkable
    world.enemies = [enemy]
    return world, enemy


class ARSoldierTests(unittest.TestCase):
    def test_both_boss_maps_spawn_exact_digit_counts_with_300_hp_50_damage_and_twenty_rounds(self):
        for index in (10, 11):
            for count in config.SPAWN_COUNTS:
                with self.subTest(index=index, count=count):
                    world = World(rng=random.Random(42))
                    world.select_stage(index)
                    advance(world, 0.1)
                    self.assertEqual(world.enemies, [])
                    tap(world.controls, f"spawn_{count}")
                    world.step(config.FIXED_DT)
                    self.assertEqual((len(world.enemies), world.spawner.spawned_count), (count, count))
                    self.assertTrue(all(type(enemy) is ARSoldier and enemy.hp == enemy.max_hp == 300
                                        and enemy.attack_damage == 50 and enemy.ammo == 20
                                        and world.stage.walkable.contains(enemy.x, enemy.ground_y, 88)
                                        for enemy in world.enemies))
                    world.controls.press(f"spawn_{count}")
                    world.step(config.FIXED_DT)
                    self.assertEqual(len(world.enemies), count)
                    self.assertEqual(len({enemy.attack_speed for enemy in world.enemies}), count)

    def test_m_selects_both_boss_entries_on_another_floor_without_replacing_existing_enemies(self):
        world = World(rng=random.Random(41))
        world.select_stage(8)
        original = world.spawner.spawn(1, 0)[0]
        original.take_damage(40)
        world.enemies = [original]
        for _ in range(11):
            world.stage.cycle_spawn_enemy_type()
        self.assertEqual(world.stage.spawn_enemy_stage_index, 10)
        for source in (10, 11):
            self.assertIs(world.spawner.enemy_type, ARSoldier)
            spawned = world.spawner.spawn(1, 0)[0]
            self.assertEqual((spawned.hp, spawned.ammo, spawned.attack_damage), (300, 20, 50))
            self.assertIs(spawned.walkable, world.stage.walkable)
            self.assertEqual((world.enemies, original.hp), ([original], 360))
            world.stage.cycle_spawn_enemy_type()
        self.assertEqual(world.stage.spawn_enemy_stage_index, 0)

    def test_range_depth_and_floor_gate_shooting_in_both_directions(self):
        for side in (-1, 1):
            for gap, depth, floor, allowed in (
                (600, 0, 0, True), (600.01, 0, 0, False),
                (300, 32, 0, True), (300, 32.01, 0, False),
                (80, 0, 0, True), (300, 0, 1, False),
            ):
                player = Player()
                enemy = ARSoldier(player.x + side * gap, -side,
                                  ground_y=player.ground_y + depth)
                enemy.floor = floor
                enemy.update(config.FIXED_DT, player)
                self.assertEqual(enemy.aiming, allowed)
                self.assertIsNone(enemy.attack_box)
                self.assertFalse(enemy.try_hit(player))
                self.assertEqual(player.hp, 500)

    def test_half_second_warning_precedes_the_first_round_at_every_attack_speed(self):
        for index in (10, 11):
            for side in (-1, 1):
                for speed in (0.8, 1, 1.4):
                    with self.subTest(index=index, side=side, speed=speed):
                        world, enemy = encounter(index, side, speed=speed)
                        world.step(config.FIXED_DT)
                        warning = enemy.aim_line
                        self.assertEqual(enemy.aim_remaining, 0.5)
                        for _ in range(round(enemy.aim_duration / config.FIXED_DT) - 1):
                            world.step(config.FIXED_DT)
                            self.assertEqual((enemy.ammo, enemy.animation.frame), (20, 1))
                            self.assertTrue(enemy.aiming)
                            self.assertFalse(world.projectiles)
                        world.step(config.FIXED_DT)
                        self.assertEqual((enemy.ammo, enemy.animation.frame), (19, 2))
                        self.assertIsNone(enemy.aim_line)
                        self.assertEqual(len(world.projectiles), 1)
                        bullet = world.projectiles[0]
                        self.assertIsInstance(bullet, RifleBullet)
                        self.assertEqual((bullet.damage, bullet.y, bullet.facing),
                                         (50, warning[1], enemy.facing))
                        self.assertEqual(bullet.x - bullet.facing * bullet.half_width, warning[0])
                        self.assertIsNone(enemy.take_projectile())
                        world.step(config.FIXED_DT)
                        self.assertEqual(enemy.ammo, 19)

    def test_animation_skips_cannot_bypass_the_warning_or_duplicate_a_shot(self):
        world, enemy = encounter()
        enemy.start_attack()
        enemy.animation.elapsed = 5 / enemy.attack_fps
        self.assertIsNone(enemy.take_projectile())
        self.assertEqual(enemy.ammo, 20)
        enemy.update(enemy.aim_duration - config.FIXED_DT, world.player)
        self.assertIsNone(enemy.take_projectile())
        enemy.update(config.FIXED_DT, world.player)
        self.assertIsInstance(enemy.take_projectile(), RifleBullet)
        for _ in range(10):
            self.assertIsNone(enemy.take_projectile())
        self.assertEqual(enemy.ammo, 19)

    def test_leaving_range_lane_floor_or_crossing_behind_restarts_a_full_warning(self):
        for reason in ("range", "depth", "floor", "behind"):
            with self.subTest(reason=reason):
                world, enemy = encounter(side=-1)
                enemy.start_attack()
                enemy.update(0.4, world.player)
                if reason == "range":
                    world.player.x = enemy.x + 601
                elif reason == "depth":
                    world.player.ground_y = enemy.ground_y + 32.01
                elif reason == "floor":
                    world.player.floor = 1
                else:
                    world.player.x = enemy.x - 100
                enemy.update(config.FIXED_DT, world.player)
                self.assertIsNone(enemy.take_projectile())
                self.assertEqual(enemy.ammo, 20)
                if reason == "depth":
                    self.assertTrue(enemy.aiming)
                    self.assertEqual(enemy.aim_cancel_remaining, 0.5)
                    enemy.update(0.5, world.player)
                if reason == "behind":
                    self.assertEqual((enemy.facing, enemy.aim_remaining), (-1, enemy.aim_duration))
                else:
                    self.assertFalse(enemy.aiming)
                world.player.x = enemy.x + 300
                world.player.ground_y = enemy.ground_y
                world.player.floor = 0
                enemy.update(config.FIXED_DT, world.player)
                self.assertEqual((enemy.facing, enemy.aim_remaining), (1, enemy.aim_duration))
                self.assertIsNone(enemy.take_projectile())

    def test_vertical_dodge_delays_cancellation_without_firing_even_on_the_last_warning_tick(self):
        for index in (10, 11):
            for side in (-1, 1):
                for depth_change in (-16, -0.25, 0.25, 16):
                    with self.subTest(index=index, side=side, depth_change=depth_change):
                        world, enemy = encounter(index, side)
                        world.step(config.FIXED_DT)
                        for _ in range(round(enemy.aim_duration / config.FIXED_DT) - 1):
                            world.step(config.FIXED_DT)
                        self.assertTrue(enemy.aiming)
                        before = enemy.x, enemy.ground_y, enemy.aim_line, enemy.aim_remaining
                        world.player.ground_y += depth_change
                        world.step(config.FIXED_DT)
                        self.assertEqual(enemy.aim_cancel_remaining, 0.5)
                        for _ in range(59):
                            self.assertTrue(enemy.aiming)
                            self.assertEqual((enemy.x, enemy.ground_y, enemy.aim_line, enemy.aim_remaining),
                                             before)
                            self.assertIsNone(enemy.take_projectile())
                            self.assertEqual(enemy.ammo, 20)
                            self.assertFalse(world.projectiles)
                            world.step(config.FIXED_DT)
                        self.assertTrue(enemy.aiming)
                        world.step(config.FIXED_DT)
                        self.assertFalse(enemy.aiming)
                        self.assertIsNone(enemy.aim_line)
                        self.assertEqual((enemy.aim_cancel_remaining, enemy.aim_remaining, enemy.ammo),
                                         (0, 0, 20))
                        self.assertEqual((enemy.x, enemy.ground_y), before[:2])
                        world.step(config.FIXED_DT)
                        self.assertEqual(enemy.aim_remaining, 0.5)
                        for _ in range(round(enemy.aim_duration / config.FIXED_DT) - 1):
                            world.step(config.FIXED_DT)
                            self.assertEqual(enemy.ammo, 20)
                        world.step(config.FIXED_DT)
                        self.assertEqual(enemy.ammo, 19)

    def test_continuing_vertical_evasion_does_not_reset_delay_and_pursuit_resumes_at_original_speed(self):
        for index in (10, 11):
            for side in (-1, 1):
                for key, direction in (("up", 1), ("down", -1)):
                    with self.subTest(index=index, side=side, key=key):
                        world, enemy = encounter(index, side, gap=200)
                        world.step(config.FIXED_DT)
                        advance(world, 0.4)
                        before = enemy.x, enemy.ground_y, enemy.aim_line
                        world.controls.press(key)
                        world.step(config.FIXED_DT)
                        for _ in range(59):
                            self.assertTrue(enemy.aiming)
                            self.assertEqual((enemy.x, enemy.ground_y, enemy.aim_line), before)
                            self.assertEqual(enemy.ammo, 20)
                            self.assertFalse(world.projectiles)
                            world.step(config.FIXED_DT)
                        self.assertTrue(enemy.aiming)
                        world.step(config.FIXED_DT)
                        self.assertFalse(enemy.aiming)
                        self.assertEqual((enemy.x, enemy.ground_y), before[:2])
                        world.step(config.FIXED_DT)
                        self.assertEqual(enemy.ground_vy, direction * 120)
                        self.assertAlmostEqual((enemy.ground_y - before[1]) * direction,
                                               120 * config.FIXED_DT)
                        world.controls.release(key)
                        for _ in range(240):
                            world.step(config.FIXED_DT)
                            if enemy.aiming:
                                break
                        self.assertEqual((enemy.aim_remaining, enemy.ammo), (enemy.aim_duration, 20))

    def test_all_ar_walking_running_and_diagonal_pursuit_speeds_remain_unchanged(self):
        for index in (10, 11):
            for side in (-1, 1):
                for run_speed in config.ENEMY_RUN_SPEEDS:
                    for gap, depth, running in ((200, 80, False), (800, 0, True), (800, 80, True)):
                        with self.subTest(index=index, side=side, run_speed=run_speed, gap=gap, depth=depth):
                            world, enemy = encounter(index, side, gap=gap)
                            enemy.run_speed = run_speed
                            enemy.ground_y -= depth
                            before = enemy.x, enemy.ground_y
                            world.step(config.FIXED_DT)
                            speed = run_speed if running else 120
                            self.assertEqual(enemy.running, running)
                            self.assertEqual(enemy.run_speed, run_speed)
                            self.assertEqual(enemy.aim_cancel_remaining, 0)
                            self.assertAlmostEqual(hypot(enemy.vx, enemy.ground_vy), speed)
                            self.assertAlmostEqual(hypot(enemy.x - before[0], enemy.ground_y - before[1]),
                                                   speed * config.FIXED_DT)

    def test_horizontal_movement_and_jump_height_do_not_cancel_the_warning(self):
        for action in ("horizontal", "jump"):
            world, enemy = encounter()
            world.step(config.FIXED_DT)
            advance(world, 0.2)
            if action == "horizontal":
                world.player.x += 10
            else:
                world.player.jump_height = 100
            enemy.update(0.1, world.player)
            self.assertTrue(enemy.aiming)
            self.assertEqual(enemy.aim_cancel_remaining, 0)
            self.assertAlmostEqual(enemy.aim_remaining, 0.2)
            enemy.update(0.2, world.player)
            self.assertIsInstance(enemy.take_projectile(), RifleBullet)
            self.assertEqual(enemy.ammo, 19)

    def test_small_vertical_movement_during_active_fire_keeps_the_existing_burst_lane(self):
        world, enemy = encounter()
        enemy.start_attack()
        enemy.update(enemy.aim_duration, world.player)
        first = enemy.take_projectile()
        world.player.ground_y += 1
        enemy.update(0.1, world.player)
        second = enemy.take_projectile()
        self.assertIsInstance(second, RifleBullet)
        self.assertEqual((enemy.ammo, second.ground_y, enemy.aim_remaining), (18, first.ground_y, 0))
        self.assertEqual(enemy.aim_cancel_remaining, 0)

    def test_researcher_pursuit_remains_full_speed(self):
        player = Player()
        for run_speed in config.ENEMY_RUN_SPEEDS:
            for gap, depth, speed in ((200, 80, 120), (800, 0, run_speed), (800, 80, run_speed)):
                enemy = Researcher(player.x - gap, 1, ground_y=player.ground_y - depth,
                                   run_speed=run_speed)
                before = enemy.x, enemy.ground_y
                enemy.update(config.FIXED_DT, player)
                self.assertAlmostEqual(hypot(enemy.vx, enemy.ground_vy), speed)
                self.assertAlmostEqual(hypot(enemy.x - before[0], enemy.ground_y - before[1]),
                                       speed * config.FIXED_DT)

    def test_cancel_delay_uses_the_shared_slow_motion_clock(self):
        world, enemy = encounter()
        world.step(config.FIXED_DT)
        world.player.ground_y += 1
        world.step(config.FIXED_DT)
        enter_kick_wait(world)
        for _ in range(299):
            world.step(config.FIXED_DT)
            self.assertTrue(enemy.aiming)
            self.assertGreater(enemy.aim_cancel_remaining, 0)
            self.assertEqual(enemy.ammo, 20)
        world.step(config.FIXED_DT)
        self.assertEqual((enemy.aim_cancel_remaining, enemy.aim_remaining, enemy.ammo), (0, 0, 20))
        self.assertFalse(enemy.aiming)

    def test_cancel_delay_pauses_off_scene_during_loading_and_f5_clears_it(self):
        world, enemy = encounter()
        world.step(config.FIXED_DT)
        world.player.ground_y += 1
        world.step(config.FIXED_DT)
        advance(world, 0.2)
        snapshot = enemy.aim_cancel_remaining, enemy.aim_remaining, enemy.animation.elapsed
        world.select_stage(9)
        advance(world, 1)
        world.select_stage(10)
        self.assertEqual((enemy.aim_cancel_remaining, enemy.aim_remaining, enemy.animation.elapsed), snapshot)
        world.pending_stage_index, world.stage_loading_remaining = 9, 2
        world.update(0.5)
        self.assertEqual((enemy.aim_cancel_remaining, enemy.aim_remaining, enemy.animation.elapsed), snapshot)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertFalse(any(stage.enemies or stage.projectiles for stage in world.stages))
        fresh = world.stages[10].spawner.spawn(1, 0)[0]
        self.assertEqual((fresh.aim_cancel_remaining, fresh.ammo), (0, 20))
        self.assertEqual(fresh.run_speed, config.ENEMY_RUN_SPEEDS[0])

    def test_vertical_evasion_and_delayed_cancellation_are_identical_at_all_render_rates(self):
        snapshots = []
        for fps in (30, 60, 120, 144):
            world, enemy = encounter(gap=200)
            advance(world, 0.5, fps)
            world.controls.press("up")
            advance(world, 0.5, fps)
            world.controls.release("up")
            advance(world, 2, fps)
            snapshots.append((enemy.x, enemy.ground_y, enemy.state, enemy.aim_remaining,
                              enemy.aim_cancel_remaining, enemy.ammo, enemy.fire_remaining, enemy.animation.elapsed,
                              world.player.ground_y))
        self.assertTrue(all(snapshot == snapshots[0] for snapshot in snapshots))

    def test_exactly_twenty_rounds_then_row_six_reload_and_a_new_warning(self):
        for speed in (0.8, 1, 1.4):
            world, enemy = encounter(side=-1, speed=speed)
            enemy.start_attack()
            enemy.update(enemy.aim_duration - config.FIXED_DT, world.player)
            self.assertIsNone(enemy.take_projectile())
            enemy.update(config.FIXED_DT, world.player)
            for remaining in range(19, -1, -1):
                self.assertIsInstance(enemy.take_projectile(), RifleBullet)
                self.assertEqual(enemy.ammo, remaining)
                self.assertEqual(enemy.animation.row, 4)
                self.assertIn(enemy.animation.frame, config.AR_SOLDIER_FIRE_FRAMES)
                self.assertIsNone(enemy.aim_line)
                self.assertIsNone(enemy.take_projectile())
                for _ in range(11):
                    enemy.update(config.FIXED_DT, world.player)
                    self.assertIsNone(enemy.take_projectile())
                enemy.update(config.FIXED_DT, world.player)
                if remaining:
                    self.assertEqual(enemy.state, "ATTACK")
            self.assertEqual((enemy.ammo, enemy.state, enemy.animation.row), (0, "RELOAD", 6))
            self.assertIsNone(enemy.aim_line)
            self.assertIsNone(enemy.take_projectile())
            enemy.update(1 - config.FIXED_DT, world.player)
            self.assertEqual((enemy.ammo, enemy.animation.frame), (0, 7))
            enemy.update(config.FIXED_DT, world.player)
            self.assertEqual((enemy.ammo, enemy.state), (20, "IDLE"))
            enemy.cooldown = 0
            enemy.update(config.FIXED_DT, world.player)
            self.assertEqual((enemy.ammo, enemy.aim_remaining, enemy.animation.frame), (20, enemy.aim_duration, 1))

    def test_natural_automatic_fire_warns_once_and_spaces_twenty_rounds_by_a_tenth_of_a_second(self):
        for index in (10, 11):
            for side in (-1, 1):
                for speed in (0.8, 1, 1.4):
                    with self.subTest(index=index, side=side, speed=speed):
                        world, enemy = encounter(index, side, speed=speed)
                        shots, reloads, warnings = [], 0, []
                        for _ in range(720):
                            previous_ammo, previous_state = enemy.ammo, enemy.state
                            was_aiming = enemy.aiming
                            world.step(config.FIXED_DT)
                            if enemy.aiming and not was_aiming:
                                warnings.append(world.elapsed)
                            if enemy.ammo == previous_ammo - 1:
                                if len(shots) % 20 == 0:
                                    self.assertAlmostEqual(world.elapsed - warnings[-1], enemy.aim_duration)
                                else:
                                    self.assertAlmostEqual(world.elapsed - shots[-1], 0.1)
                                shots.append(world.elapsed)
                                self.assertFalse(enemy.aiming)
                                self.assertEqual(enemy.animation.row, 4)
                                self.assertEqual(enemy.animation.frame, 2 + (len(shots) - 1) % 4)
                            if enemy.state == "RELOAD" and previous_state != "RELOAD":
                                reloads += 1
                                self.assertEqual((len(shots), enemy.ammo, enemy.animation.row), (20, 0, 6))
                                self.assertAlmostEqual(world.elapsed - shots[-1], 0.1)
                            if len(shots) == 21:
                                break
                        self.assertEqual((len(shots), reloads, len(warnings), enemy.ammo), (21, 1, 2, 19))
                        self.assertAlmostEqual(shots[19] - shots[0], 1.9)

    def test_range_lane_floor_and_behind_cancel_an_active_burst_not_just_its_warning(self):
        for reason in ("range", "depth", "floor", "behind"):
            with self.subTest(reason=reason):
                world, enemy = encounter(side=-1)
                enemy.start_attack()
                enemy.update(enemy.aim_duration, world.player)
                self.assertIsInstance(enemy.take_projectile(), RifleBullet)
                if reason == "range":
                    world.player.x = enemy.x + 601
                elif reason == "depth":
                    world.player.ground_y = enemy.ground_y + 32.01
                elif reason == "floor":
                    world.player.floor = 1
                else:
                    world.player.x = enemy.x - 100
                enemy.update(0.1, world.player)
                self.assertIsNone(enemy.take_projectile())
                self.assertEqual(enemy.ammo, 19)
                world.player.x = enemy.x + 300
                world.player.ground_y = enemy.ground_y
                world.player.floor = 0
                enemy.update(config.FIXED_DT, world.player)
                self.assertEqual((enemy.facing, enemy.aim_remaining, enemy.burst_shots), (1, enemy.aim_duration, 0))
                enemy.update(enemy.aim_duration - config.FIXED_DT, world.player)
                self.assertIsNone(enemy.take_projectile())
                enemy.update(config.FIXED_DT, world.player)
                self.assertIsInstance(enemy.take_projectile(), RifleBullet)
                self.assertEqual(enemy.ammo, 18)

    def test_repeated_projectile_reads_or_animation_changes_cannot_accelerate_the_fire_clock(self):
        world, enemy = encounter()
        enemy.start_attack()
        enemy.update(enemy.aim_duration, world.player)
        self.assertIsInstance(enemy.take_projectile(), RifleBullet)
        for _ in range(11):
            enemy.animation.elapsed = 100
            for _ in range(10):
                self.assertIsNone(enemy.take_projectile())
            enemy.update(config.FIXED_DT, world.player)
            self.assertEqual(enemy.ammo, 19)
            self.assertIn(enemy.animation.frame, config.AR_SOLDIER_FIRE_FRAMES)
        enemy.update(config.FIXED_DT, world.player)
        self.assertIsInstance(enemy.take_projectile(), RifleBullet)
        self.assertIsNone(enemy.take_projectile())
        self.assertEqual(enemy.ammo, 18)

    def test_mid_burst_hit_resumes_with_remaining_ammo_and_a_full_new_warning(self):
        world, enemy = encounter()
        enemy.start_attack()
        enemy.update(enemy.aim_duration, world.player)
        self.assertIsInstance(enemy.take_projectile(), RifleBullet)
        enemy.update(0.05, world.player)
        enemy.take_damage(10)
        enemy.update(0.7, world.player)
        self.assertIsNone(enemy.take_projectile())
        enemy.cooldown = 0
        enemy.update(config.FIXED_DT, world.player)
        self.assertEqual((enemy.ammo, enemy.aim_remaining, enemy.burst_shots), (19, enemy.aim_duration, 0))
        enemy.update(enemy.aim_duration - config.FIXED_DT, world.player)
        self.assertIsNone(enemy.take_projectile())
        enemy.update(config.FIXED_DT, world.player)
        self.assertIsInstance(enemy.take_projectile(), RifleBullet)
        self.assertEqual(enemy.ammo, 18)

    def test_active_fire_clock_pauses_off_scene_and_during_loading_without_catch_up_shots(self):
        world, enemy = encounter()
        advance(world, enemy.aim_duration)
        world.step(config.FIXED_DT)
        self.assertEqual(enemy.ammo, 19)
        for _ in range(6):
            world.step(config.FIXED_DT)
        snapshot = enemy.ammo, enemy.fire_remaining, enemy.burst_shots, enemy.animation.elapsed
        world.select_stage(9)
        advance(world, 1)
        world.select_stage(10)
        self.assertEqual((enemy.ammo, enemy.fire_remaining, enemy.burst_shots, enemy.animation.elapsed), snapshot)
        world.pending_stage_index, world.stage_loading_remaining = 9, 2
        world.update(0.5)
        self.assertEqual((enemy.ammo, enemy.fire_remaining, enemy.burst_shots, enemy.animation.elapsed), snapshot)
        world.select_stage(10)
        for _ in range(5):
            world.step(config.FIXED_DT)
            self.assertEqual(enemy.ammo, 19)
        world.step(config.FIXED_DT)
        self.assertEqual(enemy.ammo, 18)

    def test_automatic_fire_interval_uses_the_same_slow_motion_clock(self):
        world, enemy = encounter()
        advance(world, enemy.aim_duration)
        world.step(config.FIXED_DT)
        enter_kick_wait(world)
        for _ in range(59):
            world.step(config.FIXED_DT)
            self.assertEqual(enemy.ammo, 19)
        world.step(config.FIXED_DT)
        self.assertEqual(enemy.ammo, 18)
        self.assertAlmostEqual(enemy.fire_remaining, 0.1)

    def test_researcher_keeps_single_shots_and_its_seven_round_magazine(self):
        player = Player()
        enemy = Researcher(player.x - 300, 1, ground_y=player.ground_y)
        self.assertEqual(enemy.aim_duration, 0.5)
        enemy.start_attack()
        enemy.update(0.5, player)
        self.assertIs(type(enemy.take_projectile()), ResearcherBullet)
        enemy.update(0.1, player)
        self.assertIsNone(enemy.take_projectile())
        self.assertEqual((enemy.ammo, enemy.magazine_size), (6, 7))

    def test_reload_interruption_never_refills_early_and_restarts_all_eight_frames(self):
        world, enemy = encounter()
        enemy.ammo = 0
        enemy.update(config.FIXED_DT, world.player)
        enemy.update(0.5, world.player)
        enemy.take_damage(10)
        self.assertEqual((enemy.hp, enemy.ammo, enemy.state, enemy.animation.row), (290, 0, "HIT", 5))
        enemy.update(1, world.player)
        enemy.update(config.FIXED_DT, world.player)
        self.assertEqual((enemy.ammo, enemy.state, enemy.animation.row), (0, "RELOAD", 6))
        enemy.update(1 - config.FIXED_DT, world.player)
        self.assertEqual(enemy.ammo, 20)

    def test_hit_strong_knockback_stop_and_death_cancel_warnings_and_active_bursts(self):
        for phase in ("warning", "cancel_delay", "firing"):
            for cause in ("hit", "strong", "knockback", "stop", "lethal", "car"):
                with self.subTest(cause=cause, phase=phase):
                    world, enemy = encounter()
                    enemy.start_attack()
                    fired = phase == "firing"
                    enemy.update(enemy.aim_duration if fired else 0.2, world.player)
                    if fired:
                        self.assertIsInstance(enemy.take_projectile(), RifleBullet)
                    if phase == "cancel_delay":
                        world.player.ground_y += 1
                        enemy.update(config.FIXED_DT, world.player)
                        self.assertEqual(enemy.aim_cancel_remaining, 0.5)
                    if cause == "hit":
                        enemy.take_damage(10)
                    elif cause == "strong":
                        enemy.take_strong_hit(STRONG_MOVES["combat_q"], 1)
                    elif cause == "knockback":
                        enemy.knockback(world.player.x)
                    elif cause == "stop":
                        enemy.stop()
                    elif cause == "car":
                        enemy.hit_by_car(1)
                    else:
                        enemy.take_damage(300)
                    self.assertEqual((enemy.aim_remaining, enemy.ammo), (0, 19 if fired else 20))
                    self.assertEqual(enemy.aim_cancel_remaining, 0)
                    self.assertIsNone(enemy.aim_line)
                    self.assertIsNone(enemy.take_projectile())

    def test_warning_and_reload_use_game_time_and_pause_off_scene_during_loading(self):
        world, enemy = encounter()
        enemy.start_attack()
        enter_kick_wait(world)
        for _ in range(round(enemy.aim_duration / (config.FIXED_DT * config.AIR_KICK_TIME_SCALE)) - 1):
            world.step(config.FIXED_DT)
            self.assertTrue(enemy.aiming)
            self.assertEqual(enemy.ammo, 20)
        world.step(config.FIXED_DT)
        self.assertEqual(enemy.ammo, 19)
        enemy.ammo = 0
        enemy.start_reload()
        advance(world, 0.5)
        snapshot = enemy.ammo, enemy.animation.elapsed
        self.assertAlmostEqual(enemy.animation.elapsed, 0.1)
        world.select_stage(9)
        advance(world, 1)
        world.select_stage(10)
        self.assertEqual((enemy.ammo, enemy.animation.elapsed), snapshot)
        world.pending_stage_index, world.stage_loading_remaining = 9, 2
        world.update(1)
        self.assertEqual((enemy.ammo, enemy.animation.elapsed), snapshot)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertFalse(any(stage.enemies or stage.projectiles for stage in world.stages))
        fresh = world.stages[10].spawner.spawn(1, 0)[0]
        self.assertEqual((fresh.hp, fresh.ammo, fresh.aim_remaining), (300, 20, 0))

    def test_actual_round_deals_fifty_and_preserves_player_hit_effect_and_shake(self):
        for index in (10, 11):
            for side in (-1, 1):
                world, enemy = encounter(index, side, invincible=False)
                for _ in range(180):
                    world.step(config.FIXED_DT)
                    if world.player.hp < 500:
                        break
                self.assertEqual((world.player.hp, world.player.state), (450, "IDLE"))
                self.assertLess(enemy.ammo, 19)  # Further rounds are already in flight.
                self.assertEqual([effect.image_name for effect in world.effects], [config.CLUB_HIT_IMAGE])
                self.assertGreater(world.camera.shake_remaining, 0)
                advance(world, 0.1)
                self.assertEqual(world.player.hp, 400)

    def test_player_basic_weapon_and_strong_hits_use_own_fifth_row_and_existing_feedback(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for key in ("asdf" if weapon is None else "asf"):
                world, enemy = encounter(gap=80)
                world.player.equip_weapon(weapon)
                enemy.cooldown = 100
                strike(world, enemy, f"combat_{key}")
                move = world.player.active_move
                self.assertEqual((enemy.hp, enemy.animation.row), (300 - move.damage, 5))
                self.assertEqual(enemy.sprite_image, config.AR_SOLDIER_IMAGE)
                self.assertEqual([number.damage for number in world.damage_numbers], [move.damage])
                self.assertEqual(world.effects[-1].image_name, move.hit_image)
        for key in "qwe":
            world, enemy = encounter(gap=80)
            strike(world, enemy, f"combat_{key}")
            self.assertEqual((enemy.hp, enemy.animation.row), (enemy.max_hp - STRONG_MOVES[f"combat_{key}"].damage, 5))
            self.assertEqual(enemy.sprite_image, config.AR_SOLDIER_IMAGE)

    def test_small_red_hp_bar_uses_300_max_hp_and_remains_when_u_hides_help(self):
        world, enemy = encounter()
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            assets = SimpleNamespace(frames=json.load(file), damage_font=None)
        for visible in (True, False):
            ui = UI()
            ui.details_visible = visible
            for hp, width in ((300, 48), (150, 24), (75, 12), (0, 0)):
                enemy.hp = hp
                with patch("pico2d.draw_rectangle") as draw:
                    ui.draw_enemy_health(assets, world, 17, 29)
                bars = [call.args for call in draw.call_args_list if call.args[4:7] == (215, 38, 45)]
                if hp:
                    self.assertEqual(len(bars), 1)
                    self.assertEqual((bars[0][2] - bars[0][0] + 1, bars[0][3] - bars[0][1] + 1),
                                     (width, 5))
                else:
                    draw.assert_not_called()

    def test_lethal_hit_stops_shooting_uses_seventh_row_and_drops_rifle(self):
        world, enemy = encounter(gap=80)
        items = list(world.stage.drop_items)
        enemy.hp = 25
        strike(world, enemy, "combat_f")
        self.assertEqual((enemy.hp, enemy.state, enemy.animation.row), (0, "DYING", 7))
        self.assertEqual([number.damage for number in world.damage_numbers], [25])
        advance(world, 1)
        self.assertEqual((enemy.state, enemy.animation.row, enemy.animation.frame), ("DEAD", 7, 7))
        self.assertFalse(world.projectiles)
        enemy.corpse_elapsed = 3.5
        self.assertAlmostEqual(enemy.opacity, 0.5)
        advance(world, 0.5)
        self.assertNotIn(enemy, world.enemies)
        self.assertEqual(world.stage.drop_items[:-1], items)
        self.assertEqual(world.stage.drop_items[-1].kind, "ar_rifle")

    def test_red_dots_follow_world_camera_and_real_bullet_lane_in_both_facings(self):
        for facing in (-1, 1):
            enemy = ARSoldier(640, facing, ground_y=120)
            enemy.start_attack()
            for camera_x, camera_y in ((0, 0), (50, 35), (200, -20)):
                with patch("pico2d.draw_circle") as draw:
                    Assets.draw_researcher_aim(SimpleNamespace(), enemy, camera_x, camera_y)
                self.assertGreater(draw.call_count, 8)
                for call in draw.call_args_list:
                    x, y, radius, *color = call.args
                    self.assertEqual(y, 120 + config.AR_SOLDIER_MUZZLE_HEIGHT - camera_y)
                    self.assertEqual((radius, tuple(color)), (2, (255, 45, 55)))
                    self.assertTrue(-radius <= x < config.SCREEN_WIDTH + radius)

    def test_game_shows_warning_with_u_hidden_but_never_over_the_loading_screen(self):
        game = Game.__new__(Game)
        game.world, enemy = encounter()
        enemy.start_attack()
        game.assets, game.ui = Mock(), Mock()
        game.world.stage.draw = Mock()
        game.ui.details_visible = False
        with patch.object(pico2d, "clear_canvas"):
            game.draw(present=False)
            game.assets.draw_researcher_aim.assert_called_once_with(
                enemy, game.world.camera.render_x, game.world.camera.render_y)
            game.assets.reset_mock()
            game.world.pending_stage_index = 9
            with patch.object(game, "draw_stage_loading_screen") as loading:
                game.draw(present=False)
            loading.assert_called_once_with(False)
            game.assets.draw_researcher_aim.assert_not_called()

    def test_source_grid_and_shared_loading_preserve_all_seven_rows_and_eight_bullet_frames(self):
        with Image.open(config.ROOT / config.AR_SOLDIER_IMAGE) as image:
            self.assertEqual((image.size, image.mode), ((2048, 1792), "RGBA"))
        with Image.open(config.ROOT / config.RIFLE_BULLET_IMAGE) as image:
            self.assertEqual((image.size, image.mode), ((2048, 256), "RGBA"))
        with patch("pico2d.load_image", return_value=Mock()), patch("pico2d.load_font"):
            assets = Assets()
        self.assertEqual(len(assets.frames[config.AR_SOLDIER_IMAGE]), 7)
        self.assertEqual(len(assets.frames[config.RIFLE_BULLET_IMAGE][0]), 8)
        self.assertIn(config.AR_SOLDIER_IMAGE, assets.images)
        for archived in config.ARCHIVED_AR_SOLDIER_IMAGES:
            for name in (archived, archived.rsplit("/", 1)[-1]):
                self.assertNotIn(name, assets.images)
                self.assertNotIn(name, assets.frames)
        self.assertIn(config.RIFLE_BULLET_IMAGE, assets.images)
        self.assertEqual(len(assets.frames), 26)
        self.assertEqual(sum(len(row) for rows in assets.frames.values() for row in rows), 1344)

    def test_reload_fixed_sheet_and_both_archived_originals_keep_their_supplied_bytes(self):
        self.assertEqual(config.AR_SOLDIER_IMAGE, "AR_soldier_pico2d_reload_fixed_2048x1792.png")
        self.assertEqual(config.ARCHIVED_AR_SOLDIER_IMAGES, (
            "before_sheets/AR_soldier.png",
            "before_sheets/AR_soldier_pico2d_2048x1792.png",
        ))
        for name, digest in (
            (config.AR_SOLDIER_IMAGE, "5793b6627ee64e5eb9cbfc6a24fdb5bf202d246c159f43ab5625992d12937d98"),
            ("before_sheets/AR_soldier.png", "ad7b5d7b665199d82080579a76f571d23f150b12a1d6cc4f54ecb589587ffda6"),
            ("before_sheets/AR_soldier_pico2d_2048x1792.png",
             "2c6d6d145f9e81884d3baa5dffbd82a59164053cbdee2ac30de2a30a6cd53997"),
        ):
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((config.ROOT / name).read_bytes()).hexdigest(), digest)
                with Image.open(config.ROOT / name) as image:
                    self.assertEqual((image.size, image.mode), ((2048, 1792), "RGBA"))
        from tools.prepare_assets import SHEETS
        self.assertIn(config.AR_SOLDIER_IMAGE, SHEETS)
        for archived in config.ARCHIVED_AR_SOLDIER_IMAGES:
            self.assertFalse((config.ROOT / archived.rsplit("/", 1)[-1]).exists())
            for name in (archived, archived.rsplit("/", 1)[-1]):
                self.assertNotIn(name, SHEETS)

    def test_reload_fixed_sheet_only_changes_the_sixth_row(self):
        with (Image.open(config.ROOT / config.AR_SOLDIER_IMAGE) as fixed,
              Image.open(config.ROOT / "before_sheets/AR_soldier_pico2d_2048x1792.png") as previous):
            for row in range(7):
                with self.subTest(row=row + 1):
                    box = (0, row * 256, 2048, (row + 1) * 256)
                    difference = ImageChops.difference(fixed.crop(box), previous.crop(box))
                    if row == 5:
                        self.assertIsNotNone(difference.getbbox(alpha_only=False))
                    else:
                        self.assertIsNone(difference.getbbox(alpha_only=False))

    def test_all_reload_fixed_sheet_clips_keep_source_bounds_flips_and_feet_alignment(self):
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            metadata = json.load(file)
        texture = Mock()
        assets = SimpleNamespace(frames=metadata, images={config.AR_SOLDIER_IMAGE: texture})
        with Image.open(config.ROOT / config.AR_SOLDIER_IMAGE) as image:
            for row in range(7):
                for frame in range(8):
                    cell = image.crop((frame * 256, row * 256, (frame + 1) * 256, (row + 1) * 256))
                    left, top, right, bottom = cell.getbbox()
                    clip = (frame * 256 + left, image.height - row * 256 - bottom,
                            right - left, bottom - top)
                    self.assertEqual(tuple(metadata[config.AR_SOLDIER_IMAGE][row][frame]["clip"]), clip)
                    for facing in (-1, 1):
                        Assets.draw_sprite(assets, config.AR_SOLDIER_IMAGE, row + 1, frame, 500, 100, facing)
                        args = texture.clip_composite_draw.call_args.args
                        self.assertEqual(args[:4], clip)
                        self.assertEqual(args[5], "h" if facing < 0 else "")
                        self.assertEqual(args[7] - args[9] / 2, 100)
                        self.assertEqual(args[8:10], ((right - left) * 0.75, (bottom - top) * 0.75))

    def test_new_planted_firing_poses_align_the_warning_and_bullets_to_the_muzzle(self):
        self.assertEqual(config.AR_SOLDIER_MUZZLE_X, (208 - 128) * 0.75)
        with Image.open(config.ROOT / config.AR_SOLDIER_IMAGE) as image:
            for frame in config.AR_SOLDIER_FIRE_FRAMES:
                cell = image.crop((frame * 256, 768, (frame + 1) * 256, 1024))
                self.assertEqual(cell.getbbox()[3], 248)
                self.assertEqual(config.AR_SOLDIER_MUZZLE_HEIGHT, (248 - 143) * 0.75)
                flash_y = [y for y in range(120, 165) for x in range(190, 245)
                           if (lambda p: p[3] > 128 and p[0] > 180 and p[1] > 90 and p[2] < 100)(
                               cell.getpixel((x, y)))]
                self.assertTrue(flash_y)
                self.assertAlmostEqual(sum(flash_y) / len(flash_y), 143, delta=1)

    def test_aim_shots_reload_and_projectiles_are_identical_at_all_render_rates(self):
        snapshots = []
        for fps in (30, 60, 120, 144):
            world, enemy = encounter(side=-1)
            advance(world, 24, fps)
            snapshots.append((enemy.hp, enemy.ammo, enemy.state, enemy.aim_remaining,
                              enemy.fire_remaining, enemy.burst_shots,
                              enemy.animation.elapsed, world.player.hp,
                              [(bullet.x, bullet.elapsed, bullet.frame) for bullet in world.projectiles]))
        self.assertTrue(all(snapshot == snapshots[0] for snapshot in snapshots))


if __name__ == "__main__":
    unittest.main()
