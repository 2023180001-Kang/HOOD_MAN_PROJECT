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
from tests.test_main_menu import mouse_event, process_menu_events
from ui import UI
from world import World


class BagUITests(unittest.TestCase):
    def setUp(self):
        self.menu = MainMenu()
        self.assets = SimpleNamespace(images={
            name: Mock(w=1856, h=176)
            for name in (config.MAIN_MENU_IMAGE, config.BAG_UI_IMAGE,
                         *(image for _, image in config.MAIN_MENU_BUTTONS))
        })
        self.assets.images[config.BAG_BUTTON_IMAGE] = Mock(w=124, h=58)

    def open_bag(self):
        button = self.menu.main_buttons[-1]
        self.assertFalse(self.menu.click(button.x, button.y))

    def test_backpack_opens_bag_without_requesting_gameplay(self):
        self.open_bag()
        self.assertTrue(self.menu.bag_open)
        self.assertIsNone(self.menu.hovered_button)
        self.assertEqual(self.menu.buttons, (self.menu.bag_back_button,))
        self.menu.draw(self.assets)
        self.assets.images[config.BAG_UI_IMAGE].draw.assert_called_once_with(640, 360, 1280, 720)
        self.assets.images[config.MAIN_MENU_IMAGE].draw.assert_not_called()
        for button in self.menu.main_buttons:
            self.assets.images[button.image_name].clip_draw.assert_not_called()

    def test_back_button_is_native_size_at_top_left_beside_the_title(self):
        button = self.menu.bag_back_button
        self.assertEqual((button.x, button.y, button.width, button.height), (63, 667, 62, 58))
        self.assertEqual(button.x - button.width / 2, config.BAG_BACK_BUTTON_LEFT)
        self.assertEqual(config.SCREEN_HEIGHT - button.y - button.height / 2,
                         config.BAG_BACK_BUTTON_TOP)
        self.assertLess(button.x + button.width / 2, 134)  # Original title icon begins at x=134.
        self.assertAlmostEqual(button.width / button.height, 62 / 58)

    def test_bag_initially_draws_the_black_frame(self):
        self.open_bag()
        self.menu.draw(self.assets)
        self.assets.images[config.BAG_BUTTON_IMAGE].clip_draw.assert_called_once_with(
            0, 0, 62, 58, 63, 667, 62, 58,
        )

    def test_back_hover_uses_gray_then_restores_black_without_moving(self):
        self.open_bag()
        button = self.menu.bag_back_button
        self.menu.move_pointer(button.x, button.y)
        self.menu.draw(self.assets)
        self.assets.images[config.BAG_BUTTON_IMAGE].clip_draw.assert_called_with(
            62, 0, 62, 58, 63, 667, 62, 58,
        )
        for clear in (lambda: self.menu.move_pointer(640, 360), self.menu.clear_hover):
            self.menu.move_pointer(button.x, button.y)
            clear()
            self.menu.draw(self.assets)
            self.assets.images[config.BAG_BUTTON_IMAGE].clip_draw.assert_called_with(
                0, 0, 62, 58, 63, 667, 62, 58,
            )
            self.assertTrue(self.menu.bag_open)

    def test_back_click_restores_main_menu_and_clears_hover(self):
        self.open_bag()
        button = self.menu.bag_back_button
        self.assertFalse(self.menu.click(button.x, button.y))
        self.assertFalse(self.menu.bag_open)
        self.assertIsNone(self.menu.hovered_button)
        self.assertIs(self.menu.buttons, self.menu.main_buttons)
        self.menu.draw(self.assets)
        self.assets.images[config.MAIN_MENU_IMAGE].draw.assert_called_once_with(640, 360, 1280, 720)
        self.assets.images[config.BAG_UI_IMAGE].draw.assert_not_called()

    def test_hidden_main_buttons_cannot_start_or_navigate_from_bag(self):
        self.open_bag()
        for button in self.menu.main_buttons:
            self.assertFalse(self.menu.click(button.x, button.y))
            self.assertTrue(self.menu.bag_open)
            self.assertIsNone(self.menu.hovered_button)

    def test_repeated_navigation_and_show_main_reuse_buttons_and_clear_state(self):
        main_buttons, back = self.menu.main_buttons, self.menu.bag_back_button
        for _ in range(20):
            self.open_bag()
            self.menu.move_pointer(back.x, back.y)
            self.assertFalse(self.menu.click(back.x, back.y))
            self.assertIsNone(self.menu.hovered_button)
            self.assertIs(self.menu.buttons, main_buttons)
            self.assertIs(self.menu.bag_back_button, back)
        self.open_bag()
        self.menu.move_pointer(back.x, back.y)
        self.menu.show_main()
        self.assertFalse(self.menu.bag_open)
        self.assertIsNone(self.menu.hovered_button)

    def test_supplied_bag_assets_keep_original_bytes_and_dimensions(self):
        files = (
            (config.BAG_UI_IMAGE, (1280, 720), "RGB",
             "91636e37134ef331a296ee1d88bdfeba1a3a8a166336d13f3dcd7383f27aa87f"),
            (config.BAG_BUTTON_IMAGE, (124, 58), "RGBA",
             "e89fc88704999ff9885d1533b59dda2e15340e99f7dc025a5681cefa9ead5ee2"),
        )
        for name, size, mode, digest in files:
            path = config.ROOT / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with Image.open(path) as image:
                self.assertEqual((image.size, image.mode), (size, mode))

    def test_shared_loader_loads_bag_background_and_button_once(self):
        with patch("assets.pico2d.load_image", side_effect=lambda path: Mock()) as load, \
                patch("assets.pico2d.load_font", return_value=None):
            assets = Assets()
        loaded = [call.args[0] for call in load.call_args_list]
        for name in (config.BAG_UI_IMAGE, config.BAG_BUTTON_IMAGE):
            self.assertIn(name, assets.images)
            self.assertEqual(loaded.count(str(config.ROOT / name)), 1)


