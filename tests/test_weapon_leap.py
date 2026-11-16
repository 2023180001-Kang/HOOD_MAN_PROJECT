import unittest

import config
from controls import Controls
from enemy import Enemy
from enemy02 import Enemy02
from player import Player
from tests.helpers import advance, tap
from tests.test_weapon_combat import equipped_world, target


def launch(kind, *, side=1, running=False, moving=True):
    world = equipped_world(kind)
    player = world.player
    player.x = 350 if side > 0 else config.WORLD_WIDTH - 350
    player.facing = side
    if moving:
        player.vx = side * (config.RUN_SPEED if running else config.WALK_SPEED)
        world.controls.press("right" if side > 0 else "left")
    if running:
        world.controls.press("left_shift")
    world.controls.press("combat_d")
    for _ in range(40):
        world.step(config.FIXED_DT)
        if player.weapon_leap_phase == "AIR":
            return world
    raise AssertionError("D never launched")


class WeaponLeapTests(unittest.TestCase):
    def test_both_weapons_match_real_walking_running_double_jump_height_and_distance(self):
        for kind in config.WEAPON_POSE_IMAGES:
            for side in (-1, 1):
                for running in (False, True):
                    with self.subTest(kind=kind, side=side, running=running):
                        world = launch(kind, side=side, running=running)
                        player = world.player
                        reference, controls = Player(), Controls()
                        reference.x, reference.vx = player.x, player.vx
                        controls.press("right" if side > 0 else "left")
                        if running:
                            controls.press("left_shift")
                        controls.press("jump")
                        start, peak = player.x, 0
                        for step in range(300):
                            if step == round(0.5 / config.FIXED_DT):
                                tap(controls, "jump")
                            world.step(config.FIXED_DT)
                            reference.update(config.FIXED_DT, controls)
                            for attribute in ("x", "ground_y", "jump_height", "vy", "jump_count"):
                                self.assertAlmostEqual(getattr(player, attribute),
                                                       getattr(reference, attribute), places=8)
                            peak = max(peak, player.jump_height)
                            if player.grounded:
                                break
                            self.assertIsNone(player.attack_box)
                        self.assertTrue(player.grounded)
                        self.assertEqual(player.weapon_leap_phase, "LANDING")
                        self.assertAlmostEqual((player.x - start) * side,
                                               (reference.x - start) * side)
                        self.assertGreater(peak, 350 if running else 280)
                        self.assertGreater((player.x - start) * side, 1100 if running else 440)

    def test_stationary_d_and_shift_alone_have_the_normal_double_jump_height(self):
        peaks = []
        for kind in config.WEAPON_POSE_IMAGES:
            for shift in (False, True):
                world = launch(kind, moving=False, running=shift)
                player = world.player
                start, peak, counts = player.x, 0, set()
                for _ in range(300):
                    world.step(config.FIXED_DT)
                    peak = max(peak, player.jump_height)
                    counts.add(player.jump_count)
                    self.assertEqual(player.x, start)
                    if player.grounded:
                        break
                self.assertIn(2, counts)
                self.assertGreater(peak, 280)
                peaks.append(peak)
        self.assertTrue(all(peak == peaks[0] for peak in peaks))

    def test_long_flight_holds_air_poses_and_only_landing_hits_each_enemy_once(self):
        for kind in config.WEAPON_POSE_IMAGES:
            for enemy_type in (Enemy, Enemy02):
                for side in (-1, 1):
                    world = equipped_world(kind)
                    player = world.player
                    player.facing = side
                    enemy = target(world, enemy_type, side)
                    world.controls.press("combat_d")
                    hits, airborne_ticks = 0, 0
                    for _ in range(320):
                        hp = enemy.hp
                        world.step(config.FIXED_DT)
                        if player.weapon_leap_phase == "AIR":
                            airborne_ticks += 1
                            self.assertIn(player.animation.frame, (2, 3))
                            self.assertIsNone(player.attack_box)
                            self.assertEqual(enemy.hp, 200)
                        if enemy.hp != hp:
                            hits += 1
                            self.assertTrue(player.grounded)
                            self.assertEqual(player.weapon_leap_phase, "LANDING")
                            self.assertIn(player.animation.frame, (5, 6))
                            self.assertEqual(world.effects[-1].image_name, config.WEAPON_HIT_IMAGES[kind])
                        if player.active_move is None:
                            break
                    self.assertGreater(airborne_ticks * config.FIXED_DT, 1.4)
                    self.assertEqual((hits, enemy.hp), (1, 150))
                    self.assertEqual((player.state, player.sprite_image),
                                     ("IDLE", config.WEAPON_POSE_IMAGES[kind]))

    def test_d_repress_and_space_cannot_add_a_third_jump_or_restart_the_leap(self):
        for kind in config.WEAPON_POSE_IMAGES:
            actual = launch(kind, moving=False)
            quiet = launch(kind, moving=False)
            for step in range(300):
                if step % 5 == 0:
                    tap(actual.controls, "combat_d")
                    tap(actual.controls, "jump")
                actual.step(config.FIXED_DT)
                quiet.step(config.FIXED_DT)
                self.assertEqual((actual.player.jump_height, actual.player.vy,
                                  actual.player.jump_count, actual.player.weapon_leap_phase),
                                 (quiet.player.jump_height, quiet.player.vy,
                                  quiet.player.jump_count, quiet.player.weapon_leap_phase))
                self.assertLessEqual(actual.player.jump_count, 2)
                if actual.player.active_move is None:
                    break
            self.assertIsNone(actual.player.active_move)

    def test_interruption_clears_the_scheduled_boost_and_keeps_natural_falling(self):
        for kind in config.WEAPON_POSE_IMAGES:
            for cause in ("hit", "death", "drop", "attack", "car"):
                with self.subTest(kind=kind, cause=cause):
                    world = launch(kind, moving=False)
                    player = world.player
                    advance(world, 0.2)
                    self.assertTrue(player.weapon_leap_boost_pending)
                    if cause in ("hit", "death"):
                        player.invincible = False
                        player.take_damage(20 if cause == "hit" else 500)
                    elif cause == "drop":
                        tap(world.controls, "weapon_interact")
                    elif cause == "attack":
                        tap(world.controls, "combat_a")
                    else:
                        player.hit_by_car(1)
                    world.step(config.FIXED_DT)
                    self.assertIsNone(player.weapon_leap_phase)
                    self.assertFalse(player.weapon_leap_boost_pending)
                    advance(world, 1.5)
                    self.assertTrue(player.grounded)
                    if cause == "car":
                        self.assertEqual(player.state, "DEAD")
                        self.assertLessEqual(player.jump_count, 1)
                    else:
                        self.assertEqual(player.jump_count, 0)

    def test_switching_away_and_back_to_airborne_d_never_relaunches(self):
        for kind in config.WEAPON_POSE_IMAGES:
            world = launch(kind, moving=False)
            advance(world, 0.2)
            tap(world.controls, "combat_a")
            world.step(config.FIXED_DT)
            velocity = world.player.vy
            tap(world.controls, "combat_d")
            world.step(config.FIXED_DT)
            self.assertEqual(world.player.weapon_leap_phase, "AIR")
            self.assertFalse(world.player.weapon_leap_boost_pending)
            self.assertLess(world.player.vy, velocity)
            self.assertEqual(world.player.jump_count, 1)
            for _ in range(200):
                world.step(config.FIXED_DT)
                self.assertLessEqual(world.player.jump_count, 1)
                if world.player.grounded:
                    break
            self.assertTrue(world.player.grounded)

    def test_all_stage_corners_keep_leaping_feet_inside_the_floor(self):
        for kind in config.WEAPON_POSE_IMAGES:
            for index in range(len(config.STAGE_IMAGES)):
                for side, sy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
                    world = equipped_world(kind)
                    world.select_stage(index)
                    world.stage.traffic = None
                    player = world.player
                    left, bottom, right, top = world.stage.walkable.bounds
                    player.x = left + player.boundary_padding if side < 0 else right - player.boundary_padding
                    player.ground_y = bottom if sy < 0 else top
                    for key in ("combat_d", "left_shift", "left" if side < 0 else "right",
                                "down" if sy < 0 else "up"):
                        world.controls.press(key)
                    for _ in range(300):
                        world.step(config.FIXED_DT)
                        self.assertTrue(world.stage.walkable.contains(player.x, player.ground_y,
                                                                     player.boundary_padding))
                        self.assertGreaterEqual(player.jump_height, 0)
                    self.assertEqual(world.stage_index, index)

    def test_leap_and_boost_pause_during_loading_and_f5_clears_them(self):
        for kind in config.WEAPON_POSE_IMAGES:
            world = launch(kind, moving=False)
            advance(world, 0.2)
            player = world.player
            before = (player.jump_height, player.vy, player.weapon_leap_elapsed)
            world.pending_stage_index, world.stage_loading_remaining = 1, 2
            world.update(1.5)
            self.assertEqual((player.jump_height, player.vy, player.weapon_leap_elapsed), before)
            tap(world.controls, "restart")
            world.update(config.FIXED_DT)
            self.assertIsNone(world.player.weapon_leap_phase)
            self.assertFalse(world.player.weapon_leap_boost_pending)
            self.assertIsNone(world.player.weapon)
            self.assertTrue(world.player.grounded)

    def test_actual_d_jump_timing_and_distance_are_identical_at_different_render_rates(self):
        for kind in config.WEAPON_POSE_IMAGES:
            results = []
            for fps in (30, 60, 120, 144):
                world = equipped_world(kind)
                world.player.x, world.player.vx = 350, config.RUN_SPEED
                for key in ("right", "left_shift", "combat_d"):
                    world.controls.press(key)
                snapshots = []
                for _ in range(5):
                    advance(world, 0.5, fps)
                    player = world.player
                    snapshots.append((player.x, player.ground_y, player.jump_height, player.vy,
                                      player.jump_count, player.weapon_leap_phase, player.state))
                results.append(snapshots)
            self.assertTrue(all(result == results[0] for result in results))


if __name__ == "__main__":
    unittest.main()
