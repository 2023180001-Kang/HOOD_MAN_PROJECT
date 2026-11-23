import unittest
from math import hypot

import config
from axe_enemy import AxeEnemy
from camera import Camera
from drop_items import DropItem
from effects import DamageNumber, HitEffect
from enemy import Enemy
from enemy02 import Enemy02
from player import Player
from researcher import Researcher
from tests.helpers import advance, tap
from tests.test_weapon_combat import double_jump, equipped_world, target
from traffic import Car, Traffic


def aim(kind):
    world = equipped_world(kind)
    double_jump(world)
    tap(world.controls, "combat_d")
    world.step(config.FIXED_DT)
    return world


class WeaponLeapTests(unittest.TestCase):
    def test_d_requires_two_manual_jumps_and_accepts_second_space_and_d_in_one_tick(self):
        for kind in config.WEAPON_POSE_IMAGES:
            world = equipped_world(kind)
            player = world.player
            tap(world.controls, "combat_d")
            world.step(config.FIXED_DT)
            self.assertTrue(player.grounded)
            self.assertIsNone(player.active_move)
            self.assertEqual(world.time_scale, 1)
            tap(world.controls, "jump")
            world.step(config.FIXED_DT)
            velocity = player.vy
            tap(world.controls, "combat_d")
            world.step(config.FIXED_DT)
            self.assertIsNone(player.active_move)
            self.assertEqual(player.jump_count, 1)
            self.assertAlmostEqual(player.vy, velocity - config.GRAVITY * config.FIXED_DT)
            tap(world.controls, "jump")
            tap(world.controls, "combat_d")
            elapsed = world.elapsed
            world.step(config.FIXED_DT)
            self.assertEqual((player.jump_count, player.weapon_leap_phase), (2, "AIM"))
            self.assertEqual(world.time_scale, config.WEAPON_AIM_TIME_SCALE)
            scaled_dt = config.FIXED_DT * config.WEAPON_AIM_TIME_SCALE
            self.assertAlmostEqual(player.vy, config.DOUBLE_JUMP_SPEED - config.GRAVITY * scaled_dt)
            self.assertAlmostEqual(world.elapsed - elapsed, scaled_dt)

    def test_slow_motion_scales_player_physics_and_both_enemy_types_on_the_entry_tick(self):
        for kind in config.WEAPON_POSE_IMAGES:
            for enemy_type in (Enemy, Enemy02):
                world = equipped_world(kind)
                double_jump(world)
                player = world.player
                player.vx = config.WALK_SPEED
                world.controls.press("right")
                mover = enemy_type(200, 1, ground_y=player.ground_y)
                reactor = target(world, enemy_type)
                reactor.x = player.x + 300
                world.enemies.append(mover)
                reference = Player()
                reference.jump_height, reference.vy = player.jump_height, player.vy
                reference.jump_count = player.jump_count
                start_x, elapsed = player.x, world.elapsed
                tap(world.controls, "combat_d")
                for _ in range(60):
                    world.step(config.FIXED_DT)
                    reference.update_vertical(config.FIXED_DT * config.WEAPON_AIM_TIME_SCALE)
                simulated = 0.5 * config.WEAPON_AIM_TIME_SCALE
                self.assertAlmostEqual(player.x - start_x, config.WALK_SPEED * simulated)
                self.assertAlmostEqual(player.jump_height, reference.jump_height)
                self.assertAlmostEqual(player.vy, reference.vy)
                self.assertAlmostEqual(mover.x - 200, mover.run_speed * simulated)
                self.assertAlmostEqual(mover.animation.elapsed, simulated)
                self.assertAlmostEqual(reactor.animation.elapsed, simulated)
                self.assertAlmostEqual(reactor.cooldown, 100 - simulated)
                self.assertAlmostEqual(world.elapsed - elapsed, simulated)
                self.assertEqual(player.jump_count, 2)

    def test_items_effects_damage_numbers_and_traffic_share_slow_and_fast_time(self):
        for kind in config.WEAPON_POSE_IMAGES:
            world = aim(kind)
            item = DropItem("steel_pipe", 500, 100, jump_height=200)
            effect, number = HitEffect(500, 200, 1), DamageNumber(500, 200, 10)
            world.stage.drop_items = [item]
            world.effects, world.damage_numbers = [effect], [number]
            world.stage.traffic = Traffic()
            car = Car(100, 1, config.CAR_SPEED_RANGE[0])
            world.stage.traffic.car = car
            advance(world, 0.3)
            simulated = 0.3 * config.WEAPON_AIM_TIME_SCALE
            for clock in (item.elapsed, effect.elapsed, number.elapsed, car.animation.elapsed):
                self.assertAlmostEqual(clock, simulated)
            self.assertAlmostEqual(car.x - 100, car.speed * simulated)
            self.assertAlmostEqual(item.vy, -config.GRAVITY * simulated)
            tap(world.controls, "combat_d")
            world.step(config.FIXED_DT)
            simulated += config.FIXED_DT * config.WEAPON_DIVE_TIME_SCALE
            self.assertEqual(world.time_scale, config.WEAPON_DIVE_TIME_SCALE)
            for clock in (item.elapsed, effect.elapsed, number.elapsed, car.animation.elapsed):
                self.assertAlmostEqual(clock, simulated)
            self.assertAlmostEqual(car.x - 100, car.speed * simulated)

    def test_air_steering_turns_and_the_second_d_locks_a_fast_directional_dive(self):
        for kind in config.WEAPON_POSE_IMAGES:
            for side in (-1, 1):
                world = aim(kind)
                player = world.player
                player.facing = -side
                start_x, start_y = player.x, player.ground_y
                horizontal = "right" if side > 0 else "left"
                world.controls.press(horizontal)
                world.controls.press("up")
                advance(world, 0.5)
                self.assertEqual(player.facing, side)
                self.assertGreater((player.x - start_x) * side, 0)
                self.assertGreater(player.ground_y, start_y)
                self.assertIsNone(player.attack_box)
                world.controls.release(horizontal)
                world.controls.release("up")
                start_x, start_y, height = player.x, player.ground_y, player.jump_height
                tap(world.controls, "combat_d")
                elapsed = world.elapsed
                world.step(config.FIXED_DT)
                fast_dt = config.FIXED_DT * config.WEAPON_DIVE_TIME_SCALE
                self.assertEqual(player.weapon_leap_phase, "DIVE")
                self.assertAlmostEqual(world.elapsed - elapsed, fast_dt)
                self.assertGreater((player.x - start_x) * side, 0)
                self.assertAlmostEqual(hypot(player.x - start_x, player.ground_y - start_y),
                                       config.WEAPON_DIVE_SPEED * fast_dt)
                self.assertLess(player.jump_height, height)
                self.assertLess(player.vy, -config.WEAPON_DIVE_FALL_SPEED)
                velocity = player.vx, player.ground_vy
                world.controls.press("left" if side > 0 else "right")
                world.controls.press("down")
                world.step(config.FIXED_DT)
                self.assertEqual((player.vx, player.ground_vy), velocity)
                self.assertEqual(player.facing, side)

    def test_direction_pressed_with_the_second_d_is_used_immediately(self):
        for kind in config.WEAPON_POSE_IMAGES:
            world = aim(kind)
            player = world.player
            world.controls.press("left")
            tap(world.controls, "combat_d")
            start = player.x
            world.step(config.FIXED_DT)
            self.assertEqual(player.facing, -1)
            self.assertLess(player.x, start)
            self.assertEqual(player.vx, -config.WEAPON_DIVE_SPEED)

    def test_held_or_repeated_d_does_not_release_and_represses_never_add_a_jump(self):
        for kind in config.WEAPON_POSE_IMAGES:
            world = aim(kind)
            for _ in range(60):
                world.controls.press("combat_d")
                tap(world.controls, "jump")
                world.step(config.FIXED_DT)
                self.assertEqual(world.player.weapon_leap_phase, "AIM")
                self.assertEqual(world.player.jump_count, 2)
            tap(world.controls, "combat_d")
            world.step(config.FIXED_DT)
            self.assertEqual(world.player.weapon_leap_phase, "DIVE")
            for _ in range(60):
                tap(world.controls, "combat_d")
                tap(world.controls, "jump")
                world.step(config.FIXED_DT)
                self.assertLessEqual(world.player.jump_count, 2)
                self.assertNotEqual(world.player.weapon_leap_phase, "AIM")
                if world.player.active_move is None:
                    break
            self.assertTrue(world.player.grounded)
            self.assertIsNone(world.player.active_move)
            self.assertEqual(world.time_scale, 1)

    def test_only_the_released_dive_landing_deals_damage_once_then_restores_normal_time(self):
        for kind in config.WEAPON_POSE_IMAGES:
            for enemy_type in (Enemy, Enemy02):
                for side in (-1, 1):
                    world = aim(kind)
                    player = world.player
                    player.facing = side
                    world.controls.press("right" if side > 0 else "left")
                    enemy = target(world, enemy_type, side)
                    advance(world, 0.1)
                    self.assertEqual(enemy.hp, 200)
                    tap(world.controls, "combat_d")
                    hits = 0
                    for _ in range(90):
                        hp = enemy.hp
                        world.step(config.FIXED_DT)
                        if not player.grounded:
                            self.assertIsNone(player.attack_box)
                            self.assertEqual(enemy.hp, 200)
                        if hp != enemy.hp:
                            hits += 1
                            self.assertTrue(player.grounded)
                            self.assertEqual(player.weapon_leap_phase, "LANDING")
                            self.assertIn(player.animation.frame, (5, 6))
                            self.assertEqual(world.time_scale, config.WEAPON_DIVE_TIME_SCALE)
                            self.assertEqual(world.effects[-1].image_name, config.WEAPON_HIT_IMAGES[kind])
                        if player.active_move is None:
                            break
                    self.assertEqual((hits, enemy.hp), (1, 150))
                    self.assertEqual((player.state, world.time_scale), ("IDLE", 1))

    def test_landing_without_a_second_d_cancels_aim_with_no_automatic_hit(self):
        for kind in (*config.WEAPON_POSE_IMAGES, "steel_club"):
            world = aim(kind)
            enemy = target(world)
            advance(world, 8)
            self.assertTrue(world.player.grounded)
            self.assertIsNone(world.player.active_move)
            self.assertEqual((world.time_scale, enemy.hp), (1, 200))
            self.assertFalse(world.effects)
            self.assertFalse(world.damage_numbers)
            self.assertEqual(world.camera.shake_remaining, 0)

    def test_dive_hit_shake_doubles_both_axes_without_changing_duration_or_decay(self):
        for kind in config.WEAPON_POSE_IMAGES:
            for enemy_type in (Enemy, Enemy02, AxeEnemy, Researcher):
                for side in (-1, 1):
                    with self.subTest(kind=kind, enemy=enemy_type.__name__, side=side):
                        world = aim(kind)
                        player = world.player
                        player.facing = side
                        world.controls.press("right" if side > 0 else "left")
                        enemy = target(world, enemy_type, side)
                        hp = enemy.hp
                        advance(world, 0.1)
                        self.assertEqual(world.camera.shake_remaining, 0)
                        tap(world.controls, "combat_d")
                        for _ in range(120):
                            world.step(config.FIXED_DT)
                            if enemy.hp != hp:
                                break
                        self.assertEqual(enemy.hp, hp - 50)
                        self.assertEqual(player.weapon_leap_phase, "LANDING")
                        self.assertEqual(world.camera.shake_strength, config.SHAKE_STRENGTH * 2)
                        self.assertAlmostEqual(world.camera.shake_remaining,
                                               config.SHAKE_DURATION
                                               - config.FIXED_DT * config.WEAPON_DIVE_TIME_SCALE)
                        baseline = Camera(player.x)
                        baseline.shake()
                        baseline.update(config.SHAKE_DURATION - world.camera.shake_remaining, player.x)
                        position = player.x, player.ground_y, enemy.x, enemy.ground_y
                        for _ in range(26):
                            self.assertAlmostEqual(world.camera.shake_remaining, baseline.shake_remaining)
                            self.assertAlmostEqual(world.camera.offset_x, baseline.offset_x * 2)
                            self.assertAlmostEqual(world.camera.offset_y, baseline.offset_y * 2)
                            world.camera.update(config.FIXED_DT, player.x)
                            baseline.update(config.FIXED_DT, player.x)
                        self.assertEqual((world.camera.shake_remaining, world.camera.offset_x,
                                          world.camera.offset_y), (0, 0, 0))
                        self.assertEqual((player.x, player.ground_y, enemy.x, enemy.ground_y), position)

    def test_aim_airborne_dive_and_missed_landing_do_not_start_shake(self):
        for kind in config.WEAPON_POSE_IMAGES:
            world = aim(kind)
            phases = {world.player.weapon_leap_phase}
            advance(world, 0.1)
            self.assertEqual(world.camera.shake_remaining, 0)
            tap(world.controls, "combat_d")
            for _ in range(120):
                world.step(config.FIXED_DT)
                phases.add(world.player.weapon_leap_phase)
                self.assertEqual((world.camera.shake_remaining, world.camera.offset_x,
                                  world.camera.offset_y), (0, 0, 0))
                if world.player.active_move is None:
                    break
            self.assertTrue({"AIM", "DIVE", "LANDING", None} <= phases)

    def test_dive_boost_does_not_leak_into_the_next_basic_hit_or_restart(self):
        for kind in config.WEAPON_POSE_IMAGES:
            for action in ("basic_hit", "restart"):
                world = aim(kind)
                enemy = target(world)
                tap(world.controls, "combat_d")
                for _ in range(120):
                    world.step(config.FIXED_DT)
                    if enemy.hp < 200:
                        break
                self.assertEqual(world.camera.shake_strength, config.SHAKE_STRENGTH * 2)
                if action == "restart":
                    tap(world.controls, "restart")
                    world.update(config.FIXED_DT)
                    self.assertEqual((world.camera.shake_strength, world.camera.shake_remaining,
                                      world.camera.offset_x, world.camera.offset_y),
                                     (config.SHAKE_STRENGTH, 0, 0, 0))
                    continue
                advance(world, 0.5)
                enemy.x = world.player.x + 80
                enemy.ground_y = world.player.ground_y
                hp = enemy.hp
                tap(world.controls, "combat_a")
                for _ in range(60):
                    world.step(config.FIXED_DT)
                    if enemy.hp < hp:
                        break
                self.assertEqual(enemy.hp, hp - 10)
                self.assertEqual(world.camera.shake_strength, config.SHAKE_STRENGTH)

    def test_interruptions_clear_slow_or_fast_time_and_allow_natural_falling(self):
        for kind in config.WEAPON_POSE_IMAGES:
            for phase in ("AIM", "DIVE"):
                for cause in ("hit", "death", "drop", "attack", "swap", "car"):
                    with self.subTest(kind=kind, phase=phase, cause=cause):
                        world = aim(kind)
                        player = world.player
                        if phase == "DIVE":
                            tap(world.controls, "combat_d")
                            world.step(config.FIXED_DT)
                        if cause in ("hit", "death"):
                            player.invincible = False
                            player.take_damage(20 if cause == "hit" else 500)
                        elif cause == "drop":
                            tap(world.controls, "weapon_interact")
                        elif cause == "attack":
                            tap(world.controls, "combat_a")
                        elif cause == "swap":
                            player.equip_weapon("steel_pipe" if kind == "combat_knife" else "combat_knife")
                        else:
                            player.hit_by_car(1)
                        world.step(config.FIXED_DT)
                        self.assertIsNone(player.weapon_leap_phase)
                        self.assertEqual(world.time_scale, 1)
                        self.assertLessEqual(player.jump_count, 2)
                        advance(world, 2)
                        self.assertTrue(player.grounded)

    def test_switching_away_and_back_to_d_preserves_height_velocity_and_jump_count(self):
        for kind in config.WEAPON_POSE_IMAGES:
            world = aim(kind)
            tap(world.controls, "combat_a")
            world.step(config.FIXED_DT)
            height, velocity = world.player.jump_height, world.player.vy
            tap(world.controls, "combat_d")
            world.step(config.FIXED_DT)
            scaled_dt = config.FIXED_DT * config.WEAPON_AIM_TIME_SCALE
            self.assertEqual(world.player.weapon_leap_phase, "AIM")
            self.assertAlmostEqual(world.player.vy, velocity - config.GRAVITY * scaled_dt)
            self.assertAlmostEqual(world.player.jump_height, height + world.player.vy * scaled_dt)
            self.assertEqual(world.player.jump_count, 2)

    def test_all_stage_corners_keep_aiming_and_diving_feet_inside_the_floor(self):
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
                    double_jump(world)
                    for key in ("combat_d", "left_shift", "left" if side < 0 else "right",
                                "down" if sy < 0 else "up"):
                        world.controls.press(key)
                    for step in range(60):
                        if step == 12:
                            tap(world.controls, "combat_d")
                        world.step(config.FIXED_DT)
                        self.assertTrue(world.stage.walkable.contains(player.x, player.ground_y,
                                                                     player.boundary_padding))
                        self.assertGreaterEqual(player.jump_height, 0)
                    self.assertEqual((world.stage_index, world.time_scale), (index, 1))

    def test_loading_pauses_aim_and_dive_and_f5_restores_normal_time(self):
        for kind in config.WEAPON_POSE_IMAGES:
            for phase in ("AIM", "DIVE", "LANDING"):
                world = aim(kind)
                player = world.player
                if phase != "AIM":
                    tap(world.controls, "combat_d")
                    world.step(config.FIXED_DT)
                if phase == "LANDING":
                    while not player.grounded:
                        world.step(config.FIXED_DT)
                before = (player.x, player.jump_height, player.vy, player.animation.elapsed, world.elapsed)
                world.pending_stage_index, world.stage_loading_remaining = 1, 2
                world.update(1.5)
                self.assertEqual((player.x, player.jump_height, player.vy,
                                  player.animation.elapsed, world.elapsed), before)
                tap(world.controls, "restart")
                world.update(config.FIXED_DT)
                self.assertIsNone(world.player.weapon_leap_phase)
                self.assertIsNone(world.player.weapon)
                self.assertTrue(world.player.grounded)
                self.assertEqual(world.time_scale, 1)

    def test_two_stage_d_and_enemy_motion_are_identical_at_different_render_rates(self):
        for kind in config.WEAPON_POSE_IMAGES:
            results = []
            for fps in (30, 60, 120, 144):
                world = equipped_world(kind)
                enemy = Enemy02(200, 1)
                world.enemies.append(enemy)
                double_jump(world)
                snapshots = []
                for keys in (("combat_d", "right"), ("left",), ("combat_d",), ()):
                    world.controls.release("right")
                    for key in keys:
                        tap(world.controls, key)
                    advance(world, 0.5, fps)
                    player = world.player
                    snapshots.append((player.x, player.ground_y, player.jump_height, player.vy,
                                      player.jump_count, player.weapon_leap_phase, player.state,
                                      enemy.x, enemy.animation.elapsed, world.elapsed))
                results.append(snapshots)
            self.assertTrue(all(result == results[0] for result in results))


if __name__ == "__main__":
    unittest.main()
