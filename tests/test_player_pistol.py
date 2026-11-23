import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import pico2d

import config
from assets import Assets
from game import Game
from main_menu import MainMenu
from player import Player
from tests.test_bag_drag import slot_center
from tests.test_main_menu import mouse_event, process_menu_events
from ui import UI
from world import World


class PistolEquipmentTests(unittest.TestCase):
    def bag(self):
        menu = MainMenu()
        button = menu.main_buttons[-1]
        menu.press_pointer(button.x, button.y)
        return menu

    def equip(self, menu):
        slot = next(index for index, item in enumerate(menu.bag_items) if item[0] == "pistol")
        menu.press_pointer(*slot_center(slot))
        menu.release_pointer(config.BAG_PLAYER_X, config.BAG_PLAYER_FEET_Y + 100)

    def test_original_pistol_sheet_and_all_64_clips_are_preserved(self):
        path = config.ROOT / config.PLAYER_PISTOL_IMAGE
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "07ce9ed3d617a3bd568ece1308e1ce599bede982c750522ecd129c92b7c0d09e")
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            rows = json.load(file)[config.PLAYER_PISTOL_IMAGE]
        with Image.open(path) as image:
            self.assertEqual((image.size, image.mode), ((2048, 2048), "RGBA"))
            self.assertEqual(len(rows), 8)
            for row, frames in enumerate(rows):
                self.assertEqual(len(frames), 8)
                for col, tile in enumerate(frames):
                    box = image.crop((col * 256, row * 256, (col + 1) * 256,
                                      (row + 1) * 256)).getbbox()
                    left, top, right, bottom = box
                    self.assertEqual(tile["clip"], [col * 256 + left,
                                                   image.height - row * 256 - bottom,
                                                   right - left, bottom - top])
                    self.assertEqual(tile["offset_x"], (left + right) / 2 - 128)

    def test_pistol_texture_is_shared_and_loaded_once(self):
        with patch("assets.pico2d.load_image", side_effect=lambda path: Mock()) as load, \
                patch("assets.pico2d.load_font", return_value=None):
            assets = Assets()
        self.assertIn(config.PLAYER_PISTOL_IMAGE, assets.images)
        self.assertEqual([call.args[0] for call in load.call_args_list].count(
            str(config.ROOT / config.PLAYER_PISTOL_IMAGE)), 1)

    def test_pistol_pose_rows_and_return_to_base_equipment(self):
        player = Player()
        player.equip_weapon("pistol")
        for state, row in (("IDLE", 1), ("WALK", 2), ("RUN", 3), ("JUMP", 4),
                           ("SHOOT", 5), ("RELOAD", 6), ("HIT", 7),
                           ("DYING", 8), ("DEAD", 8)):
            player.animation.set_state(state)
            self.assertEqual((player.sprite_image, player.sprite_row),
                             (config.PLAYER_PISTOL_IMAGE, row))
        player.equip_weapon(None)
        player.animation.set_state("IDLE")
        self.assertEqual(player.sprite_image, config.PLAYER_IMAGE)
        self.assertEqual(player.animation.definitions["HIT"], config.PLAYER_ANIMATIONS["HIT"])

    def test_pistol_drop_equips_preview_without_removing_or_reordering_items(self):
        menu = self.bag()
        original = menu.bag_items[:]
        self.equip(menu)
        self.assertEqual(menu.equipped_weapon, "pistol")
        self.assertEqual(menu.bag_items, original)
        self.assertIsNone(menu.dragged_slot)
        assets = SimpleNamespace(draw_sprite=Mock())
        menu.draw_bag_player(assets)
        assets.draw_sprite.assert_called_once_with(
            config.PLAYER_PISTOL_IMAGE, 1, 0, 640, 320, scale=1.7)
        menu.update(1 / 7)
        menu.draw_bag_player(assets)
        self.assertEqual(assets.draw_sprite.call_args.args[:3],
                         (config.PLAYER_PISTOL_IMAGE, 1, 1))

    def test_pistol_equips_from_its_rearranged_slot_and_survives_reopening(self):
        menu = self.bag()
        menu.press_pointer(*slot_center(3))
        menu.release_pointer(*slot_center(0))
        self.equip(menu)
        menu.show_main()
        button = menu.main_buttons[-1]
        menu.press_pointer(button.x, button.y)
        self.assertEqual(menu.equipped_weapon, "pistol")
        self.assertEqual(menu.bag_items[0][0], "pistol")
        self.assertEqual(menu.bag_player_animation.frame, 0)

    def test_other_items_outside_drops_and_cancelled_pistol_drags_do_not_equip(self):
        menu = self.bag()
        for slot in (1, 2, 4, 5):
            menu.press_pointer(*slot_center(slot))
            menu.release_pointer(640, 420)
            self.assertIsNone(menu.equipped_weapon)
        for point in ((0, 0), (640, 300), (800, 420)):
            menu.press_pointer(*slot_center(3))
            menu.release_pointer(*point)
            self.assertIsNone(menu.equipped_weapon)
        menu.press_pointer(*slot_center(3))
        menu.move_pointer(640, 420)
        menu.cancel_drag()
        menu.release_pointer(640, 420)
        self.assertIsNone(menu.equipped_weapon)

    def test_sdl_drop_then_start_applies_loadout_without_updating_the_waiting_world(self):
        game = Game.__new__(Game)
        game.menu, game.world, game.ui = self.bag(), World(), UI()
        game.running, game._menu_requested, game._escape_held = True, False, False
        player = game.world.player
        process_menu_events(
            game, mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, *slot_center(3)),
            mouse_event(pico2d.SDL_MOUSEMOTION, 640, 420),
            mouse_event(pico2d.SDL_MOUSEBUTTONUP, 640, 420),
        )
        self.assertIs(game.world.player, player)
        self.assertIsNone(player.weapon)
        self.assertEqual(game.world.elapsed, 0)
        with patch.object(game, "draw_main_menu"), \
                patch.object(game, "handle_events", return_value=True):
            game.show_main_menu()
        self.assertIsNot(game.world.player, player)
        self.assertEqual((game.world.player.weapon, game.world.player.state), ("pistol", "IDLE"))
        self.assertEqual(game.world.player.sprite_image, config.PLAYER_PISTOL_IMAGE)
        self.assertFalse(game.world.controls.held)
        self.assertFalse(game.world.controls.pressed)

    def test_restart_restores_selected_loadout_and_g_drops_a_collectible_pistol(self):
        world = World()
        world.starting_weapon = "pistol"
        world.reset()
        world.stage.drop_items.clear()
        self.assertTrue(world.interact_weapon())
        self.assertIsNone(world.player.weapon)
        self.assertEqual([item.kind for item in world.stage.drop_items], ["pistol"])
        self.assertEqual(world.stage.drop_items[0].pistol_ammo, 7)
        world.reset()
        self.assertEqual(world.player.weapon, "pistol")
        item = world.stage.drop_items[0]
        world.player.x, world.player.ground_y = item.x, item.ground_y
        self.assertTrue(world.interact_weapon())
        self.assertEqual(world.player.weapon, item.kind)
        self.assertEqual(len(world.stage.drop_items), 15)
        self.assertEqual(world.stage.drop_items[-1].kind, "pistol")
        world.reset()
        self.assertEqual(world.player.weapon, "pistol")
        self.assertEqual(len(world.stage.drop_items), 15)


if __name__ == "__main__":
    unittest.main()
