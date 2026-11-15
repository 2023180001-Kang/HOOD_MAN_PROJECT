import random
import unittest

import config
from collision import bodies_overlap, resolve_bodies
from controls import Controls
from counter import can_counter
from enemy02 import Enemy02, leap_height
from enemy_spacing import prepare_enemy_spacing, resolve_enemy_spacing
from player import Player
from tests.helpers import advance, spawn_encounter, tap
from traffic import Car
from world import World


def flying_enemy(*, side=-1, gap=400, ground_y=100):
    player = Player()
    enemy = Enemy02(player.x + side * gap, -side, ground_y=ground_y)
    assert enemy.start_leap(player)
    while not enemy.leaping:
        enemy.update(config.FIXED_DT, player)
    return player, enemy


class Enemy02LeapTests(unittest.TestCase):
    def test_distance_boundaries_trigger_a_leap_in_both_directions(self):
        for side in (-1, 1):
            for gap, expected in ((319.99, False), (320, True), (480, True),
                                  (640, True), (640.01, False), (1000, False)):
                with self.subTest(side=side, gap=gap):
                    player = Player()
                    enemy = Enemy02(player.x + side * gap, -side)
                    enemy.update(config.FIXED_DT, player)
                    self.assertEqual(enemy.leap_phase == "WINDUP", expected)
                    if expected:
                        self.assertEqual((enemy.attack_kind, enemy.animation.row), ("slam", 5))
                        self.assertEqual((enemy.vx, enemy.ground_vy), (0, 0))
                    else:
                        self.assertIn(enemy.state, ("WALK", "RUN"))

    def test_status_and_cooldowns_prevent_starting_an_extra_leap(self):
        for blocked in ("cooldown", "leap_cooldown", "hit", "airborne", "knockback",
                        "dead", "player_dead"):
            with self.subTest(blocked=blocked):
                player = Player()
                enemy = Enemy02(player.x - 400)
                if blocked in ("cooldown", "leap_cooldown"):
                    setattr(enemy, blocked, 1)
                elif blocked == "hit":
                    enemy.take_damage(10)
                elif blocked == "airborne":
                    enemy.jump_height = 20
                elif blocked == "knockback":
                    enemy.knockback(player.x)
                elif blocked == "dead":
                    enemy.take_damage(200)
                else:
                    player.take_damage(500)
                self.assertFalse(enemy.start_leap(player))
                self.assertIsNone(enemy.leap_phase)

    def test_too_distant_enemy_runs_into_range_then_launches(self):
        player = Player()
        enemy = Enemy02(player.x - 1000, run_speed=480)
        for _ in range(240):
            gap = player.x - enemy.x
            enemy.update(config.FIXED_DT, player)
            if enemy.leap_phase is not None:
                self.assertGreaterEqual(gap, 320)
                self.assertLessEqual(gap, 640)
                break
            self.assertEqual(enemy.state, "RUN")
        self.assertEqual(enemy.leap_phase, "WINDUP")
        self.assertGreater(enemy.x, player.x - 1000)

    def test_apex_matches_a_real_normal_player_double_jump(self):
        reference, controls = Player(), Controls()
        controls.press("jump")
        reference.update(config.FIXED_DT, controls)
        while reference.vy > 0:
            reference.update(config.FIXED_DT, controls)
        tap(controls, "jump")
        peak = reference.jump_height
        for _ in range(240):
            reference.update(config.FIXED_DT, controls)
            peak = max(peak, reference.jump_height)
            if reference.grounded:
                break
        player, enemy = flying_enemy()
        observed = 0
        while enemy.leaping:
            enemy.update(config.FIXED_DT, player)
            observed = max(observed, enemy.jump_height)
            self.assertIsNone(enemy.attack_box)
        self.assertAlmostEqual(observed, peak, delta=0.1)
        self.assertAlmostEqual(observed, leap_height(), delta=0.02)
        self.assertGreater(observed, 300)
        self.assertEqual(enemy.jump_height, 0)

    def test_plane_moves_toward_both_axes_and_lands_eighty_pixels_short(self):
        for side in (-1, 1):
            player, enemy = flying_enemy(side=side, ground_y=56)
            origin, target = enemy.leap_origin, enemy.leap_target
            self.assertEqual(target, (player.x + side * 80, player.ground_y))
            previous_x = enemy.x
            while enemy.leaping:
                enemy.update(config.FIXED_DT, player)
                self.assertGreaterEqual((enemy.x - previous_x) * -side, -1e-8)
                self.assertGreaterEqual(enemy.ground_y, origin[1])
                self.assertLessEqual(enemy.ground_y, target[1])
                self.assertTrue(enemy.walkable.contains(enemy.x, enemy.ground_y, 128))
                self.assertFalse(enemy.try_hit(player))
                previous_x = enemy.x
            self.assertEqual((enemy.x, enemy.ground_y), target)
            self.assertEqual(enemy.leap_phase, "LANDING")
            for _ in range(30):
                enemy.update(config.FIXED_DT, player)
                if enemy.try_hit(player):
                    break
            self.assertEqual(player.hp, 420)
            for _ in range(10):
                enemy.update(config.FIXED_DT, player)
                self.assertFalse(enemy.try_hit(player))
            self.assertEqual(player.hp, 420)

    def test_takeoff_targets_latest_player_position_but_air_does_not_home(self):
        player = Player()
        enemy = Enemy02(player.x - 400)
        self.assertTrue(enemy.start_leap(player))
        player.x += 100
        player.ground_y = 116
        while not enemy.leaping:
            enemy.update(config.FIXED_DT, player)
        target = enemy.leap_target
        self.assertEqual(target, (player.x - 80, 116))
        player.x += 300
        player.ground_y = 56
        while enemy.leaping:
            enemy.update(config.FIXED_DT, player)
            self.assertEqual(enemy.leap_target, target)
        self.assertEqual((enemy.x, enemy.ground_y), target)
        for _ in range(30):
            enemy.update(config.FIXED_DT, player)
            self.assertFalse(enemy.try_hit(player))
        self.assertEqual(player.hp, 500)

    def test_player_moving_during_windup_cannot_force_an_unbounded_or_backward_flight(self):
        for target_x in (900, 2400):
            player = Player()
            enemy = Enemy02(880)
            self.assertTrue(enemy.start_leap(player))
            player.x = target_x
            while not enemy.leaping:
                enemy.update(config.FIXED_DT, player)
            self.assertGreaterEqual(enemy.leap_target[0], 880)
            self.assertLessEqual(enemy.leap_target[0] - 880, 560)

    def test_airborne_trajectory_is_not_modified_by_body_or_formation_corrections(self):
        player, enemy = flying_enemy()
        enemy.x = enemy.previous_x = player.x + 10
        enemy.jump_height = 1
        self.assertTrue(bodies_overlap(player, enemy))
        self.assertFalse(enemy.blocks_movement)
        before = player.x, player.ground_y, enemy.x, enemy.ground_y
        resolve_bodies(player, [enemy])
        prepare_enemy_spacing(player, [enemy])
        resolve_enemy_spacing(player, [enemy], config.FIXED_DT)
        self.assertEqual((player.x, player.ground_y, enemy.x, enemy.ground_y), before)
        self.assertIsNone(enemy.target_x)
        player.x = enemy.x + enemy.facing * 80
        enemy.jump_height = 0  # Even the exact takeoff instant cannot be countered.
        self.assertFalse(can_counter(player, enemy))

    def test_landing_cooldown_prevents_immediate_repeated_leaps(self):
        player, enemy = flying_enemy()
        while enemy.leap_phase is not None:
            enemy.update(config.FIXED_DT, player)
        self.assertGreater(enemy.leap_cooldown, 1.5)
        self.assertLess(enemy.leap_cooldown, 2)
        enemy.x = player.x - 400
        enemy.cooldown = 0
        self.assertFalse(enemy.start_leap(player))
        enemy.leap_cooldown = 0.01
        enemy.update(config.FIXED_DT, player)
        self.assertIsNone(enemy.leap_phase)
        enemy.update(config.FIXED_DT, player)
        self.assertEqual(enemy.leap_phase, "WINDUP")

    def test_high_flight_clears_a_car_but_low_flight_still_uses_normal_car_collision(self):
        player, enemy = flying_enemy()
        enemy.update(enemy.leap_duration / 2 - enemy.leap_elapsed, player)
        enemy.ground_y = enemy.previous_ground_y = config.CAR_GROUND_Y
        enemy.previous_x = enemy.x
        enemy.previous_jump_height = enemy.jump_height
        car = Car(enemy.x, 1, 1400)
        car.update(config.FIXED_DT)
        self.assertFalse(car.hits(enemy))
        enemy.jump_height = enemy.previous_jump_height = 60
        self.assertTrue(car.hits(enemy))
        self.assertTrue(enemy.hit_by_car(1))
        self.assertIsNone(enemy.leap_phase)
        self.assertEqual((enemy.hp, enemy.state), (0, "CAR_HIT"))

    def test_air_target_phase_height_and_cooldowns_pause_during_loading_and_revisit(self):
        world = World(rng=random.Random(13))
        world.stage_index = 3
        enemy = spawn_encounter(world, 1)[0]
        enemy.x = enemy.previous_x = world.player.x - 400
        enemy.ground_y = enemy.previous_ground_y = world.player.ground_y
        while not enemy.leaping:
            world.step(config.FIXED_DT)
        snapshot = (enemy.leap_phase, enemy.leap_elapsed, enemy.leap_target,
                    enemy.x, enemy.ground_y, enemy.jump_height, enemy.vy,
                    enemy.animation.elapsed, enemy.cooldown, enemy.leap_cooldown)
        world.stage.arrows_visible = True
        world.player.x, world.player.vx = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN, config.RUN_SPEED
        self.assertTrue(world.try_stage_transition())
        advance(world, 2)
        world.select_stage(3)
        self.assertIs(world.enemies[0], enemy)
        self.assertEqual((enemy.leap_phase, enemy.leap_elapsed, enemy.leap_target,
                          enemy.x, enemy.ground_y, enemy.jump_height, enemy.vy,
                          enemy.animation.elapsed, enemy.cooldown, enemy.leap_cooldown), snapshot)
        world.controls.press("restart")
        world.update(1 / 60)
        self.assertEqual(world.stages[3].enemies, [])
        self.assertEqual(world.stages[3].spawner.spawned_count, 0)
        world.select_stage(3)
        world.controls.press("spawn_4")
        world.update(config.FIXED_DT)
        self.assertTrue(all(actor.leap_phase is None and actor.leap_cooldown == 0
                            for actor in world.stages[3].enemies))
        self.assertEqual(len(world.stages[3].enemies), 4)


if __name__ == "__main__":
    unittest.main()
