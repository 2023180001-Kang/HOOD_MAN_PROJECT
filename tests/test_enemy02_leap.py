import random
import unittest

import config
from collision import bodies_overlap, body_contact_time, resolve_bodies
from combat import MOVES
from controls import Controls
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


def midair_encounter(index=3, side=-1):
    world = World(rng=random.Random(17))
    world.stage_index = index
    world.stage.traffic = None
    _, enemy = flying_enemy(side=side)
    world.enemies = [enemy]
    enemy.walkable = world.stage.walkable
    enemy.update(enemy.leap_duration / 2 - enemy.leap_elapsed, world.player)
    player = world.player
    player.x = player.previous_x = enemy.x - side * 60
    player.jump_height = player.previous_jump_height = enemy.jump_height
    player.jump_count = 2
    player.facing = side
    player.animation.set_state("JUMP")
    return world, enemy


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

    def test_plane_targets_the_player_position_and_stops_at_an_occupied_body_edge(self):
        for side in (-1, 1):
            player, enemy = flying_enemy(side=side, ground_y=56)
            origin, target = enemy.leap_origin, enemy.leap_target
            self.assertEqual(target, (player.x, player.ground_y))
            previous_x = enemy.x
            while enemy.leaping:
                enemy.update(config.FIXED_DT, player)
                self.assertGreaterEqual((enemy.x - previous_x) * -side, -1e-8)
                self.assertGreaterEqual(enemy.ground_y, origin[1])
                self.assertLessEqual(enemy.ground_y, target[1])
                self.assertTrue(enemy.walkable.contains(enemy.x, enemy.ground_y, 128))
                self.assertFalse(enemy.try_hit(player))
                previous_x = enemy.x
            self.assertLessEqual(abs(enemy.x - player.x), 61 + 1e-8)
            self.assertLess(abs(enemy.ground_y - player.ground_y), config.BODY_DEPTH_TOLERANCE)
            self.assertTrue(enemy.leap_blocked)
            self.assertEqual(enemy.leap_phase, "LANDING")
            for _ in range(30):
                enemy.update(config.FIXED_DT, player)
                if enemy.try_hit(player):
                    break
            self.assertEqual(player.hp, 450)
            for _ in range(10):
                enemy.update(config.FIXED_DT, player)
                self.assertFalse(enemy.try_hit(player))
            self.assertEqual(player.hp, 450)

    def test_takeoff_targets_latest_player_position_but_air_does_not_home(self):
        player = Player()
        enemy = Enemy02(player.x - 400)
        self.assertTrue(enemy.start_leap(player))
        player.x += 100
        player.ground_y = 116
        while not enemy.leaping:
            enemy.update(config.FIXED_DT, player)
        target = enemy.leap_target
        self.assertEqual(target, (player.x, 116))
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

    def test_windup_reaim_uses_the_actual_player_position_and_caps_flight_distance(self):
        for target_x in (760, 900, 2400):
            player = Player()
            enemy = Enemy02(880)
            self.assertTrue(enemy.start_leap(player))
            player.x = target_x
            while not enemy.leaping:
                enemy.update(config.FIXED_DT, player)
            self.assertGreaterEqual((enemy.leap_target[0] - 880) * (target_x - 880), 0)
            self.assertLessEqual(abs(enemy.leap_target[0] - 880), 640)
            if abs(target_x - 880) <= 640:
                self.assertEqual(enemy.leap_target, (target_x, player.ground_y))

    def test_high_flight_avoids_ground_bodies_but_matching_airborne_bodies_block(self):
        player, enemy = flying_enemy()
        enemy.x = enemy.previous_x = player.x + 10
        enemy.jump_height = 220
        self.assertFalse(bodies_overlap(player, enemy))
        self.assertTrue(enemy.blocks_movement)
        before = player.x, player.ground_y, enemy.x, enemy.ground_y
        resolve_bodies(player, [enemy])
        prepare_enemy_spacing(player, [enemy])
        resolve_enemy_spacing(player, [enemy], config.FIXED_DT)
        self.assertEqual((player.x, player.ground_y, enemy.x, enemy.ground_y), before)
        self.assertIsNone(enemy.target_x)
        player.jump_height = player.previous_jump_height = 220
        self.assertTrue(bodies_overlap(player, enemy))
        resolve_bodies(player, [enemy])
        self.assertFalse(bodies_overlap(player, enemy))

    def test_both_city_maps_apply_one_normal_club_hit_when_jumpers_meet(self):
        for index in (2, 3):
            for side in (-1, 1):
                with self.subTest(stage=index, side=side):
                    world, enemy = midair_encounter(index, side)
                    world.step(config.FIXED_DT)
                    self.assertEqual(world.player.hp, 470)
                    self.assertEqual((enemy.attack_kind, enemy.animation.row), ("clubs", 4))
                    self.assertTrue(enemy.air_contact_attack and enemy.has_hit)
                    self.assertFalse(enemy.air_contact_pending)
                    self.assertIsNone(enemy.leap_phase)
                    self.assertGreater(enemy.jump_height, 0)
                    self.assertFalse(bodies_overlap(world.player, enemy))
                    self.assertEqual(len(world.effects), 1)
                    self.assertEqual(world.effects[0].image_name, config.CLUB_HIT_IMAGE)
                    advance(world, 0.7)
                    self.assertEqual(world.player.hp, 470)  # No extra hit on landing.
                    self.assertEqual(enemy.jump_height, 0)

    def test_midair_normal_hit_respects_invincibility_and_player_attack_priority(self):
        world, enemy = midair_encounter()
        world.player.invincible = True
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 500)
        self.assertTrue(enemy.has_hit)
        self.assertFalse(world.effects)
        world.player.invincible = False
        advance(world, 0.5)
        self.assertEqual(world.player.hp, 500)
        for lethal in (False, True):
            world, enemy = midair_encounter()
            enemy.hp = 10 if lethal else 200
            world.player.start_move(MOVES["combat_a"], -1)
            world.player.animation.elapsed = 3 / MOVES["combat_a"].fps
            world.step(config.FIXED_DT)
            self.assertEqual(world.player.hp, 500)
            self.assertEqual(enemy.hp, 0 if lethal else 190)
            self.assertEqual(enemy.state, "DYING" if lethal else "HIT")
            self.assertFalse(enemy.air_contact_pending)
            self.assertEqual(len(world.effects), 1)
            self.assertEqual(world.effects[0].image_name, config.PUNCH_KICK_HIT_IMAGE)

    def test_depth_or_height_misses_do_not_trigger_an_air_contact_attack(self):
        for depth, height in ((12, 0), (32, 0), (0, 200), (0, -200)):
            with self.subTest(depth=depth, height=height):
                world, enemy = midair_encounter()
                world.player.ground_y += depth
                world.player.previous_ground_y = world.player.ground_y
                world.player.jump_height += height
                world.player.previous_jump_height = world.player.jump_height
                world.step(config.FIXED_DT)
                self.assertTrue(enemy.leaping)
                self.assertFalse(enemy.air_contact_attack)
                self.assertEqual(world.player.hp, 500)

    def test_swept_air_contact_catches_fast_crossing_without_false_axis_matches(self):
        player, enemy = flying_enemy()
        player.jump_height = player.previous_jump_height = 200
        enemy.previous_jump_height = enemy.jump_height = 200
        enemy.previous_x, enemy.x = player.x - 200, player.x + 200
        contact = body_contact_time(player, enemy)
        self.assertAlmostEqual(contact, (200 - 61) / 400)
        self.assertTrue(enemy._resolve_leap_contact(player))
        resolve_bodies(player, [enemy])
        self.assertFalse(bodies_overlap(player, enemy))
        self.assertLess(enemy.x, player.x)
        self.assertTrue(enemy.try_hit(player))
        self.assertEqual(player.hp, 470)
        self.assertFalse(enemy.try_hit(player))
        enemy.previous_x, enemy.x = player.x, player.x + 400
        enemy.previous_jump_height, enemy.jump_height = 500, 200
        self.assertIsNone(body_contact_time(player, enemy))

    def test_actual_jump_meetings_have_the_same_result_at_all_render_rates(self):
        for index in (2, 3):
            for side in (-1, 1):
                outcomes = []
                for fps in (30, 60, 120, 144):
                    world = World()
                    world.stage_index = index
                    world.stage.traffic = None
                    enemy = Enemy02(world.player.x + side * 400, -side)
                    world.enemies = [enemy]
                    advance(world, 0.5, fps)
                    world.controls.press("jump")
                    for _ in range(fps):
                        world.update(1 / fps)
                        if enemy.air_contact_attack:
                            self.assertFalse(bodies_overlap(world.player, enemy))
                    self.assertEqual(world.player.hp, 470)
                    outcomes.append((world.player.x, world.player.jump_height, world.player.state,
                                     enemy.x, enemy.jump_height, enemy.state, enemy.attack_kind,
                                     enemy.has_hit, enemy.leap_phase))
                self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))

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
