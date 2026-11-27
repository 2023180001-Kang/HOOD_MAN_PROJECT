import hashlib
import random
import unittest

from PIL import Image

import config
from researcher import Researcher
from tests.helpers import advance, tap
from tests.helpers import ManualSpawnWorld as World


class FactoryInsideFloorTests(unittest.TestCase):
    def test_original_background_and_full_floor_source_rows_stay_aligned(self):
        path = config.ROOT / "factoryInside-1.png"
        self.assertEqual(config.STAGE_IMAGES[6], path.name)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "87d5e7453dd7a097f2d6f83ae0526f6f31093bb8498fcfcc5c97fe340ca9e31a")
        with Image.open(path) as image:
            self.assertEqual((image.size, image.mode), ((1672, 941), "RGB"))
        stage = World().stages[6]
        self.assertEqual(stage.walkable.bounds, (0, -3, 2560, 172))
        anchor = config.STAGE_GROUND_ANCHORS.get(stage.image_name, config.STAGE_GROUND_Y)
        source_world_top = config.GROUND_Y - anchor + config.STAGE_IMAGE_HEIGHT
        self.assertEqual((config.STAGE_SCALE, anchor, source_world_top), (1, 144, 897))
        self.assertEqual((source_world_top - stage.walkable.bounds[3],
                          source_world_top - stage.walkable.bounds[1]), (725, 900))
        self.assertEqual(stage.floor_areas, (stage.walkable,))
        self.assertIsNone(stage.upper_walkable)
        self.assertEqual((stage.stairs, stage.doors), ([], []))
        self.assertIsNone(stage.traffic)
        self.assertIs(stage.spawn_area, stage.walkable)
        self.assertIs(stage.drop_spawn_area, stage.walkable)
        for x in (68, 300, 590, 1280, 1672, 2260, 2492):
            for source_y in range(725, 901):
                self.assertTrue(stage.walkable.contains(x, source_world_top - source_y, 68))
        self.assertFalse(stage.walkable.contains(1280, -3.01, 68))
        self.assertFalse(stage.walkable.contains(590, 172.01, 68))

    def test_all_loadouts_walk_and_run_to_every_expanded_floor_corner(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for running in (False, True):
                for side in (-1, 1):
                    for depth in (-1, 1):
                        with self.subTest(weapon=weapon, running=running, side=side, depth=depth):
                            world = World()
                            world.select_stage(6)
                            player = world.player
                            player.equip_weapon(weapon)
                            player.x = player.previous_x = 300 if side < 0 else 2260
                            world.controls.press("left" if side < 0 else "right")
                            world.controls.press("down" if depth < 0 else "up")
                            if running:
                                world.controls.press("left_shift")
                            advance(world, 1.5)
                            self.assertEqual((player.x, player.ground_y, player.floor, player.jump_height),
                                             (68 if side < 0 else 2492, -3 if depth < 0 else 172, 0, 0))
                            self.assertTrue(player.grounded)
                            self.assertIsNone(player.staircase)
                            self.assertGreaterEqual(player.y - world.camera.render_y, 0)

    def test_double_jumps_and_g_drop_pickup_stay_on_both_depth_edges(self):
        for depth in (-3, 172):
            for weapon in config.WEAPON_POSE_IMAGES:
                with self.subTest(depth=depth, weapon=weapon):
                    world = World()
                    world.select_stage(6)
                    player = world.player
                    player.ground_y = player.previous_ground_y = depth
                    world.controls.press("down" if depth == -3 else "up")
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

    def test_researchers_and_items_use_new_bands_and_survive_revisit_and_f5(self):
        world = World(rng=random.Random(41), item_rng=random.Random(23))
        world.select_stage(6)
        stage = world.stage
        self.assertEqual(len(stage.drop_items), 15)
        self.assertTrue(all(item.floor == 0 and stage.walkable.contains(item.x, item.ground_y)
                            for item in stage.drop_items))
        self.assertTrue(any(item.ground_y < 56 for item in stage.drop_items))
        self.assertTrue(any(item.ground_y > 148 - config.DROP_ITEM_HEIGHT for item in stage.drop_items))
        tap(world.controls, "spawn_9")
        world.step(config.FIXED_DT)
        self.assertEqual((len(world.enemies), stage.spawner.spawned_count), (9, 9))
        self.assertTrue(all(type(enemy) is Researcher and enemy.hp == 200 and enemy.ammo == 7
                            and enemy.attack_damage == 40
                            and stage.walkable.contains(enemy.x, enemy.ground_y, 88)
                            for enemy in world.enemies))
        self.assertTrue(any(enemy.ground_y < 56 for enemy in world.enemies))
        self.assertTrue(any(enemy.ground_y > 148 for enemy in world.enemies))
        first, items = world.enemies[0], stage.drop_items
        first.take_damage(40)
        snapshot = first.x, first.ground_y, first.animation.elapsed, first.ammo, first.rng.getstate()
        world.select_stage(7)
        advance(world, 1)
        world.select_stage(6)
        self.assertIs(world.stage, stage)
        self.assertIs(world.enemies[0], first)
        self.assertIs(stage.drop_items, items)
        self.assertEqual((first.hp, stage.spawner.spawned_count), (160, 9))
        self.assertEqual((first.x, first.ground_y, first.animation.elapsed, first.ammo, first.rng.getstate()), snapshot)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertEqual(world.stage_index, 0)
        self.assertEqual(world.stages[6].walkable.bounds, (0, -3, 2560, 172))
        self.assertEqual((world.stages[6].enemies, world.stages[6].spawner.spawned_count), ([], 0))
        self.assertEqual(len(world.stages[6].drop_items), 15)

    def test_researchers_track_between_both_extreme_depths_without_leaving_the_floor(self):
        for depth, opposite in ((-3, 172), (172, -3)):
            world = World()
            world.select_stage(6)
            player = world.player
            player.invincible = True
            player.ground_y = player.previous_ground_y = depth
            enemy = Researcher(player.x + 300, -1, ground_y=opposite)
            world.enemies.append(enemy)
            advance(world, 3)
            self.assertLessEqual(abs(enemy.ground_y - depth), config.ATTACK_DEPTH_TOLERANCE)
            self.assertTrue(world.stage.walkable.contains(enemy.x, enemy.ground_y, 88))
            self.assertEqual(enemy.floor, 0)

    def test_neighbor_transitions_preserve_common_depth_and_only_project_outside_values(self):
        cases = ((5, 6, 45, 45), (5, 6, 258, 172), (6, 5, -3, 45), (6, 5, 172, 172),
                 (6, 7, -3, 16), (6, 7, 172, 172), (7, 6, 16, 16), (7, 6, 200, 172))
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
