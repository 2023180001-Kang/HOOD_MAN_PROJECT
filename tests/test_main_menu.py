import ctypes
import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import pico2d
from sdl2 import (
    SDL_BUTTON_LEFT, SDL_BUTTON_MIDDLE, SDL_BUTTON_RIGHT, SDL_Event,
    SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST, SDL_WINDOWEVENT_LEAVE,
)

import config
from assets import Assets
from game import Game, KEYS
from main_menu import MainMenu
from ui import UI
from world import World


def mouse_event(kind, x, y, button=SDL_BUTTON_LEFT):
    event = SDL_Event()
    event.type = kind
    target = event.motion if kind == pico2d.SDL_MOUSEMOTION else event.button
    target.x, target.y = int(x), config.SCREEN_HEIGHT - 1 - int(y)
    if kind != pico2d.SDL_MOUSEMOTION:
        target.button = button
    return event


def process_menu_events(game, *events, menu_screen=True):
    queue = iter(events)

    def poll(pointer):
        event = next(queue, None)
        if event is None:
            return 0
        ctypes.memmove(pointer, ctypes.byref(event), ctypes.sizeof(event))
        return 1

    with patch("game.SDL_PollEvent", side_effect=poll):
        return Game.handle_events(game, menu_screen=menu_screen)


