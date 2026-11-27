import random
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import config
from assets import Assets
from doors import StageDoor
from spawn_manager import SpawnManager
from tests.helpers import advance, archived_first_map, tap
from tests.helpers import ManualSpawnWorld as World


class FirstMapTests(unittest.TestCase):
    def test_current_first_map_uses_the_supplied_background_without_door_layers_or_spawns(self):
        world = World()
        self.assertEqual(world.stage.image_name, "changed_first_map.png")
        tap(world.controls, "toggle_doors")
        advance(world, 1)
        self.assertEqual(world.stage.doors, [])
        self.assertFalse(world.stage.open_door_spawns())
        with patch("pico2d.load_image", side_effect=lambda path: Mock(w=1672, h=941)), patch("pico2d.load_font"):
            assets = Assets()
        self.assertIn("changed_first_map.png", assets.images)
        self.assertIn(config.FACTORY_GATE_IMAGE, assets.images)
        for name in (config.ARCHIVED_FIRST_STAGE_IMAGE, "before_sheets/newStage.png", *config.DOOR_IMAGES.values()):
            self.assertTrue((config.ROOT / name).is_file())
            self.assertFalse((config.ROOT / name.removeprefix("before_sheets/")).exists())
            self.assertNotIn(name, assets.images)
        with patch.object(assets, "draw_stage_door") as draw_door:
            world.stage.draw(assets, 640, 0)
        draw_door.assert_not_called()
        assets.images[world.stage.image_name].clip_composite_draw.assert_not_called()


class ArchivedStageDoorTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(archived_first_map())

    def test_first_map_has_one_closed_door_and_one_closed_shutter_on_a_single_floor(self):
        world = World()
        self.assertEqual(world.stage.image_name, config.ARCHIVED_FIRST_STAGE_IMAGE)
        self.assertEqual([door.kind for door in world.stage.doors],
                         ["door", "warehouse_shutter"])
        self.assertEqual([door.source_rect for door in world.stage.doors],
                         [(250, 400, 83, 173), (1333, 417, 211, 202)])
        self.assertEqual(config.STAGE_DOOR_FLOORS[world.stage.image_name], (0, 0))
        self.assertEqual(world.stage.floor_areas, (world.stage.walkable,))
        self.assertIsNone(world.stage.upper_walkable)
        self.assertEqual(world.stage.stairs, [])
        self.assertTrue(all((door.state, door.row, door.frame) == ("CLOSED", 1, 0)
                            for door in world.stage.doors))
        self.assertTrue(all(not stage.doors for stage in world.stages[1:]))
        advance(world, 3)
        self.assertTrue(all(door.state == "CLOSED" for door in world.stage.doors))

    def test_only_fully_open_props_offer_spawns_and_starting_to_close_excludes_them(self):
        for index in (0, 1):
            world = World()
            door = world.stage.doors[index]
            self.assertEqual(world.stage.open_door_spawns(), [])
            door.toggle()
            world.stage.update_doors(0.2)
            self.assertEqual(world.stage.open_door_spawns(), [])
            world.stage.update_doors(1)
            sources = {point.source for point in world.stage.open_door_spawns()}
            expected = {("door", index, 0)}
            if index == 1:
                expected.add(("door", index, 1))
            self.assertEqual(sources, expected)
            door.toggle()
            self.assertEqual(world.stage.open_door_spawns(), [])
            world.stage.update_doors(1)
            self.assertEqual(world.stage.open_door_spawns(), [])

    def test_open_spawn_points_match_both_openings_and_only_the_in_world_mirrored_shutter(self):
        world = World()
        world.stage.toggle_doors()
        world.stage.update_doors(1)
        points = world.stage.open_door_spawns()
        self.assertEqual([(point.source, point.x, point.ground_y, point.floor) for point in points],
                          [(("door", 0, 0), 291.5, 277, 0),
                          (("door", 1, 0), 1438.5, 266, 0),
                          (("door", 1, 1), 1905.5, 266, 0)])
        for point in points:
            self.assertIs(point.walkable, world.stage.walkable)
            self.assertTrue(point.walkable.contains(point.x, point.ground_y, 88))
        world.camera.x, world.camera.y = 1280, 120
        self.assertEqual(world.stage.open_door_spawns(), points)
        for index in range(1, len(world.stages)):
            world.select_stage(index)
            self.assertEqual(world.stage.open_door_spawns(), ())

    def test_open_spawn_pool_keeps_both_edges_all_three_doors_and_individual_profiles(self):
        world = World(rng=random.Random(41))
        world.stage.toggle_doors()
        world.stage.update_doors(1)
        points = {point.source: point for point in world.stage.open_door_spawns()}
        enemies = world.spawner.spawn(160, 7)
        self.assertEqual({enemy.spawn_source for enemy in enemies},
                         set(points) | {("edge", -1), ("edge", 1)})
        self.assertEqual(world.spawner.spawned_count, 160)
        self.assertEqual(len({enemy.attack_speed for enemy in enemies}), 160)
        for index, enemy in enumerate(enemies):
            self.assertEqual((enemy.floor, enemy.hp, enemy.spawned_at), (0, 200, 7))
            self.assertEqual(enemy.run_speed, config.ENEMY_RUN_SPEEDS[index % 4])
            self.assertIs(enemy.walkable, world.stage.walkable)
            self.assertTrue(enemy.walkable.contains(enemy.x, enemy.ground_y, enemy.boundary_padding))
            if enemy.spawn_source in points:
                point = points[enemy.spawn_source]
                self.assertEqual((enemy.x, enemy.ground_y), (point.x, point.ground_y))

    def test_closed_props_preserve_the_original_boundary_spawn_randomness(self):
        world = World(rng=random.Random(71))
        reference = SpawnManager(rng=random.Random(71))
        actual, expected = world.spawner.spawn(25, 3), reference.spawn(25, 3)
        self.assertEqual([(e.x, e.ground_y, e.facing, e.attack_speed) for e in actual],
                         [(e.x, e.ground_y, e.facing, e.attack_speed) for e in expected])

    def test_numeric_open_door_spawns_are_exact_and_only_follow_fresh_input(self):
        for count in config.SPAWN_COUNTS:
            world = World(rng=random.Random(41))
            world.player.invincible = True
            world.controls.press("toggle_doors")
            advance(world, 1)
            self.assertFalse(world.enemies)
            world.controls.press(f"spawn_{count}")
            world.step(config.FIXED_DT)
            self.assertEqual(len(world.enemies), count)
            self.assertTrue(any(enemy.spawn_source[0] == "door" for enemy in world.enemies))
            world.controls.press(f"spawn_{count}")
            advance(world, 0.1)
            self.assertEqual(len(world.enemies), count)
            tap(world.controls, f"spawn_{count}")
            world.step(config.FIXED_DT)
            self.assertEqual(len(world.enemies), count * 2)
            self.assertEqual(world.spawner.spawned_count, count * 2)
            self.assertTrue(all(enemy.floor == 0 and enemy.staircase is None for enemy in world.enemies))

    def test_double_jump_and_old_stair_position_never_create_a_ghost_upper_floor(self):
        for x in (238, 500, 1280, 1905.5):
            world = World()
            world.player.x = world.player.previous_x = x
            world.player.ground_y = world.player.previous_ground_y = 277
            world.controls.press("up")
            world.controls.press("jump")
            advance(world, 0.05, 120)
            tap(world.controls, "jump")
            for _ in range(240):
                world.step(config.FIXED_DT)
                self.assertEqual(world.player.floor, 0)
                self.assertIsNone(world.player.staircase)
                self.assertFalse(world.player.falling_from_upper)
            self.assertEqual(world.player.ground_y, 277)
            self.assertTrue(world.player.grounded)

    def test_both_sheets_play_all_eight_opening_and_closing_frames_and_hold_the_endpoints(self):
        for kind in config.DOOR_IMAGES:
            with self.subTest(kind=kind):
                door = StageDoor(kind, (0, 0, 100, 200))
                door.toggle()
                for frame in range(8):
                    self.assertEqual((door.state, door.row, door.frame), ("OPENING", 1, frame))
                    door.update(1 / config.DOOR_FPS + 1e-10)
                self.assertEqual((door.state, door.row, door.frame), ("OPEN", 1, 7))
                door.update(10)
                self.assertEqual((door.state, door.frame), ("OPEN", 7))
                door.toggle()
                for frame in range(8):
                    self.assertEqual((door.state, door.row, door.frame), ("CLOSING", 2, frame))
                    door.update(1 / config.DOOR_FPS + 1e-10)
                self.assertEqual((door.state, door.row, door.frame), ("CLOSED", 1, 0))
                door.update(10)
                self.assertEqual((door.state, door.frame), ("CLOSED", 0))

    def test_f3_toggles_all_props_once_per_fresh_press_without_affecting_p_or_spawns(self):
        world = World(rng=random.Random(13))
        world.controls.press("toggle_doors")
        world.step(config.FIXED_DT)
        self.assertTrue(all(door.state == "OPENING" for door in world.stage.doors))
        world.controls.press("toggle_doors")
        advance(world, 1)
        self.assertTrue(all(door.state == "OPEN" for door in world.stage.doors))
        self.assertFalse(world.player.invincible)
        self.assertEqual(world.enemies, [])
        self.assertEqual(len(world.stage.drop_items), 15)
        tap(world.controls, "toggle_doors")
        world.controls.press("invincibility")
        world.step(config.FIXED_DT)
        self.assertTrue(world.player.invincible)
        self.assertTrue(all(door.state == "CLOSING" for door in world.stage.doors))
        advance(world, 1)
        self.assertTrue(all(door.state == "CLOSED" for door in world.stage.doors))

    def test_mid_animation_repress_reverses_from_the_matching_pose(self):
        door = StageDoor("door", (0, 0, 100, 200))
        door.toggle()
        door.update(3.1 / config.DOOR_FPS)
        self.assertEqual(door.frame, 3)
        door.toggle()
        self.assertEqual((door.state, door.row, door.frame), ("CLOSING", 2, 4))
        door.toggle()
        self.assertEqual((door.state, door.row, door.frame), ("OPENING", 1, 3))
        door.update(10)
        self.assertEqual(door.state, "OPEN")

    def test_inactive_stage_and_loading_pause_motion_without_buffering_f3_elsewhere(self):
        world = World()
        world.controls.press("toggle_doors")
        advance(world, 0.2)
        doors = world.stage.doors
        snapshot = [(door.state, door.animation.elapsed) for door in doors]
        world.select_stage(1)
        tap(world.controls, "toggle_doors")
        advance(world, 0.5)
        self.assertNotIn("toggle_doors", world.controls.pressed)
        self.assertEqual([(door.state, door.animation.elapsed) for door in doors], snapshot)
        world.select_stage(0)
        world.pending_stage_index, world.stage_loading_remaining = 1, 2
        tap(world.controls, "toggle_doors")
        world.update(0.5)
        self.assertEqual([(door.state, door.animation.elapsed) for door in doors], snapshot)
        self.assertNotIn("toggle_doors", world.controls.pressed)

    def test_f5_restores_all_closed_poses_and_f3_requires_a_new_press(self):
        world = World()
        original = world.stage.doors
        world.controls.press("toggle_doors")
        advance(world, 1)
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertIsNot(world.stage.doors, original)
        self.assertTrue(all(door.state == "CLOSED" for door in world.stage.doors))
        self.assertNotIn("toggle_doors", world.controls.held)
        advance(world, 1)
        self.assertTrue(all(door.state == "CLOSED" for door in world.stage.doors))
        tap(world.controls, "toggle_doors")
        advance(world, 1)
        self.assertTrue(all(door.state == "OPEN" for door in world.stage.doors))

    def test_door_timing_and_reversal_are_independent_of_render_rate(self):
        snapshots = []
        for fps in (30, 60, 120, 144):
            world = World()
            world.controls.press("toggle_doors")
            advance(world, 0.5, fps)
            opening = [(door.state, door.frame, door.animation.elapsed) for door in world.stage.doors]
            tap(world.controls, "toggle_doors")
            advance(world, 1, fps)
            snapshots.append((opening, [(door.state, door.frame, door.animation.elapsed)
                                        for door in world.stage.doors]))
        self.assertTrue(all(snapshot == snapshots[0] for snapshot in snapshots))

    def test_door_art_has_two_rows_of_eight_transparent_cells(self):
        for kind, name in config.DOOR_IMAGES.items():
            with Image.open(config.ROOT / name) as image:
                self.assertEqual((image.size, image.mode), ((2048, 512), "RGBA"))
                self.assertEqual(image.getchannel("A").getextrema(), (0, 255))
                first = image.crop((0, 0, 256, 256))
                left, top, right, bottom = first.getbbox()
                self.assertEqual(config.DOOR_CLOSED_BOUNDS[kind],
                                 (left, top, right - left, bottom - top))
                for row in range(2):
                    for frame in range(8):
                        self.assertIsNotNone(image.crop((frame * 256, row * 256,
                                                        (frame + 1) * 256, (row + 1) * 256)).getbbox())

    def test_closed_props_fit_the_source_openings_and_mirror_with_the_background(self):
        assets = Assets.__new__(Assets)
        background = Mock(w=1672, h=941)
        assets.images = {name: Mock(w=2048, h=512) for name in config.DOOR_IMAGES.values()}
        for kind, rect in config.STAGE_DOOR_SPECS[config.STAGE_IMAGE]:
            door = StageDoor(kind, rect)
            anchor_x, anchor_y, closed_w, closed_h = config.DOOR_CLOSED_BOUNDS[kind]
            for mirrored in (False, True):
                texture = assets.images[door.image_name]
                assets.draw_stage_door(door, background, 70, -44, 1, mirrored=mirrored)
                args = texture.clip_composite_draw.call_args.args
                self.assertEqual(args[:4], (0, 256, 256, 256))
                self.assertEqual(args[5], "h" if mirrored else "")
                cell_left, cell_top = args[6] - args[8] / 2, args[7] + args[9] / 2
                source_left = 256 - anchor_x - closed_w if mirrored else anchor_x
                visible_left = cell_left + source_left / 256 * args[8]
                visible_top = cell_top - anchor_y / 256 * args[9]
                expected_left = 70 + (1672 - rect[0] - rect[2] if mirrored else rect[0])
                self.assertAlmostEqual(visible_left, expected_left)
                self.assertAlmostEqual(visible_top, -44 + 941 - rect[1])
                self.assertAlmostEqual(closed_w / 256 * args[8], rect[2])
                self.assertAlmostEqual(closed_h / 256 * args[9], rect[3])

    def test_air_conditioner_foreground_draws_after_doors_in_both_tiles_for_every_pose(self):
        world = World()
        background = Mock(w=1672, h=941)
        assets = Mock(images={world.stage.image_name: background})
        order = Mock()
        order.attach_mock(background.composite_draw, "background")
        order.attach_mock(assets.draw_stage_door, "door")
        order.attach_mock(background.clip_composite_draw, "foreground")
        for row in (1, 2):
            for frame in range(8):
                order.reset_mock()
                for door in world.stage.doors:
                    door.target_open = row == 1
                    door.moving = True
                    door.animation.set_state("OPENING" if row == 1 else "CLOSING")
                    door.animation.elapsed = (frame + 0.1) / config.DOOR_FPS
                world.stage.draw(assets, 640, 0)
                self.assertEqual([call[0] for call in order.mock_calls],
                                 ["background", "door", "door", "foreground"] * 2)
                calls = background.clip_composite_draw.call_args_list
                for index, call in enumerate(calls):
                    self.assertEqual(call.args[:4], (1482, 506, 78, 60))
                    self.assertEqual(call.args[5], "h" if index else "")

    def test_air_conditioner_foreground_matches_background_pixels_during_scroll_and_shake(self):
        world = World()
        background = Mock(w=1672, h=941)
        assets = Mock(images={world.stage.image_name: background})
        for camera_x in (640, 645.387, 1274.613):
            for camera_y in (0, 6.569, -6.569, 120.75):
                background.reset_mock()
                world.stage.draw(assets, camera_x, camera_y)
                bottom = min(0, config.GROUND_Y - config.STAGE_GROUND_Y - camera_y)
                for index, call in enumerate(background.clip_composite_draw.call_args_list):
                    args = call.args
                    destination_left = int(args[6] - args[8] / 2)
                    destination_top = int(config.SCREEN_HEIGHT - args[7] - args[9] / 2)
                    source_left = 1672 - 1482 - 78 if index else 1482
                    self.assertEqual(destination_left, int(index * 1672 - camera_x) + source_left)
                    self.assertEqual(destination_top, int(config.SCREEN_HEIGHT - bottom - 941) + 375)

    def test_air_conditioner_foreground_is_only_applied_to_the_archived_first_map(self):
        self.assertEqual(config.STAGE_DOOR_FOREGROUND_RECTS,
                         {config.ARCHIVED_FIRST_STAGE_IMAGE: ((1482, 375, 78, 60),)})
        world = World()
        world.select_stage(1)
        background = Mock(w=1672, h=941)
        assets = Mock(images={world.stage.image_name: background})
        world.stage.draw(assets, 640, 0)
        background.clip_composite_draw.assert_not_called()


if __name__ == "__main__":
    unittest.main()
