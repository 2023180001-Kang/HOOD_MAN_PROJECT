import hashlib
import random
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import config
from assets import Assets
from enemy import Enemy
from tests.helpers import advance, tap
from tests.helpers import ManualSpawnWorld as World


class SecondAlleyTests(unittest.TestCase):
    def test_expanded_background_loads_and_old_alley_is_archived_byte_identically(self):
        self.assertEqual(config.SECOND_STAGE_IMAGE, "newStage-2_floor300_1672x941.png")
        self.assertEqual(config.ARCHIVED_SECOND_STAGE_IMAGE, "before_sheets/newStage-2.png")
        self.assertEqual(config.STAGE_IMAGES[1], config.SECOND_STAGE_IMAGE)
        hashes = {
            config.SECOND_STAGE_IMAGE: "2ecf70e60d35d051ed09cc3d70b107b743730acc2356c38eb14cae892c27eaa1",
            config.ARCHIVED_SECOND_STAGE_IMAGE: "4fdc858f111058ce6160a615a7e4f527f23e13236c77f8425a4953fd289d468d",
        }
        for name, digest in hashes.items():
            path = config.ROOT / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with Image.open(path) as image:
                self.assertEqual(image.size, (1672, 941))
                self.assertEqual(image.mode, "RGBA" if name == config.SECOND_STAGE_IMAGE else "RGB")
        self.assertFalse((config.ROOT / "newStage-2.png").exists())
        with patch("pico2d.load_image", return_value=Mock()), patch("pico2d.load_font"):
            assets = Assets()
        self.assertIn(config.SECOND_STAGE_IMAGE, assets.images)
        self.assertNotIn(config.ARCHIVED_SECOND_STAGE_IMAGE, assets.images)
        self.assertNotIn("newStage-2.png", assets.images)

    def test_floor_covers_every_tile_row_below_the_step_bases_to_the_image_bottom(self):
        stage = World().stages[1]
        self.assertEqual(stage.walkable.bounds, (0, -44, 2560, 239))
        anchor = config.STAGE_GROUND_ANCHORS.get(stage.image_name, config.STAGE_GROUND_Y)
        source_world_top = config.GROUND_Y - anchor + config.STAGE_IMAGE_HEIGHT
        self.assertEqual((config.STAGE_SCALE, anchor, source_world_top), (1, 144, 897))
        self.assertEqual((source_world_top - stage.walkable.bounds[3],
                          source_world_top - stage.walkable.bounds[1]), (658, 941))
        self.assertEqual(stage.floor_areas, (stage.walkable,))
        self.assertIsNone(stage.upper_walkable)
        self.assertEqual((stage.stairs, stage.doors), ([], []))
        self.assertIsNone(stage.traffic)
        self.assertIs(stage.spawn_area, stage.walkable)
        self.assertIs(stage.drop_spawn_area, stage.walkable)
        for x in (68, 300, 1280, 1490, 1672, 2260, 2492):
            for source_y in range(658, 942):
                self.assertTrue(stage.walkable.contains(x, source_world_top - source_y, 68))
        self.assertFalse(stage.walkable.contains(1280, -44.01, 68))
        self.assertFalse(stage.walkable.contains(1490, 239.01, 68))

    def test_all_loadouts_walk_and_run_to_all_four_expanded_floor_corners(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for running in (False, True):
                for side in (-1, 1):
                    for depth in (-1, 1):
                        with self.subTest(weapon=weapon, running=running, side=side, depth=depth):
                            world = World()
                            world.select_stage(1)
                            player = world.player
                            player.equip_weapon(weapon)
                            player.x = player.previous_x = 300 if side < 0 else 2260
                            world.controls.press("left" if side < 0 else "right")
                            world.controls.press("down" if depth < 0 else "up")
                            if running:
                                world.controls.press("left_shift")
                            advance(world, 1.5)
                            self.assertEqual((player.x, player.ground_y, player.floor, player.jump_height),
                                             (68 if side < 0 else 2492, -44 if depth < 0 else 239, 0, 0))
                            self.assertTrue(player.grounded)
                            self.assertIsNone(player.staircase)
                            self.assertGreaterEqual(player.y - world.camera.render_y, 0)

    def test_both_depth_edges_keep_double_jumps_and_weapon_drop_pickup_on_the_floor(self):
        for depth in (-44, 239):
            for weapon in config.WEAPON_POSE_IMAGES:
                with self.subTest(depth=depth, weapon=weapon):
                    world = World()
                    world.select_stage(1)
                    player = world.player
                    player.ground_y = player.previous_ground_y = depth
                    world.controls.press("up" if depth > 0 else "down")
                    world.controls.press("left_shift")
                    world.controls.press("jump")
                    advance(world, 0.05)
                    tap(world.controls, "jump")
                    advance(world, 1.5)
                    self.assertTrue(player.grounded)
                    self.assertEqual((player.ground_y, player.floor, player.jump_height), (depth, 0, 0))
                    self.assertIsNone(player.staircase)
                    world.controls.held.clear()
                    world.stage.drop_items.clear()
                    player.equip_weapon(weapon)
                    tap(world.controls, "weapon_interact")
                    world.step(config.FIXED_DT)
                    self.assertIsNone(player.weapon)
                    item = world.stage.drop_items[0]
                    advance(world, 1)
                    self.assertTrue(item.grounded)
                    self.assertTrue(world.stage.drop_spawn_area.contains(item.x, item.ground_y))
                    player.x, player.ground_y = item.x, item.ground_y
                    tap(world.controls, "weapon_interact")
                    world.step(config.FIXED_DT)
                    self.assertEqual(player.weapon, weapon)

    def test_basic_enemies_items_pursuit_revisit_and_f5_use_the_expanded_floor(self):
        world = World(rng=random.Random(41), item_rng=random.Random(23))
        world.select_stage(1)
        stage = world.stage
        self.assertEqual(world.enemies, [])
        self.assertEqual(len(stage.drop_items), 15)
        self.assertTrue(all(item.floor == 0 and stage.walkable.contains(item.x, item.ground_y)
                            for item in stage.drop_items))
        self.assertTrue(any(item.ground_y < 56 for item in stage.drop_items))
        self.assertTrue(any(item.ground_y > 116 for item in stage.drop_items))
        tap(world.controls, "spawn_9")
        world.step(config.FIXED_DT)
        self.assertEqual((len(world.enemies), world.spawner.spawned_count), (9, 9))
        self.assertTrue(all(type(enemy) is Enemy and enemy.hp == 200 and enemy.attack_damage == 20
                            and stage.walkable.contains(enemy.x, enemy.ground_y, 88)
                            for enemy in world.enemies))
        self.assertTrue(any(enemy.ground_y < 56 for enemy in world.enemies))
        self.assertTrue(any(enemy.ground_y > 116 for enemy in world.enemies))
        first, items = world.enemies[0], stage.drop_items
        first.take_damage(40)
        snapshot = first.x, first.ground_y, first.animation.elapsed
        world.select_stage(0)
        advance(world, 1)
        world.select_stage(1)
        self.assertIs(world.stage, stage)
        self.assertIs(world.enemies[0], first)
        self.assertIs(stage.drop_items, items)
        self.assertEqual((first.hp, stage.spawner.spawned_count), (160, 9))
        self.assertEqual((first.x, first.ground_y, first.animation.elapsed), snapshot)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertEqual(world.stage_index, 0)
        self.assertEqual(world.stages[1].image_name, config.SECOND_STAGE_IMAGE)
        self.assertEqual(world.stages[1].walkable.bounds, (0, -44, 2560, 239))
        self.assertEqual((world.stages[1].enemies, world.stages[1].spawner.spawned_count), ([], 0))
        self.assertEqual(len(world.stages[1].drop_items), 15)
        for depth, opposite in ((-44, 239), (239, -44)):
            world = World()
            world.select_stage(1)
            world.player.invincible = True
            world.player.ground_y = depth
            enemy = Enemy(world.player.x + 150, -1, ground_y=opposite)
            world.enemies.append(enemy)
            advance(world, 3)
            self.assertLessEqual(abs(enemy.ground_y - depth), config.ATTACK_DEPTH_TOLERANCE)
            self.assertTrue(world.stage.walkable.contains(enemy.x, enemy.ground_y, 88))
            self.assertEqual(enemy.floor, 0)

    def test_neighboring_floor_projection_only_clamps_depths_outside_the_destination(self):
        cases = ((0, 1, 277, 239), (0, 1, -3, -3),
                 (1, 0, 239, 239), (1, 0, -44, -3),
                 (1, 2, 239, 239), (1, 2, -44, -44),
                 (2, 1, 247, 239), (2, 1, -44, -44))
        for source, destination, depth, projected in cases:
            with self.subTest(source=source, destination=destination, depth=depth):
                world = World()
                world.select_stage(source)
                stage, player = world.stage, world.player
                stage.arrows_visible = True
                side = 1 if destination > source else -1
                player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN if side > 0 else 80
                player.ground_y = depth
                player.hp, player.invincible = 420, True
                player.jump_height, player.vy, player.jump_count = 150, -100, 2
                player.vx = side * config.RUN_SPEED
                player.animation.set_state("JUMP")
                player.animation.elapsed = 0.25
                world.controls.press("right" if side > 0 else "left")
                world.controls.press("left_shift")
                held = set(world.controls.held)
                self.assertTrue(world.try_stage_transition())
                loading = (source, destination) in config.STAGE_LOADING_TRANSITIONS
                self.assertEqual(world.stage_loading, loading)
                if loading:
                    world.update(1.999)
                    self.assertTrue(world.stage_loading)
                    self.assertEqual(world.stage_index, source)
                    self.assertEqual(player.ground_y, depth)
                    world.update(0.001)
                self.assertFalse(world.stage_loading)
                self.assertEqual(world.stage_index, destination)
                self.assertIs(world.player, player)
                self.assertEqual((player.ground_y, player.previous_ground_y), (projected, projected))
                self.assertEqual((player.hp, player.invincible, player.jump_height, player.vy,
                                  player.jump_count, player.vx, player.animation.elapsed),
                                 (420, True, 150, -100, 2, side * config.RUN_SPEED, 0.25))
                self.assertEqual(world.controls.held, held)
                self.assertFalse(world.try_stage_transition())


if __name__ == "__main__":
    unittest.main()