class MainMenuTests(unittest.TestCase):
    def setUp(self):
        self.menu = MainMenu()
        self.assets = SimpleNamespace(images={
            name: Mock(w=1856, h=176)
            for name in (config.MAIN_MENU_IMAGE,
                         *(image for _, image in config.MAIN_MENU_BUTTONS))
        })

    def test_buttons_follow_requested_order_on_the_right(self):
        self.assertEqual(
            [(button.action, button.image_name) for button in self.menu.buttons],
            [("game_start", "menu_game_start.png"), ("stage_progress", "menu_stage_progress.png"),
             ("controls", "menu_controls.png"), ("backpack", "menu_backpack.png")],
        )
        for index, button in enumerate(self.menu.buttons):
            self.assertGreaterEqual(button.x - button.width / 2, config.SCREEN_WIDTH / 2)
            self.assertEqual(button.x + button.width / 2,
                             config.SCREEN_WIDTH - config.MAIN_MENU_RIGHT_MARGIN)
            self.assertGreaterEqual(button.y - button.height / 2, 0)
            self.assertLessEqual(button.y + button.height / 2, config.SCREEN_HEIGHT)
            self.assertAlmostEqual(button.width / button.height, 928 / 176)
            if index:
                previous = self.menu.buttons[index - 1]
                self.assertEqual(previous.y - previous.height / 2 - button.y - button.height / 2,
                                 config.MAIN_MENU_BUTTON_GAP)

    def test_initial_draw_fills_background_and_uses_only_black_frames(self):
        self.menu.draw(self.assets)
        self.assets.images[config.MAIN_MENU_IMAGE].draw.assert_called_once_with(
            config.SCREEN_WIDTH / 2, config.SCREEN_HEIGHT / 2,
            config.SCREEN_WIDTH, config.SCREEN_HEIGHT,
        )
        for button in self.menu.buttons:
            self.assets.images[button.image_name].clip_draw.assert_called_once_with(
                0, 0, 928, 176, button.x, button.y, button.width, button.height,
            )

    def test_hover_uses_only_that_buttons_gray_frame_without_moving_it(self):
        for hovered in self.menu.buttons:
            self.menu.move_pointer(hovered.x, hovered.y)
            self.menu.draw(self.assets)
            for button in self.menu.buttons:
                self.assets.images[button.image_name].clip_draw.assert_called_with(
                    928 if button is hovered else 0, 0, 928, 176,
                    button.x, button.y, button.width, button.height,
                )

    def test_moving_off_buttons_and_clearing_hover_restore_black(self):
        button = self.menu.buttons[0]
        for clear in (lambda: self.menu.move_pointer(10, 10), self.menu.clear_hover):
            self.menu.move_pointer(button.x, button.y)
            clear()
            self.assertIsNone(self.menu.hovered_button)
            self.menu.draw(self.assets)
            for item in self.menu.buttons:
                self.assertEqual(self.assets.images[item.image_name].clip_draw.call_args.args[0], 0)

    def test_play_buttons_select_a_scene_and_submenus_have_a_back_button(self):
        for button in self.menu.buttons:
            self.assertEqual(self.menu.click(button.x, button.y), button.action in ("controls", "game_start"))
            if button.action in ("backpack", "stage_progress"):
                self.assertEqual(self.menu.screen, button.action)
                self.assertIsNone(self.menu.hovered_button)
                back, = self.menu.buttons
                self.assertFalse(self.menu.click(back.x, back.y))
                self.assertEqual(self.menu.screen, "main")
            else:
                self.assertIs(self.menu.hovered_button, button)
        self.assertFalse(self.menu.click(10, 10))
        self.assertIsNone(self.menu.hovered_button)

    def test_hit_bounds_match_drawn_rectangles_and_gaps_are_inactive(self):
        for button in self.menu.buttons:
            left, right = button.x - button.width / 2, button.x + button.width / 2
            bottom, top = button.y - button.height / 2, button.y + button.height / 2
            self.assertTrue(button.contains(left, bottom))
            self.assertTrue(button.contains(right - 1, top - 1))
            for x, y in ((left - 1, button.y), (right, button.y),
                         (button.x, bottom - 1), (button.x, top)):
                self.assertFalse(button.contains(x, y))
        for upper, lower in zip(self.menu.buttons, self.menu.buttons[1:]):
            self.assertFalse(self.menu.click(upper.x, (upper.y + lower.y) / 2))

    def test_old_title_is_archived_without_changing_original_bytes(self):
        path = config.ROOT / config.ARCHIVED_TITLE_IMAGE
        self.assertFalse((config.ROOT / path.name).exists())
        self.assertEqual(
            hashlib.sha256(path.read_bytes()).hexdigest(),
            "5544a7fe218bd44b4de9850aee52c5e519b2274c7f5e162955b498b310b6ff95",
        )

    def test_supplied_menu_art_preserves_original_bytes_and_two_frame_dimensions(self):
        hashes = {
            config.MAIN_MENU_IMAGE: "1190f788db3b24c6bf7092a5751dce3acc3632e353b254295c583119c9ed173d",
            "menu_game_start.png": "88f45c91098c68f68a7fa2707c7a79d5f7b4bb14d7593ab7e5f68a22eb26ac7f",
            "menu_stage_progress.png": "aa3b3e12100d4e2ba1488462f3f171d20b51c23ce18c873571bd9f821074e390",
            "menu_controls.png": "57a99fb572a98427205402b716ed288cf2ba3f055a4e9e3d32620bc72514dc58",
            "menu_backpack.png": "43efc604cdc7997a44e72034d4928e7c24c6989624d44575895c91cd9b30ff7b",
        }
        for name, digest in hashes.items():
            path = config.ROOT / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with Image.open(path) as image:
                self.assertEqual(image.size, (1280, 720) if name == config.MAIN_MENU_IMAGE
                                 else (1856, 176))
                self.assertEqual(image.mode, "RGBA")

    def test_shared_loader_includes_menu_but_never_loads_archived_title(self):
        with patch("assets.pico2d.load_image", side_effect=lambda path: Mock()) as load, \
                patch("assets.pico2d.load_font", return_value=None):
            assets = Assets()
        loaded = [call.args[0] for call in load.call_args_list]
        for name in (config.MAIN_MENU_IMAGE, config.STAGE_PROGRESS_IMAGE, config.STAGE_LOCK_IMAGE,
                     *(image for _, image in config.MAIN_MENU_BUTTONS)):
            self.assertIn(name, assets.images)
            self.assertEqual(loaded.count(str(config.ROOT / name)), 1)
        self.assertNotIn(config.ARCHIVED_TITLE_IMAGE, assets.images)
        self.assertNotIn(str(config.ROOT / config.ARCHIVED_TITLE_IMAGE), loaded)


