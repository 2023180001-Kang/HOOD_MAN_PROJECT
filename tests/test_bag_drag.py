from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import pico2d
from sdl2 import (
    SDL_BUTTON_MIDDLE, SDL_BUTTON_RIGHT, SDL_Event,
    SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST, SDL_WINDOWEVENT_LEAVE,
)

import config
from game import Game
from main_menu import MainMenu
from tests.test_main_menu import mouse_event, process_menu_events
from world import World


def slot_center(slot):
    left, top, right, bottom = config.BAG_ITEM_SLOT_RECTS[slot]
    return (left + right) / 2, config.SCREEN_HEIGHT - (top + bottom) / 2


class BagDragTests(unittest.TestCase):
    def setUp(self):
        self.menu = MainMenu()
        self.assets = SimpleNamespace(images={
            name: Mock() for _, name, _ in config.BAG_ITEM_SPECS
        })
        bag = self.menu.main_buttons[-1]
        self.menu.press_pointer(bag.x, bag.y)

    def test_press_and_motion_keep_the_grab_offset_without_committing_layout(self):
        x, y = slot_center(0)
        self.assertFalse(self.menu.press_pointer(x + 24, y - 12))
        self.assertEqual(self.menu.dragged_slot, 0)
        self.assertEqual(self.menu.drag_position, (x, y))
        self.menu.move_pointer(700, 350)
        self.assertEqual(self.menu.drag_position, (676, 362))
        self.assertEqual(self.menu.bag_items, list(config.BAG_ITEM_SPECS))
        self.assertIsNone(self.menu.hovered_button)

    def test_every_source_and_target_pair_swaps_exactly_those_two_items(self):
        for source in range(6):
            for target in range(6):
                with self.subTest(source=source, target=target):
                    self.menu.press_pointer(*slot_center(source))
                    self.menu.move_pointer(*slot_center(target))
                    before = list(self.menu.bag_items)
                    self.menu.release_pointer(*slot_center(target))
                    expected = before[:]
                    expected[source], expected[target] = before[target], before[source]
                    self.assertEqual(self.menu.bag_items, expected)
                    self.assertCountEqual(self.menu.bag_items, config.BAG_ITEM_SPECS)
                    self.assertIsNone(self.menu.dragged_slot)
                    self.assertIsNone(self.menu.drag_position)
                    self.assertEqual(self.menu.drag_offset, (0, 0))

    def test_rearranged_items_fit_each_destination_slot_without_distortion(self):
        for source in range(6):
            for target in range(6):
                self.menu.press_pointer(*slot_center(source))
                self.menu.release_pointer(*slot_center(target))
                self.menu.draw_bag_items(self.assets)
                for slot, (_, name, clip) in enumerate(self.menu.bag_items):
                    with self.subTest(source=source, target=target, slot=slot):
                        args = self.assets.images[name].clip_draw.call_args.args
                        self.assertEqual(args[:4], clip)
                        self.assertEqual(args[4:6], slot_center(slot))
                        left, top, right, bottom = config.BAG_ITEM_SLOT_RECTS[slot]
                        padding = config.BAG_ITEM_SLOT_PADDING
                        scale = min((right - left - padding * 2) / clip[2],
                                    (bottom - top - padding * 2) / clip[3])
                        self.assertEqual(args[6:], (clip[2] * scale, clip[3] * scale))

    def test_dragged_icon_is_drawn_once_last_and_keeps_its_source_size(self):
        calls = []
        for _, name, _ in config.BAG_ITEM_SPECS:
            self.assets.images[name].clip_draw.side_effect = (
                lambda *args, image=name: calls.append((image, args)))
        self.menu.draw_bag_items(self.assets)
        initial = dict(calls)
        calls.clear()
        self.menu.press_pointer(*slot_center(0))
        self.menu.move_pointer(1111, 180)
        self.menu.draw_bag_items(self.assets)
        names = [name for _, name, _ in config.BAG_ITEM_SPECS]
        self.assertEqual([name for name, _ in calls], names[1:] + names[:1])
        self.assertEqual(calls[-1][1][4:6], (1111, 180))
        self.assertEqual(calls[-1][1][6:], initial[names[0]][6:])
        for name, args in calls[:-1]:
            self.assertEqual(args, initial[name])

    def test_invalid_drops_restore_the_original_layout(self):
        back = self.menu.bag_back_button
        for point in ((0, 0), (640, 360), (267, 148), (1208, 148),
                      (171, 59), (171, 236), (-20, 148), (1300, 148),
                      (back.x, back.y)):
            with self.subTest(point=point):
                self.menu.press_pointer(*slot_center(0))
                self.menu.move_pointer(*point)
                self.menu.release_pointer(*point)
                self.assertEqual(self.menu.bag_items, list(config.BAG_ITEM_SPECS))
                self.assertTrue(self.menu.bag_open)
                self.assertIsNone(self.menu.dragged_slot)

    def test_slot_hit_bounds_match_drawn_rectangles_and_gaps_are_inactive(self):
        for slot, (left, top, right, bottom) in enumerate(config.BAG_ITEM_SLOT_RECTS):
            low, high = config.SCREEN_HEIGHT - bottom, config.SCREEN_HEIGHT - top
            self.assertEqual(self.menu.bag_slot_at(left, low), slot)
            self.assertEqual(self.menu.bag_slot_at(right - 1, high - 1), slot)
            for point in ((left - 1, low), (right, low), (left, low - 1), (left, high)):
                self.assertIsNone(self.menu.bag_slot_at(*point))
        self.menu.show_main()
        for slot in range(6):
            self.assertIsNone(self.menu.bag_slot_at(*slot_center(slot)))
        self.assertFalse(self.menu.press_pointer(*slot_center(0)))
        self.assertIsNone(self.menu.dragged_slot)

    def test_click_or_drop_on_the_same_slot_does_not_change_the_order(self):
        for slot in range(6):
            self.menu.press_pointer(*slot_center(slot))
            self.menu.move_pointer(640, 360)
            self.menu.release_pointer(*slot_center(slot))
            self.assertEqual(self.menu.bag_items, list(config.BAG_ITEM_SPECS))

    def test_reopening_keeps_order_but_cancels_an_unfinished_drag(self):
        self.menu.press_pointer(*slot_center(0))
        self.menu.release_pointer(*slot_center(5))
        arranged = self.menu.bag_items[:]
        self.menu.press_pointer(*slot_center(2))
        self.menu.move_pointer(*slot_center(4))
        self.menu.show_main()
        self.assertIsNone(self.menu.dragged_slot)
        bag = self.menu.main_buttons[-1]
        self.menu.press_pointer(bag.x, bag.y)
        self.menu.release_pointer(*slot_center(4))
        self.assertEqual(self.menu.bag_items, arranged)
        self.assertTrue(self.menu.bag_open)

    def test_layout_is_private_to_each_menu_and_never_mutates_config(self):
        original = tuple(config.BAG_ITEM_SPECS)
        other = MainMenu()
        self.menu.press_pointer(*slot_center(0))
        self.menu.release_pointer(*slot_center(5))
        self.assertNotEqual(self.menu.bag_items, other.bag_items)
        self.assertEqual(other.bag_items, list(original))
        self.assertEqual(config.BAG_ITEM_SPECS, original)

    def test_release_without_press_never_reorders_or_navigates(self):
        back = self.menu.bag_back_button
        for point in (*map(slot_center, range(6)), (back.x, back.y)):
            self.menu.release_pointer(*point)
            self.assertTrue(self.menu.bag_open)
            self.assertIsNone(self.menu.dragged_slot)
            self.assertEqual(self.menu.bag_items, list(config.BAG_ITEM_SPECS))

    def test_repeated_press_cannot_replace_a_drag_or_activate_a_button(self):
        self.menu.press_pointer(*slot_center(0))
        back = self.menu.bag_back_button
        for point in (slot_center(5), (back.x, back.y)):
            self.assertFalse(self.menu.press_pointer(*point))
            self.assertEqual(self.menu.dragged_slot, 0)
            self.assertTrue(self.menu.bag_open)
            self.menu.move_pointer(*point)
            self.assertIsNone(self.menu.hovered_button)
        self.menu.release_pointer(*slot_center(5))
        self.assertEqual(self.menu.bag_items[5], config.BAG_ITEM_SPECS[0])


