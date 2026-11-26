import unittest

import config
from ar_soldier import ARSoldier
from main_menu import MainMenu
from projectiles import ShieldProjectile
from researcher import Researcher
from tests.helpers import advance, tap
from tests.test_bag_drag import slot_center
from tests.test_combat import attacking_enemy
from tests.test_crowd_escape import fire_at_player, melee_group, tap_keys, tick
from tests.test_weapon_combat import equipped_world, target
from world import World


class PlayerShieldTests(unittest.TestCase):
    def test_bag_equips_returns_and_starts_with_shield_from_rearranged_slot(self):
        menu = MainMenu()
        menu.screen = "backpack"
        menu.press_pointer(*slot_center(4))
        menu.release_pointer(640, 420)
        self.assertEqual(menu.equipped_weapon, "shield_item")
        menu.press_pointer(640, 420)
        menu.release_pointer(*slot_center(2))
        self.assertIsNone(menu.equipped_weapon)
        self.assertEqual(menu.bag_items[2][0], "shield_item")
        self.assertCountEqual(menu.bag_items, config.BAG_ITEM_SPECS)
        menu.press_pointer(*slot_center(2))
        menu.release_pointer(640, 420)
        world = World()
        world.starting_weapon = menu.equipped_weapon
        world.reset()
        self.assertEqual((world.player.weapon, world.player.sprite_image, world.player.sprite_row),
                         ("shield_item", config.PLAYER_SHIELD_IMAGE, 1))

    def test_bash_uses_row_five_and_hits_once_per_press(self):
        for facing in (-1, 1):
            world = equipped_world("shield_item")
            world.player.facing = facing
            enemy = target(world, side=facing)
            world.controls.press("combat_a")
            tick(world)
            self.assertEqual((world.player.sprite_image, world.player.sprite_row), (config.PLAYER_SHIELD_IMAGE, 5))
            advance(world, 0.7)
            self.assertEqual(enemy.max_hp - enemy.hp, 20)
            self.assertEqual(world.player.state, "IDLE")

    def test_held_guard_halves_simultaneous_melee_and_both_kinds_of_enemy_fire(self):
        world = equipped_world("shield_item")
        player = world.player
        player.invincible = False
        world.controls.press("combat_s")
        tick(world)
        self.assertEqual((player.state, player.sprite_row), ("GUARD", 6))
        melee_group(world, 2)
        self.assertEqual(player.hp, config.MAX_HP - 20)
        rounds = [fire_at_player(world, Researcher(player.x - 230, 1)),
                  fire_at_player(world, ARSoldier(player.x + 230, -1))]
        advance(world, 0.45)
        self.assertEqual([bullet.impact_damage for bullet in rounds], [15, 2.5])
        self.assertEqual(player.hp, config.MAX_HP - 37.5)
        self.assertTrue(player.crowd_escape.ready)
        world.enemies.clear()
        advance(world, 1)
        self.assertEqual((player.sprite_row, player.animation.frame), (6, config.SHIELD_GUARD_HOLD_FRAME))
        self.assertIsNone(player.attack_box)
        world.controls.release("combat_s")
        tick(world)
        self.assertEqual((player.state, player.sprite_row), ("IDLE", 1))
        self.assertTrue(attacking_enemy(player.x - 80).try_hit(player))
        self.assertEqual((player.last_hit_damage, player.sprite_row), (20, 8))

    def test_guard_respects_escape_invincibility_lethal_hits_and_equipment(self):
        world = equipped_world("shield_item")
        player = world.player
        world.controls.press("combat_s")
        tick(world)
        self.assertFalse(player.take_damage(100))
        player.invincible = False
        melee_group(world)
        tap_keys(world, "left", "right", "left")
        world.controls.press("right")
        tick(world)
        self.assertTrue(player.crowd_escape.active)
        self.assertEqual(player.state, "WALK")
        self.assertFalse(player.take_damage(100))
        world.enemies.clear()
        world.controls.release("right")
        advance(world, 1.1)
        self.assertEqual(player.state, "GUARD")
        player.equip_weapon("axe")
        self.assertEqual(player.state, "IDLE")
        self.assertTrue(player.take_damage(20))
        self.assertEqual(player.last_hit_damage, 20)
        player.equip_weapon("shield_item")
        advance(world, 1)
        player.hp = 2
        self.assertTrue(player.take_damage(5))
        self.assertEqual((player.hp, player.last_hit_damage, player.state, player.sprite_row), (0, 2, "DYING", 9))

    def test_d_releases_one_shield_on_sixth_cell_then_g_recovers_drops_and_recovers(self):
        for facing in (-1, 1):
            world = equipped_world("shield_item")
            player = world.player
            player.facing = facing
            world.controls.press("combat_d")
            tick(world, 37)
            self.assertEqual((player.sprite_row, player.animation.frame, player.weapon), (7, 4, "shield_item"))
            self.assertFalse(world.projectiles)
            tick(world)
            shield, = world.projectiles
            self.assertIsInstance(shield, ShieldProjectile)
            self.assertEqual((player.sprite_row, player.animation.frame, player.weapon), (7, 5, None))
            self.assertEqual((shield.facing, shield.image_name), (facing, config.SHIELD_PROJECTILE_IMAGE))
            tap(world.controls, "combat_d")
            advance(world, 0.1)
            self.assertEqual(world.projectiles, [shield])
            self.assertGreater((shield.x - player.x) * facing, 0)
            advance(world, 1.6)
            item, = world.stage.drop_items
            self.assertEqual((item.kind, item.grounded), ("shield_item", True))
            player.x, player.ground_y = item.x, item.ground_y
            tap(world.controls, "weapon_interact")
            tick(world)
            self.assertEqual(player.weapon, "shield_item")
            world.controls.press("combat_s")
            tick(world)
            tap(world.controls, "weapon_interact")
            tick(world)
            self.assertEqual((player.weapon, player.state), (None, "IDLE"))
            dropped, = world.stage.drop_items
            self.assertFalse(dropped.grounded)
            advance(world, 1)
            tap(world.controls, "weapon_interact")
            tick(world)
            self.assertEqual((player.weapon, player.state), ("shield_item", "GUARD"))
            self.assertFalse(world.stage.drop_items)

    def test_interrupted_windup_keeps_shield_without_emitting_it(self):
        world = equipped_world("shield_item")
        world.player.invincible = False
        world.controls.press("combat_d")
        tick(world, 37)
        world.player.take_damage(20)
        advance(world, 1)
        self.assertEqual(world.player.weapon, "shield_item")
        self.assertFalse(world.projectiles or world.stage.drop_items)
