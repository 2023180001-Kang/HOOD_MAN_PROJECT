import unittest
from unittest.mock import Mock, call, patch

import pico2d
from sdl2 import SDL_BUTTON_RIGHT

import config
from tests.helpers import advance
from tests.test_main_menu import mouse_event, process_menu_events
from tests.test_menu_return import click_event, key_event, scene


# Label centers on the supplied artwork and the map each label promises.
REGIONS = (
    ("WHO", 129, config.STAGE_IMAGE),
    ("WHEN", 336, config.CITY_STAGE_IMAGES[0]),
    ("WHERE", 540, config.FACTORY_EXTERIOR_IMAGE),
    ("WHAT", 745, config.FACTORY_INSIDE_IMAGES[0]),
    ("HOW", 950, config.LAB_STAGE_IMAGES[0]),
    ("WHY", 1157, config.BOSS_STAGE_IMAGES[0]),
)


class StageProgressTests(unittest.TestCase):
    def test_only_who_starts_open_and_p_temporarily_opens_the_other_five(self):
        game = scene()
        menu = game.menu
        p = pico2d.SDLK_p
        progress = click_event(menu.main_buttons[1])
        assets = Mock()
        assets.images = {name: Mock(w=32, h=24) for name in
                         (*config.STAGE_STATUS_IMAGES.values(), "stage_status_locked.png",
                          "stage_status_complete.png", config.STAGE_PROGRESS_IMAGE, config.BAG_BUTTON_IMAGE)}
        process_menu_events(game, key_event(p), key_event(p, down=False), progress)
        for unlocked in (False, True, False):
            with self.subTest(unlocked=unlocked):
                self.assertEqual(menu.stages_unlocked, unlocked)
                for image in assets.images.values():
                    image.reset_mock()
                menu.draw(assets)
                for status, name in config.STAGE_STATUS_IMAGES.items():
                    panel_draws = [c for c in assets.images[name].draw.call_args_list if c.args[1] == 320]
                    expected = [call(x, 320) for label, x, _ in REGIONS
                                if status == ("in_progress" if unlocked or label == "WHO" else "locked")]
                    self.assertEqual(panel_draws, expected)
                for legend_text in ("stage_status_locked.png", "stage_status_complete.png"):
                    assets.images[legend_text].draw.assert_called_once()
                for label, x, _ in REGIONS:
                    click = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, x, 360)
                    self.assertEqual(process_menu_events(game, click), unlocked or label == "WHO")
                process_menu_events(game, key_event(p), key_event(p, repeat=True), key_event(p, down=False))
        self.assertFalse(game.world.controls.held or game.world.controls.pressed)
        self.assertFalse(game.world.player.invincible)

    def test_clearing_both_maps_checks_each_region_and_opens_its_successor(self):
        game = scene()
        world, menu = game.world, game.menu
        menu.screen = "stage_progress"
        for first, (_, x, _) in zip(config.STAGE_PROGRESS_PANELS, REGIONS):
            self.assertEqual(menu.region_status(first), "in_progress")
            self.assertTrue(menu.click(x, 360))
            for index in (first, first + 1):
                world.select_stage(index)
                advance(world, 1)
                for enemy in world.enemies[:3]:
                    enemy.take_damage(enemy.hp)
                world.step(config.FIXED_DT)
                self.assertEqual(menu.region_status(first), "in_progress")
                self.assertNotIn(index, world.cleared_stages)
                world.enemies[-1].take_damage(world.enemies[-1].hp)
                world.step(config.FIXED_DT)
                self.assertIn(index, world.cleared_stages)
                if index == first and first + 2 in config.STAGE_PROGRESS_PANELS:
                    self.assertEqual(menu.region_status(first + 2), "locked")
            self.assertEqual(menu.region_status(first), "complete")
            self.assertTrue(menu.click(x, 360))
            world.controls.press("restart")
            world.update(config.FIXED_DT)
            world.controls.release("restart")
            self.assertEqual(menu.region_status(first), "complete")
        self.assertEqual(world.cleared_stages, set(range(12)))

    def test_shortcuts_do_not_award_clears_and_relocking_preserves_earned_access(self):
        game = scene()
        world, menu = game.world, game.menu
        world.controls.press("stage_exits")
        world.step(config.FIXED_DT)
        self.assertTrue(world.stage.arrows_visible)
        self.assertFalse(world.cleared_stages)
        for index in (1, 0):
            world.select_stage(index)
            advance(world, 1)
            for enemy in world.enemies:
                enemy.take_damage(enemy.hp)
            world.step(config.FIXED_DT)
            if index == 1:
                self.assertEqual(menu.region_status(2), "locked")
        menu.screen = "stage_progress"
        for expected in (["complete"] + ["in_progress"] * 5,
                         ["complete", "in_progress"] + ["locked"] * 4):
            process_menu_events(game, key_event(pico2d.SDLK_p), key_event(pico2d.SDLK_p, down=False))
            self.assertEqual([menu.region_status(i) for i in config.STAGE_PROGRESS_PANELS], expected)
        self.assertEqual(world.cleared_stages, {0, 1})

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
