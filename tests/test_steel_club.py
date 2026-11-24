import unittest
from math import tau
from unittest.mock import Mock

import config
from assets import Assets
from combat import MOVES, STEEL_CLUB_DIVE, STEEL_CLUB_SWING, STEEL_CLUB_THROW
from enemy import Enemy
from main_menu import MainMenu
from projectiles import SteelClubProjectile
from tests.helpers import advance, tap
from tests.test_bag_drag import slot_center
from tests.test_weapon_combat import double_jump, equipped_world, target
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


class SteelClubCombatTests(unittest.TestCase):
    def setUp(self):
        self.world = World()
        self.player = self.world.player
        self.player.equip_weapon("steel_club")
        self.world.stage.drop_items.clear()

    def test_d_kicks_before_the_second_jump_and_can_aim_on_the_second_space_press(self):
        for jumping in (False, True):
            world = equipped_world("steel_club")
            if jumping:
                tap(world.controls, "jump")
                world.update(config.FIXED_DT)
            tap(world.controls, "combat_d")
            world.update(config.FIXED_DT)
            self.assertIs(world.player.active_move, MOVES["combat_d"])
            self.assertEqual(world.time_scale, 1)

        tap(self.world.controls, "jump")
        self.world.update(config.FIXED_DT)
        tap(self.world.controls, "jump")
        tap(self.world.controls, "combat_d")
        self.world.update(config.FIXED_DT)
        self.assertEqual((self.player.jump_count, self.player.weapon_leap_phase), (2, "AIM"))
        self.assertIs(self.player.active_move, STEEL_CLUB_DIVE)
        self.assertEqual(self.world.time_scale, config.WEAPON_AIM_TIME_SCALE)

    def test_second_d_leaves_club_afterimages_and_hits_once_on_landing_in_either_direction(self):
        for side in (-1, 1):
            with self.subTest(side=side):
                world = equipped_world("steel_club")
                player = world.player
                double_jump(world)
                tap(world.controls, "combat_d")
                advance(world, 0.6)  # Holding D keeps aiming until a fresh press.
                self.assertEqual(player.weapon_leap_phase, "AIM")
                self.assertFalse(world.afterimages)
                self.assertIsNone(player.attack_box)
                enemy = target(world, side=side)
                enemy.x = player.x + side * 155
                world.controls.press("right" if side == 1 else "left")
                tap(world.controls, "combat_d")
                world.update(config.FIXED_DT)
                self.assertEqual((player.weapon_leap_phase, world.time_scale), ("DIVE", config.WEAPON_DIVE_TIME_SCALE))
                for _ in range(60):
                    if player.grounded:
                        break
                    self.assertIsNone(player.attack_box)
                    self.assertEqual(enemy.hp, enemy.max_hp)
                    world.update(config.FIXED_DT)
                self.assertEqual(player.weapon_leap_phase, "LANDING")
                self.assertGreaterEqual(len(world.afterimages), 2)
                for echo in world.afterimages:
                    self.assertEqual((echo.image_name, echo.row, echo.facing),
                                     (config.PLAYER_STEEL_CLUB_IMAGE, STEEL_CLUB_SWING.row, side))
                self.assertEqual([number.damage for number in world.damage_numbers], [50])
                self.assertEqual(world.effects[-1].image_name, config.CLUB_HIT_IMAGE)
                advance(world, 0.6)
                self.assertEqual((enemy.hp, player.weapon, world.time_scale), (enemy.max_hp - 50, "steel_club", 1))
                self.assertFalse(world.projectiles or world.afterimages)

    def test_a_uses_swing_row_and_damages_each_target_once(self):
        enemy = Enemy(self.player.x + 82, -1, ground_y=self.player.ground_y)
        self.world.enemies.append(enemy)
        hp = enemy.hp
        tap(self.world.controls, "combat_a")
        advance(self.world, 0.15)
        self.assertIs(self.player.active_move, STEEL_CLUB_SWING)
        self.assertEqual((self.player.sprite_image, self.player.sprite_row),
                         (config.PLAYER_STEEL_CLUB_IMAGE, 5))
        self.assertEqual(enemy.hp, hp)
        advance(self.world, 0.45)
        self.assertEqual(enemy.hp, hp - 40)
        self.assertEqual(self.player.weapon, "steel_club")
        self.assertFalse(self.world.projectiles)

    def test_throw_releases_exactly_on_fifth_frame_then_only_the_empty_hand_moves_work(self):
        for facing in (1, -1):
            with self.subTest(facing=facing):
                self.player.equip_weapon("steel_club")
                self.player.facing = facing
                tap(self.world.controls, "combat_s")
                for _ in range(29):
                    self.world.update(config.FIXED_DT)
                self.assertEqual((self.player.sprite_row, self.player.animation.frame), (6, 3))
                self.assertFalse(self.world.projectiles)
                self.assertEqual(self.player.weapon, "steel_club")
                self.world.update(config.FIXED_DT)
                self.assertIs(self.player.active_move, STEEL_CLUB_THROW)
                self.assertEqual(self.player.animation.frame, 4)
                self.assertIsNone(self.player.weapon)
                club, = self.world.projectiles
                self.assertIsInstance(club, SteelClubProjectile)
                self.assertEqual(club.facing, facing)
                x, height = club.x, club.height
                tap(self.world.controls, "combat_s")
                advance(self.world, 0.3)
                self.assertEqual(self.world.projectiles, [club])
                self.assertAlmostEqual((club.x - x) * facing, club.speed * 0.3)
                self.assertEqual(club.height, height)
                self.assertEqual(self.player.sprite_image, config.PLAYER_IMAGE)
                tap(self.world.controls, "combat_s")
                self.world.update(config.FIXED_DT)
                self.assertIs(self.player.active_move, MOVES["combat_s"])
                advance(self.world, 1.1)
                self.assertFalse(self.world.projectiles)

    def test_interrupted_windup_keeps_the_club_and_never_emits_a_projectile(self):
        tap(self.world.controls, "combat_s")
        advance(self.world, 0.2)
        self.player.take_damage(10)
        self.assertEqual(self.player.sprite_row, 7)
        advance(self.world, 1)
        self.assertEqual(self.player.weapon, "steel_club")
        self.assertFalse(self.world.projectiles or self.world.stage.drop_items)

    def test_throw_pierces_both_enemies_on_its_floor_and_g_recovers_after_landing(self):
        x, y = self.player.x, self.player.ground_y
        enemies = [Enemy(x + offset, -1, ground_y=y) for offset in (300, 250, 160)]
        enemies[2].floor = 1
        self.world.enemies = enemies
        self.player.start_move(STEEL_CLUB_THROW, 1)
        self.player.animation.elapsed = 4 / STEEL_CLUB_THROW.fps
        self.world.update_projectiles(0)
        self.world.update_projectiles(0.4)
        self.assertEqual([enemy.max_hp - enemy.hp for enemy in enemies], [50, 50, 0])
        self.assertEqual([number.damage for number in self.world.damage_numbers], [50, 50])
        club, = self.world.projectiles
        self.assertGreater(club.x, max(enemy.x for enemy in enemies))
        self.assertFalse(self.world.stage.drop_items)
        self.world.enemies = []
        self.player.x = club.x
        tap(self.world.controls, "weapon_interact")
        self.world.update(config.FIXED_DT)
        self.assertIsNone(self.player.weapon)
        advance(self.world, 1)
        drop, = self.world.stage.drop_items
        self.assertTrue(drop.grounded)
        self.player.x = drop.x
        self.assertIs(self.world.pickup_item, drop)
        tap(self.world.controls, "weapon_interact")
        self.world.update(config.FIXED_DT)
        self.assertEqual((self.player.weapon, self.player.sprite_image),
                         ("steel_club", config.PLAYER_STEEL_CLUB_IMAGE))
        self.assertFalse(self.world.stage.drop_items)
        tap(self.world.controls, "combat_s")
        advance(self.world, 0.25)
        self.assertEqual(len(self.world.projectiles), 1)

    def test_missed_throw_falls_after_720_pixels_and_stays_reachable_in_its_city_lane(self):
        self.world.select_stage(2)
        self.world.stage.drop_items.clear()
        club = SteelClubProjectile(1400, 0, 80, -1)
        self.world.projectiles.append(club)
        self.world.update_projectiles(club.straight_duration)
        self.assertAlmostEqual(club.x, 680)
        self.assertEqual(club.height, 80)
        self.world.update_projectiles(0.1)
        self.assertLess(club.height, 80)
        self.world.update_projectiles(1)
        drop, = self.world.stage.drop_items
        self.assertTrue(drop.grounded)
        self.assertEqual(drop.ground_y, club.ground_y)
        self.assertAlmostEqual(drop.x, club.x)
        self.world.projectiles.append(SteelClubProjectile(90, 0, 90, -1))
        self.world.update_projectiles(1)
        edge_drop = self.world.stage.drop_items[-1]
        self.player.equip_weapon(None)
        self.player.x, self.player.ground_y = 90, 0
        advance(self.world, 0.75)
        self.assertIs(self.world.pickup_item, edge_drop)

    def test_rotating_projectile_and_falling_club_use_the_supplied_texture_around_its_center(self):
        texture = Mock(w=256, h=256)
        assets = Assets.__new__(Assets)
        assets.images = {config.STEEL_CLUB_PROJECTILE_IMAGE: texture}
        for facing in (1, -1):
            club = SteelClubProjectile(600, 100, 80, facing)
            club.update(1 / 16, [])
            assets.draw_projectile(club, 20, 5)
            args = texture.clip_composite_draw.call_args.args
            self.assertEqual(args[:4], (0, 0, 256, 256))
            self.assertAlmostEqual(args[4], -facing * tau / 2)
            self.assertEqual(args[5:8], ("h" if facing < 0 else "", club.x - 20, club.y - 5))
            self.world.projectiles.append(club)
            club.spent = True
            self.world.update_projectiles(0)
            drop = self.world.stage.drop_items[-1]
            assets.draw_drop_item(drop, 20, 5)
            self.assertEqual(texture.clip_composite_draw.call_args.args, args)
            drop.update(1)
            assets.draw_drop_item(drop, 20, 5)
            self.assertNotEqual(texture.clip_composite_draw.call_args.args[4], args[4])
