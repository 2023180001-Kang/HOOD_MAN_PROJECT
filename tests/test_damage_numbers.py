import unittest

import config
from combat import MOVES
from enemy import Enemy
from tests.helpers import advance, tap
from world import World


def target(world, offset=80):
    enemy = Enemy(world.player.x + offset, facing=-1 if offset > 0 else 1)
    enemy.cooldown = 100
    world.enemies.append(enemy)
    return enemy


class DamageNumberTests(unittest.TestCase):
    def test_each_attack_reports_hp_loss_once_and_a_new_swing_can_report_again(self):
        for key, damage in zip("asdf", (10, 40, 50, 60)):
            with self.subTest(key=key):
                world = World()
                enemy = target(world)
                world.controls.press(f"combat_{key}")
                advance(world, 4 / MOVES[f"combat_{key}"].fps)
                self.assertEqual(enemy.hp, 200 - damage)
                self.assertEqual([number.damage for number in world.damage_numbers], [damage])
                first = world.damage_numbers[0]
                advance(world, 0.15)
                self.assertEqual(world.damage_numbers, [first])
                advance(world, 0.35)
                self.assertEqual(world.damage_numbers, [])
                tap(world.controls, f"combat_{key}")
                advance(world, 4 / MOVES[f"combat_{key}"].fps)
                self.assertEqual(enemy.hp, 200 - damage * 2)
                self.assertEqual([number.damage for number in world.damage_numbers], [damage])
                self.assertIsNot(world.damage_numbers[0], first)

    def test_misses_failed_counters_dead_targets_and_enemy_attacks_do_not_report_numbers(self):
        cases = ((-80, 0, False, "a"), (500, 0, False, "a"),
                 (80, 300, False, "a"), (80, 0, True, "a"), (80, 0, False, "h"))
        for offset, height, dead, key in cases:
            with self.subTest(offset=offset, height=height, dead=dead, key=key):
                world = World()
                enemy = target(world, offset)
                enemy.y += height
                if dead:
                    enemy.take_damage(200)
                world.controls.press(f"counter_{key}" if key == "h" else f"combat_{key}")
                advance(world, 0.3)
                self.assertEqual(world.damage_numbers, [])
        world = World()
        enemy = target(world)
        enemy.animation.set_state("ATTACK")
        enemy.animation.elapsed = 4 / config.ENEMY_ANIMATIONS["ATTACK"][1]
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 480)
        self.assertEqual(world.damage_numbers, [])

    def test_multi_target_attack_keeps_independent_numbers_at_each_enemy(self):
        world = World()
        enemies = [target(world, offset) for offset in (80, 95, 110)]
        world.controls.press("combat_s")
        advance(world, 0.175)
        self.assertEqual([enemy.hp for enemy in enemies], [160, 160, 160])
        self.assertEqual([number.damage for number in world.damage_numbers], [40, 40, 40])
        self.assertEqual([number.x for number in world.damage_numbers],
                         [enemy.x for enemy in enemies])

    def test_lethal_hit_reports_remaining_hp_and_expires_even_after_player_death(self):
        world = World()
        enemy = target(world)
        enemy.hp = 10
        world.controls.press("combat_f")
        advance(world, 4 / MOVES["combat_f"].fps)
        self.assertFalse(enemy.alive)
        self.assertEqual([number.damage for number in world.damage_numbers], [10])
        advance(world, 0.3)
        self.assertEqual(len(world.damage_numbers), 1)
        world.player.take_damage(500)
        advance(world, 0.2)
        self.assertEqual(world.damage_numbers, [])

    def test_numbers_pause_on_inactive_maps_and_restart_clears_both_maps(self):
        world = World()
        target(world)
        world.controls.press("combat_a")
        advance(world, 0.175)
        first = world.damage_numbers[0]
        elapsed = first.elapsed
        world.stage_index = 1
        advance(world, 0.5)
        self.assertEqual(world.damage_numbers, [])
        self.assertEqual(first.elapsed, elapsed)
        target(world)
        world.controls.press("combat_d")
        advance(world, 4 / MOVES["combat_d"].fps)
        self.assertEqual([number.damage for number in world.damage_numbers], [50])
        self.assertEqual(first.elapsed, elapsed)
        world.stage_index = 0
        self.assertIs(world.damage_numbers[0], first)
        advance(world, 0.025)
        self.assertGreater(first.elapsed, elapsed)
        world.controls.press("restart")
        world.update(1 / 60)
        self.assertTrue(all(stage.damage_numbers == [] for stage in world.stages))

    def test_rise_and_expiry_are_identical_across_render_rates(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world = World()
            enemy = target(world)
            world.controls.press("combat_s")
            advance(world, 0.5, fps)
            self.assertEqual(len(world.damage_numbers), 1)
            number = world.damage_numbers[0]
            self.assertGreater(number.display_y, number.y)
            outcomes.append((enemy.hp, number.damage, number.x, number.display_y, number.elapsed))
            advance(world, 0.4, fps)
            self.assertEqual(world.damage_numbers, [])
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))

    def test_number_stays_at_hit_position_when_actor_or_camera_moves(self):
        world = World()
        enemy = target(world)
        world.controls.press("combat_a")
        advance(world, 0.175)
        number = world.damage_numbers[0]
        origin = (number.x, number.y)
        enemy.x += 100
        enemy.y += 100
        world.camera.shake()
        world.camera.update(0.05, world.player.x + 400)
        world.step(config.FIXED_DT)
        self.assertEqual((number.x, number.y), origin)
        self.assertGreater(number.display_y, number.y)


if __name__ == "__main__":
    unittest.main()
