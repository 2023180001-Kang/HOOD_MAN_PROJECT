import unittest

import config
from collision import resolve_bodies
from enemy import Enemy
from spawn_manager import SpawnManager
from tests.helpers import advance
from world import World


class EnemyTests(unittest.TestCase):
    def test_four_distinct_spawns_at_map_boundaries(self):
        spawner = SpawnManager()
        self.assertEqual(spawner.update(0.99), [])
        spawned = []
        for index, at in enumerate((1, 3, 5, 7)):
            batch = spawner.update(at)
            self.assertEqual(len(batch), 1)
            enemy = batch[0]
            expected = (config.ENEMY_HALF_WIDTH if index % 2 == 0
                        else config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH)
            self.assertEqual(enemy.x, expected)
            self.assertEqual(enemy.spawned_at, at)
            spawned.append(enemy)
        self.assertEqual(len({id(enemy) for enemy in spawned}), 4)
        self.assertEqual(spawner.update(1000), [])

    def test_world_spawns_on_schedule_and_tracks_player(self):
        world = World()
        advance(world, 7.1)
        self.assertEqual(len(world.enemies), 4)
        enemy = world.enemies[0]
        world.player.x = 200
        advance(world, 0.1)
        self.assertEqual(enemy.facing, -1)
        self.assertLess(enemy.vx, 0)

    def test_enemies_overlap_each_other_without_separation(self):
        world = World(spawn_schedule=())
        world.enemies = [Enemy(500), Enemy(500)]
        advance(world, 0.5)
        self.assertEqual(world.enemies[0].x, world.enemies[1].x)
        self.assertTrue(world.enemies[0].body.overlaps(world.enemies[1].body))
        world.enemies[0].animation.elapsed = 99
        self.assertNotEqual(world.enemies[0].animation.elapsed,
                            world.enemies[1].animation.elapsed)

    def test_body_blocks_player_but_can_be_jumped_over(self):
        world = World(spawn_schedule=())
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
            world = World(spawn_schedule=())
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
