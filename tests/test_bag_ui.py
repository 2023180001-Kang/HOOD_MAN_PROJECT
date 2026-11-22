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
                         *(image for _, image, _ in config.BAG_ITEM_SPECS),
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

    def test_shared_loader_loads_bag_background_button_and_items_once(self):
        with patch("assets.pico2d.load_image", side_effect=lambda path: Mock()) as load, \
                patch("assets.pico2d.load_font", return_value=None):
            assets = Assets()
        loaded = [call.args[0] for call in load.call_args_list]
        for name in (config.BAG_UI_IMAGE, config.BAG_BUTTON_IMAGE,
                     *(image for _, image, _ in config.BAG_ITEM_SPECS)):
            self.assertIn(name, assets.images)
            self.assertEqual(loaded.count(str(config.ROOT / name)), 1)

    def test_items_match_requested_left_to_right_order(self):
        self.assertEqual(
            [(kind, image) for kind, image, _ in config.BAG_ITEM_SPECS],
            [("steel_club", "steel_club.png"), ("dual_black_batons", "dual_black_batons_pico2d.png"),
             ("axe", "axe_weapon.png"), ("pistol", "pistol_item_256.png"),
             ("shield_item", "HOOD_MAN_shield_item_256x256.png"),
             ("ar_rifle", "ar_rifle_item_256.png")],
        )
        self.assertEqual(len(config.BAG_ITEM_SPECS), len(config.BAG_ITEM_SLOT_RECTS))
        self.assertEqual(len(config.BAG_ITEM_SPECS), 6)
        for first, second in zip(config.BAG_ITEM_SLOT_RECTS, config.BAG_ITEM_SLOT_RECTS[1:]):
            self.assertLess(first[2], second[0])

    def test_item_clips_trim_transparent_padding_and_keep_original_files(self):
        originals = {
            "steel_club": ((2172, 724), "efcfcc648e1fa63fa1b52532ed31de415dda19a4c35a29a7613b8a72a67da743"),
            "dual_black_batons": ((512, 512), "f2545fb5941d486b206b1dd7f52c8c885003c80fdaf8bc6d7d4efa985e3f6b3c"),
            "axe": ((1254, 1254), "6922c22be97be0109d040238f8414d2a00539ba14d1c8811f6b55ae7b4c60a6e"),
            "pistol": ((256, 256), "0ac560814a59cba562bcd57a620de5ae1433f75dc146433068358dc37df29003"),
            "shield_item": ((256, 256), "a4a18bab602767fc49c506272bc540575e8e8aa0dc7f127367540cf4fb35e662"),
            "ar_rifle": ((256, 256), "27104451c8bcce2eb57387643d7a186fa03a2870d25394a7ed6fe7bb3e55cab7"),
        }
        for kind, name, (left, bottom, width, height) in config.BAG_ITEM_SPECS:
            path = config.ROOT / name
            size, digest = originals[kind]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with Image.open(path) as image:
                self.assertEqual((image.size, image.mode), (size, "RGBA"))
                bounds = image.getchannel("A").point(lambda alpha: 255 if alpha > 8 else 0).getbbox()
                self.assertEqual((left, image.height - bottom - height, left + width,
                                  image.height - bottom), bounds)

    def test_items_draw_in_order_centered_inside_slots_without_distortion(self):
        calls = []
        for _, name, _ in config.BAG_ITEM_SPECS:
            self.assets.images[name].clip_draw.side_effect = (
                lambda *args, image=name: calls.append((image, args)))
        self.open_bag()
        self.menu.draw(self.assets)
        self.assertEqual([name for name, _ in calls], [name for _, name, _ in config.BAG_ITEM_SPECS])
        for (_, args), (_, _, clip), (left, top, right, bottom) in zip(
                calls, config.BAG_ITEM_SPECS, config.BAG_ITEM_SLOT_RECTS):
            self.assertEqual(args[:4], clip)
            x, y, width, height = args[4:]
            self.assertEqual((x, y), ((left + right) / 2,
                                     config.SCREEN_HEIGHT - (top + bottom) / 2))
            self.assertAlmostEqual(width / height, clip[2] / clip[3])
            available_width = right - left - 2 * config.BAG_ITEM_SLOT_PADDING
            available_height = bottom - top - 2 * config.BAG_ITEM_SLOT_PADDING
            self.assertLessEqual(width, available_width + 1e-9)
            self.assertLessEqual(height, available_height + 1e-9)
            self.assertTrue(abs(width - available_width) < 1e-9
                            or abs(height - available_height) < 1e-9)

    def test_item_images_only_draw_while_bag_is_open(self):
        self.menu.draw(self.assets)
        for _, name, _ in config.BAG_ITEM_SPECS:
            self.assets.images[name].clip_draw.assert_not_called()
        self.open_bag()
        self.menu.draw(self.assets)
        for _, name, _ in config.BAG_ITEM_SPECS:
            self.assets.images[name].clip_draw.assert_called_once()
            self.assets.images[name].clip_draw.reset_mock()
        back = self.menu.bag_back_button
        self.menu.click(back.x, back.y)
        self.menu.draw(self.assets)
        for _, name, _ in config.BAG_ITEM_SPECS:
            self.assets.images[name].clip_draw.assert_not_called()

    def test_item_slots_are_display_only_not_new_buttons(self):
        self.open_bag()
        for left, top, right, bottom in config.BAG_ITEM_SLOT_RECTS:
            self.assertFalse(self.menu.click((left + right) / 2,
                                            config.SCREEN_HEIGHT - (top + bottom) / 2))
            self.assertTrue(self.menu.bag_open)
            self.assertIsNone(self.menu.hovered_button)
        self.assertEqual(self.menu.buttons, (self.menu.bag_back_button,))

    def test_item_layout_is_unchanged_during_back_button_hover(self):
        self.open_bag()
        self.menu.draw(self.assets)
        calls = [self.assets.images[name].clip_draw.call_args
                 for _, name, _ in config.BAG_ITEM_SPECS]
        back = self.menu.bag_back_button
        self.menu.move_pointer(back.x, back.y)
        self.menu.draw(self.assets)
        self.assertEqual(calls, [self.assets.images[name].clip_draw.call_args
                                 for _, name, _ in config.BAG_ITEM_SPECS])


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
