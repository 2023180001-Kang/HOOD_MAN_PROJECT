import unittest

import config
from drop_items import DropItem
from enemy import Enemy
from main_menu import MainMenu
from projectiles import PlayerRifleBullet
from tests.helpers import advance, tap
from tests.test_bag_drag import slot_center
from world import World


def rifle_world():
    world = World()
    world.starting_weapon = "ar_rifle"
    world.reset()
    world.stage.drop_items.clear()
    return world


class PlayerRifleTests(unittest.TestCase):
    def test_drag_from_bag_and_return_from_equipped_preview(self):
        menu = MainMenu()
        menu.screen = "backpack"
        slot = next(i for i, item in enumerate(menu.bag_items) if item[0] == "ar_rifle")
        menu.press_pointer(*slot_center(slot))
        menu.release_pointer(config.BAG_PLAYER_X, config.BAG_PLAYER_FEET_Y + 100)
        self.assertEqual(menu.equipped_weapon, "ar_rifle")
        left, top, right, bottom = config.BAG_EQUIPPED_RECTS["ar_rifle"]
        menu.press_pointer((left + right) / 2, config.SCREEN_HEIGHT - (top + bottom) / 2)
        menu.release_pointer(*slot_center(slot))
        self.assertIsNone(menu.equipped_weapon)

    def test_twenty_rounds_at_twelve_tick_intervals_then_manual_reload(self):
        world = rifle_world()
        player = world.player
        world.controls.press("combat_a")
        shots = []
        for tick in range(300):
            before = player.rifle_ammo
            world.update(config.FIXED_DT)
            if player.rifle_ammo < before:
                shots.append(tick)
                self.assertIsInstance(world.projectiles[-1], PlayerRifleBullet)
        self.assertEqual(shots, list(range(0, 240, 12)))
        self.assertEqual((player.state, player.rifle_ammo), ("IDLE", 0))
        tap(world.controls, "combat_r")
        advance(world, 0.95)
        self.assertEqual((player.sprite_row, player.rifle_ammo), (6, 0))
        advance(world, 0.05)
        self.assertEqual(player.rifle_ammo, 20)
        world.update(config.FIXED_DT)
        self.assertEqual(player.rifle_ammo, 19)

    def test_tap_hits_once_for_twenty_in_either_direction(self):
        for side in (-1, 1):
            with self.subTest(side=side):
                world = rifle_world()
                player = world.player
                player.facing = side
                enemy = Enemy(player.x + side * 200, -side, ground_y=player.ground_y)
                world.enemies.append(enemy)
                tap(world.controls, "combat_a")
                world.controls.release("combat_a")
                advance(world, 0.5)
                self.assertEqual(player.rifle_ammo, 19)
                self.assertEqual((enemy.max_hp - enemy.hp, world.damage_numbers[0].damage), (20, 20))
                self.assertEqual(player.hp, config.MAX_HP)

    def test_walk_run_jump_and_land_during_fire_and_reload(self):
        for running in (False, True):
            with self.subTest(running=running):
                world = rifle_world()
                player = world.player
                world.controls.press("right")
                if running:
                    world.controls.press("left_shift")
                advance(world, 0.3)
                world.controls.press("combat_a")
                world.update(config.FIXED_DT)
                self.assertEqual((player.sprite_row, player.rifle_ammo), (8 if running else 7, 19))
                tap(world.controls, "jump")
                advance(world, 0.1)
                self.assertEqual((player.sprite_row, player.rifle_ammo), (5, 18))
                x = player.x
                tap(world.controls, "combat_r")
                advance(world, 0.1)
                self.assertTrue(player.jump_height > 0)
                self.assertEqual((player.state, player.sprite_row, player.rifle_ammo), ("RELOAD", 6, 18))
                self.assertGreater(player.x, x)
                world.controls.release("combat_a")
                advance(world, 0.85)
                self.assertEqual((player.sprite_row, player.rifle_ammo), (10 if running else 9, 18))
                advance(world, 0.05)
                self.assertEqual((player.state, player.rifle_ammo), ("RUN" if running else "WALK", 20))

    def test_jumping_after_starting_reload_preserves_its_progress(self):
        world = rifle_world()
        player = world.player
        player.rifle_ammo = 3
        tap(world.controls, "combat_r")
        advance(world, 0.4)
        tap(world.controls, "jump")
        world.update(config.FIXED_DT)
        self.assertGreater(player.jump_height, 0)
        self.assertGreater(player.animation.elapsed, 0.4)
        advance(world, 0.6)
        self.assertEqual(player.rifle_ammo, 20)

    def test_g_preserves_each_magazine_and_interrupts_reload(self):
        world = rifle_world()
        player = world.player
        player.rifle_ammo = 4
        tap(world.controls, "combat_r")
        advance(world, 0.25)
        world.stage.drop_items.append(DropItem("ar_rifle", player.x, player.ground_y, rifle_ammo=2))
        tap(world.controls, "weapon_interact")
        world.update(config.FIXED_DT)
        self.assertEqual((player.weapon, player.state, player.rifle_ammo), ("ar_rifle", "IDLE", 2))
        old, = world.stage.drop_items
        self.assertEqual((old.image_name, old.rifle_ammo), (config.RIFLE_ITEM_IMAGE, 4))
        tap(world.controls, "weapon_interact")
        world.update(config.FIXED_DT)
        self.assertIsNone(player.weapon)
        advance(world, 1.2)
        self.assertTrue(all(item.grounded for item in world.stage.drop_items))
        tap(world.controls, "weapon_interact")
        world.update(config.FIXED_DT)
        self.assertEqual((player.weapon, player.rifle_ammo), ("ar_rifle", 4))
        self.assertEqual(world.stage.drop_items[0].rifle_ammo, 2)
