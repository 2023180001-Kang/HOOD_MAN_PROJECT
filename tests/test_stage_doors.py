import random
import unittest
from unittest.mock import Mock

from PIL import Image

import config
from assets import Assets
from doors import StageDoor
from tests.helpers import advance, tap
from world import World


class StageDoorTests(unittest.TestCase):
    def test_first_map_has_three_closed_doors_and_one_closed_shutter_only(self):
        world = World()
        self.assertEqual(world.stage.image_name, "HoodMan_2F_Map_1672x941.png")
        self.assertEqual([door.kind for door in world.stage.doors],
                         ["door", "door", "door", "warehouse_shutter"])
        self.assertTrue(all((door.state, door.row, door.frame) == ("CLOSED", 1, 0)
                            for door in world.stage.doors))
        self.assertTrue(all(not stage.doors for stage in world.stages[1:]))
        for name in ("changed_first_map.png", "newStage.png"):
            self.assertTrue((config.ROOT / name).is_file())
        advance(world, 3)
        self.assertTrue(all(door.state == "CLOSED" for door in world.stage.doors))

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


if __name__ == "__main__":
    unittest.main()
