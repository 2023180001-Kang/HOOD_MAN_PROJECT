import unittest
from unittest.mock import Mock

import config
from assets import Assets
from projectiles import DualBatonProjectile
from tests.helpers import advance, tap
from tests.test_weapon_combat import equipped_world, target


class DualBatonTests(unittest.TestCase):
    def test_a_uses_row_five_and_deals_fifty_once(self):
        for facing in (-1, 1):
            world = equipped_world("dual_black_batons")
            player = world.player
            player.facing = facing
            enemy = target(world, side=facing)
            tap(world.controls, "combat_a")
            world.step(config.FIXED_DT)
            self.assertEqual((player.sprite_image, player.sprite_row), (config.PLAYER_DUAL_BATONS_IMAGE, 5))
            advance(world, 0.35)
            self.assertEqual([n.damage for n in world.damage_numbers], [50])
            advance(world, 0.25)
            self.assertEqual(enemy.max_hp - enemy.hp, 50)

    def test_s_releases_one_pair_on_fifth_cell_and_g_recovers_or_drops_it(self):
        for facing in (-1, 1):
            world = equipped_world("dual_black_batons")
            player = world.player
            player.facing = facing
            tap(world.controls, "combat_s")
            for _ in range(29):
                world.step(config.FIXED_DT)
            self.assertEqual((player.sprite_row, player.animation.frame, player.weapon), (6, 3, "dual_black_batons"))
            self.assertFalse(world.projectiles)
            world.step(config.FIXED_DT)
            pair, = world.projectiles
            self.assertIsInstance(pair, DualBatonProjectile)
            self.assertEqual((player.sprite_row, player.animation.frame, player.weapon), (6, 4, None))
            self.assertEqual(pair.facing, facing)
            tap(world.controls, "combat_s")
            advance(world, 0.15)
            self.assertEqual(world.projectiles, [pair])
            self.assertGreater((pair.x - player.x) * facing, 0)
            advance(world, 1.5)
            item, = world.stage.drop_items
            self.assertEqual((item.kind, item.grounded), ("dual_black_batons", True))
            player.x, player.ground_y = item.x, item.ground_y
            tap(world.controls, "weapon_interact")
            world.step(config.FIXED_DT)
            self.assertEqual(player.weapon, "dual_black_batons")
            tap(world.controls, "weapon_interact")
            world.step(config.FIXED_DT)
            self.assertIsNone(player.weapon)
            dropped, = world.stage.drop_items
            self.assertFalse(dropped.grounded)
            advance(world, 1)
            tap(world.controls, "weapon_interact")
            world.step(config.FIXED_DT)
            self.assertEqual(player.weapon, "dual_black_batons")
            self.assertFalse(world.stage.drop_items)

    def test_interrupted_throw_keeps_the_pair(self):
        world = equipped_world("dual_black_batons")
        world.player.invincible = False
        tap(world.controls, "combat_s")
        advance(world, 0.2)
        world.player.take_damage(20)
        advance(world, 1)
        self.assertEqual(world.player.weapon, "dual_black_batons")
        self.assertFalse(world.projectiles or world.stage.drop_items)

    def test_draws_both_spin_rows_and_rests_on_the_horizontal_frame(self):
        assets = Assets.__new__(Assets)
        image = Mock(w=1024, h=256)
        assets.images = {config.DUAL_BATON_PROJECTILE_IMAGE: image}
        for facing in (-1, 1):
            for index in range(8):
                assets.draw_thrown_weapon("dual_black_batons", 600, 100, facing, index / 64)
                upper, lower = [call.args for call in image.clip_composite_draw.call_args_list[-2:]]
                self.assertEqual(upper[:6], (index * 128, 128, 128, 128, 0, "h" if facing < 0 else ""))
                self.assertEqual(lower[:6], (index * 128, 0, 128, 128, 0, upper[5]))
                self.assertGreater(upper[7], lower[7])
            assets.draw_thrown_weapon("dual_black_batons", 600, 100, facing, 0.1, grounded=True)
            self.assertEqual([call.args[0] for call in image.clip_composite_draw.call_args_list[-2:]], [0, 0])
