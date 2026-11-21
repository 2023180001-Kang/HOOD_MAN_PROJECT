import hashlib
import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import config
from assets import Assets
from axe_enemy import AxeEnemy
from effects import DamageNumber, HitEffect
from enemy import Enemy
from tests.helpers import advance, clear_encounters
from world import World


def at_factory_boundary(side=1, first=3):
    world = clear_encounters(World())
    world.stage_index = first if side > 0 else first + 1
    world.stage.arrows_visible = True
    world.player.x = (config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN if side > 0
                      else config.STAGE_EXIT_MARGIN)
    world.player.vx = side * config.RUN_SPEED
    world.controls.press("right" if side > 0 else "left")
    world.controls.press("left_shift")
    return world


class FactoryStageTests(unittest.TestCase):
    def test_stair_free_dock_loads_new_art_and_archives_the_old_png_byte_identically(self):
        self.assertEqual(config.FACTORY_OUTSIDE_IMAGE, "factory_loading_dock_no_stairs_1672x941.png")
        self.assertEqual(config.STAGE_IMAGES[4], config.FACTORY_OUTSIDE_IMAGE)
        expected = {
            config.FACTORY_OUTSIDE_IMAGE: "be43a67389ada502c862880b4a73f28406de01f537bf07e8819af6c22bddadbf",
            config.ARCHIVED_FACTORY_OUTSIDE_IMAGE: "a2884d63b029bad7f92331015edb183a1023d09b0824e8cca0accb7f69059514",
        }
        for name, digest in expected.items():
            path = config.ROOT / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with Image.open(path) as image:
                self.assertEqual(image.size, (1672, 941))
        self.assertFalse((config.ROOT / "hood_man_factory_loading_dock_1672x941.png").exists())
        with patch("pico2d.load_image", return_value=Mock()), patch("pico2d.load_font"):
            assets = Assets()
        self.assertIn(config.FACTORY_OUTSIDE_IMAGE, assets.images)
        self.assertNotIn(config.ARCHIVED_FACTORY_OUTSIDE_IMAGE, assets.images)
        self.assertNotIn("hood_man_factory_loading_dock_1672x941.png", assets.images)

    def test_stair_free_dock_uses_all_concrete_between_the_fascia_and_drain(self):
        stage = World().stages[4]
        self.assertEqual(stage.walkable.bounds, (0, 45, 2560, 258))
        anchor = config.STAGE_GROUND_ANCHORS[stage.image_name]
        source_world_top = config.GROUND_Y - anchor + config.STAGE_IMAGE_HEIGHT
        self.assertEqual((source_world_top - stage.walkable.bounds[3],
                          source_world_top - stage.walkable.bounds[1]), (683, 896))
        self.assertIsNone(stage.upper_walkable)
        self.assertEqual((stage.stairs, stage.doors), ([], []))
        for x in (68, 250, 1280, 1672, 2260, 2492):
            for y in (45, 48, 100, 240, 258):
                self.assertTrue(stage.walkable.contains(x, y, 68))
        self.assertFalse(stage.walkable.contains(1280, 44.99, 68))
        self.assertFalse(stage.walkable.contains(1280, 258.01, 68))

    def test_each_loadout_walks_and_runs_to_every_stair_free_dock_corner(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for running in (False, True):
                for side in (-1, 1):
                    for depth in (-1, 1):
                        with self.subTest(weapon=weapon, running=running, side=side, depth=depth):
                            world = World()
                            world.select_stage(4)
                            player = world.player
                            player.equip_weapon(weapon)
                            player.x = player.previous_x = 300 if side < 0 else 2260
                            world.controls.press("left" if side < 0 else "right")
                            world.controls.press("down" if depth < 0 else "up")
                            if running:
                                world.controls.press("left_shift")
                            advance(world, 1.5)
                            self.assertEqual((player.x, player.ground_y),
                                             (68 if side < 0 else 2492, 45 if depth < 0 else 258))
                            self.assertEqual((player.floor, player.jump_height), (0, 0))
                            self.assertIsNone(player.staircase)
                            self.assertTrue(player.grounded)

    def test_new_dock_retains_axe_spawns_items_revisit_state_and_restart(self):
        world = World(rng=random.Random(41), item_rng=random.Random(23))
        world.select_stage(4)
        stage = world.stage
        self.assertEqual(len(stage.drop_items), 15)
        self.assertTrue(all(item.floor == 0 and stage.walkable.contains(item.x, item.ground_y)
                            for item in stage.drop_items))
        world.controls.press("spawn_9")
        world.step(config.FIXED_DT)
        self.assertEqual(len(world.enemies), 9)
        self.assertTrue(all(type(enemy) is AxeEnemy and enemy.hp == 400 and enemy.attack_damage == 60
                            and stage.walkable.contains(enemy.x, enemy.ground_y, 88)
                            for enemy in world.enemies))
        first, items = world.enemies[0], stage.drop_items
        first.take_damage(40)
        world.select_stage(5)
        advance(world, 1)
        world.select_stage(4)
        self.assertIs(world.stage, stage)
        self.assertIs(world.stage.drop_items, items)
        self.assertEqual(first.hp, 360)
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        world.select_stage(4)
        self.assertEqual(world.stage.image_name, "factory_loading_dock_no_stairs_1672x941.png")
        self.assertEqual(world.stage.walkable.bounds, (0, 45, 2560, 258))
        self.assertEqual(world.enemies, [])
        self.assertEqual(len(world.stage.drop_items), 15)

    def test_factory_zone_boundaries_wait_two_seconds_and_preserve_the_same_player_both_ways(self):
        for first, side in ((3, -1), (3, 1), (5, -1), (5, 1),
                            (7, -1), (7, 1), (9, -1), (9, 1)):
            with self.subTest(first=first, side=side):
                world = at_factory_boundary(side, first)
                source = world.stage_index
                player = world.player
                player.hp, player.invincible = 420, True
                player.jump_height, player.vy, player.jump_count = 140, 300, 2
                player.animation.set_state("JUMP")
                player.animation.elapsed = 0.2
                self.assertTrue(world.try_stage_transition())
                self.assertEqual(world.pending_stage_index, source + side)
                world.update(1.999)
                self.assertTrue(world.stage_loading)
                self.assertEqual(world.stage_index, source)
                world.update(0.001)
                self.assertFalse(world.stage_loading)
                self.assertEqual(world.stage_index, source + side)
                self.assertIs(world.player, player)
                self.assertEqual((player.hp, player.invincible, player.jump_height,
                                  player.vy, player.jump_count, player.vx, player.animation.elapsed),
                                 (420, True, 140, 300, 2, side * config.RUN_SPEED, 0.2))
                self.assertEqual(player.x, config.STAGE_ENTRY_MARGIN if side > 0 else
                                 config.WORLD_WIDTH - config.STAGE_ENTRY_MARGIN)
                self.assertFalse(world.try_stage_transition())

    def test_factory_loading_freezes_both_maps_and_discards_actions_without_losing_held_movement(self):
        for first in (3, 5, 7, 9):
            with self.subTest(first=first):
                world = at_factory_boundary(first=first)
                source, target = world.stages[first:first + 2]
                for stage in (source, target):
                    stage.enemies.append(Enemy(1500))
                    stage.effects.append(HitEffect(1500, 180, 1))
                    stage.damage_numbers.append(DamageNumber(1500, 250, 40))
                self.assertTrue(world.try_stage_transition())
                for action in ("jump", "combat_a", "invincibility", "stage_exits"):
                    world.controls.press(action)
                advance(world, 1.9)
                self.assertEqual(world.elapsed, 0)
                for stage in (source, target):
                    self.assertEqual(stage.enemies[0].x, 1500)
                    self.assertEqual(stage.enemies[0].animation.elapsed, 0)
                    self.assertEqual(stage.effects[0].elapsed, 0)
                    self.assertEqual(stage.damage_numbers[0].elapsed, 0)
                self.assertFalse(world.controls.pressed)
                world.update(0.1)
                self.assertIs(world.stage, target)
                self.assertIn("right", world.controls.held)
                self.assertIn("left_shift", world.controls.held)
                self.assertFalse(target.arrows_visible)
                world.update(config.FIXED_DT)
                self.assertIsNone(world.player.active_move)
                self.assertEqual(len(world.enemies), 1)
                self.assertEqual(world.player.jump_count, 0)
                self.assertFalse(world.player.invincible)

    def test_f5_during_factory_loading_cancels_the_destination_and_clears_all_maps(self):
        for first, side in ((3, -1), (3, 1), (5, -1), (5, 1),
                            (7, -1), (7, 1), (9, -1), (9, 1)):
            world = at_factory_boundary(side, first)
            for stage in world.stages:
                stage.arrows_visible = True
                stage.enemies.extend(stage.spawner.spawn(2, 0))
            self.assertTrue(world.try_stage_transition())
            world.update(1)
            world.controls.press("restart")
            world.update(1 / 60)
            self.assertEqual((world.stage_index, world.player.hp, len(world.stages)), (0, 500, 12))
            self.assertIsNone(world.pending_stage_index)
            self.assertTrue(all(not stage.enemies and not stage.arrows_visible
                                for stage in world.stages))
            advance(world, 2.5)
            self.assertEqual(world.stage_index, 0)

    def test_factory_background_covers_the_viewport_at_both_edges_and_during_vertical_shake(self):
        stage = World().stages[4]
        image = SimpleNamespace(w=1672, h=941, composite_draw=Mock())
        assets = SimpleNamespace(images={config.FACTORY_OUTSIDE_IMAGE: image}, draw_drop_item=Mock())
        for camera_x in (0, 640, 1280):
            for camera_y in (-8, 0, 8):
                image.composite_draw.reset_mock()
                stage.draw(assets, camera_x, camera_y)
                rectangles = []
                for call in image.composite_draw.call_args_list:
                    _, _, x, y, width, height = call.args
                    self.assertLessEqual(y - height / 2, 0)
                    self.assertGreaterEqual(y + height / 2, config.SCREEN_HEIGHT)
                    rectangles.append((x - width / 2, x + width / 2))
                self.assertLessEqual(min(left for left, _ in rectangles), 0)
                self.assertGreaterEqual(max(right for _, right in rectangles), config.SCREEN_WIDTH)

    def test_factory_loading_completion_is_identical_at_different_render_rates(self):
        for first in (3, 5, 7, 9):
            with self.subTest(first=first):
                results = []
                for fps in (30, 60, 120, 144):
                    world = at_factory_boundary(first=first)
                    world.try_stage_transition()
                    for _ in range(2 * fps - 1):
                        world.update(1 / fps)
                    self.assertTrue(world.stage_loading)
                    world.update(1 / fps)
                    self.assertFalse(world.stage_loading)
                    results.append((world.stage_index, world.player.x, world.player.vx,
                                    world.player.ground_y, world.elapsed, world.accumulator))
                self.assertTrue(all(result == results[0] for result in results))

    def test_factory_exterior_round_trip_preserves_objects_and_projects_only_the_ground(self):
        world = World()
        world.stage_index = 4
        source = world.stage
        source.arrows_visible = True
        enemy = source.spawner.spawn(1, world.elapsed)[0]
        source.enemies.append(enemy)
        enemy.x = 1400
        enemy.take_damage(40)
        player = world.player
        player.hp, player.invincible = 420, True
        player.ground_y = 116
        player.jump_height, player.vy, player.jump_count = 140, 300, 2
        player.x, player.vx = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN, config.RUN_SPEED
        world.controls.press("right")
        world.controls.press("left_shift")
        self.assertTrue(world.try_stage_transition())
        self.assertFalse(world.stage_loading)
        self.assertEqual(world.stage.image_name, config.FACTORY_EXTERIOR_IMAGE)
        self.assertIs(world.player, player)
        self.assertEqual((player.hp, player.invincible, player.ground_y, player.jump_height,
                          player.vy, player.jump_count, player.vx),
                         (420, True, 100, 140, 300, 2, config.RUN_SPEED))
        exterior = world.stage
        exterior.arrows_visible = True
        self.assertEqual(exterior.destination(1), 6)
        world.controls.release("right")
        world.controls.press("left")
        player.x, player.vx = config.STAGE_EXIT_MARGIN, -config.RUN_SPEED
        self.assertTrue(world.try_stage_transition())
        self.assertFalse(world.stage_loading)
        self.assertIs(world.stage, source)
        self.assertIs(source.enemies[0], enemy)
        self.assertEqual(enemy.hp, 360)
        self.assertEqual(exterior.spawner.spawned_count, 0)
        self.assertEqual(exterior.enemies, [])
        self.assertEqual((player.ground_y, player.jump_height, player.vy, player.jump_count),
                         (100, 140, 300, 2))


if __name__ == "__main__":
    unittest.main()
