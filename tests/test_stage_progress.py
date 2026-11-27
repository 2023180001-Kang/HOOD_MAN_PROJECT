import unittest
from unittest.mock import Mock, patch

import pico2d
from sdl2 import SDL_BUTTON_RIGHT

import config
from tests.test_main_menu import mouse_event, process_menu_events
from tests.test_menu_return import click_event, key_event, scene


# Label centers on the supplied artwork and the map each label promises.
REGIONS = (
    ("WHO", 129, config.STAGE_IMAGE),
    ("WHEN", 336, config.CITY_STAGE_IMAGES[0]),
    ("WHERE", 540, config.FACTORY_OUTSIDE_IMAGE),
    ("WHAT", 745, config.FACTORY_INSIDE_IMAGES[0]),
    ("HOW", 950, config.LAB_STAGE_IMAGES[0]),
    ("WHY", 1157, config.BOSS_STAGE_IMAGES[0]),
)


class StageProgressTests(unittest.TestCase):
    def test_six_locks_and_clicks_follow_p_only_in_progress_screen(self):
        game = scene()
        menu = game.menu
        p = pico2d.SDLK_p
        progress = click_event(menu.main_buttons[1])
        assets = Mock()
        lock = Mock()
        assets.images = {config.STAGE_LOCK_IMAGE: lock, config.STAGE_PROGRESS_IMAGE: Mock(),
                         config.BAG_BUTTON_IMAGE: Mock(w=128, h=64)}
        process_menu_events(game, key_event(p), key_event(p, down=False), progress)
        for unlocked in (False, True, False):
            with self.subTest(unlocked=unlocked):
                self.assertEqual(menu.stages_unlocked, unlocked)
                lock.reset_mock()
                menu.draw(assets)
                self.assertEqual([call.args for call in lock.draw.call_args_list],
                                 [] if unlocked else [(x, 320) for _, x, _ in REGIONS])
                for _, x, _ in REGIONS:
                    click = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, x, 360)
                    self.assertEqual(process_menu_events(game, click), unlocked)
                process_menu_events(game, key_event(p), key_event(p, repeat=True), key_event(p, down=False))
        self.assertFalse(game.world.controls.held or game.world.controls.pressed)
        self.assertFalse(game.world.player.invincible)

    def test_each_panel_starts_a_fresh_campaign_directly_in_its_region(self):
        game = scene()
        game.menu.equipped_weapon = "sword"
        for label, x, image in REGIONS:
            with self.subTest(region=label):
                events = [click_event(game.menu.main_buttons[1])]
                if not game.menu.stages_unlocked:
                    events.extend([key_event(pico2d.SDLK_p), key_event(pico2d.SDLK_p, down=False)])
                events.append(mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, x, 360))

                def choose_region(*, menu_screen):
                    self.assertTrue(process_menu_events(game, *events, menu_screen=menu_screen))
                    return True

                with patch.object(game, "draw_main_menu"), patch.object(game, "handle_events", choose_region):
                    game.show_main_menu()
                world = game.world
                self.assertEqual((world.stage.image_name, world.player.weapon), (image, "sword"))
                self.assertEqual(len(world.enemies), 4)
                self.assertTrue(all(not stage.encounter_started for stage in world.stages if stage is not world.stage))
        process_menu_events(game, key_event(pico2d.SDLK_p), menu_screen=False)
        world.step(config.FIXED_DT)
        self.assertTrue(world.player.invincible)
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertEqual(world.stage_index, 0)

    def test_gaps_wrong_mouse_button_relock_and_back_cannot_launch_a_region(self):
        game = scene()
        menu = game.menu
        p = pico2d.SDLK_p
        progress = click_event(menu.main_buttons[1])
        back = click_event(menu.bag_back_button)
        city = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, 336, 360)
        self.assertFalse(process_menu_events(game, progress, key_event(p), key_event(p, down=False)))
        for x, y in ((230, 360), (336, 410), (336, 285)):
            self.assertFalse(process_menu_events(game, mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, x, y)))
        self.assertFalse(process_menu_events(game, mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, 336, 360, SDL_BUTTON_RIGHT)))
        self.assertFalse(process_menu_events(game, city, key_event(p), key_event(p, down=False), city))
        self.assertFalse(process_menu_events(game, key_event(p), key_event(p, down=False), city, back))
        self.assertTrue(process_menu_events(game, click_event(menu.main_buttons[0])))
        self.assertEqual((menu.launch_action, menu.launch_stage), ("game_start", 0))
