import unittest

import config
from enemy import Enemy
from projectiles import AxeProjectile, DualBatonProjectile, SteelClubProjectile
from shield_soldier import ShieldSoldier
from world import World


class ThrowPiercingTests(unittest.TestCase):
    def test_each_enemy_is_hit_once_in_order_through_straight_flight_and_fall(self):
        for weapon, damage in ((SteelClubProjectile, 50), (AxeProjectile, 60), (DualBatonProjectile, 60)):
            for facing in (-1, 1):
                for dt, steps in ((2.0, 1), (config.FIXED_DT, 240)):
                    with self.subTest(weapon=weapon, facing=facing, dt=dt):
                        world = World()
                        world.stage.drop_items.clear()
                        x, y = world.player.x, world.player.ground_y
                        weapon_in_flight = weapon(x, y, 100, facing)
                        world.projectiles.append(weapon_in_flight)

                        guard = ShieldSoldier(x + facing * 210, ground_y=y)
                        guard.start_guard()
                        overlapping = Enemy(guard.x, ground_y=y)
                        first = Enemy(x + facing * 100, ground_y=y)
                        first.hp = 7
                        at_bend = Enemy(x + facing * 720, ground_y=y)
                        in_fall = Enemy(x + facing * 960, ground_y=y)
                        beyond = Enemy(x + facing * 1200, ground_y=y)
                        other_lane = Enemy(x + facing * 400, ground_y=y + 40)
                        airborne = Enemy(x + facing * 300, ground_y=y)
                        airborne.jump_height = airborne.previous_jump_height = 220
                        world.enemies = [beyond, in_fall, at_bend, other_lane, guard,
                                         overlapping, first, airborne]
                        for _ in range(steps):
                            world.update_projectiles(dt)

                        self.assertEqual([n.damage for n in world.damage_numbers],
                                         [7, damage // 2, damage, damage, damage])
                        self.assertEqual(first.hp, 0)
                        self.assertEqual(guard.max_hp - guard.hp, damage // 2)
                        for enemy in (overlapping, at_bend, in_fall):
                            self.assertEqual(enemy.max_hp - enemy.hp, damage)
                        self.assertTrue(all(enemy.hp == enemy.max_hp for enemy in (beyond, other_lane, airborne)))
                        self.assertEqual(len(world.effects), 5)
                        positions = [facing * (effect.x - x) for effect in world.effects]
                        self.assertEqual(positions, sorted(positions))
                        self.assertEqual(positions[1], positions[2])
                        self.assertLess(world.effects[-1].y, world.effects[0].y)
                        self.assertFalse(world.projectiles)
                        drop, = world.stage.drop_items
                        self.assertTrue(drop.grounded)
                        self.assertGreater((drop.x - in_fall.x) * facing, 0)

    def test_overlapping_targets_at_release_can_be_hit_again_by_a_new_throw(self):
        for weapon in (SteelClubProjectile, AxeProjectile, DualBatonProjectile):
            world = World()
            x, y = world.player.x, world.player.ground_y
            world.enemies = [Enemy(x, ground_y=y) for _ in range(3)]
            for count in (1, 2):
                world.projectiles.append(weapon(x, y, 80, 1))
                world.update_projectiles(0)
                world.update_projectiles(0)
                self.assertEqual([e.max_hp - e.hp for e in world.enemies], [weapon.damage * count] * 3)
                self.assertEqual(len(world.effects), 3 * count)
