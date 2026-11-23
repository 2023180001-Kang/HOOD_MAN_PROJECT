import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pico2d
from sdl2 import (
    SDL_BUTTON_MIDDLE, SDL_BUTTON_RIGHT, SDL_Event,
    SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST, SDL_WINDOWEVENT_LEAVE,
)

import config
from assets import Assets
from drop_items import DropItem
from game import Game
from main_menu import MainMenu
from tests.helpers import advance, tap
from tests.test_bag_drag import slot_center
from tests.test_main_menu import mouse_event, process_menu_events
from tests.test_pistol_combat import armed_world
from ui import UI
from world import World


def gun_center():
    left, top, right, bottom = config.BAG_EQUIPPED_PISTOL_RECT
    return (left + right) / 2, config.SCREEN_HEIGHT - (top + bottom) / 2


def equipped_bag():
    menu = MainMenu()
    button = menu.main_buttons[-1]
    menu.press_pointer(button.x, button.y)
    menu.press_pointer(*slot_center(3))
    menu.release_pointer(640, 420)
    return menu


class BagPistolReturnTests(unittest.TestCase):
    def test_returning_the_equipped_gun_to_any_slot_unequips_and_moves_its_existing_icon(self):
        for target in range(6):
            menu = equipped_bag()
            original = menu.bag_items[:]
            self.assertFalse(menu.press_pointer(*gun_center()))
            self.assertTrue(menu.dragged_from_player)
            self.assertEqual(menu.equipped_weapon, "pistol")  # Commit only on a valid drop.
            menu.move_pointer(*slot_center(target))
            menu.release_pointer(*slot_center(target))
            self.assertIsNone(menu.equipped_weapon)
            self.assertFalse(menu.dragged_from_player)
            self.assertIsNone(menu.dragged_slot)
            expected = original[:]
            expected[3], expected[target] = original[target], original[3]
            self.assertEqual(menu.bag_items, expected)
            self.assertCountEqual(menu.bag_items, config.BAG_ITEM_SPECS)
            self.assertEqual(menu.bag_player_animation.elapsed, 0)

    def test_preview_is_unarmed_during_the_drag_and_the_gun_icon_draws_only_once(self):
        menu = equipped_bag()
        assets = SimpleNamespace(draw_sprite=Mock(), images={
            name: Mock() for _, name, _ in config.BAG_ITEM_SPECS
        })
        menu.press_pointer(*gun_center())
        menu.move_pointer(800, 350)
        menu.draw_bag_player(assets)
        menu.draw_bag_items(assets)
        self.assertEqual(assets.draw_sprite.call_args.args[0], config.PLAYER_IMAGE)
        assets.images[config.PISTOL_ITEM_IMAGE].clip_draw.assert_called_once()
        args = assets.images[config.PISTOL_ITEM_IMAGE].clip_draw.call_args.args
        self.assertEqual(args[4:6], (800, 350))
        menu.cancel_drag()
        menu.draw_bag_player(assets)
        self.assertEqual(assets.draw_sprite.call_args.args[0], config.PLAYER_PISTOL_IMAGE)

    def test_invalid_drops_restore_the_equipped_gun_without_moving_items(self):
        menu = equipped_bag()
        back = menu.bag_back_button
        for point in ((0, 0), (267, 148), (640, 420), gun_center(), (back.x, back.y)):
            menu.press_pointer(*gun_center())
            menu.move_pointer(*point)
            menu.release_pointer(*point)
            self.assertEqual(menu.equipped_weapon, "pistol")
            self.assertEqual(menu.bag_items, list(config.BAG_ITEM_SPECS))
            self.assertTrue(menu.bag_open)
            self.assertIsNone(menu.dragged_slot)

    def test_only_an_open_equipped_gun_region_can_start_a_return_drag(self):
        menu = equipped_bag()
        for point in ((560, 600), (640, 380), (780, 490)):
            menu.press_pointer(*point)
            self.assertIsNone(menu.dragged_slot)
        menu.equipped_weapon = None
        menu.press_pointer(*gun_center())
        self.assertIsNone(menu.dragged_slot)
        menu.equipped_weapon = "pistol"
        menu.show_main()
        menu.press_pointer(*gun_center())
        self.assertIsNone(menu.dragged_slot)

    def test_cancelled_return_survives_navigation_focus_loss_and_late_release(self):
        for kind in (SDL_WINDOWEVENT_LEAVE, SDL_WINDOWEVENT_FOCUS_LOST, None):
            game = Game.__new__(Game)
            game.menu, game.world = equipped_bag(), World()
            game.running, game._menu_requested, game._escape_held = True, False, False
            process_menu_events(game, mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, *gun_center()))
            if kind is None:
                game.menu.show_main()
            else:
                event = SDL_Event()
                event.type, event.window.event = SDL_WINDOWEVENT, kind
                process_menu_events(game, event)
            process_menu_events(game, mouse_event(pico2d.SDL_MOUSEBUTTONUP, *slot_center(0)))
            self.assertEqual(game.menu.equipped_weapon, "pistol")
            self.assertIsNone(game.menu.dragged_slot)
            self.assertFalse(game.menu.dragged_from_player)
            self.assertEqual(game.menu.bag_items, list(config.BAG_ITEM_SPECS))

    def test_sdl_return_then_start_and_f5_use_the_new_unarmed_selection(self):
        game = Game.__new__(Game)
        game.menu, game.world, game.ui = equipped_bag(), armed_world(), UI()
        game.running, game._menu_requested, game._escape_held = True, False, False
        old_player = game.world.player
        process_menu_events(
            game, mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, *gun_center()),
            mouse_event(pico2d.SDL_MOUSEMOTION, *slot_center(0)),
            mouse_event(pico2d.SDL_MOUSEBUTTONUP, *slot_center(0)),
        )
        self.assertIsNone(game.menu.equipped_weapon)
        self.assertIs(game.world.player, old_player)
        self.assertEqual(old_player.weapon, "pistol")  # Paused world is not changed.
        with patch.object(game, "draw_main_menu"), \
                patch.object(game, "handle_events", return_value=True):
            game.show_main_menu()
        self.assertIsNone(game.world.player.weapon)
        self.assertIsNone(game.world.starting_weapon)
        game.world.reset()
        self.assertIsNone(game.world.player.weapon)
        self.assertFalse(game.world.controls.pressed)

    def test_right_and_middle_buttons_neither_start_nor_finish_equipment_drag(self):
        game = Game.__new__(Game)
        game.menu, game.world = equipped_bag(), World()
        game.running, game._menu_requested, game._escape_held = True, False, False
        for button in (SDL_BUTTON_RIGHT, SDL_BUTTON_MIDDLE):
            process_menu_events(game, mouse_event(
                pico2d.SDL_MOUSEBUTTONDOWN, *gun_center(), button))
            self.assertIsNone(game.menu.dragged_slot)
        process_menu_events(game, mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, *gun_center()))
        for button in (SDL_BUTTON_RIGHT, SDL_BUTTON_MIDDLE):
            process_menu_events(game, mouse_event(
                pico2d.SDL_MOUSEBUTTONUP, *slot_center(0), button))
            self.assertTrue(game.menu.dragged_from_player)
        process_menu_events(game, mouse_event(pico2d.SDL_MOUSEBUTTONUP, *slot_center(0)))
        self.assertIsNone(game.menu.equipped_weapon)

    def test_repeated_equip_return_and_rearrangement_never_duplicate_items(self):
        menu = equipped_bag()
        for target in range(18):
            menu.press_pointer(*gun_center())
            menu.release_pointer(*slot_center(target % 6))
            self.assertIsNone(menu.equipped_weapon)
            self.assertCountEqual(menu.bag_items, config.BAG_ITEM_SPECS)
            slot = next(index for index, item in enumerate(menu.bag_items) if item[0] == "pistol")
            menu.press_pointer(*slot_center(slot))
            menu.release_pointer(640, 420)
            self.assertEqual(menu.equipped_weapon, "pistol")


