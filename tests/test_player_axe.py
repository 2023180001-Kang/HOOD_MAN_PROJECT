import unittest
from unittest.mock import Mock

import config
from assets import Assets
from main_menu import MainMenu
from tests.helpers import advance, tap
from tests.test_bag_drag import slot_center
from world import World


class PlayerAxeTests(unittest.TestCase):
    def test_drag_axe_to_player_and_return_it_from_the_blade_to_a_slot(self):
        menu = MainMenu()
        bag = menu.main_buttons[-1]
        menu.press_pointer(bag.x, bag.y)
        menu.press_pointer(*slot_center(2))
        menu.release_pointer(640, 420)
        self.assertEqual(menu.equipped_weapon, "axe")
        assets = Mock()
        menu.draw_bag_player(assets)
        self.assertEqual(assets.draw_sprite.call_args.args[0], config.PLAYER_AXE_IMAGE)
        world = World()
        world.starting_weapon = menu.equipped_weapon
        world.reset()
        self.assertEqual(world.player.sprite_image, config.PLAYER_AXE_IMAGE)
        menu.press_pointer(800, 525)
        menu.release_pointer(*slot_center(0))
        self.assertIsNone(menu.equipped_weapon)
        self.assertEqual(menu.bag_items[0][0], "axe")

    def test_g_drops_and_recovers_the_axe_at_the_held_sprite_scale(self):
        world = World()
        world.stage.drop_items.clear()
        world.player.equip_weapon("axe")
        tap(world.controls, "weapon_interact")
        advance(world, 0.75)
        drop, = world.stage.drop_items
        self.assertIsNone(world.player.weapon)
        self.assertTrue(drop.grounded)
        self.assertEqual(drop.image_name, config.AXE_PROJECTILE_IMAGE)
        texture = Mock(w=256, h=256)
        assets = Assets.__new__(Assets)
        assets.images = {config.AXE_PROJECTILE_IMAGE: texture}
        assets.draw_drop_item(drop, 0, 0)
        self.assertEqual(texture.clip_composite_draw.call_args.args[-2:],
                         (256 * config.SPRITE_SCALE, 256 * config.SPRITE_SCALE))
        tap(world.controls, "weapon_interact")
        world.update(config.FIXED_DT)
        self.assertEqual(world.player.sprite_image, config.PLAYER_AXE_IMAGE)
        self.assertFalse(world.stage.drop_items)
