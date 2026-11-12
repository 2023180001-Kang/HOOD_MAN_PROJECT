import random
import unittest

import config
from collision import resolve_bodies
from enemy import Enemy
from spawn_manager import SpawnManager
from tests.helpers import advance, tap
from world import World


class EnemyTests(unittest.TestCase):
    def test_requested_batches_spawn_randomly_at_both_map_boundaries(self):
        spawner = SpawnManager(rng=random.Random(42))
        spawned = spawner.spawn(9, 3)
        boundaries = {config.ENEMY_HALF_WIDTH, config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH}
        self.assertEqual({enemy.x for enemy in spawned}, boundaries)
        self.assertEqual(len({id(enemy) for enemy in spawned}), 9)
        self.assertEqual(spawner.spawned_count, 9)
        for index, enemy in enumerate(spawned):
            self.assertEqual(enemy.spawned_at, 3)
            self.assertEqual(enemy.facing, 1 if enemy.x < config.START_X else -1)
            self.assertEqual(enemy.hp, 200)
            self.assertEqual(enemy.run_speed, config.ENEMY_RUN_SPEEDS[index % 4])
        next_batch = spawner.spawn(2, 5)
        self.assertEqual([enemy.run_speed for enemy in next_batch], [420, 480])
        self.assertEqual(spawner.spawned_count, 11)

    def test_no_automatic_spawns_and_requested_enemies_track_player(self):
        world = World()
        advance(world, 10)
        self.assertEqual(world.enemies, [])
        world.controls.press("spawn_4")
        world.update(1 / 60)
        self.assertEqual(len(world.enemies), 4)
        enemy = world.enemies[0]
        enemy.x = 600
        world.player.x = 200
        # A committed attack finishes before the next chase direction is chosen.
        advance(world, 1)
        self.assertEqual(enemy.facing, -1)
        self.assertLess(enemy.vx, 0)

    def test_each_digit_spawns_exactly_its_count_once_until_repressed(self):
        for count in range(1, 10):
            with self.subTest(count=count):
                world = World()
                action = f"spawn_{count}"
                world.controls.press(action)
                advance(world, 0.1)
                self.assertEqual(len(world.enemies), count)
                world.controls.press(action)
                advance(world, 0.1)
                self.assertEqual(len(world.enemies), count)
                tap(world.controls, action)
                world.update(1 / 60)
                self.assertEqual(len(world.enemies), count * 2)

    def test_simultaneous_different_digits_add_the_requested_counts(self):
        world = World()
        world.controls.press("spawn_2")
        world.controls.press("spawn_5")
        world.update(1 / 60)
        self.assertEqual(len(world.enemies), 7)
        self.assertEqual(world.spawner.spawned_count, 7)
        self.assertEqual(world.controls.pressed, set())

    def test_numeric_spawns_work_while_attacking_or_hit(self):
        for action in (None, "combat_a", "hit"):
            with self.subTest(action=action):
                world = World()
                if action == "hit":
                    world.player.take_damage(20)
                elif action is not None:
                    world.controls.press(action)
                world.controls.press("spawn_3")
                world.update(1 / 60)
                self.assertEqual(len(world.enemies), 3)

    def test_death_discards_spawn_presses_and_restart_clears_pending_requests(self):
        world = World()
        world.player.take_damage(500)
        for _ in range(2):
            tap(world.controls, "spawn_9")
            advance(world, 1)
            self.assertEqual(world.enemies, [])
            self.assertNotIn("spawn_9", world.controls.pressed)
        tap(world.controls, "spawn_9")
        world.controls.press("restart")
        world.update(1 / 60)
        advance(world, 1)
        self.assertEqual(world.enemies, [])
        tap(world.controls, "spawn_1")
        world.update(1 / 60)
        self.assertEqual(len(world.enemies), 1)
        self.assertEqual(world.enemies[0].run_speed, 360)

    def test_enemies_overlap_each_other_without_separation(self):
        world = World()
        world.enemies = [Enemy(500), Enemy(500)]
        advance(world, 0.5)
        self.assertEqual(world.enemies[0].x, world.enemies[1].x)
        self.assertTrue(world.enemies[0].body.overlaps(world.enemies[1].body))
        world.enemies[0].animation.elapsed = 99
        self.assertNotEqual(world.enemies[0].animation.elapsed,
                            world.enemies[1].animation.elapsed)

    def test_body_blocks_player_but_can_be_jumped_over(self):
        world = World()
        world.enemies = [Enemy(config.START_X + 100, facing=-1)]
        world.controls.press("right")
        world.controls.press("left_shift")
        advance(world, 0.2)
        self.assertFalse(world.player.body.overlaps(world.enemies[0].body))
        self.assertLess(world.player.x, world.enemies[0].x)
        world.player.y = config.GROUND_Y + config.ENEMY_HEIGHT + 40
        world.player.vy = 300
        advance(world, 0.5)
        self.assertGreater(world.player.x, world.enemies[0].x)

    def test_crowd_and_boundary_collisions_do_not_leave_penetration(self):
        for x in (config.PLAYER_HALF_WIDTH, config.START_X,
                  config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH):
            world = World()
            world.player.x = world.player.previous_x = x
            world.enemies = [Enemy(x, 1), Enemy(x, -1), Enemy(x, 1), Enemy(x, -1)]
            resolve_bodies(world.player, world.enemies)
            self.assertGreaterEqual(world.player.x, config.PLAYER_HALF_WIDTH)
            self.assertLessEqual(world.player.x, config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)
            for enemy in world.enemies:
                self.assertFalse(world.player.body.overlaps(enemy.body))
                self.assertGreaterEqual(enemy.x, config.ENEMY_HALF_WIDTH)
                self.assertLessEqual(enemy.x, config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH)


if __name__ == "__main__":
    unittest.main()
