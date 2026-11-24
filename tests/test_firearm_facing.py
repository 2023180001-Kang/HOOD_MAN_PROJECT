import unittest

import config
from tests.helpers import advance, tap
from world import World


def armed_world(weapon, facing=1):
    world = World()
    world.player.equip_weapon(weapon)
    world.player.facing = facing
    return world


class FirearmFacingTests(unittest.TestCase):
    def test_locked_walk_run_and_diagonals_keep_facing_and_normal_speed(self):
        directions = (("left",), ("right",), ("up",), ("down",), ("left", "up"), ("right", "down"))
        for gun in ("pistol", "ar_rifle"):
            for facing in (-1, 1):
                for keys in directions:
                    for running in (False, True):
                        with self.subTest(gun=gun, facing=facing, keys=keys, running=running):
                            world = armed_world(gun, facing)
                            player = world.player
                            tap(world.controls, "combat_s")
                            for key in keys:
                                world.controls.press(key)
                            if running:
                                world.controls.press("left_shift")
                            x, y = player.x, player.ground_y
                            advance(world, 0.15)
                            self.assertEqual((player.facing, player.state), (facing, "RUN" if running else "WALK"))
                            dx, dy = world.controls.movement
                            self.assertAlmostEqual((player.x - x) * dy, (player.ground_y - y) * dx)
                            self.assertGreater((player.x - x) * dx + (player.ground_y - y) * dy, 0)
                            self.assertAlmostEqual(player.vx * dx + player.ground_vy * dy,
                                                   min(config.ACCELERATION * 0.15,
                                                       config.RUN_SPEED if running else config.WALK_SPEED))
                            world.controls.held.clear()
                            backwards = "left" if facing > 0 else "right"
                            world.controls.press(backwards)
                            tap(world.controls, "combat_s")
                            world.update(config.FIXED_DT)
                            self.assertEqual(player.facing, -facing)

    def test_s_and_a_in_either_order_fire_in_the_locked_direction_while_backpedalling(self):
        for gun in ("pistol", "ar_rifle"):
            for facing in (-1, 1):
                for keys in (("combat_a", "combat_s"), ("combat_s", "combat_a")):
                    with self.subTest(gun=gun, facing=facing, keys=keys):
                        world = armed_world(gun, facing)
                        player = world.player
                        for key in keys:
                            world.controls.press(key)
                        world.controls.press("left" if facing > 0 else "right")
                        x = player.x
                        advance(world, 0.15)
                        self.assertLess((player.x - x) * facing, 0)
                        self.assertEqual((player.state, player.facing), ("SHOOT", facing))
                        self.assertEqual([shot.facing for shot in world.projectiles],
                                         [facing] * (2 if gun == "ar_rifle" else 1))
                        self.assertTrue(all((shot.x - player.x) * facing > 0 for shot in world.projectiles))
                        if gun == "pistol":
                            muzzle_x, _, end_x, _ = player.aim_line
                            self.assertGreater((end_x - muzzle_x) * facing, 0)
                        else:
                            tap(world.controls, "combat_s")
                            advance(world, 0.1)
                            self.assertEqual(world.projectiles[-1].facing, -facing)
                            self.assertEqual(player.rifle_ammo, 17)

    def test_lock_and_unlock_during_reload_do_not_restart_it(self):
        for gun in ("pistol", "ar_rifle"):
            world = armed_world(gun)
            player = world.player
            player.firearm_ammo = 2
            tap(world.controls, "combat_r")
            advance(world, 0.25)
            tap(world.controls, "combat_s")
            world.controls.press("left")
            advance(world, 0.5)
            self.assertEqual((player.state, player.facing, player.firearm_ammo), ("RELOAD", 1, 2))
            tap(world.controls, "combat_s")
            advance(world, 0.25)
            self.assertEqual((player.state, player.facing), ("WALK", -1))
            self.assertEqual(player.firearm_ammo, config.FIREARM_MAGAZINE_SIZES[gun])

    def test_s_counts_each_fresh_press_and_dropping_or_restarting_releases_lock(self):
        world = armed_world("pistol")
        player = world.player
        for _ in range(2):
            tap(world.controls, "combat_s")
        world.update(config.FIXED_DT)
        self.assertFalse(player.firearm_facing_locked)
        tap(world.controls, "combat_s")
        world.update(config.FIXED_DT)
        world.controls.press("combat_s")
        world.update(config.FIXED_DT)
        self.assertTrue(player.firearm_facing_locked)
        world.stage.drop_items.clear()
        tap(world.controls, "weapon_interact")
        world.update(config.FIXED_DT)
        self.assertEqual((player.weapon, player.firearm_facing_locked), (None, False))
        tap(world.controls, "combat_s")
        world.update(config.FIXED_DT)
        self.assertEqual(player.state, "ATTACK_S")
        player.equip_weapon("ar_rifle")
        tap(world.controls, "combat_s")
        world.update(config.FIXED_DT)
        self.assertTrue(player.firearm_facing_locked)
        world.starting_weapon = "ar_rifle"
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertFalse(world.player.firearm_facing_locked)