class BagUIFlowTests(unittest.TestCase):
    def setUp(self):
        self.game = Game.__new__(Game)
        self.game.menu = MainMenu()
        self.game.world = World()
        self.game.ui = UI()
        self.game.running = True

    def click_event(self, button, mouse_button=SDL_BUTTON_LEFT):
        return mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, button.x, button.y, mouse_button)

    def process(self, *events):
        return process_menu_events(self.game, *events)

    def open_bag(self):
        self.assertFalse(self.process(self.click_event(self.game.menu.main_buttons[-1])))
        self.assertTrue(self.game.menu.bag_open)

    def test_sdl_navigation_and_hover_only_use_visible_buttons(self):
        self.open_bag()
        back = self.game.menu.bag_back_button
        self.assertFalse(self.process(mouse_event(pico2d.SDL_MOUSEMOTION, back.x, back.y)))
        self.assertIs(self.game.menu.hovered_button, back)
        for button in self.game.menu.main_buttons:
            self.assertFalse(self.process(self.click_event(button)))
            self.assertTrue(self.game.menu.bag_open)
        self.assertFalse(self.process(self.click_event(back)))
        self.assertFalse(self.game.menu.bag_open)
        self.assertTrue(self.process(self.click_event(self.game.menu.main_buttons[0])))

    def test_bag_consumes_game_keys_and_ignores_nonleft_back_clicks(self):
        self.open_bag()
        events = []
        for key in (*KEYS, pico2d.SDLK_RETURN, pico2d.SDLK_ESCAPE):
            for kind, repeat in ((pico2d.SDL_KEYDOWN, 0), (pico2d.SDL_KEYDOWN, 1),
                                 (pico2d.SDL_KEYUP, 0)):
                event = SDL_Event()
                event.type, event.key.keysym.sym, event.key.repeat = kind, key, repeat
                events.append(event)
        self.assertFalse(self.process(*events))
        back = self.game.menu.bag_back_button
        for button in (SDL_BUTTON_RIGHT, SDL_BUTTON_MIDDLE):
            self.assertFalse(self.process(self.click_event(back, button)))
            self.assertTrue(self.game.menu.bag_open)
        self.assertFalse(self.process(mouse_event(pico2d.SDL_MOUSEBUTTONUP, back.x, back.y)))
        self.assertTrue(self.game.menu.bag_open)
        self.assertFalse(self.game.world.controls.held)
        self.assertFalse(self.game.world.controls.pressed)
        self.assertEqual(self.game.world.elapsed, 0)

    def test_mouse_leave_and_focus_loss_clear_hover_without_closing_bag(self):
        self.open_bag()
        back = self.game.menu.bag_back_button
        for kind in (SDL_WINDOWEVENT_LEAVE, SDL_WINDOWEVENT_FOCUS_LOST):
            self.process(mouse_event(pico2d.SDL_MOUSEMOTION, back.x, back.y))
            event = SDL_Event()
            event.type, event.window.event = SDL_WINDOWEVENT, kind
            self.assertFalse(self.process(event))
            self.assertTrue(self.game.menu.bag_open)
            self.assertIsNone(self.game.menu.hovered_button)

    def test_navigation_cancels_earlier_start_requests_in_the_same_batch(self):
        start, bag = self.game.menu.main_buttons[0], self.game.menu.main_buttons[-1]
        back = self.game.menu.bag_back_button
        self.assertFalse(self.process(self.click_event(start), self.click_event(bag)))
        self.assertTrue(self.game.menu.bag_open)
        self.game.menu.show_main()
        self.assertFalse(self.process(
            self.click_event(start), self.click_event(bag), self.click_event(back),
        ))
        self.assertFalse(self.game.menu.bag_open)

    def test_full_bag_back_start_loop_freezes_world_until_final_start(self):
        world = self.game.world
        world.select_stage(11)
        player = world.player
        player.hp = 200
        start, bag = self.game.menu.main_buttons[0], self.game.menu.main_buttons[-1]
        back = self.game.menu.bag_back_button
        steps = iter((
            self.click_event(bag),
            mouse_event(pico2d.SDL_MOUSEMOTION, back.x, back.y),
            self.click_event(back, SDL_BUTTON_RIGHT),
            self.click_event(back),
            self.click_event(start),
        ))
        pages = []

        def handle(*, menu_screen):
            self.assertTrue(menu_screen)
            self.assertIs(world.player, player)
            self.assertEqual((world.stage_index, world.elapsed, player.hp), (11, 0, 200))
            return self.process(next(steps))

        with patch.object(self.game, "handle_events", side_effect=handle), \
                patch.object(self.game, "draw_main_menu",
                             side_effect=lambda: pages.append(self.game.menu.bag_open)), \
                patch("game.sleep"), patch.object(world, "update") as update, \
                patch.object(world, "reset", wraps=world.reset) as reset:
            self.game.show_main_menu()
        self.assertEqual(pages, [False, True, True, True, False])
        update.assert_not_called()
        reset.assert_called_once_with()
        self.assertIsNot(world.player, player)
        self.assertEqual((world.stage_index, world.player.hp, world.player.state), (0, 500, "IDLE"))
        self.assertFalse(world.controls.held)
        self.assertFalse(world.controls.pressed)

    def test_quit_from_bag_or_with_back_click_never_starts_gameplay(self):
        for back_first in (False, True):
            self.game.running = True
            self.game.menu.show_main()
            self.open_bag()
            event = SDL_Event()
            event.type = pico2d.SDL_QUIT
            events = [self.click_event(self.game.menu.bag_back_button)] if back_first else []
            with patch.object(self.game.world, "reset") as reset:
                self.assertFalse(self.process(*events, event))
            reset.assert_not_called()
            self.assertFalse(self.game.running)
            self.assertEqual(self.game.run(max_frames=3), 0)


if __name__ == "__main__":
    unittest.main()
