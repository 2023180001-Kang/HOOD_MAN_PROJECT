import unittest
from unittest.mock import Mock, patch

import config
from main_menu import MainMenu
from projectiles import EnemyAxeProjectile, ResearcherBullet, RifleBullet
from tests.helpers import advance, tap
from tests.test_bag_drag import slot_center
from tests.test_combat import attacking_enemy
from tests.test_weapon_combat import equipped_world, target
from world import World


class PlayerSwordTests(unittest.TestCase):
    def test_drag_between_bag_and_player_then_start_with_equipped_sword(self):
        menu = MainMenu()
        menu.screen = "backpack"
        menu.press_pointer(*slot_center(1))
        menu.release_pointer(640, 420)
        assets = Mock()
        menu.draw_bag_player(assets)
        self.assertEqual(assets.draw_sprite.call_args.args[:3], (config.PLAYER_SWORD_IMAGE, 1, 0))
        menu.press_pointer(640, 420)
        menu.release_pointer(*slot_center(4))
        self.assertIsNone(menu.equipped_weapon)
        menu.draw_bag_player(assets)
        self.assertEqual(assets.draw_sprite.call_args.args[0], config.PLAYER_IMAGE)
        menu.press_pointer(*slot_center(4))
        menu.release_pointer(640, 420)
        self.assertCountEqual(menu.bag_items, config.BAG_ITEM_SPECS)
        world = World()
        world.starting_weapon = menu.equipped_weapon
        world.reset()
        self.assertEqual((world.player.weapon, world.player.sprite_image),
                         ("sword", config.PLAYER_SWORD_IMAGE))

    def test_a_plays_row_five_and_slashes_once_for_seventy(self):
        for facing in (-1, 1):
            world = equipped_world("sword")
            world.player.facing = facing
            enemy = target(world, side=facing)
            tap(world.controls, "combat_a")
            world.step(config.FIXED_DT)
            self.assertEqual((world.player.sprite_image, world.player.sprite_row), (config.PLAYER_SWORD_IMAGE, 5))
            advance(world, 0.6)
            self.assertEqual((enemy.hp, world.player.state), (130, "IDLE"))
            self.assertEqual([number.damage for number in world.damage_numbers], [70])

    def test_s_loops_only_cells_two_to_six_then_releases_to_idle(self):
        world = equipped_world("sword")
        player = world.player
        world.controls.press("combat_s")
        sequence = []
        for _ in range(75):
            world.step(config.FIXED_DT)
            self.assertEqual((player.sprite_image, player.sprite_row), (config.PLAYER_SWORD_IMAGE, 6))
            self.assertIsNone(player.attack_box)
            if not sequence or sequence[-1] != player.animation.frame:
                sequence.append(player.animation.frame)
        self.assertEqual(sequence[:15], [1, 2, 3, 4, 5] * 3)
        self.assertEqual(set(sequence), set(range(1, 6)))
        world.controls.release("combat_s")
        world.step(config.FIXED_DT)
        self.assertEqual((player.state, player.sprite_row), ("IDLE", 1))

    def test_turning_in_place_during_parry_keeps_animation_and_deflects_incoming_rounds(self):
        world = equipped_world("sword")
        player = world.player
        player.invincible = False
        position = player.x, player.ground_y
        world.controls.press("combat_s")
        advance(world, 0.05)
        for key, facing, bullet_type in (("left", -1, ResearcherBullet), ("right", 1, RifleBullet)):
            elapsed = player.animation.elapsed
            bullet = bullet_type(player.x + facing * 10, player.ground_y, 80, -facing)
            world.projectiles.append(bullet)
            world.controls.press(key)
            world.step(config.FIXED_DT)
            self.assertEqual((player.facing, player.state, player.sprite_row), (facing, "SWORD_PARRY", 6))
            self.assertAlmostEqual(player.animation.elapsed, elapsed + config.FIXED_DT)
            self.assertTrue(bullet.deflected)
            self.assertEqual(player.hp, player.max_hp)
            world.controls.release(key)
            world.step(config.FIXED_DT)
            self.assertEqual(player.facing, facing)
            self.assertEqual((player.x, player.ground_y), position)

    @patch("projectiles.choice")
    def test_parried_rounds_enlarge_at_contact_then_bounce_and_fall(self, choose):
        for kind in (ResearcherBullet, RifleBullet):
            for facing, pick in ((-1, min), (-1, max), (1, min), (1, max)):
                choose.reset_mock()
                choose.side_effect = pick
                world = equipped_world("sword")
                player = world.player
                player.invincible = False
                floor_y = player.ground_y
                shot = kind(player.x - facing * 100, floor_y, 80, facing)
                self.assertEqual(shot.display_scale, shot.scale)
                world.projectiles.append(shot)
                world.controls.press("combat_s")
                for _ in range(60):
                    world.step(config.FIXED_DT)
                    if shot.deflected:
                        break
                self.assertTrue(shot.deflected)
                self.assertEqual((shot.facing, player.hp), (-facing, player.max_hp))
                x, height, vy = shot.x, shot.height, shot.vy
                peak_scale = shot.scale * 2.5
                self.assertEqual(shot.display_scale, peak_scale)
                world.controls.release("combat_s")
                advance(world, 0.05)
                self.assertEqual((shot.x, shot.height, shot.display_scale), (x, height, peak_scale))
                advance(world, 0.1)
                self.assertGreater((shot.x - x) * -facing, 0)
                if pick is max:
                    self.assertGreater(shot.height, height)
                else:
                    self.assertLess(shot.height, height)
                self.assertLess(shot.vy, vy)
                self.assertTrue(shot.scale < shot.display_scale < peak_scale)
                self.assertFalse(world.effects or world.damage_numbers)
                next_shot = kind(player.x, floor_y, 80, facing)
                world.projectiles.append(next_shot)
                world.step(config.FIXED_DT)
                self.assertFalse(next_shot.deflected)
                self.assertEqual(player.hp, player.max_hp - next_shot.damage)
                advance(world, 1)
                self.assertEqual(shot.display_scale, shot.scale)
                self.assertLess(shot.vy, 0)
                self.assertEqual(shot.height, shot.half_height)
                self.assertFalse(world.projectiles)
                choose.assert_called_once_with(shot.ricochet_vertical_speeds)

    @patch("projectiles.choice", side_effect=max)
    def test_airborne_parry_falls_to_the_same_landing_point_across_update_sizes(self, _choose):
        world = equipped_world("sword")
        player = world.player
        world.controls.press("combat_s")
        world.step(config.FIXED_DT)
        player.jump_height = player.previous_jump_height = 240
        for kind in (ResearcherBullet, RifleBullet):
            shot = kind(player.x - 100, player.ground_y, 320, 1)
            stepped = kind(shot.x, shot.ground_y, shot.height, shot.facing)
            shot.update(0.3, player)
            self.assertTrue(shot.deflected)
            self.assertFalse(shot.finished)
            self.assertGreater(shot.height, shot.half_height)
            shot.update(2, player)
            for _ in range(240):
                stepped.update(config.FIXED_DT, player)
            self.assertTrue(shot.finished and stepped.finished)
            self.assertEqual((shot.height, stepped.height), (shot.half_height, shot.half_height))
            self.assertAlmostEqual(shot.x, stepped.x)

    def test_melee_and_thrown_axes_still_hit_and_interrupt_the_parry(self):
        for attack in ("melee", "axe"):
            world = equipped_world("sword")
            player = world.player
            player.invincible = False
            world.controls.press("combat_s")
            world.step(config.FIXED_DT)
            if attack == "melee":
                self.assertTrue(attacking_enemy(player.x - 80).try_hit(player))
                damage = 20
            else:
                axe = EnemyAxeProjectile(player.x, player.ground_y, 80, 1)
                world.projectiles.append(axe)
                world.step(config.FIXED_DT)
                self.assertFalse(axe.deflected)
                damage = axe.damage
            self.assertEqual((player.hp, player.state), (player.max_hp - damage, "HIT"))

    def test_dropping_the_sword_ends_the_parry_and_it_can_be_picked_up(self):
        world = equipped_world("sword")
        player = world.player
        world.controls.press("combat_s")
        world.step(config.FIXED_DT)
        tap(world.controls, "weapon_interact")
        world.step(config.FIXED_DT)
        item, = world.stage.drop_items
        self.assertEqual((player.weapon, item.image_name), (None, config.SWORD_ITEM_IMAGE))
        self.assertNotEqual(player.state, "SWORD_PARRY")
        world.controls.release("combat_s")
        advance(world, 1)
        tap(world.controls, "weapon_interact")
        world.step(config.FIXED_DT)
        self.assertEqual((player.weapon, player.sprite_image), ("sword", config.PLAYER_SWORD_IMAGE))