class PistolDropPickupTests(unittest.TestCase):
    def test_g_drops_and_picks_up_the_same_ammo_repeatedly_without_refilling(self):
        world = armed_world()
        world.stage.drop_items.clear()
        world.player.pistol_ammo = 4
        for _ in range(4):
            tap(world.controls, "weapon_interact")
            world.update(config.FIXED_DT)
            self.assertIsNone(world.player.weapon)
            self.assertEqual(len(world.stage.drop_items), 1)
            item = world.stage.drop_items[0]
            self.assertEqual((item.kind, item.pistol_ammo), ("pistol", 4))
            self.assertGreater(item.jump_height, 0)
            self.assertIsNone(world.pickup_item)
            advance(world, 0.5)
            self.assertTrue(item.grounded)
            self.assertIs(world.pickup_item, item)
            tap(world.controls, "weapon_interact")
            world.update(config.FIXED_DT)
            self.assertEqual((world.player.weapon, world.player.pistol_ammo), ("pistol", 4))
            self.assertEqual(world.player.sprite_image, config.PLAYER_PISTOL_IMAGE)
            self.assertFalse(world.stage.drop_items)

    def test_g_replaces_pistol_with_melee_and_back_without_losing_either_weapon(self):
        for kind in config.WEAPON_POSE_IMAGES:
            world = armed_world()
            world.player.pistol_ammo = 3
            item = DropItem(kind, world.player.x, world.player.ground_y)
            world.stage.drop_items = [item]
            world.interact_weapon()
            self.assertEqual(world.player.weapon, kind)
            self.assertEqual([drop.kind for drop in world.stage.drop_items], ["pistol"])
            self.assertEqual(world.stage.drop_items[0].pistol_ammo, 3)
            advance(world, 0.5)
            world.interact_weapon()
            self.assertEqual((world.player.weapon, world.player.pistol_ammo), ("pistol", 3))
            self.assertEqual([drop.kind for drop in world.stage.drop_items], [kind])

    def test_empty_pistol_stays_empty_after_drop_and_resumes_a_full_reload(self):
        world = armed_world()
        world.stage.drop_items.clear()
        world.player.pistol_ammo = 0
        world.player.start_pistol_reload()
        advance(world, 0.4)
        tap(world.controls, "weapon_interact")
        world.update(config.FIXED_DT)
        self.assertEqual(world.stage.drop_items[0].pistol_ammo, 0)
        self.assertIsNone(world.player.weapon)
        advance(world, 0.5)
        tap(world.controls, "weapon_interact")
        world.update(config.FIXED_DT)
        self.assertEqual((world.player.weapon, world.player.state, world.player.pistol_ammo),
                         ("pistol", "RELOAD", 0))
        advance(world, 0.9)
        self.assertEqual(world.player.pistol_ammo, 0)
        advance(world, 0.1)
        self.assertEqual((world.player.state, world.player.pistol_ammo), ("IDLE", 7))

    def test_g_cancels_a_pending_shot_and_never_refills_the_dropped_gun(self):
        world = armed_world()
        world.stage.drop_items.clear()
        world.player.pistol_ammo = 5
        world.player.start_pistol_shot()
        tap(world.controls, "weapon_interact")
        world.update(config.FIXED_DT)
        advance(world, 0.5)
        self.assertFalse(world.projectiles)
        self.assertEqual(world.stage.drop_items[0].pistol_ammo, 5)
        self.assertFalse(world.player.pistol_shot_pending)

    def test_swapping_two_pistols_preserves_each_magazine_and_cancels_the_old_animation(self):
        for state in ("SHOOT", "RELOAD"):
            world = armed_world()
            player = world.player
            player.pistol_ammo = 5 if state == "SHOOT" else 0
            if state == "SHOOT":
                player.start_pistol_shot()
            else:
                player.start_pistol_reload()
            item = DropItem("pistol", player.x, player.ground_y, pistol_ammo=2)
            world.stage.drop_items = [item]
            world.interact_weapon()
            self.assertEqual((player.state, player.pistol_ammo), ("IDLE", 2))
            self.assertFalse(player.pistol_shot_pending)
            self.assertEqual(len(world.stage.drop_items), 1)
            self.assertEqual(world.stage.drop_items[0].pistol_ammo, 5 if state == "SHOOT" else 0)

    def test_held_g_never_automatically_reacquires_the_landed_pistol(self):
        world = armed_world()
        world.stage.drop_items.clear()
        world.controls.press("weapon_interact")
        advance(world, 0.6)
        world.controls.press("weapon_interact")
        advance(world, 0.6)
        self.assertIsNone(world.player.weapon)
        self.assertEqual(len(world.stage.drop_items), 1)
        tap(world.controls, "weapon_interact")
        world.update(config.FIXED_DT)
        self.assertEqual(world.player.weapon, "pistol")

    def test_ground_pistol_uses_the_existing_pickup_distance_depth_floor_and_air_filters(self):
        world = World()
        player = world.player
        item = DropItem("pistol", player.x + 72, player.ground_y + 32)
        world.stage.drop_items = [item]
        self.assertIs(world.pickup_item, item)
        for attribute, value in (("x", player.x + 72.01), ("ground_y", player.ground_y + 32.01),
                                 ("floor", 1), ("jump_height", 1)):
            old = getattr(item, attribute)
            setattr(item, attribute, value)
            self.assertIsNone(world.pickup_item)
            setattr(item, attribute, old)
        world.interact_weapon()
        self.assertEqual((player.weapon, player.pistol_ammo), ("pistol", 7))

    def test_airborne_pistol_falls_to_the_same_floor_and_keeps_its_magazine(self):
        world = armed_world()
        world.stage.drop_items.clear()
        player = world.player
        player.jump_height, player.vy, player.jump_count = 180, 200, 1
        player.pistol_ammo = 2
        tap(world.controls, "weapon_interact")
        world.update(config.FIXED_DT)
        item = world.stage.drop_items[0]
        self.assertGreater(item.jump_height, 180)
        self.assertEqual(item.floor, player.floor)
        advance(world, 1)
        self.assertTrue(item.grounded)
        self.assertIs(world.pickup_item, item)
        world.interact_weapon()
        self.assertEqual((player.weapon, player.pistol_ammo), ("pistol", 2))

    def test_dropped_pistol_fits_all_stage_corners_using_its_own_display_height(self):
        world = armed_world()
        for index in range(len(world.stages)):
            world.select_stage(index)
            left, bottom, right, top = world.stage.drop_spawn_area.bounds
            for x in (left + 68, right - 68):
                for y in (bottom, top):
                    world.player.x, world.player.ground_y = x, y
                    item = world.drop_weapon("pistol")
                    width = config.PISTOL_ITEM_CLIP[2] * config.PISTOL_DROP_SCALE
                    self.assertGreaterEqual(item.x - width / 2, left)
                    self.assertLessEqual(item.x + width / 2, right)
                    self.assertGreaterEqual(item.ground_y, bottom)
                    self.assertLessEqual(item.ground_y + item.display_height, top + 1e-9)

    def test_inactive_stage_and_loading_pause_drops_and_f5_restores_only_initial_melee_items(self):
        world = armed_world()
        world.stage.drop_items.clear()
        world.player.pistol_ammo = 3
        world.interact_weapon()
        item = world.stage.drop_items[0]
        snapshot = item.jump_height, item.vy, item.elapsed, item.pistol_ammo
        world.select_stage(1)
        advance(world, 1)
        self.assertEqual((item.jump_height, item.vy, item.elapsed, item.pistol_ammo), snapshot)
        world.select_stage(0)
        world.pending_stage_index, world.stage_loading_remaining = 1, 2
        world.update(1)
        self.assertEqual((item.jump_height, item.vy, item.elapsed, item.pistol_ammo), snapshot)
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertEqual((world.player.weapon, world.player.pistol_ammo), ("pistol", 7))
        for stage in world.stages:
            self.assertEqual(len(stage.drop_items), 15)
            self.assertTrue(all(drop.kind in ("combat_knife", "steel_pipe") for drop in stage.drop_items))

    def test_pistol_is_a_static_full_icon_with_correct_camera_height_and_horizontal_flip(self):
        image = Mock()
        assets = SimpleNamespace(images={config.PISTOL_ITEM_IMAGE: image})
        for facing in (-1, 1):
            item = DropItem("pistol", 900, 160, facing, jump_height=80, pistol_ammo=4)
            item.update(0.01)
            self.assertEqual((item.frame, item.image_name), (0, config.PISTOL_ITEM_IMAGE))
            Assets.draw_drop_item(assets, item, 600, 50)
            image.clip_composite_draw.assert_called_with(
                *config.PISTOL_ITEM_CLIP, 0, "h" if facing < 0 else "",
                300, 160 - 50 + item.jump_height + item.display_height / 2,
                config.PISTOL_ITEM_CLIP[2] * config.PISTOL_DROP_SCALE,
                config.PISTOL_ITEM_CLIP[3] * config.PISTOL_DROP_SCALE,
            )
        item = DropItem("pistol", 900, 160)
        item.update(20)
        self.assertEqual((item.frame, item.jump_height, item.vy), (0, 0, 0))

    def test_pickup_prompt_uses_the_pistol_icon_height_and_reuses_the_existing_font(self):
        world = World()
        item = DropItem("pistol", world.player.x, world.player.ground_y, pistol_ammo=3)
        world.stage.drop_items = [item]
        assets = SimpleNamespace(font=Mock())
        UI().draw_pickup_prompt(assets, world, 600, 50)
        assets.font.draw.assert_called_with(
            item.x - 605, item.ground_y - 50 + item.display_height + config.WEAPON_PROMPT_GAP,
            "G", (255, 224, 110))

    def test_initial_random_drops_never_include_the_pistol(self):
        for seed in range(5):
            world = World(item_rng=random.Random(seed))
            for stage in world.stages:
                self.assertEqual(len(stage.drop_items), 15)
                self.assertEqual({item.kind for item in stage.drop_items}, {"combat_knife", "steel_pipe"})


if __name__ == "__main__":
    unittest.main()
