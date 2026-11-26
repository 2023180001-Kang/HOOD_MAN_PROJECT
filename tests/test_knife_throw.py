import unittest
from unittest.mock import Mock

import config
from assets import Assets
from combat import MOVES
from projectiles import KnifeProjectile
from tests.helpers import advance, tap
from tests.test_weapon_combat import double_jump, equipped_world, target


class KnifeThrowTests(unittest.TestCase):
    def test_fifth_cell_releases_one_knife_that_hits_flies_falls_and_can_be_recovered(self):
        for facing in (-1, 1):
            with self.subTest(facing=facing):
                world = equipped_world("combat_knife")
                player = world.player
                player.facing = facing
                enemy = target(world, side=facing)
                tap(world.controls, "combat_s")
                for _ in range(29):
                    world.step(config.FIXED_DT)
                self.assertEqual((player.sprite_row, player.animation.frame, player.weapon),
                                 (6, 3, "combat_knife"))
                self.assertEqual((world.projectiles, enemy.hp), ([], 200))
                world.step(config.FIXED_DT)
                knife, = world.projectiles
                self.assertIsInstance(knife, KnifeProjectile)
                self.assertEqual((player.sprite_image, player.sprite_row, player.animation.frame),
                                 (config.WEAPON_POSE_IMAGES["combat_knife"], 6, 4))
                self.assertIsNone(player.weapon)
                self.assertEqual((knife.facing, enemy.hp), (facing, 160))
                x, height = knife.x, knife.height
                tap(world.controls, "combat_s")
                advance(world, 0.6)
                self.assertEqual(world.projectiles, [knife])
                self.assertAlmostEqual(knife.height, height)
                self.assertAlmostEqual((knife.x - x) * facing, 720)
                advance(world, 0.12)
                self.assertGreater((knife.x - x) * facing, knife.straight_range)
                self.assertLess(knife.height, height)
                advance(world, 0.8)
                item, = world.stage.drop_items
                self.assertEqual((world.projectiles, item.kind, item.grounded, enemy.hp),
                                 ([], "combat_knife", True, 160))
                player.x, player.ground_y = item.x, item.ground_y
                tap(world.controls, "weapon_interact")
                world.step(config.FIXED_DT)
                self.assertEqual((player.weapon, world.stage.drop_items), ("combat_knife", []))

    def test_d_uses_the_regular_kick_after_double_jump_and_never_enters_slow_motion(self):
        world = equipped_world("combat_knife")
        double_jump(world)
        for _ in range(2):
            tap(world.controls, "combat_d")
            world.step(config.FIXED_DT)
            self.assertIs(world.player.active_move, MOVES["combat_d"])
            self.assertIsNone(world.player.weapon_leap_phase)
            self.assertEqual(world.time_scale, 1.0)

    def test_blade_keeps_its_throw_direction_during_flight_and_at_the_map_edge(self):
        assets = Assets.__new__(Assets)
        texture = Mock()
        assets.images = {config.KNIFE_PROJECTILE_IMAGE: texture}
        for facing in (-1, 1):
            world = equipped_world("combat_knife")
            player = world.player
            player.facing = facing
            player.x = 146 if facing < 0 else world.stage.width - 146
            tap(world.controls, "combat_s")
            advance(world, 0.25)
            knife, = world.projectiles
            self.assertEqual(knife.image_name, "hoodman_throw_combat_knife.png")
            for _ in range(2):
                assets.draw_projectile(knife, 0, 0)
                args = texture.clip_composite_draw.call_args.args
                self.assertEqual(args[:4], config.KNIFE_PROJECTILE_CLIP)
                self.assertEqual(args[4:6], (0, "h" if facing < 0 else ""))
                world.step(config.FIXED_DT)
            advance(world, 0.05)
            item, = world.stage.drop_items
            self.assertFalse(item.grounded)
            assets.draw_drop_item(item, 0, 0)
            args = texture.clip_composite_draw.call_args.args
            self.assertEqual(args[:4], config.KNIFE_PROJECTILE_CLIP)
            self.assertEqual(args[4:6], (0, "h" if facing < 0 else ""))
