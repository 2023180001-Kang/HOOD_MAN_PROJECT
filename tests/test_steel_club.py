import unittest
from unittest.mock import Mock

import config
from main_menu import MainMenu
from tests.test_bag_drag import slot_center
from world import World


class SteelClubBagTests(unittest.TestCase):
    def test_equip_start_and_return_club_after_reordering_slots(self):
        menu = MainMenu()
        bag = menu.main_buttons[-1]
        menu.press_pointer(bag.x, bag.y)
        menu.press_pointer(*slot_center(0))
        menu.release_pointer(*slot_center(4))
        menu.press_pointer(*slot_center(4))
        menu.release_pointer(640, 420)
        self.assertEqual(menu.equipped_weapon, "steel_club")
        assets = Mock()
        menu.draw_bag_player(assets)
        self.assertEqual(assets.draw_sprite.call_args.args[0], config.PLAYER_STEEL_CLUB_IMAGE)
        world = World()
        world.starting_weapon = menu.equipped_weapon
        world.reset()
        self.assertEqual(world.player.sprite_image, config.PLAYER_STEEL_CLUB_IMAGE)
        menu.press_pointer(735, 510)
        menu.release_pointer(20, 20)
        self.assertEqual(menu.equipped_weapon, "steel_club")
        menu.press_pointer(735, 510)
        self.assertTrue(menu.dragged_from_player)
        menu.release_pointer(*slot_center(2))
        self.assertIsNone(menu.equipped_weapon)
        self.assertEqual(menu.bag_items[2][0], "steel_club")
        self.assertCountEqual(menu.bag_items, config.BAG_ITEM_SPECS)
        menu.draw_bag_player(assets)
        self.assertEqual(assets.draw_sprite.call_args.args[0], config.PLAYER_IMAGE)
