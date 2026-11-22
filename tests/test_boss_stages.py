import hashlib
import random
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import config
from assets import Assets
from ar_soldier import ARSoldier
from tests.helpers import advance, tap
from world import World


BOSS_FLOORS = ((10, -28, 247, 650, 925), (11, -20, 242, 655, 917))


class BossStageTests(unittest.TestCase):
    def test_new_boss_backgrounds_replace_the_old_pair_and_preserve_all_original_bytes(self):
        self.assertEqual(config.BOSS_STAGE_IMAGES,
                         ("bossStage_floor300_1672x941.png", "bossStage-2_floor300_1672x941.png"))
        self.assertEqual(config.ARCHIVED_BOSS_STAGE_IMAGES,
                         ("before_sheets/bossStage-1.png", "before_sheets/bossStage-2.png"))
        self.assertEqual(config.STAGE_IMAGES[10:], config.BOSS_STAGE_IMAGES)
        originals = (
            (config.BOSS_STAGE_IMAGES[0], "RGB",
             "7ca981b46088c3bcb29c074b0be1f7a131fa7330d9710e38d19c98b43fc2f2e7"),
            (config.BOSS_STAGE_IMAGES[1], "RGBA",
             "070a369d7eb381bbc30713cbf22cba492532a8f799202d405d2801ffe4aa3d0e"),
            (config.ARCHIVED_BOSS_STAGE_IMAGES[0], "RGB",
             "8f46fa912eaad669e2c5d86d586b98ef1ea02b40513393646561a37c5d6b773d"),
            (config.ARCHIVED_BOSS_STAGE_IMAGES[1], "RGB",
             "05e3ec5c3c57fac6057d8fade866a27b6ee4c6e65b3eaea4f7c7ec300b276468"),
        )
        for name, mode, digest in originals:
            path = config.ROOT / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with Image.open(path) as image:
                self.assertEqual((image.size, image.mode), ((1672, 941), mode))
        with patch("pico2d.load_image", return_value=Mock()), patch("pico2d.load_font"):
            assets = Assets()
        for active, archived in zip(config.BOSS_STAGE_IMAGES, config.ARCHIVED_BOSS_STAGE_IMAGES):
            archived_path = config.ROOT / archived
            self.assertIn(active, assets.images)
            self.assertNotIn(archived, assets.images)
            self.assertNotIn(archived_path.name, assets.images)
            self.assertFalse((config.ROOT / archived_path.name).exists())

    def test_all_open_floor_rows_share_the_same_movement_spawn_and_item_bounds(self):
        world = World()
        for index, bottom, top, source_top, source_bottom in BOSS_FLOORS:
            stage = world.stages[index]
            anchor = config.STAGE_GROUND_ANCHORS.get(stage.image_name, config.STAGE_GROUND_Y)
            self.assertEqual((config.STAGE_SCALE, anchor), (1, 144))
            self.assertEqual(stage.walkable.bounds, (0, bottom, 2560, top))
            self.assertEqual((897 - top, 897 - bottom), (source_top, source_bottom))
            self.assertEqual(stage.floor_areas, (stage.walkable,))
            self.assertEqual((stage.doors, stage.stairs), ([], []))
            self.assertIsNone(stage.upper_walkable)
            self.assertIsNone(stage.traffic)
            self.assertIs(stage.spawn_area, stage.walkable)
            self.assertIs(stage.drop_spawn_area, stage.walkable)
            for x in (68, 300, 1050, 1280, 1672, 2260, 2492):
                for source_y in range(source_top, source_bottom + 1):
                    self.assertTrue(stage.walkable.contains(x, 897 - source_y, 68))
            self.assertFalse(stage.walkable.contains(1280, bottom - 0.01, 68))
            self.assertFalse(stage.walkable.contains(1280, top + 0.01, 68))

    def test_all_loadouts_walk_and_run_to_all_four_corners_of_both_boss_floors(self):
        for index, bottom, top, _, _ in BOSS_FLOORS:
            for weapon in (None, *config.WEAPON_POSE_IMAGES):
                for running in (False, True):
                    for side in (-1, 1):
                        for depth in (-1, 1):
                            with self.subTest(index=index, weapon=weapon, running=running,
                                              side=side, depth=depth):
                                world = World()
                                world.select_stage(index)
                                player = world.player
                                player.equip_weapon(weapon)
                                player.x = player.previous_x = 300 if side < 0 else 2260
                                world.controls.press("left" if side < 0 else "right")
                                world.controls.press("down" if depth < 0 else "up")
                                if running:
                                    world.controls.press("left_shift")
                                advance(world, 1.5)
                                self.assertEqual((player.x, player.ground_y, player.floor, player.jump_height),
                                                 (68 if side < 0 else 2492, bottom if depth < 0 else top, 0, 0))
                                self.assertTrue(player.grounded)
                                self.assertIsNone(player.staircase)
                                self.assertGreaterEqual(player.y - world.camera.render_y, 0)

    def test_both_depth_edges_keep_double_jumps_and_weapon_discard_pickup_on_the_same_floor(self):
        for index, bottom, top, _, _ in BOSS_FLOORS:
            for depth in (bottom, top):
                for weapon in config.WEAPON_POSE_IMAGES:
                    with self.subTest(index=index, depth=depth, weapon=weapon):
                        world = World()
                        world.select_stage(index)
                        player = world.player
                        player.ground_y = player.previous_ground_y = depth
                        world.controls.press("up" if depth == top else "down")
                        world.controls.press("left_shift")
                        tap(world.controls, "jump")
                        advance(world, 0.05)
                        tap(world.controls, "jump")
                        advance(world, 1.5)
                        self.assertTrue(player.grounded)
                        self.assertEqual((player.ground_y, player.floor, player.jump_height), (depth, 0, 0))
                        world.controls.held.clear()
                        world.stage.drop_items.clear()
                        player.equip_weapon(weapon)
                        tap(world.controls, "weapon_interact")
                        world.step(config.FIXED_DT)
                        self.assertIsNone(player.weapon)
                        item = world.stage.drop_items[0]
                        advance(world, 1)
                        self.assertTrue(item.grounded)
                        self.assertTrue(world.stage.walkable.contains(item.x, item.ground_y))
                        player.x, player.ground_y = item.x, item.ground_y
                        tap(world.controls, "weapon_interact")
                        world.step(config.FIXED_DT)
                        self.assertEqual(player.weapon, weapon)

    def test_ar_soldiers_items_pursuit_revisit_and_f5_use_the_expanded_boss_floors(self):
        world = World(rng=random.Random(41), item_rng=random.Random(23))
        for index, bottom, top, _, _ in BOSS_FLOORS:
            world.select_stage(index)
            stage = world.stage
            self.assertEqual(world.enemies, [])
            self.assertEqual(len(stage.drop_items), 15)
            self.assertTrue(all(item.floor == 0 and stage.walkable.contains(item.x, item.ground_y)
                                for item in stage.drop_items))
            self.assertTrue(any(item.ground_y < 56 for item in stage.drop_items))
            self.assertTrue(any(item.ground_y > 148 for item in stage.drop_items))
            tap(world.controls, "spawn_9")
            world.step(config.FIXED_DT)
            self.assertEqual((len(world.enemies), stage.spawner.spawned_count), (9, 9))
            self.assertTrue(all(type(enemy) is ARSoldier and enemy.hp == 300 and enemy.attack_damage == 5
                                and stage.walkable.contains(enemy.x, enemy.ground_y, 88)
                                for enemy in world.enemies))
            self.assertTrue(any(enemy.ground_y < 56 for enemy in world.enemies))
            self.assertTrue(any(enemy.ground_y > 148 for enemy in world.enemies))
            enemy, items = world.enemies[0], stage.drop_items
            enemy.take_damage(40)
            snapshot = enemy.x, enemy.ground_y, enemy.animation.elapsed
            world.select_stage(0)
            advance(world, 1)
            world.select_stage(index)
            self.assertIs(world.stage, stage)
            self.assertIs(stage.drop_items, items)
            self.assertEqual((enemy.hp, stage.spawner.spawned_count), (260, 9))
            self.assertEqual((enemy.x, enemy.ground_y, enemy.animation.elapsed), snapshot)
            for depth, opposite in ((bottom, top), (top, bottom)):
                chase = World()
                chase.select_stage(index)
                chase.player.invincible = True
                chase.player.ground_y = depth
                pursuer = ARSoldier(chase.player.x + 150, -1, ground_y=opposite)
                chase.enemies = [pursuer]
                advance(chase, 3)
                self.assertLessEqual(abs(pursuer.ground_y - depth), config.ATTACK_DEPTH_TOLERANCE)
                self.assertTrue(chase.stage.walkable.contains(pursuer.x, pursuer.ground_y, 88))
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertEqual(world.stage_index, 0)
        for index, bottom, top, _, _ in BOSS_FLOORS:
            stage = world.stages[index]
            self.assertEqual(stage.image_name, config.BOSS_STAGE_IMAGES[index - 10])
            self.assertEqual(stage.walkable.bounds, (0, bottom, 2560, top))
            self.assertEqual((stage.enemies, stage.spawner.spawned_count), ([], 0))
            self.assertEqual(len(stage.drop_items), 15)

    def test_lab_and_boss_travel_preserve_shared_depth_and_project_only_outside_values(self):
        cases = ((9, 10, -48, -28), (9, 10, 100, 100), (9, 10, 239, 239),
                 (10, 9, -28, -28), (10, 9, 100, 100), (10, 9, 247, 239),
                 (10, 11, -28, -20), (10, 11, 100, 100), (10, 11, 247, 242),
                 (11, 10, -20, -20), (11, 10, 100, 100), (11, 10, 242, 242))
        for source, destination, depth, projected in cases:
            with self.subTest(source=source, destination=destination, depth=depth):
                world = World()
                world.select_stage(source)
                world.stage.arrows_visible = True
                player = world.player
                side = 1 if destination > source else -1
                player.x = (config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN if side > 0
                            else config.STAGE_EXIT_MARGIN)
                player.ground_y = depth
                player.hp, player.invincible = 420, True
                player.equip_weapon("steel_pipe")
                player.jump_height, player.vy, player.jump_count = 150, -100, 2
                player.vx = side * config.RUN_SPEED
                player.animation.set_state("JUMP")
                player.animation.elapsed = 0.25
                world.controls.press("right" if side > 0 else "left")
                world.controls.press("left_shift")
                held = set(world.controls.held)
                self.assertTrue(world.try_stage_transition())
                loading = source == 9 or destination == 9
                self.assertEqual(world.stage_loading, loading)
                if loading:
                    world.update(1.999)
                    self.assertEqual(world.stage_index, source)
                    self.assertEqual(player.ground_y, depth)
                    world.update(0.001)
                self.assertEqual(world.stage_index, destination)
                self.assertIs(world.player, player)
                self.assertEqual((player.ground_y, player.previous_ground_y), (projected, projected))
                self.assertEqual((player.hp, player.invincible, player.weapon, player.jump_height,
                                  player.vy, player.jump_count, player.vx, player.animation.elapsed),
                                 (420, True, "steel_pipe", 150, -100, 2, side * config.RUN_SPEED, 0.25))
                self.assertEqual(world.controls.held, held)
                self.assertFalse(world.try_stage_transition())

    def test_second_boss_right_exit_stays_the_final_boundary(self):
        world = World()
        world.select_stage(11)
        tap(world.controls, "stage_exits")
        world.controls.press("right")
        world.controls.press("left_shift")
        world.player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
        advance(world, 0.5)
        self.assertEqual((world.stage_index, world.player.x), (11, 2492))
        self.assertFalse(world.stage_loading)
        self.assertIsNone(world.stage.destination(1))
        self.assertEqual(len(world.stages), 12)


if __name__ == "__main__":
    unittest.main()
