import unittest

import config
from enemy import Enemy
from enemy02 import Enemy02
from tests.helpers import advance, tap
from tests.test_strong_attacks import encounter


class RaisePunchTests(unittest.TestCase):
    def test_only_the_prepare_animation_is_slow_and_the_world_keeps_running(self):
        for enemy_type in (Enemy, Enemy02):
            world, target = encounter(enemy_type)
            mover = enemy_type(200, 1)
            world.enemies.append(mover)
            tap(world.controls, "combat_r")
            elapsed = world.elapsed
            advance(world, 0.5)
            self.assertAlmostEqual(world.elapsed - elapsed, 0.5)
            self.assertAlmostEqual(mover.x - 200, mover.run_speed * 0.5)
            self.assertAlmostEqual(world.player.animation.elapsed, 0.5 * config.R_RAISE_SPEED)
            self.assertEqual((world.time_scale, target.hp), (1, 200))
            self.assertIsNone(world.player.attack_box)

    def test_fresh_r_releases_one_fifty_damage_attack_and_restores_each_loadout(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for enemy_type in (Enemy, Enemy02):
                for side in (-1, 1):
                    world, enemy = encounter(enemy_type, side, weapon)
                    tap(world.controls, "combat_r")
                    advance(world, 0.1)
                    tap(world.controls, "combat_r")
                    world.step(config.FIXED_DT)
                    self.assertEqual((world.player.raise_punch_phase, enemy.hp), ("STRIKE", 150))
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
        self.assertEqual((world.player.animation.frame, enemy.hp, world.time_scale), (4, 200, 1))
        self.assertEqual(world.player.raise_punch_phase, "RAISE")
        tap(world.controls, "combat_r")
        world.step(config.FIXED_DT)
        self.assertEqual(enemy.hp, 150)

    def test_other_attacks_damage_and_f5_cancel_the_raised_punch(self):
        for cause in ("attack", "hit", "restart"):
            world, enemy = encounter()
            tap(world.controls, "combat_r")
            advance(world, 0.1)
            if cause == "attack":
                tap(world.controls, "combat_q")
            elif cause == "hit":
                world.player.invincible = False
                world.player.take_damage(20)
            else:
                tap(world.controls, "restart")
            world.update(config.FIXED_DT)
            self.assertIsNone(world.player.raise_punch_phase)
            self.assertEqual(world.time_scale, 1)
            self.assertEqual(enemy.hp, 200)


if __name__ == "__main__":
    unittest.main()
