import unittest
from unittest.mock import patch

import pico2d

import config
from game import Game, KEYS
from tests.helpers import tap
from ui import ENEMY_BOUNDS_COLOR, PLAYER_BOUNDS_COLOR, UI
from walkable import WalkableArea
from world import World


def scene():
    game = Game.__new__(Game)  # Presentation/input tests need no canvas or textures.
    game.world = World()
    game.ui = UI()
    return game


class FloorBoundsTests(unittest.TestCase):
    def test_default_hidden_and_f4_is_separate_from_p_invincibility(self):
        game = scene()
        self.assertEqual(KEYS[pico2d.SDLK_p], "invincibility")
        self.assertEqual(KEYS[pico2d.SDLK_F4], "toggle_floor_bounds")
        self.assertFalse(game.ui.floor_bounds_visible)
        with patch("pico2d.draw_line") as draw:
            game.ui.draw_floor_bounds(game.world, 0, 0)
        draw.assert_not_called()

    def test_f4_toggles_only_on_fresh_presses_and_does_not_enable_invincibility(self):
        game = scene()
        controls = game.world.controls
        controls.press("toggle_floor_bounds")
        game.update(0)
        self.assertTrue(game.ui.floor_bounds_visible)
        controls.press("toggle_floor_bounds")
        game.update(0)
        self.assertTrue(game.ui.floor_bounds_visible)
        self.assertFalse(game.world.player.invincible)
        tap(controls, "toggle_floor_bounds")
        game.update(0)
        self.assertFalse(game.ui.floor_bounds_visible)
        controls.press("invincibility")
        game.update(config.FIXED_DT)
        self.assertTrue(game.world.player.invincible)
        self.assertFalse(game.ui.floor_bounds_visible)
        tap(controls, "toggle_floor_bounds")
        game.update(0)
        self.assertTrue(game.ui.floor_bounds_visible)
        self.assertTrue(game.world.player.invincible)

    def test_visibility_survives_hud_hiding_stage_travel_and_restart(self):
        game = scene()
        game.world.controls.press("toggle_floor_bounds")
        game.update(0)
        game.world.controls.press("toggle_details")
        game.update(0)
        self.assertFalse(game.ui.details_visible)
        self.assertTrue(game.ui.floor_bounds_visible)
        game.world.select_stage(1)
        self.assertTrue(game.ui.floor_bounds_visible)
        game.world.controls.press("restart")
        game.update(config.FIXED_DT)
        self.assertEqual(game.world.stage_index, 0)
        self.assertTrue(game.ui.floor_bounds_visible)
        self.assertFalse(game.world.player.invincible)

    def test_loading_and_death_do_not_block_or_buffer_the_toggle(self):
        for loading in (False, True):
            with self.subTest(loading=loading):
                game = scene()
                if loading:
                    game.world.pending_stage_index = 1
                    game.world.stage_loading_remaining = 2
                else:
                    game.world.player.take_damage(500)
                for visible in (True, False):
                    tap(game.world.controls, "toggle_floor_bounds")
                    game.update(0)
                    self.assertEqual(game.ui.floor_bounds_visible, visible)
                    self.assertNotIn("toggle_floor_bounds", game.world.controls.pressed)

    def test_player_outline_matches_first_floor_padding_camera_and_shake_not_jump(self):
        game = scene()
        game.ui.floor_bounds_visible = True
        camera_x, camera_y = 640, -4
        expected = [
            (68 - camera_x, -3 - camera_y, 2492 - camera_x, -3 - camera_y),
            (2492 - camera_x, -3 - camera_y, 2492 - camera_x, 277 - camera_y),
            (2492 - camera_x, 277 - camera_y, 68 - camera_x, 277 - camera_y),
            (68 - camera_x, 277 - camera_y, 68 - camera_x, -3 - camera_y),
        ]
        for height in (0, 240):
            game.world.player.jump_height = height
            with patch("pico2d.draw_line") as draw:
                game.ui.draw_floor_bounds(game.world, camera_x, camera_y)
            player_lines = [call.args[:4] for call in draw.call_args_list
                            if call.args[4:] == PLAYER_BOUNDS_COLOR]
            self.assertCountEqual(player_lines, expected)
            enemy_lines = [call.args[:4] for call in draw.call_args_list
                           if call.args[4:] == ENEMY_BOUNDS_COLOR]
            self.assertGreater(len(enemy_lines), 4)  # Dashed segments along the single floor.
            for ax, ay, bx, by in enemy_lines:
                for x, y in ((ax, ay), (bx, by)):
                    self.assertTrue(any(area.contains(x + camera_x, y + camera_y, 88)
                                        for area in game.world.stage.floor_areas))

    def test_city_outline_uses_enemy02_padding_even_before_enemies_are_summoned(self):
        game = scene()
        game.world.select_stage(2)
        game.ui.floor_bounds_visible = True
        self.assertEqual(game.world.enemies, [])
        with patch("pico2d.draw_line") as draw:
            game.ui.draw_floor_bounds(game.world, 0, 0)
        lines = [call.args[:4] for call in draw.call_args_list
                 if call.args[4:] == ENEMY_BOUNDS_COLOR]
        xs = [x for ax, _, bx, _ in lines for x in (ax, bx)]
        self.assertEqual((min(xs), max(xs)), (128, config.WORLD_WIDTH - 128))

    def test_second_alley_outline_matches_full_tiles_and_both_actor_paddings(self):
        game = scene()
        game.world.select_stage(1)
        game.ui.floor_bounds_visible = True
        for camera_x, camera_y in ((0, -44), (640, 8), (1280, 120)):
            for height in (0, 240):
                game.world.player.jump_height = height
                with patch("pico2d.draw_line") as draw:
                    game.ui.draw_floor_bounds(game.world, camera_x, camera_y)
                player_lines = [call.args[:4] for call in draw.call_args_list
                                if call.args[4:] == PLAYER_BOUNDS_COLOR]
                self.assertCountEqual(player_lines,
                                      [(68 - camera_x, -44 - camera_y, 2492 - camera_x, -44 - camera_y),
                                       (2492 - camera_x, -44 - camera_y, 2492 - camera_x, 239 - camera_y),
                                       (2492 - camera_x, 239 - camera_y, 68 - camera_x, 239 - camera_y),
                                       (68 - camera_x, 239 - camera_y, 68 - camera_x, -44 - camera_y)])
                enemy_lines = [call.args[:4] for call in draw.call_args_list
                               if call.args[4:] == ENEMY_BOUNDS_COLOR]
                xs = [x + camera_x for ax, _, bx, _ in enemy_lines for x in (ax, bx)]
                ys = [y + camera_y for _, ay, _, by in enemy_lines for y in (ay, by)]
                self.assertEqual((min(xs), max(xs), min(ys), max(ys)), (88, 2472, -44, 239))

    def test_floor300_factory_exterior_outline_matches_full_asphalt_and_both_actor_paddings(self):
        game = scene()
        game.world.select_stage(5)
        game.ui.floor_bounds_visible = True
        for camera_x, camera_y in ((0, 0), (640, 8), (1280, 120)):
            for height in (0, 240):
                game.world.player.jump_height = height
                with patch("pico2d.draw_line") as draw:
                    game.ui.draw_floor_bounds(game.world, camera_x, camera_y)
                player_lines = [call.args[:4] for call in draw.call_args_list
                                if call.args[4:] == PLAYER_BOUNDS_COLOR]
                self.assertCountEqual(player_lines,
                                      [(68 - camera_x, -camera_y, 2492 - camera_x, -camera_y),
                                       (2492 - camera_x, -camera_y, 2492 - camera_x, 284 - camera_y),
                                       (2492 - camera_x, 284 - camera_y, 68 - camera_x, 284 - camera_y),
                                       (68 - camera_x, 284 - camera_y, 68 - camera_x, -camera_y)])
                enemy_lines = [call.args[:4] for call in draw.call_args_list
                               if call.args[4:] == ENEMY_BOUNDS_COLOR]
                xs = [x + camera_x for ax, _, bx, _ in enemy_lines for x in (ax, bx)]
                ys = [y + camera_y for _, ay, _, by in enemy_lines for y in (ay, by)]
                self.assertEqual((min(xs), max(xs), min(ys), max(ys)), (88, 2472, 0, 284))

    def test_factory_inside_full_floor_outline_matches_player_and_researcher_foot_bounds(self):
        game = scene()
        game.world.select_stage(6)
        game.ui.floor_bounds_visible = True
        for camera_x, camera_y in ((0, -44), (640, 8), (1280, 120)):
            for height in (0, 240):
                game.world.player.jump_height = height
                with patch("pico2d.draw_line") as draw:
                    game.ui.draw_floor_bounds(game.world, camera_x, camera_y)
                for color, padding in ((PLAYER_BOUNDS_COLOR, 68), (ENEMY_BOUNDS_COLOR, 88)):
                    lines = [call.args[:4] for call in draw.call_args_list if call.args[4:] == color]
                    xs = [x + camera_x for ax, _, bx, _ in lines for x in (ax, bx)]
                    ys = [y + camera_y for _, ay, _, by in lines for y in (ay, by)]
                    self.assertEqual((min(xs), max(xs), min(ys), max(ys)), (padding, 2560 - padding, -3, 172))

    def test_both_lab_floor300_outlines_match_player_and_shield_soldier_foot_bounds(self):
        game = scene()
        game.ui.floor_bounds_visible = True
        for index, bottom, top in ((8, -109, 178), (9, -48, 239)):
            game.world.select_stage(index)
            for camera_x, camera_y in ((0, -180), (640, 8), (1280, 120)):
                with patch("pico2d.draw_line") as draw:
                    game.ui.draw_floor_bounds(game.world, camera_x, camera_y)
                for color, padding in ((PLAYER_BOUNDS_COLOR, 68), (ENEMY_BOUNDS_COLOR, 88)):
                    lines = [call.args[:4] for call in draw.call_args_list if call.args[4:] == color]
                    xs = [x + camera_x for ax, _, bx, _ in lines for x in (ax, bx)]
                    ys = [y + camera_y for _, ay, _, by in lines for y in (ay, by)]
                    self.assertEqual((min(xs), max(xs), min(ys), max(ys)),
                                     (padding, 2560 - padding, bottom, top))

    def test_stair_free_loading_dock_outline_matches_the_full_concrete_floor(self):
        game = scene()
        game.world.select_stage(4)
        game.ui.floor_bounds_visible = True
        camera_x, camera_y = 640, 8
        with patch("pico2d.draw_line") as draw:
            game.ui.draw_floor_bounds(game.world, camera_x, camera_y)
        player_lines = [call.args[:4] for call in draw.call_args_list
                        if call.args[4:] == PLAYER_BOUNDS_COLOR]
        self.assertCountEqual(player_lines,
                              [(68 - camera_x, 45 - camera_y, 2492 - camera_x, 45 - camera_y),
                               (2492 - camera_x, 45 - camera_y, 2492 - camera_x, 258 - camera_y),
                               (2492 - camera_x, 258 - camera_y, 68 - camera_x, 258 - camera_y),
                               (68 - camera_x, 258 - camera_y, 68 - camera_x, 45 - camera_y)])

    def test_both_new_city_outlines_cover_the_full_sidewalk_and_road(self):
        game = scene()
        game.ui.floor_bounds_visible = True
        for index, top in ((2, 247), (3, 279)):
            game.world.select_stage(index)
            for camera_x, camera_y in ((0, -44), (640, 8), (1280, 120)):
                with patch("pico2d.draw_line") as draw:
                    game.ui.draw_floor_bounds(game.world, camera_x, camera_y)
                player_lines = [call.args[:4] for call in draw.call_args_list
                                if call.args[4:] == PLAYER_BOUNDS_COLOR]
                self.assertCountEqual(player_lines,
                                      [(68 - camera_x, -44 - camera_y, 2492 - camera_x, -44 - camera_y),
                                       (2492 - camera_x, -44 - camera_y, 2492 - camera_x, top - camera_y),
                                       (2492 - camera_x, top - camera_y, 68 - camera_x, top - camera_y),
                                       (68 - camera_x, top - camera_y, 68 - camera_x, -44 - camera_y)])

    def test_convex_floor_uses_its_actual_inset_polygon_not_a_bounding_rectangle(self):
        game = scene()
        game.ui.floor_bounds_visible = True
        area = WalkableArea(((0, 56), (1000, 56), (1000, 140), (800, 268), (0, 268)))
        game.world.stage.walkable = area
        vertices = area.inset(game.world.player.boundary_padding)
        with patch("pico2d.draw_line") as draw:
            game.ui.draw_floor_bounds(game.world, 0, 0)
        lines = [call.args[:4] for call in draw.call_args_list
                 if call.args[4:] == PLAYER_BOUNDS_COLOR]
        self.assertEqual(lines[:len(vertices)], [(*point, *vertices[(index + 1) % len(vertices)])
                                                for index, point in enumerate(vertices)])
        self.assertEqual(len(lines), len(vertices))


if __name__ == "__main__":
    unittest.main()