class MainMenuFlowTests(unittest.TestCase):
    def setUp(self):
        self.game = Game.__new__(Game)
        self.game.menu = MainMenu()
        self.game.world = World()
        self.game.ui = UI()
        self.game.running = True
        self.game._menu_requested = False
        self.game._escape_held = False

    def process(self, *events):
        return process_menu_events(self.game, *events)

    def test_sdl_mouse_coordinates_hover_and_click_the_matching_button(self):
        for button in self.game.menu.buttons:
            self.assertFalse(self.process(mouse_event(pico2d.SDL_MOUSEMOTION, button.x, button.y)))
            self.assertIs(self.game.menu.hovered_button, button)
            self.assertEqual(self.process(mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, button.x, button.y)),
                             button.action in ("controls", "game_start"))
            if self.game.menu.screen != "main":
                back, = self.game.menu.buttons
                self.assertFalse(self.process(mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, back.x, back.y)))
        self.process(mouse_event(pico2d.SDL_MOUSEMOTION, 0, 0))
        self.assertIsNone(self.game.menu.hovered_button)

    def test_opening_progress_cancels_pending_start_and_hides_main_buttons(self):
        start, progress, _, _ = self.game.menu.main_buttons
        start_click = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, start.x, start.y)
        progress_click = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, progress.x, progress.y)
        self.assertFalse(self.process(start_click, progress_click, start_click))
        self.assertEqual(self.game.menu.screen, "stage_progress")
        back, = self.game.menu.buttons
        self.assertTrue(self.process(mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, back.x, back.y), start_click))

    def test_right_middle_release_and_outside_clicks_cannot_start(self):
        button = self.game.menu.buttons[0]
        for kind, mouse_button, x, y in (
            (pico2d.SDL_MOUSEBUTTONDOWN, SDL_BUTTON_RIGHT, button.x, button.y),
            (pico2d.SDL_MOUSEBUTTONDOWN, SDL_BUTTON_MIDDLE, button.x, button.y),
            (pico2d.SDL_MOUSEBUTTONUP, SDL_BUTTON_LEFT, button.x, button.y),
            (pico2d.SDL_MOUSEBUTTONDOWN, SDL_BUTTON_LEFT, 20, 20),
        ):
            self.game.menu.move_pointer(button.x, button.y)
            self.assertFalse(self.process(mouse_event(kind, x, y, mouse_button)))

    def test_keyboard_inputs_before_and_after_start_click_are_not_buffered(self):
        events = []
        for key in KEYS:
            for kind in (pico2d.SDL_KEYDOWN, pico2d.SDL_KEYUP):
                event = SDL_Event()
                event.type, event.key.keysym.sym = kind, key
                events.append(event)
        self.assertFalse(self.process(*events))
        button = self.game.menu.buttons[0]
        events.insert(len(events) // 2, mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, button.x, button.y))
        self.assertTrue(self.process(*events))
        self.assertFalse(self.game.world.controls.held)
        self.assertFalse(self.game.world.controls.pressed)
        self.assertEqual(self.game.world.elapsed, 0)

    def test_mouse_leave_and_focus_loss_clear_hover_and_pending_input(self):
        button = self.game.menu.buttons[0]
        for kind in (SDL_WINDOWEVENT_LEAVE, SDL_WINDOWEVENT_FOCUS_LOST):
            self.game.menu.move_pointer(button.x, button.y)
            event = SDL_Event()
            event.type, event.window.event = SDL_WINDOWEVENT, kind
            self.assertFalse(self.process(event))
            self.assertIsNone(self.game.menu.hovered_button)
        self.game.world.controls.press("right")
        self.game.world.controls.press("spawn_9")
        self.assertFalse(self.process(
            mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, button.x, button.y), event,
        ))
        self.assertFalse(self.game.world.controls.held)
        self.assertFalse(self.game.world.controls.pressed)

    def test_quit_wins_over_start_click_in_either_order(self):
        button = self.game.menu.buttons[0]
        click = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, button.x, button.y)
        quit_event = SDL_Event()
        quit_event.type = pico2d.SDL_QUIT
        for events in ((click, quit_event), (quit_event, click)):
            self.game.running = True
            self.assertFalse(self.process(*events))
            self.assertFalse(self.game.running)
            self.assertEqual(self.game.world.elapsed, 0)

    def test_menu_waits_beyond_old_timeout_then_resets_to_first_stage_on_click(self):
        world = self.game.world
        world.select_stage(11)
        player = world.player
        player.hp = 200
        world.controls.press("spawn_9")
        waited = 0.0

        def pause(dt):
            nonlocal waited
            waited += dt

        def handle(*, menu_screen):
            self.assertTrue(menu_screen)
            self.assertEqual(world.elapsed, 0)
            self.assertEqual((world.stage_index, player.hp), (11, 200))
            self.assertFalse(world.controls.held)
            self.assertFalse(world.controls.pressed)
            return waited >= 2.5

        with patch.object(self.game, "handle_events", side_effect=handle), \
                patch.object(self.game, "draw_main_menu") as draw, \
                patch.object(world, "update") as update, \
                patch("game.sleep", side_effect=pause):
            self.game.show_main_menu()
        self.assertGreater(draw.call_count, 2.5 * config.TARGET_FPS)
        update.assert_not_called()
        self.assertIsNot(world.player, player)
        self.assertEqual((world.stage_index, world.player.hp, world.player.state), (0, 500, "IDLE"))
        self.assertFalse(world.stage_loading)
        self.assertTrue(all(not stage.enemies and len(stage.drop_items) == 15 for stage in world.stages))

    def test_closed_game_does_not_display_or_wait_in_menu(self):
        self.game.running = False
        with patch.object(self.game, "draw_main_menu") as draw, \
                patch.object(self.game, "handle_events") as handle:
            self.game.show_main_menu()
        draw.assert_not_called()
        handle.assert_not_called()


if __name__ == "__main__":
    unittest.main()
