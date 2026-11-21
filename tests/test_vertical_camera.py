import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import config
from camera import Camera
from tests.helpers import ArchivedTwoFloorTests, advance, tap
from tests.test_two_floors import place
from ui import UI
from world import World


class VerticalCameraTests(ArchivedTwoFloorTests):
    def assert_player_visible(self, world):
        feet = world.player.y - world.camera.render_y
        self.assertGreaterEqual(feet, 0)
        self.assertLessEqual(feet + config.CAMERA_PLAYER_HEIGHT, config.SCREEN_HEIGHT)
        low, high = world.stage.camera_y_bounds
        self.assertGreaterEqual(world.camera.render_y, low)
        self.assertLessEqual(world.camera.render_y, high)

    def test_upstairs_normal_jump_keeps_the_full_player_on_screen(self):
        world = World()
        place(world, world.player, 1, 1280, 502)
        world.controls.press("jump")
        maximum = 0
        for _ in range(180):
            world.step(config.FIXED_DT)
            self.assert_player_visible(world)
            maximum = max(maximum, world.camera.y)
        self.assertGreater(maximum, 100)
        self.assertEqual(world.player.floor, 1)
        self.assertTrue(world.player.grounded)

    def test_upstairs_double_jumps_keep_the_full_player_visible_at_both_map_edges(self):
        for running in (False, True):
            for direction in (-1, 1):
                world = World()
                place(world, world.player, 1, 68 if direction < 0 else 2492, 502)
                if running:
                    world.controls.press("left" if direction < 0 else "right")
                    world.controls.press("left_shift")
                world.controls.press("jump")
                advance(world, 0.35, 120)
                tap(world.controls, "jump")
                maximum = 0
                for _ in range(240):
                    world.step(config.FIXED_DT)
                    self.assert_player_visible(world)
                    maximum = max(maximum, world.camera.y)
                self.assertGreater(maximum, 300)
                self.assertEqual(world.player.floor, 1)
                self.assertTrue(world.player.grounded)

    def test_bounds_cover_the_full_background_and_headroom_above_the_upper_floor(self):
        world = World()
        low, high = world.stage.camera_y_bounds
        self.assertEqual(low, config.GROUND_Y - config.STAGE_GROUND_Y)
        self.assertGreater(high, config.STAGE_IMAGE_HEIGHT + low - config.SCREEN_HEIGHT)
        world.camera.update(0, world.player.x, player_y=10000, vertical_bounds=(low, high))
        self.assertEqual(world.camera.y, high)
        world.camera.update(0, world.player.x, player_y=-10000, vertical_bounds=(low, high))
        self.assertEqual(world.camera.y, low)

    def test_lower_floor_uses_the_bottom_of_the_map_without_hiding_the_feet(self):
        world = World()
        place(world, world.player, 0, 1280, 56)
        world.update_camera(0)
        self.assertLess(world.camera.y, 0)
        self.assert_player_visible(world)

    def test_vertical_shake_stays_within_the_extended_camera_bounds(self):
        world = World()
        low, high = world.stage.camera_y_bounds
        for height in (56, 502, 880, 10000):
            world.camera.update(0, 1280, player_y=height, vertical_bounds=(low, high))
            world.camera.shake(strength=config.PLAYER_HIT_SHAKE_STRENGTH)
            for _ in range(30):
                world.camera.update(config.FIXED_DT, 1280, player_y=height,
                                    vertical_bounds=(low, high))
                self.assertGreaterEqual(world.camera.render_y, low)
                self.assertLessEqual(world.camera.render_y, high)

    def test_ground_level_and_the_original_horizontal_camera_api_remain_unchanged(self):
        camera = Camera(1280)
        self.assertEqual(camera.y, 0)
        self.assertEqual(camera.render_y, 0)
        world = World()
        for index in range(len(world.stages)):
            world.select_stage(index)
            self.assertEqual(world.camera.y, 0)
            self.assertEqual(world.camera.x, config.START_X - config.SCREEN_WIDTH / 2)

    def test_restart_and_travel_recompute_vertical_framing_and_clear_shake(self):
        world = World()
        place(world, world.player, 1, 1280, 476)
        world.player.jump_height = 100
        world.update_camera(0)
        self.assertGreater(world.camera.y, 0)
        world.camera.shake()
        world.select_stage(1)
        self.assertEqual(world.camera.y, 0)
        self.assertEqual(world.camera.shake_remaining, 0)
        place(world, world.player, 0, 1280, 100)
        world.player.jump_height = 500
        world.update_camera(0)
        self.assertGreater(world.camera.y, 0)
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertEqual((world.camera.y, world.camera.render_y), (0, 0))

    def test_extended_background_keeps_world_alignment_and_fills_above_the_original_roof(self):
        world = World()
        image = SimpleNamespace(w=1672, h=941, composite_draw=Mock(), clip_composite_draw=Mock())
        assets = Mock(images={world.stage.image_name: image})
        world.stage.draw(assets, 0, 400)
        bottom = config.GROUND_Y - config.STAGE_GROUND_Y - 400
        self.assertEqual(image.composite_draw.call_args_list[0].args[3], bottom + 941 / 2)
        roof = bottom + 941
        fill = config.SCREEN_HEIGHT - roof
        args = image.clip_composite_draw.call_args_list[0].args
        self.assertEqual(args[:4], (0, 940, 1672, 1))
        self.assertEqual(args[7], roof + fill / 2)
        self.assertEqual(args[9], fill)

    def test_fixed_hud_does_not_move_with_vertical_tracking(self):
        world = World()
        ui = UI()
        ui.details_visible = False
        hp = Mock(w=700, h=80)
        assets = SimpleNamespace(images={config.HP_IMAGE: hp}, font=Mock())
        ui.draw(assets, world)
        baseline = hp.draw_to_origin.call_args
        place(world, world.player, 1, 1280, 502)
        world.player.jump_height = 350
        world.update_camera(0)
        self.assertGreater(world.camera.y, 0)
        ui.draw(assets, world)
        self.assertEqual(hp.draw_to_origin.call_args, baseline)

    def test_camera_height_envelope_covers_all_player_sprite_sheets(self):
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            frames = json.load(file)
        names = (config.PLAYER_IMAGE, config.COMBAT_IMAGE, config.STRONG_ATTACK_IMAGE,
                 config.COUNTER_PLAYER_IMAGE, *config.WEAPON_POSE_IMAGES.values())
        for name in names:
            scale = config.SPRITE_IMAGE_SCALES.get(name, config.SPRITE_SCALE)
            for row in frames[name]:
                for tile in row:
                    self.assertLessEqual((tile["clip"][3] + tile.get("offset_y", 0)) * scale,
                                         config.CAMERA_PLAYER_HEIGHT)

    def test_help_panels_and_labels_keep_original_positions_at_every_camera_height(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            world = World()
            world.player.equip_weapon(weapon)
            ui = UI()
            ui.floor_bounds_visible = True
            assets = SimpleNamespace(images={config.HP_IMAGE: Mock(w=700, h=80)}, font=Mock())
            with patch("pico2d.draw_rectangle") as draw:
                ui.draw(assets, world)
            panels = [call.args for call in draw.call_args_list if call.args[0] == 688]
            labels = [call.args[:2] for call in assets.font.draw.call_args_list]
            hp = assets.images[config.HP_IMAGE].draw_to_origin.call_args
            self.assertEqual([panel[:4] for panel in panels],
                             [(688, 616, config.SCREEN_WIDTH - 20, 704),
                              (688, 436, config.SCREEN_WIDTH - 20, 610)])
            for floor, ground_y, height in ((0, 136, 420), (1, 452, 0),
                                            (1, 502, 300), (0, 56, 0)):
                place(world, world.player, floor, 1280, ground_y)
                world.player.jump_height = height
                world.update_camera(0)
                assets.font.reset_mock()
                with patch("pico2d.draw_rectangle") as draw:
                    ui.draw(assets, world)
                self.assertEqual([call.args for call in draw.call_args_list if call.args[0] == 688],
                                 panels)
                self.assertEqual([call.args[:2] for call in assets.font.draw.call_args_list], labels)
                self.assertEqual(assets.images[config.HP_IMAGE].draw_to_origin.call_args, hp)

    def test_camera_tracking_does_not_change_jump_physics(self):
        snapshots = []
        for enabled in (False, True):
            world = World()
            place(world, world.player, 1, 1280, 476)
            world.controls.press("jump")
            if enabled:
                advance(world, 0.5)
            else:
                with patch.object(world, "update_camera"):
                    advance(world, 0.5)
            snapshots.append((world.player.x, world.player.y, world.player.vy, world.player.floor))
        self.assertEqual(snapshots[0], snapshots[1])

    def test_vertical_tracking_is_render_rate_independent(self):
        snapshots = []
        for fps in (30, 60, 120, 144):
            world = World()
            place(world, world.player, 1, 1280, 502)
            world.controls.press("jump")
            advance(world, 0.5, fps)
            snapshots.append((world.camera.x, world.camera.y, world.camera.render_y))
        self.assertTrue(all(snapshot == snapshots[0] for snapshot in snapshots))


if __name__ == "__main__":
    unittest.main()
