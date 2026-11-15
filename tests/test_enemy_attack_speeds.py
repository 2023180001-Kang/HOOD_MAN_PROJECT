import random
import unittest

import config
from enemy import Enemy
from tests.helpers import advance
from world import World


class EnemyAttackSpeedTests(unittest.TestCase):
    def test_spawn_rates_are_unique_across_batches_and_all_stages(self):
        world = World(rng=random.Random(17))
        enemies = []
        for _ in range(2):
            for stage in world.stages:
                enemies.extend(stage.spawner.spawn(100, 0))
        speeds = [enemy.attack_speed for enemy in enemies]
        self.assertEqual(len(set(speeds)), 200 * len(world.stages))
        low, high = config.ENEMY_ATTACK_SPEED_RANGE
        self.assertTrue(all(low < speed < high for speed in speeds))
        self.assertEqual([stage.spawner.spawned_count for stage in world.stages],
                          [200] * len(world.stages))
        for enemy in enemies:
            self.assertAlmostEqual(enemy.attack_fps, 12 * enemy.attack_speed)
            self.assertAlmostEqual(enemy.attack_interval, 1 / enemy.attack_speed)

    def test_each_enemy_has_an_independent_attack_clock_and_definitions(self):
        original = dict(config.ENEMY_ANIMATIONS)
        slow = Enemy(config.START_X + 80, -1, attack_speed=0.8)
        fast = Enemy(config.START_X + 80, -1, attack_speed=1.4)
        for enemy in (slow, fast):
            enemy.animation.set_state("ATTACK")
            enemy.animation.update(0.25)
        self.assertEqual((slow.animation.frame, fast.animation.frame), (2, 4))
        slow.animation.update(0.3)
        fast.animation.update(0.3)
        self.assertFalse(slow.animation.finished)
        self.assertTrue(fast.animation.finished)
        self.assertIsNot(slow.animation.definitions, fast.animation.definitions)
        self.assertEqual(config.ENEMY_ANIMATIONS, original)
        self.assertEqual(slow.animation.definitions["HIT"], original["HIT"])
        self.assertEqual(fast.animation.definitions["WALK"], original["WALK"])

    def test_real_attack_windup_and_repeat_interval_follow_the_assigned_rate(self):
        timings = []
        for speed in (0.8, 1.4):
            world = World()
            enemy = Enemy(world.player.x + 80, -1, attack_speed=speed)
            world.enemies = [enemy]
            starts, hits = [], []
            for _ in range(3 * 120):
                old_state, old_hit = enemy.state, enemy.has_hit
                world.step(config.FIXED_DT)
                if enemy.state == "ATTACK" and old_state != "ATTACK":
                    starts.append(world.elapsed)
                if enemy.state == "ATTACK" and enemy.has_hit and not old_hit:
                    hits.append(world.elapsed)
            self.assertGreaterEqual(len(starts), 3)
            self.assertEqual(world.player.hp, 500 - len(hits) * config.ENEMY_DAMAGE)
            for first, second in zip(starts, starts[1:]):
                self.assertGreaterEqual(second - first + 1e-9, enemy.attack_interval)
                self.assertLess(second - first, enemy.attack_interval + 2 * config.FIXED_DT)
            timings.append((hits[0], starts[1] - starts[0]))
        self.assertLess(timings[1][0], timings[0][0])
        self.assertLess(timings[1][1], timings[0][1])

    def test_state_changes_and_inactive_map_do_not_reroll_the_rate(self):
        world = World()
        enemy = world.spawner.spawn(1, 0)[0]
        world.enemies = [enemy]
        expected = enemy.attack_speed, enemy.attack_fps, enemy.attack_interval
        enemy.take_damage(20)
        advance(world, 0.8)
        enemy.knockback(world.player.x, world.player.ground_y)
        advance(world, 0.8)
        world.stage_index = 1
        advance(world, 1)
        world.stage_index = 0
        self.assertIs(world.enemies[0], enemy)
        self.assertEqual((enemy.attack_speed, enemy.attack_fps, enemy.attack_interval), expected)

    def test_f5_resets_the_global_rate_sequence_and_keeps_run_profiles(self):
        world = World()
        world.controls.press("spawn_9")
        world.update(config.FIXED_DT)
        speeds = [enemy.attack_speed for enemy in world.enemies]
        running = [enemy.run_speed for enemy in world.enemies]
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertEqual(world.enemies, [])
        world.controls.press("spawn_9")
        world.update(config.FIXED_DT)
        self.assertEqual([enemy.attack_speed for enemy in world.enemies], speeds)
        self.assertEqual([enemy.run_speed for enemy in world.enemies], running)

    def test_spawned_combat_is_identical_across_render_rates(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world = World(rng=random.Random(73))
            world.player.invincible = True
            world.controls.press("spawn_9")
            world.update(config.FIXED_DT)
            advance(world, 7, fps)
            outcomes.append([(enemy.attack_speed, enemy.x, enemy.ground_y,
                              enemy.state, enemy.animation.frame, enemy.has_hit)
                             for enemy in world.enemies])
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
