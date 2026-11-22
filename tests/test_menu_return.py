import unittest
from unittest.mock import patch

import pico2d
from sdl2 import SDL_Event, SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST

import config
from combat import MOVES, STRONG_MOVES
from game import Game, KEYS
from main_menu import MainMenu
from tests.test_main_menu import mouse_event, process_menu_events
from ui import UI
from world import World


def scene():
    game = Game.__new__(Game)
    game.world = World()
    game.menu = MainMenu()
    game.ui = UI()
    game.running = True
    game._menu_requested = False
    game._escape_held = False
    return game


def key_event(key=pico2d.SDLK_ESCAPE, *, down=True, repeat=False):
    event = SDL_Event()
    event.type = pico2d.SDL_KEYDOWN if down else pico2d.SDL_KEYUP
    event.key.keysym.sym, event.key.repeat = key, int(repeat)
    return event


def click_event(button):
    return mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, button.x, button.y)


def quit_event():
    event = SDL_Event()
    event.type = pico2d.SDL_QUIT
    return event


class MenuReturnEventTests(unittest.TestCase):
    def setUp(self):
        self.game = scene()

    def process(self, *events, menu_screen=False):
        return process_menu_events(self.game, *events, menu_screen=menu_screen)

    def test_fresh_escape_requests_menu_without_quitting_or_resetting_world(self):
        world = self.game.world
        world.select_stage(11)
        world.player.hp = 200
        player = world.player
        world.controls.press("right")
        world.controls.press("spawn_9")
        with patch.object(world, "reset") as reset, patch.object(world, "update") as update:
            self.assertFalse(self.process(key_event()))
        self.assertTrue(self.game._menu_requested)
        self.assertTrue(self.game.running)
        self.assertTrue(self.game._escape_held)
        self.assertIs(world.player, player)
        self.assertEqual((world.stage_index, world.player.hp, world.elapsed), (11, 200, 0))
        self.assertFalse(world.controls.held)
        self.assertFalse(world.controls.pressed)
        reset.assert_not_called()
        update.assert_not_called()
        self.assertNotIn(pico2d.SDLK_ESCAPE, KEYS)

    def test_escape_discards_game_keys_and_mouse_clicks_from_the_entire_batch(self):
        self.assertFalse(self.process(
            key_event(pico2d.SDLK_RIGHT), key_event(pico2d.SDLK_2), key_event(),
            key_event(pico2d.SDLK_F5), key_event(pico2d.SDLK_SPACE),
            click_event(self.game.menu.main_buttons[0]), key_event(pico2d.SDLK_u),
        ))
        self.assertTrue(self.game._menu_requested)
        self.assertFalse(self.game.world.controls.held)
        self.assertFalse(self.game.world.controls.pressed)
        self.assertEqual(self.game.world.elapsed, 0)
        self.assertTrue(self.game.ui.details_visible)

    def test_escape_hold_and_repeat_cannot_request_another_menu_until_keyup(self):
        self.process(key_event())
        self.game._menu_requested = False  # Menu has consumed the first request.
        for repeat in (True, False, True):
            self.process(key_event(repeat=repeat))
            self.assertFalse(self.game._menu_requested)
        self.process(key_event(down=False))
        self.assertFalse(self.game._escape_held)
        self.process(key_event())
        self.assertTrue(self.game._menu_requested)

    def test_escape_has_no_navigation_or_start_action_in_menu_or_bag(self):
        for bag_open in (False, True):
            self.game.menu.bag_open = bag_open
            self.assertFalse(self.process(key_event(), key_event(repeat=True),
                                          key_event(down=False), menu_screen=True))
            self.assertFalse(self.game._menu_requested)
            self.assertEqual(self.game.menu.bag_open, bag_open)
            self.assertFalse(self.game.world.controls.held)
            self.assertFalse(self.game.world.controls.pressed)

    def test_escape_held_in_menu_cannot_immediately_return_after_start_click(self):
        self.assertTrue(self.process(key_event(), click_event(self.game.menu.main_buttons[0]),
                                     menu_screen=True))
        self.assertFalse(self.game._menu_requested)
        self.process(key_event(repeat=True), key_event())
        self.assertFalse(self.game._menu_requested)
        self.process(key_event(down=False), key_event())
        self.assertTrue(self.game._menu_requested)

    def test_escape_is_available_during_attack_death_and_stage_loading(self):
        for state in ("IDLE", "ATTACK_A", "ATTACK_R", "DYING", "DEAD", "loading"):
            self.game = scene()
            if state == "loading":
                self.game.world.pending_stage_index = 2
                self.game.world.stage_loading_remaining = 1.5
            elif state.startswith("ATTACK_"):
                moves = STRONG_MOVES if state == "ATTACK_R" else MOVES
                self.game.world.player.start_move(moves[f"combat_{state[-1].lower()}"], 1)
            elif state in ("DYING", "DEAD"):
                self.game.world.player.take_damage(config.MAX_HP)
                if state == "DEAD":
                    self.game.world.player.animation.set_state("DEAD")
            self.process(key_event())
            self.assertTrue(self.game._menu_requested, state)
            self.assertTrue(self.game.running)
            self.assertEqual(self.game.world.elapsed, 0)

    def test_focus_loss_releases_escape_latch_and_game_keys(self):
        self.process(key_event(), menu_screen=True)
        event = SDL_Event()
        event.type, event.window.event = SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST
        self.process(event)
        self.assertFalse(self.game._escape_held)
        self.process(key_event())
        self.assertTrue(self.game._menu_requested)

    def test_quit_wins_over_escape_in_either_event_order(self):
        for events in ((key_event(), quit_event()), (quit_event(), key_event())):
            self.game = scene()
            self.assertFalse(self.process(*events))
            self.assertFalse(self.game.running)
            self.assertEqual(self.game.world.elapsed, 0)


