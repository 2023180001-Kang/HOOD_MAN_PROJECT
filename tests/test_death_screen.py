import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pico2d
from sdl2 import SDL_BUTTON_RIGHT

import config
from tests.test_main_menu import mouse_event, process_menu_events
from tests.test_menu_return import click_event, key_event, scene


class DeathScreenTests(unittest.TestCase):
    def setUp(self):
        self.game = scene()
        self.world = self.game.world
        self.world.starting_hp, self.world.starting_max_hp = 370, 550
        self.world.starting_weapon = "sword"
        self.world.reset(stage_index=3)
        self.player = self.world.player
        self.player.take_damage(self.player.hp)
        self.screen = self.game.ui.death_screen
        self.retry, self.menu = self.screen.buttons

    def events(self, *events):
        process_menu_events(self.game, *events, menu_screen=False)

    def test_message_buttons_and_hover_use_the_supplied_frames_in_order(self):
        title = Mock(w=4096, h=128)
        buttons = Mock(w=2048, h=256)
        assets = SimpleNamespace(images={config.DEATH_TITLE_IMAGE: title, config.DEATH_BUTTONS_IMAGE: buttons})
        self.game.ui.details_visible = False
        with patch("death_screen.draw_black_overlay") as dim, patch("death_screen.SDL_SetTextureBlendMode"):
            self.game.update(0.3)
            self.screen.draw(assets)
            self.assertGreater(dim.call_args.args[0], 0)
            self.assertEqual(title.clip_draw.call_args.args[4:6], (640, 360))
            buttons.clip_draw.assert_not_called()
            self.events(click_event(self.retry), click_event(self.menu))
            self.assertIs(self.world.player, self.player)
            self.assertFalse(self.game._menu_requested)

            self.events(mouse_event(pico2d.SDL_MOUSEMOTION, self.retry.x, self.retry.y))
            self.game.update(0.5)
            self.screen.draw(assets)
            highlighted = buttons.clip_draw.call_args.args
            self.assertEqual(highlighted[4:6], (self.retry.x, self.retry.y))
            self.events(click_event(self.menu))
            self.assertFalse(self.game._menu_requested)
            self.events(mouse_event(pico2d.SDL_MOUSEMOTION, self.menu.x, self.menu.y))
            self.game.update(0.4)
            buttons.clip_draw.reset_mock()
            self.screen.draw(assets)
            idle, hovered = [call.args for call in buttons.clip_draw.call_args_list]
            self.assertGreater(highlighted[0], idle[0])
            self.assertGreater(hovered[0], idle[0])
            self.assertGreater(idle[1], hovered[1])  # RETRY uses the upper source row.
            self.assertEqual(hovered[4:6], (self.menu.x, self.menu.y))

    def test_retry_rebuilds_the_dead_map_with_starting_gear_and_keeps_other_maps(self):
        previous = self.world.stages[2]
        self.world.cleared_stages.add(2)
        before = self.world.stage
        before.arrows_visible = True
        self.game.update(1.2)
        self.events(mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, self.retry.x, self.retry.y, SDL_BUTTON_RIGHT))
        self.assertIs(self.world.player, self.player)
        self.events(click_event(self.retry), key_event(pico2d.SDLK_9))
        self.assertFalse(self.game._menu_requested)
        self.assertEqual(self.world.stage_index, 3)
        self.assertIsNot(self.world.stage, before)
        self.assertIs(self.world.stages[2], previous)
        self.assertIn(2, self.world.cleared_stages)
        self.assertEqual((self.world.player.hp, self.world.player.max_hp, self.world.player.weapon),
                         (370, 550, "sword"))
        self.assertEqual(len(self.world.enemies), 4)
        self.assertFalse(self.world.stage.arrows_visible or self.world.controls.pressed)
        self.assertEqual(self.screen.elapsed, 0)

    def test_main_menu_click_requests_menu_without_retrying(self):
        self.game.update(1.2)
        self.events(click_event(self.menu), click_event(self.retry))
        self.assertTrue(self.game._menu_requested)
        self.assertIs(self.world.player, self.player)
        self.assertEqual(self.world.stage_index, 3)