class BagDragFlowTests(unittest.TestCase):
    def setUp(self):
        self.game = Game.__new__(Game)
        self.game.menu = MainMenu()
        self.game.world = World()
        self.game.running = True
        self.game._menu_requested = False
        self.game._escape_held = False
        bag = self.game.menu.main_buttons[-1]
        self.process(mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, bag.x, bag.y))

    def process(self, *events, menu_screen=True):
        return process_menu_events(self.game, *events, menu_screen=menu_screen)

    def slot_event(self, kind, slot, **kwargs):
        return mouse_event(kind, *slot_center(slot), **kwargs)

    def test_sdl_drag_swaps_on_left_release_without_changing_the_world(self):
        menu, world = self.game.menu, self.game.world
        world.player.hp = 200
        player, stage = world.player, world.stage
        self.assertFalse(self.process(self.slot_event(pico2d.SDL_MOUSEBUTTONDOWN, 0)))
        self.assertEqual(menu.dragged_slot, 0)
        self.process(mouse_event(pico2d.SDL_MOUSEMOTION, 800, 350))
        # Slot 0's half-pixel center is preserved despite SDL's integer input.
        self.assertEqual(menu.drag_position, (800.5, 350))
        self.assertEqual(menu.bag_items, list(config.BAG_ITEM_SPECS))
        self.assertFalse(self.process(self.slot_event(pico2d.SDL_MOUSEBUTTONUP, 5)))
        self.assertEqual(menu.bag_items[0], config.BAG_ITEM_SPECS[5])
        self.assertEqual(menu.bag_items[5], config.BAG_ITEM_SPECS[0])
        self.assertIsNone(menu.dragged_slot)
        self.assertTrue(menu.bag_open)
        self.assertIs(world.player, player)
        self.assertIs(world.stage, stage)
        self.assertEqual((world.elapsed, player.hp), (0, 200))
        self.assertFalse(world.controls.held)
        self.assertFalse(world.controls.pressed)

    def test_release_uses_its_own_position_even_without_a_final_motion_event(self):
        self.process(
            self.slot_event(pico2d.SDL_MOUSEBUTTONDOWN, 0),
            self.slot_event(pico2d.SDL_MOUSEMOTION, 1),
            self.slot_event(pico2d.SDL_MOUSEBUTTONUP, 5),
        )
        self.assertEqual(self.game.menu.bag_items[5], config.BAG_ITEM_SPECS[0])
        self.assertEqual(self.game.menu.bag_items[1], config.BAG_ITEM_SPECS[1])

    def test_multiple_swaps_in_one_event_batch_use_the_updated_layout(self):
        self.assertFalse(self.process(
            self.slot_event(pico2d.SDL_MOUSEBUTTONDOWN, 0),
            self.slot_event(pico2d.SDL_MOUSEBUTTONUP, 5),
            self.slot_event(pico2d.SDL_MOUSEBUTTONDOWN, 5),
            self.slot_event(pico2d.SDL_MOUSEBUTTONUP, 2),
        ))
        self.assertEqual(self.game.menu.bag_items,
                         [config.BAG_ITEM_SPECS[index] for index in (5, 1, 0, 3, 4, 2)])

    def test_right_and_middle_buttons_cannot_start_or_release_a_drag(self):
        menu = self.game.menu
        for button in (SDL_BUTTON_RIGHT, SDL_BUTTON_MIDDLE):
            self.process(
                self.slot_event(pico2d.SDL_MOUSEBUTTONDOWN, 0, button=button),
                self.slot_event(pico2d.SDL_MOUSEMOTION, 5),
                self.slot_event(pico2d.SDL_MOUSEBUTTONUP, 5, button=button),
            )
            self.assertIsNone(menu.dragged_slot)
            self.assertEqual(menu.bag_items, list(config.BAG_ITEM_SPECS))
        self.process(self.slot_event(pico2d.SDL_MOUSEBUTTONDOWN, 0))
        for button in (SDL_BUTTON_RIGHT, SDL_BUTTON_MIDDLE):
            self.process(self.slot_event(pico2d.SDL_MOUSEBUTTONUP, 5, button=button))
            self.assertEqual(menu.dragged_slot, 0)
        self.process(self.slot_event(pico2d.SDL_MOUSEBUTTONUP, 5))
        self.assertEqual(menu.bag_items[5], config.BAG_ITEM_SPECS[0])

    def test_window_leave_focus_loss_and_quit_cancel_without_a_later_drop(self):
        for kind in (SDL_WINDOWEVENT_LEAVE, SDL_WINDOWEVENT_FOCUS_LOST, None):
            with self.subTest(kind=kind):
                self.process(
                    self.slot_event(pico2d.SDL_MOUSEBUTTONDOWN, 0),
                    self.slot_event(pico2d.SDL_MOUSEMOTION, 5),
                )
                event = SDL_Event()
                if kind is None:
                    event.type = pico2d.SDL_QUIT
                else:
                    event.type, event.window.event = SDL_WINDOWEVENT, kind
                self.assertFalse(self.process(event))
                self.assertIsNone(self.game.menu.dragged_slot)
                self.process(self.slot_event(pico2d.SDL_MOUSEBUTTONUP, 5))
                self.assertEqual(self.game.menu.bag_items, list(config.BAG_ITEM_SPECS))
                self.assertTrue(self.game.menu.bag_open)
                self.assertIsNone(self.game.menu.hovered_button)
        self.assertFalse(self.game.running)

    def test_dropping_on_back_does_not_navigate_but_a_fresh_click_does(self):
        menu = self.game.menu
        back = menu.bag_back_button
        self.process(
            self.slot_event(pico2d.SDL_MOUSEBUTTONDOWN, 0),
            mouse_event(pico2d.SDL_MOUSEMOTION, back.x, back.y),
            mouse_event(pico2d.SDL_MOUSEBUTTONUP, back.x, back.y),
        )
        self.assertTrue(menu.bag_open)
        self.assertEqual(menu.bag_items, list(config.BAG_ITEM_SPECS))
        self.process(mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, back.x, back.y))
        self.assertFalse(menu.bag_open)
        self.assertIsNone(menu.dragged_slot)

    def test_gameplay_mouse_events_do_not_rearrange_bag_items(self):
        self.process(
            self.slot_event(pico2d.SDL_MOUSEBUTTONDOWN, 0),
            self.slot_event(pico2d.SDL_MOUSEMOTION, 5),
            self.slot_event(pico2d.SDL_MOUSEBUTTONUP, 5),
            menu_screen=False,
        )
        self.assertIsNone(self.game.menu.dragged_slot)
        self.assertEqual(self.game.menu.bag_items, list(config.BAG_ITEM_SPECS))


if __name__ == "__main__":
    unittest.main()
