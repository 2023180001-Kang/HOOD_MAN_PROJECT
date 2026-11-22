import hashlib
import random
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import config
from assets import Assets
from shield_soldier import ShieldSoldier
from tests.helpers import advance, tap
from world import World


class LabStageTests(unittest.TestCase):
    def test_floor300_labs_replace_both_old_backgrounds_with_byte_identical_archives(self):
        self.assertEqual(config.LAB_STAGE_IMAGES,
                         ("labStage-1_floor300_1672x941.png", "labStage-2_floor300_1672x941.png"))
        self.assertEqual(config.STAGE_IMAGES[8:10], config.LAB_STAGE_IMAGES)
        hashes = ("ad22b6f063046bb1cb45db47899a778f32729332bc70f23aaa4d8d74cd589bbb",
                  "35b1ff0781d6033aed5efa8adeb6233b2774fe4b695a4a23c0b7747dac30bb52",
                  "20f3a5b124c4da30dd63666906ac309258cda6fe9af4335557482022643d06dd",
                  "2c361aaf8b6d344a1ed517ac1ba61a7c067c31407839a2a87f008d12d099bd10")
        for name, digest in zip((*config.LAB_STAGE_IMAGES, *config.ARCHIVED_LAB_STAGE_IMAGES), hashes):
            path = config.ROOT / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with Image.open(path) as image:
                self.assertEqual((image.size, image.mode), ((1672, 941), "RGB"))
        with patch("pico2d.load_image", return_value=Mock()), patch("pico2d.load_font"):
            assets = Assets()
        for active, archived in zip(config.LAB_STAGE_IMAGES, config.ARCHIVED_LAB_STAGE_IMAGES):
            self.assertIn(active, assets.images)
            self.assertNotIn(archived, assets.images)
            self.assertFalse((config.ROOT / archived.removeprefix("before_sheets/")).exists())

    def test_each_lab_uses_every_floor_row_between_equipment_and_foreground_grates(self):
        world = World()
        for index, bottom, top, source_top, source_bottom in ((8, -109, 178, 583, 870),
                                                             (9, -48, 239, 522, 809)):
            stage = world.stages[index]
            self.assertEqual(stage.walkable.bounds, (0, bottom, 2560, top))
            self.assertEqual(config.STAGE_GROUND_ANCHORS[stage.image_name], 280)
            self.assertEqual((761 - top, 761 - bottom), (source_top, source_bottom))
            self.assertEqual((stage.stairs, stage.doors), ([], []))
            self.assertIsNone(stage.upper_walkable)
            self.assertIsNone(stage.traffic)
            for x in (68, 450, 1280, 1672, 2260, 2492):
                for source_y in range(source_top, source_bottom + 1):
                    self.assertTrue(stage.walkable.contains(x, 761 - source_y, 68))
            self.assertFalse(stage.walkable.contains(1280, bottom - 0.01, 68))
            self.assertFalse(stage.walkable.contains(1280, top + 0.01, 68))
            self.assertIs(stage.spawn_area, stage.walkable)
            self.assertIs(stage.drop_spawn_area, stage.walkable)

    def test_all_loadouts_walk_and_run_to_all_four_corners_of_both_lab_floors(self):
        for index, bottom, top in ((8, -109, 178), (9, -48, 239)):
            for weapon in (None, *config.WEAPON_POSE_IMAGES):
                for running in (False, True):
                    for side in (-1, 1):
                        for depth in (-1, 1):
                            with self.subTest(index=index, weapon=weapon, running=running, side=side, depth=depth):
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

    def test_lab_depth_edges_keep_double_jumps_and_g_drop_pickup_on_the_same_floor(self):
        for index, bottom, top in ((8, -109, 178), (9, -48, 239)):
            for depth in (bottom, top):
                for weapon in config.WEAPON_POSE_IMAGES:
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

    def test_new_labs_preserve_shield_enemies_items_guard_state_revisit_and_f5(self):
        world = World(rng=random.Random(41), item_rng=random.Random(23))
        for index in (8, 9):
            world.select_stage(index)
            stage = world.stage
            self.assertEqual(len(stage.drop_items), 15)
            self.assertTrue(all(item.floor == 0 and stage.walkable.contains(item.x, item.ground_y)
                                for item in stage.drop_items))
            tap(world.controls, "spawn_9")
            world.step(config.FIXED_DT)
            self.assertEqual(len(stage.enemies), 9)
            self.assertTrue(all(type(enemy) is ShieldSoldier and enemy.hp == 400
                                and stage.walkable.contains(enemy.x, enemy.ground_y, 88)
                                for enemy in stage.enemies))
            enemy, items = stage.enemies[0], stage.drop_items
            enemy.start_guard()
            enemy.take_damage(40)
            snapshot = enemy.hp, enemy.animation.elapsed, enemy.cooldown
            world.select_stage(7)
            advance(world, 1)
            world.select_stage(index)
            self.assertIs(world.stage, stage)
            self.assertIs(stage.drop_items, items)
            self.assertEqual((enemy.hp, enemy.animation.elapsed, enemy.cooldown), snapshot)
            self.assertTrue(enemy.guarding)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        for index, bottom, top in ((8, -109, 178), (9, -48, 239)):
            stage = world.stages[index]
            self.assertEqual(stage.image_name, config.LAB_STAGE_IMAGES[index - 8])
            self.assertEqual(stage.walkable.bounds, (0, bottom, 2560, top))
            self.assertEqual((stage.enemies, stage.spawner.spawned_count), ([], 0))
            self.assertEqual(len(stage.drop_items), 15)

    def test_lab_and_neighbor_transitions_keep_loading_motion_and_common_depths(self):
        cases = ((7, 8, 200, 178), (7, 8, 16, 16), (8, 7, -109, 16), (8, 7, 178, 178),
                 (8, 9, -109, -48), (8, 9, 178, 178), (9, 8, -48, -48), (9, 8, 239, 178),
                 (9, 10, -48, -28), (9, 10, 239, 239), (10, 9, -28, -28), (10, 9, 247, 239))
        for source, destination, depth, projected in cases:
            world = World()
            world.select_stage(source)
            world.stage.arrows_visible = True
            player = world.player
            side = 1 if destination > source else -1
            player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN if side > 0 else config.STAGE_EXIT_MARGIN
            player.ground_y = depth
            player.hp, player.invincible = 420, True
            player.jump_height, player.vy, player.jump_count = 150, -100, 2
            player.vx = side * config.RUN_SPEED
            player.animation.set_state("JUMP")
            player.animation.elapsed = 0.25
            self.assertTrue(world.try_stage_transition())
            loading = (source, destination) in config.STAGE_LOADING_TRANSITIONS
            self.assertEqual(world.stage_loading, loading)
            if loading:
                world.update(1.999)
                self.assertEqual(world.stage_index, source)
                self.assertEqual(player.ground_y, depth)
                world.update(0.001)
            self.assertEqual(world.stage_index, destination)
            self.assertIs(world.player, player)
            self.assertEqual((player.ground_y, player.previous_ground_y), (projected, projected))
            self.assertEqual((player.hp, player.invincible, player.jump_height, player.vy,
                              player.jump_count, player.vx, player.animation.elapsed),
                             (420, True, 150, -100, 2, side * config.RUN_SPEED, 0.25))
            self.assertFalse(world.try_stage_transition())


if __name__ == "__main__":
    unittest.main()
