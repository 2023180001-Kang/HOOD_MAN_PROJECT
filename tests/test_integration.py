import json
import random
import unittest

import config
from collision import bodies_overlap
from tests.helpers import advance, tap
from world import World


class IntegrationTests(unittest.TestCase):
    def test_normal_spawn_chase_attack_death_and_restart_cycle(self):
        world = World(rng=random.Random(1))
        world.controls.press("spawn_4")
        advance(world, 8)
        self.assertEqual(len(world.enemies), 4)
        self.assertGreater(world.player.hp, 0)
        self.assertLess(world.player.hp, config.MAX_HP)
        advance(world, 50)
        self.assertEqual(world.player.hp, 0)
        self.assertEqual(world.player.state, "DEAD")
        self.assertTrue(all(enemy.knockback_started for enemy in world.enemies))
        self.assertTrue(all(enemy.vx == 0 for enemy in world.enemies))
        tap(world.controls, "restart")
        world.update(1 / 60)
        self.assertEqual(world.player.hp, 500)
        self.assertEqual(world.enemies, [])
        world.controls.press("spawn_4")
        world.update(1 / 60)
        self.assertEqual(len(world.enemies), 4)

    def test_combat_and_spawning_are_identical_at_different_render_rates(self):
        results = []
        for fps in (30, 60, 120, 144):
            world = World(rng=random.Random(1))
            world.controls.press("spawn_4")
            advance(world, 18, fps)
            results.append((world.player.hp, world.player.state,
                            [(enemy.x, enemy.state, enemy.animation.frame)
                             for enemy in world.enemies]))
        for result in results[1:]:
            self.assertEqual(result, results[0])

    def test_variable_inputs_and_restarts_preserve_world_invariants(self):
        rng = random.Random(20261110)
        world = World(rng=random.Random(20261110))
        keys = ("left", "right", "left_shift", "jump")
        for frame in range(3600):
            if frame % 13 == 0:
                key = rng.choice(keys)
                if key in world.controls.held:
                    world.controls.release(key)
                else:
                    world.controls.press(key)
            if frame % 900 == 899:
                tap(world.controls, "restart")
            elif frame % 180 == 0:
                tap(world.controls, "spawn_3")
            world.update(1 / 60)
            self.assertGreaterEqual(world.player.hp, 0)
            self.assertLessEqual(world.player.hp, 500)
            self.assertGreaterEqual(world.player.y, config.GROUND_Y)
            self.assertGreaterEqual(world.player.x, config.PLAYER_HALF_WIDTH)
            self.assertLessEqual(world.player.x, config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)
            self.assertEqual(len(world.enemies), world.spawner.spawned_count)
            self.assertGreaterEqual(world.camera.render_x, 0)
            self.assertLessEqual(world.camera.render_x,
                                 config.WORLD_WIDTH - config.SCREEN_WIDTH)
            for enemy in world.enemies:
                self.assertGreaterEqual(enemy.x, config.ENEMY_HALF_WIDTH)
                self.assertLessEqual(enemy.x, config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH)
                if world.player.alive:
                    self.assertFalse(bodies_overlap(world.player, enemy))

    def test_long_frame_is_bounded_and_does_not_repeat_numeric_spawns(self):
        world = World()
        world.controls.press("right")
        world.controls.press("spawn_9")
        world.update(5)
        self.assertAlmostEqual(world.elapsed, config.MAX_FRAME_DT)
        self.assertEqual(world.spawner.spawned_count, 9)
        self.assertLess(world.player.x - config.START_X, 20)
        self.assertTrue(all(enemy.spawned_at == config.FIXED_DT for enemy in world.enemies))
        advance(world, 0.1)
        self.assertEqual(world.spawner.spawned_count, 9)

    def test_generated_clips_stay_inside_original_sprite_sheets(self):
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            metadata = json.load(file)
        row_counts = {config.PLAYER_IMAGE: 6, config.ENEMY_IMAGE: 6, config.COMBAT_IMAGE: 4,
                      config.COUNTER_PLAYER_IMAGE: 4, config.COUNTER_ENEMY_IMAGE: 4}
        self.assertEqual(set(metadata), set(row_counts))
        for name, rows in metadata.items():
            self.assertTrue((config.ROOT / name).is_file())
            self.assertEqual(len(rows), row_counts[name])
            for row_index, row in enumerate(rows):
                self.assertEqual(len(row), 8)
                for col_index, frame in enumerate(row):
                    left, bottom, width, height = frame["clip"]
                    self.assertGreater(width, 0)
                    self.assertGreater(height, 0)
                    self.assertGreaterEqual(left, col_index * 256)
                    self.assertLessEqual(left + width, (col_index + 1) * 256)
                    self.assertGreaterEqual(bottom, (row_counts[name] - 1 - row_index) * 256)
                    self.assertLessEqual(bottom + height, (row_counts[name] - row_index) * 256)

    def test_counter_clips_preserve_the_shared_ground_anchor_and_airborne_poses(self):
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            metadata = json.load(file)
        for name in (config.COUNTER_PLAYER_IMAGE, config.COUNTER_ENEMY_IMAGE):
            for row_index, row in enumerate(metadata[name]):
                row_bottom = (3 - row_index) * 256
                anchors = {256 - (tile["clip"][1] - row_bottom) + tile["offset_y"]
                           for tile in row}
                self.assertEqual(len(anchors), 1)
                self.assertTrue(all(tile["offset_y"] >= 0 for tile in row))
        self.assertGreaterEqual(metadata[config.COUNTER_ENEMY_IMAGE][3][2]["offset_y"], 50)


if __name__ == "__main__":
    unittest.main()
