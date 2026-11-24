import unittest
from math import tau
from unittest.mock import Mock

import config
from assets import Assets
from combat import AXE_SWING, AXE_THROW
from enemy import Enemy
from main_menu import MainMenu
from projectiles import AxeProjectile
from tests.helpers import advance, tap
from tests.test_bag_drag import slot_center
from tests.test_weapon_combat import equipped_world, target
from tests.test_weapon_leap import aim
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

    def test_a_swings_on_row_five_and_deals_sixty_once(self):
        world = equipped_world("axe")
        enemy = target(world)
        hp = enemy.hp
        tap(world.controls, "combat_a")
        advance(world, 0.2)
        self.assertIs(world.player.active_move, AXE_SWING)
        self.assertEqual((world.player.sprite_image, world.player.sprite_row), (config.PLAYER_AXE_IMAGE, 5))
        self.assertEqual(enemy.hp, hp)
        advance(world, 0.4)
        self.assertEqual(enemy.hp, hp - 60)
        self.assertEqual(world.player.weapon, "axe")
        self.assertFalse(world.projectiles)

    def test_second_d_dives_with_axe_afterimages_and_hits_for_forty_on_landing(self):
        for side in (-1, 1):
            with self.subTest(side=side):
                world = aim("axe")
                player = world.player
                advance(world, 0.6)
                self.assertEqual((player.weapon_leap_phase, world.time_scale), ("AIM", 0.2))
                self.assertFalse(world.afterimages)

                enemy = target(world, side=side)
                enemy.x = player.x + side * 155
                world.controls.press("right" if side > 0 else "left")
                tap(world.controls, "combat_d")
                world.step(config.FIXED_DT)
                self.assertEqual(player.weapon_leap_phase, "DIVE")
                echo = world.afterimages[0]
                self.assertEqual((echo.image_name, echo.row, echo.facing), (config.PLAYER_AXE_IMAGE, 5, side))
                self.assertGreater((player.x - echo.x) * side, 0)
                self.assertLess(player.jump_height, echo.jump_height)

                for _ in range(60):
                    if player.grounded:
                        break
                    self.assertEqual(enemy.hp, enemy.max_hp)
                    world.step(config.FIXED_DT)
                self.assertEqual(player.weapon_leap_phase, "LANDING")
                self.assertEqual([number.damage for number in world.damage_numbers], [40])
                advance(world, 0.6)
                self.assertEqual((enemy.max_hp - enemy.hp, player.weapon, world.time_scale), (40, "axe", 1))

    def test_s_releases_one_spinning_axe_on_cell_five_in_the_original_direction(self):
        for facing in (-1, 1):
            with self.subTest(facing=facing):
                world = equipped_world("axe")
                player = world.player
                player.facing = facing
                tap(world.controls, "combat_s")
                world.update(config.FIXED_DT)
                world.controls.press("left" if facing > 0 else "right")
                for _ in range(28):
                    world.update(config.FIXED_DT)
                self.assertEqual((player.sprite_row, player.animation.frame, player.weapon), (6, 3, "axe"))
                self.assertFalse(world.projectiles)
                world.update(config.FIXED_DT)
                self.assertEqual((player.animation.frame, player.weapon), (4, None))
                self.assertIs(player.active_move, AXE_THROW)
                axe, = world.projectiles
                self.assertIsInstance(axe, AxeProjectile)
                self.assertEqual(axe.facing, facing)
                x, y = axe.x, axe.y
                tap(world.controls, "combat_s")
                advance(world, 0.3)
                self.assertEqual(world.projectiles, [axe])
                self.assertEqual(axe.y, y)
                self.assertAlmostEqual(axe.x - x, facing * axe.speed * 0.3)
                self.assertEqual(player.sprite_image, config.PLAYER_IMAGE)
                texture = Mock(w=256, h=256)
                assets = Assets.__new__(Assets)
                assets.images = {config.AXE_PROJECTILE_IMAGE: texture}
                assets.draw_projectile(axe, 0, 0)
                args = texture.clip_composite_draw.call_args.args
                self.assertAlmostEqual(args[4], -facing * tau * 8 * axe.elapsed)
                self.assertEqual(args[5], "h" if facing < 0 else "")
                self.assertEqual(args[-2:], (256 * config.SPRITE_SCALE, 256 * config.SPRITE_SCALE))

    def test_interrupted_windup_keeps_the_axe(self):
        world = equipped_world("axe")
        world.player.invincible = False
        tap(world.controls, "combat_s")
        advance(world, 0.2)
        world.player.take_damage(10)
        advance(world, 1)
        self.assertEqual(world.player.weapon, "axe")
        self.assertFalse(world.projectiles or world.stage.drop_items)

    def test_throw_deals_sixty_to_each_enemy_then_lands_and_can_be_thrown_again(self):
        world = equipped_world("axe")
        player = world.player
        enemies = [Enemy(player.x + dx, -1, ground_y=player.ground_y) for dx in (240, 150)]
        world.enemies = enemies
        player.start_move(AXE_THROW, 1)
        player.animation.elapsed = 4 / AXE_THROW.fps
        world.update_projectiles(0)
        world.update_projectiles(0.4)
        self.assertEqual([e.max_hp - e.hp for e in enemies], [60, 60])
        self.assertEqual([n.damage for n in world.damage_numbers], [60, 60])
        axe, = world.projectiles
        self.assertGreater(axe.x, max(enemy.x for enemy in enemies))
        self.assertFalse(world.stage.drop_items)
        world.enemies.clear()
        player.x = axe.x
        tap(world.controls, "weapon_interact")
        world.update(config.FIXED_DT)
        self.assertIsNone(player.weapon)
        advance(world, 1)
        item, = world.stage.drop_items
        self.assertEqual((item.kind, item.grounded), ("axe", True))
        player.x = item.x
        tap(world.controls, "weapon_interact")
        world.update(config.FIXED_DT)
        self.assertEqual(player.sprite_image, config.PLAYER_AXE_IMAGE)
        self.assertFalse(world.stage.drop_items)
        tap(world.controls, "combat_s")
        advance(world, 0.25)
        self.assertEqual(len(world.projectiles), 1)

    def test_missed_throw_begins_falling_after_720_pixels_and_lands_in_its_lane(self):
        world = equipped_world("axe")
        player = world.player
        axe = AxeProjectile(player.x, player.ground_y, 95, 1, player.floor)
        world.projectiles.append(axe)
        world.update_projectiles(axe.straight_duration)
        self.assertAlmostEqual(axe.x, player.x + 720)
        self.assertEqual(axe.height, 95)
        world.update_projectiles(0.1)
        self.assertLess(axe.height, 95)
        world.update_projectiles(1)
        item, = world.stage.drop_items
        self.assertTrue(item.grounded)
        self.assertEqual((item.x, item.ground_y, item.floor), (axe.x, axe.ground_y, axe.floor))