class MenuReturnLoopTests(unittest.TestCase):
    def setUp(self):
        self.game = scene()
        self.clock = 0.0

    def now(self):
        self.clock += 0.001
        return self.clock

    def sleep(self, seconds):
        self.clock += seconds

    def test_real_menu_bag_back_start_loop_resets_stage_and_excludes_menu_time_from_dt(self):
        world = self.game.world
        world.select_stage(11)
        world.player.hp = 200
        old_player = world.player
        start, bag = self.game.menu.main_buttons[0], self.game.menu.main_buttons[-1]
        back = self.game.menu.bag_back_button
        menu_inputs = iter((
            (key_event(repeat=True), key_event(pico2d.SDLK_9)),
            (click_event(bag),),
            (click_event(back),),
            (click_event(start), key_event(pico2d.SDLK_SPACE), key_event(pico2d.SDLK_F5)),
        ))
        first_play_event = True
        pages = []

        def handle(*, menu_screen=False):
            nonlocal first_play_event
            if menu_screen:
                self.assertIs(world.player, old_player)
                self.assertEqual((world.stage_index, old_player.hp, world.elapsed), (11, 200, 0))
                events = next(menu_inputs)
            elif first_play_event:
                events = (key_event(pico2d.SDLK_RIGHT), key_event(),
                          click_event(start), key_event(pico2d.SDLK_9))
                first_play_event = False
            else:
                events = ()
            return process_menu_events(self.game, *events, menu_screen=menu_screen)

        def menu_draw():
            pages.append(self.game.menu.bag_open)
            self.clock += 10  # Simulate a long user wait on every menu page.

        with patch("game.perf_counter", side_effect=self.now), \
                patch("game.sleep", side_effect=self.sleep), \
                patch.object(self.game, "handle_events", side_effect=handle), \
                patch.object(self.game, "draw_main_menu", side_effect=menu_draw), \
                patch.object(self.game, "draw") as draw, \
                patch.object(self.game, "update", wraps=self.game.update) as update, \
                patch.object(world, "reset", wraps=world.reset) as reset:
            self.assertEqual(self.game.run(max_frames=1), 1)
        self.assertEqual(pages, [False, False, True, False])
        reset.assert_called_once_with()
        draw.assert_called_once_with()
        self.assertEqual(update.call_count, 1)
        self.assertLess(update.call_args.args[0], 0.01)
        self.assertIsNot(world.player, old_player)
        self.assertEqual((world.stage_index, world.player.hp, world.player.state), (0, 500, "IDLE"))
        self.assertEqual(world.elapsed, 0)
        self.assertFalse(world.controls.held)
        self.assertFalse(world.controls.pressed)
        self.assertTrue(all(not stage.enemies and len(stage.drop_items) == 15 for stage in world.stages))
        self.assertFalse(self.game._menu_requested)

    def test_multiple_start_escape_cycles_stay_in_one_game_loop(self):
        batches = iter(((key_event(),), (), (key_event(down=False), key_event()), (),
                        (key_event(down=False), key_event()), ()))

        def handle(*, menu_screen=False):
            events = ((click_event(self.game.menu.main_buttons[0]),) if menu_screen
                      else next(batches))
            return process_menu_events(self.game, *events, menu_screen=menu_screen)

        with patch("game.perf_counter", side_effect=self.now), \
                patch("game.sleep", side_effect=self.sleep), \
                patch.object(self.game, "handle_events", side_effect=handle), \
                patch.object(self.game, "draw_main_menu") as menu_draw, \
                patch.object(self.game, "draw") as draw, \
                patch.object(self.game.world, "reset", wraps=self.game.world.reset) as reset:
            self.assertEqual(self.game.run(max_frames=3), 3)
        self.assertEqual(reset.call_count, 3)
        self.assertEqual(menu_draw.call_count, 3)
        self.assertEqual(draw.call_count, 3)
        self.assertTrue(self.game.running)

    def test_quit_with_escape_never_opens_menu_or_advances_play(self):
        def handle():
            return process_menu_events(self.game, key_event(), quit_event(), menu_screen=False)

        with patch.object(self.game, "handle_events", side_effect=handle), \
                patch.object(self.game, "show_main_menu") as menu, \
                patch.object(self.game, "update") as update, \
                patch.object(self.game, "draw") as draw:
            self.assertEqual(self.game.run(max_frames=1), 0)
        menu.assert_not_called()
        update.assert_not_called()
        draw.assert_not_called()
        self.assertFalse(self.game.running)

    def test_closing_returned_menu_exits_without_reset_or_gameplay_frame(self):
        def handle(*, menu_screen=False):
            events = (quit_event(),) if menu_screen else (key_event(),)
            return process_menu_events(self.game, *events, menu_screen=menu_screen)

        with patch.object(self.game, "handle_events", side_effect=handle), \
                patch.object(self.game, "draw_main_menu") as menu_draw, \
                patch.object(self.game, "update") as update, \
                patch.object(self.game, "draw") as draw, \
                patch.object(self.game.world, "reset") as reset:
            self.assertEqual(self.game.run(max_frames=1), 0)
        menu_draw.assert_called_once_with()
        update.assert_not_called()
        draw.assert_not_called()
        reset.assert_not_called()
        self.assertFalse(self.game.running)

    def test_normal_finite_run_does_not_show_a_menu_without_escape(self):
        with patch("game.perf_counter", side_effect=self.now), \
                patch("game.sleep", side_effect=self.sleep), \
                patch.object(self.game, "handle_events", return_value=False), \
                patch.object(self.game, "show_main_menu") as menu, \
                patch.object(self.game, "update") as update, \
                patch.object(self.game, "draw") as draw:
            self.assertEqual(self.game.run(max_frames=3), 3)
        menu.assert_not_called()
        self.assertEqual(update.call_count, 3)
        self.assertEqual(draw.call_count, 3)


if __name__ == "__main__":
    unittest.main()
