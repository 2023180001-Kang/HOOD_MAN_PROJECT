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
        world.update(config.FIXED_DT)
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
        self.assertEqual(len(world.enemies), 4)
        world.controls.press("spawn_4")
        world.update(config.FIXED_DT)
        self.assertEqual(len(world.enemies), 8)

    def test_combat_and_spawning_are_identical_at_different_render_rates(self):
        results = []
        for fps in (30, 60, 120, 144):
            world = World(rng=random.Random(1))
            world.controls.press("spawn_4")
            world.update(config.FIXED_DT)
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
        self.assertEqual(world.stage_index, 0)
        self.assertAlmostEqual(world.elapsed, config.MAX_FRAME_DT)
        self.assertEqual(world.spawner.spawned_count, 13)
        self.assertLess(world.player.x - config.START_X, 20)
        self.assertTrue(all(enemy.spawned_at == config.FIXED_DT for enemy in world.enemies[4:]))
        advance(world, 0.1)
        self.assertEqual(world.spawner.spawned_count, 13)

    def test_generated_clips_stay_inside_original_sprite_sheets(self):
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            metadata = json.load(file)
        row_counts = {config.PLAYER_IMAGE: 6, config.PLAYER_PISTOL_IMAGE: 12, config.PLAYER_STEEL_CLUB_IMAGE: 8,
                      config.PLAYER_AXE_IMAGE: 8, config.PLAYER_RIFLE_IMAGE: 12,
                      config.PLAYER_SWORD_IMAGE: 10, config.PLAYER_SHIELD_IMAGE: 9, config.ENEMY_IMAGE: 6, config.ENEMY02_IMAGE: 7,
                      config.AXE_ENEMY_IMAGE: 7, config.AXE_ENEMY_UNARMED_IMAGE: 7,
                      config.SHIELD_SOLDIER_IMAGE: 7, config.SWORD_ENEMY_IMAGE: 7,
                      config.RESEARCHER_IMAGE: 7, config.RESEARCHER_BULLET_IMAGE: 1,
                      config.AR_SOLDIER_IMAGE: 7, config.RIFLE_BULLET_IMAGE: 1, config.SNIPER_IMAGE: 7,
                      config.FINAL_BOSS_IMAGE: 12, config.COMBAT_IMAGE: 4,
                      config.STRONG_ATTACK_IMAGE: 3, config.STRONG_HIT_IMAGE: 5,
                      config.PLAYER_CAR_HIT_IMAGE: 1, config.ENEMY_CAR_HIT_IMAGE: 1,
                      **{name: config.WEAPON_SHEET_ROWS[kind]
                         for kind, name in config.WEAPON_POSE_IMAGES.items()}}
        self.assertEqual(set(metadata), set(row_counts))
        for name, rows in metadata.items():
            cell_width, cell_height = (384, 384) if name == config.ENEMY02_IMAGE else (256, 256)
            self.assertTrue((config.ROOT / name).is_file())
            self.assertEqual(len(rows), row_counts[name])
            for row_index, row in enumerate(rows):
                self.assertEqual(len(row), 8)
                for col_index, frame in enumerate(row):
                    left, bottom, width, height = frame["clip"]
                    self.assertGreater(width, 0)
                    self.assertGreater(height, 0)
                    self.assertGreaterEqual(left, col_index * cell_width)
                    self.assertLessEqual(left + width, (col_index + 1) * cell_width)
                    self.assertGreaterEqual(bottom, (row_counts[name] - 1 - row_index) * cell_height)
                    self.assertLessEqual(bottom + height, (row_counts[name] - row_index) * cell_height)

    def test_enemy02_lift_matches_the_source_feet_without_a_second_render_offset(self):
        from PIL import Image

        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            rows = json.load(file)[config.ENEMY02_IMAGE]
        with Image.open(config.ROOT / config.ENEMY02_IMAGE) as image:
            self.assertEqual(image.size, (3072, 2688))
            feet = [image.crop((col * 384, 4 * 384, (col + 1) * 384, 5 * 384)).getbbox()[3]
                    for col in range(8)]
        self.assertEqual([frame["jump_height"] for frame in rows[4]],
                         [max(feet) - foot for foot in feet])
        self.assertEqual([frame["jump_height"] for frame in rows[4]], [0, 0, 48, 26, 0, 0, 0, 0])
        self.assertTrue(all(frame.get("offset_y", 0) == 0 for frame in rows[4]))

    def test_sword_enemy_landing_sparks_and_fallen_blade_keep_the_feet_aligned(self):
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            rows = json.load(file)[config.SWORD_ENEMY_IMAGE]
        leap, death = rows[4], rows[6]
        self.assertEqual([tile.get("offset_y", 0) for tile in leap], [0, 0, 0, 0, 0, 0, -4, 0])
        self.assertEqual([tile["offset_y"] for tile in death], [0, 0, 0, 0, -8, -8, -12, -12])

    def test_weapon_airborne_attack_clips_do_not_double_add_the_physical_jump(self):
        from PIL import Image

        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            metadata = json.load(file)
        for kind, row in config.WEAPON_AIRBORNE_ROWS.items():
            name = config.WEAPON_POSE_IMAGES[kind]
            with Image.open(config.ROOT / name) as image:
                feet = [image.crop((col * 256, (row - 1) * 256,
                                    (col + 1) * 256, row * 256)).getbbox()[3]
                        for col in range(8)]
            self.assertEqual([tile["jump_height"] for tile in metadata[name][row - 1]],
                             [max(feet) - foot for foot in feet])
            self.assertGreater(max(tile["jump_height"] for tile in metadata[name][row - 1]), 25)
            self.assertTrue(all(tile.get("offset_y", 0) == 0 for tile in metadata[name][row - 1]))

    def test_strong_attack_and_hit_sheets_preserve_source_airborne_offsets(self):
        from PIL import Image

        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            metadata = json.load(file)
        for name, height in ((config.STRONG_ATTACK_IMAGE, 768), (config.STRONG_HIT_IMAGE, 1280)):
            with Image.open(config.ROOT / name) as image:
                self.assertEqual((image.size, image.mode), ((2048, height), "RGBA"))
                for row_index, row in enumerate(metadata[name]):
                    feet = [image.crop((col * 256, row_index * 256,
                                        (col + 1) * 256, (row_index + 1) * 256)).getbbox()[3]
                            for col in range(8)]
                    self.assertEqual([tile["offset_y"] for tile in row],
                                     [max(feet) - foot for foot in feet])
            self.assertTrue(any(tile["offset_y"] >= 20 for row in metadata[name] for tile in row))


if __name__ == "__main__":
    unittest.main()
