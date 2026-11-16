import unittest

import config
from drop_items import DropItem
from enemy import Enemy
from enemy02 import Enemy02
from effects import DamageNumber, HitEffect
from player import Player
from tests.helpers import advance, tap
from tests.test_strong_attacks import encounter
from traffic import Car, Traffic


class RaisePunchTests(unittest.TestCase):
    def test_prepare_slows_player_enemy_and_world_clocks_from_the_entry_tick(self):
        for enemy_type in (Enemy, Enemy02):
            world, target = encounter(enemy_type)
            mover = enemy_type(200, 1)
            world.enemies.append(mover)
            tap(world.controls, "combat_r")
            elapsed = world.elapsed
            advance(world, 0.5)
            simulated = 0.5 * config.R_RAISE_TIME_SCALE
            self.assertAlmostEqual(world.elapsed - elapsed, simulated)
            self.assertAlmostEqual(mover.x - 200, mover.run_speed * simulated)
            self.assertAlmostEqual(mover.animation.elapsed, simulated)
            self.assertAlmostEqual(world.player.animation.elapsed, simulated)
            self.assertEqual((world.time_scale, target.hp), (config.R_RAISE_TIME_SCALE, 200))
            self.assertIsNone(world.player.attack_box)

    def test_fresh_r_releases_one_fifty_damage_attack_and_restores_each_loadout(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for enemy_type in (Enemy, Enemy02):
                for side in (-1, 1):
                    world, enemy = encounter(enemy_type, side, weapon)
                    tap(world.controls, "combat_r")
                    advance(world, 0.1)
                    tap(world.controls, "combat_r")
                    elapsed_world = world.elapsed
                    world.step(config.FIXED_DT)
                    self.assertEqual((world.player.raise_punch_phase, enemy.hp), ("STRIKE", 150))
                    self.assertEqual(world.time_scale, 1)
                    self.assertAlmostEqual(world.elapsed - elapsed_world, config.FIXED_DT)
                    self.assertEqual(enemy.animation.row, 2)
                    elapsed = world.player.animation.elapsed
                    tap(world.controls, "combat_r")
                    world.step(config.FIXED_DT)
                    self.assertAlmostEqual(world.player.animation.elapsed, elapsed + config.FIXED_DT)
                    advance(world, 0.4)
                    self.assertEqual(enemy.hp, 150)
                    self.assertIsNone(world.player.raise_punch_phase)
                    self.assertIsNone(world.player.active_move)
                    self.assertEqual(world.player.sprite_image,
                                     config.WEAPON_POSE_IMAGES.get(weapon, config.PLAYER_IMAGE))

    def test_holding_r_waits_without_damage_and_a_new_press_after_ready_still_works(self):
        world, enemy = encounter()
        tap(world.controls, "combat_r")
        advance(world, 3)
        world.controls.press("combat_r")
        world.step(config.FIXED_DT)
        self.assertEqual((world.player.animation.frame, enemy.hp, world.time_scale),
                         (4, 200, config.R_RAISE_TIME_SCALE))
        self.assertEqual(world.player.raise_punch_phase, "RAISE")
        tap(world.controls, "combat_r")
        world.step(config.FIXED_DT)
        self.assertEqual(enemy.hp, 150)

    def test_interruptions_restore_normal_time_without_a_pending_r_hit(self):
        for cause in ("attack", "hit", "death", "car", "drop", "swap", "counter", "restart"):
            world, enemy = encounter(weapon="steel_pipe")
            world.stage.drop_items.clear()
            tap(world.controls, "combat_r")
            advance(world, 0.1)
            if cause == "attack":
                tap(world.controls, "combat_q")
            elif cause in ("hit", "death"):
                world.player.invincible = False
                world.player.take_damage(20 if cause == "hit" else 500)
            elif cause == "car":
                world.player.hit_by_car(1)
            elif cause == "drop":
                tap(world.controls, "weapon_interact")
            elif cause == "swap":
                world.player.equip_weapon("combat_knife")
            elif cause == "counter":
                enemy.start_attack()
                enemy.animation.elapsed = 2 / enemy.attack_fps
                tap(world.controls, "counter_h")
            else:
                tap(world.controls, "restart")
            world.update(config.FIXED_DT)
            self.assertIsNone(world.player.raise_punch_phase)
            self.assertEqual(world.time_scale, 1)
            self.assertEqual(enemy.hp, 200)

    def test_prepare_slows_gravity_items_effects_and_traffic_without_double_scaling(self):
        world, _ = encounter()
        player = world.player
        player.jump_height, player.vy, player.jump_count = 140, 100, 1
        reference = Player()
        reference.jump_height, reference.vy = player.jump_height, player.vy
        item = DropItem("steel_pipe", 500, 100, jump_height=200)
        effect, number = HitEffect(500, 200, 1), DamageNumber(500, 200, 10)
        world.stage.drop_items = [item]
        world.effects, world.damage_numbers = [effect], [number]
        world.stage.traffic = Traffic()
        car = Car(100, 1, config.CAR_SPEED_RANGE[0])
        world.stage.traffic.car = car
        tap(world.controls, "combat_r")
        for _ in range(60):
            world.step(config.FIXED_DT)
            reference.update_vertical(config.FIXED_DT * config.R_RAISE_TIME_SCALE)
        simulated = 0.5 * config.R_RAISE_TIME_SCALE
        for clock in (item.elapsed, effect.elapsed, number.elapsed, car.animation.elapsed,
                      player.animation.elapsed):
            self.assertAlmostEqual(clock, simulated)
        self.assertAlmostEqual(car.x - 100, car.speed * simulated)
        self.assertAlmostEqual(item.vy, -config.GRAVITY * simulated)
        self.assertAlmostEqual(player.jump_height, reference.jump_height)
        self.assertAlmostEqual(player.vy, reference.vy)
        tap(world.controls, "combat_r")
        world.step(config.FIXED_DT)
        self.assertEqual(world.time_scale, 1)
        self.assertAlmostEqual(effect.elapsed, simulated + config.FIXED_DT)

    def test_loading_uses_real_time_while_prepare_is_paused_and_f5_clears_the_scale(self):
        world, enemy = encounter()
        tap(world.controls, "combat_r")
        advance(world, 0.5)
        before = (world.player.animation.elapsed, enemy.animation.elapsed, world.elapsed)
        world.pending_stage_index, world.stage_loading_remaining = 1, 2
        tap(world.controls, "combat_r")
        world.update(0.5)
        self.assertEqual(world.stage_loading_remaining, 1.5)
        self.assertEqual((world.player.animation.elapsed, enemy.animation.elapsed, world.elapsed), before)
        self.assertFalse(world.controls.pressed)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertIsNone(world.player.raise_punch_phase)
        self.assertEqual(world.time_scale, 1)


if __name__ == "__main__":
    unittest.main()
