import unittest

import config
from combat import MOVES
from tests.helpers import ManualSpawnWorld, tap


class RetiredDualBatonTests(unittest.TestCase):
    def test_player_art_is_archived_and_the_item_is_absent_from_the_bag(self):
        for name in ("HoodMan_DualBatons_2048x2048(1).png", "dual_black_batons_pico2d.png",
                     "HoodMan_DualBaton_Projectiles_1024x256.png"):
            with self.subTest(name=name):
                self.assertTrue((config.ROOT / "before_sheets" / name).is_file())
                self.assertFalse((config.ROOT / name).exists())
        self.assertNotIn("dual_black_batons", [kind for kind, _, _ in config.BAG_ITEM_SPECS])

    def test_old_starting_weapon_leaves_a_and_s_as_unarmed_attacks(self):
        world = ManualSpawnWorld()
        world.starting_weapon = "dual_black_batons"
        for action in ("combat_a", "combat_s"):
            with self.subTest(action=action):
                world.reset()
                self.assertIsNone(world.player.weapon)
                tap(world.controls, action)
                world.step(config.FIXED_DT)
                self.assertIs(world.player.active_move, MOVES[action])
