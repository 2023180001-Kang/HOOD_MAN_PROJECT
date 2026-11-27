import unittest
from math import cos, radians, sin
from unittest.mock import Mock, call, patch

import config
from axe_enemy import AxeEnemy
from enemy import Enemy
from main_menu import MainMenu
from projectiles import EnemyAxeProjectile, ResearcherBullet, RifleBullet, SniperBullet
from researcher import Researcher
from tests.helpers import advance, tap
from tests.test_bag_drag import slot_center
from tests.test_combat import attacking_enemy
from tests.test_weapon_combat import double_jump, equipped_world, target
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

    def test_double_jump_second_d_slashes_on_descent_and_leaves_sword_afterimages(self):
        for side in (-1, 1):
            with self.subTest(side=side):
                world = equipped_world("sword")
                player = world.player
                double_jump(world)
                advance(world, 0.23)
                enemy = target(world, side=side)
                enemy.x = player.x + side * 165
                tap(world.controls, "combat_d")
                advance(world, 0.2)
                self.assertEqual((player.weapon_leap_phase, world.time_scale), ("AIM", 0.2))
                self.assertIsNone(player.attack_box)
                self.assertFalse(world.afterimages)
                self.assertEqual(enemy.hp, 200)

                world.controls.press("left" if side < 0 else "right")
                tap(world.controls, "combat_d")
                for _ in range(60):
                    world.step(config.FIXED_DT)
                    if enemy.hp < 200:
                        break
                self.assertEqual((player.weapon_leap_phase, enemy.hp), ("DIVE", 130))
                self.assertGreater(player.jump_height, 0)
                self.assertLess(player.vy, 0)
                self.assertEqual((player.sprite_image, player.sprite_row), (config.PLAYER_SWORD_IMAGE, 5))
                self.assertGreaterEqual(len(world.afterimages), 2)
                for image in world.afterimages:
                    self.assertEqual((image.image_name, image.row, image.facing), (config.PLAYER_SWORD_IMAGE, 5, side))
                    self.assertGreater(image.jump_height, player.jump_height)
                world.controls.release("left" if side < 0 else "right")
                advance(world, 0.7)
                self.assertEqual((player.state, world.time_scale, enemy.hp), ("IDLE", 1, 130))
                self.assertFalse(world.afterimages)

    def test_sword_d_on_ground_or_first_jump_keeps_the_basic_kick(self):
        for jumping in (False, True):
            world = equipped_world("sword")
            if jumping:
                tap(world.controls, "jump")
                world.step(config.FIXED_DT)
            tap(world.controls, "combat_d")
            world.step(config.FIXED_DT)
            self.assertEqual((world.player.active_move.name, world.player.active_move.damage), ("왼발 차기", 20))
            self.assertIsNone(world.player.weapon_leap_phase)
            self.assertEqual(world.time_scale, 1)

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

    def test_moving_parry_uses_full_stride_and_deflects_at_walking_and_running_speed(self):
        for key, facing, running, row in (("left", -1, False, 9), ("right", 1, True, 10)):
            with self.subTest(row=row):
                world = equipped_world("sword")
                player = world.player
                player.invincible = False
                world.controls.press(key)
                if running:
                    world.controls.press("left_shift")
                advance(world, 0.4)
                speed = config.RUN_SPEED if running else config.WALK_SPEED
                start = player.x
                world.controls.press("combat_s")
                frames = set()
                for _ in range(48):
                    world.step(config.FIXED_DT)
                    self.assertEqual((player.state, player.sprite_row, player.facing), ("SWORD_PARRY", row, facing))
                    self.assertEqual(player.vx, facing * speed)
                    frames.add(player.animation.frame)
                self.assertEqual(frames, set(range(8)))
                self.assertAlmostEqual(player.x - start, facing * speed * 48 * config.FIXED_DT)
                for kind in (ResearcherBullet, RifleBullet, EnemyAxeProjectile):
                    shot = kind(player.x + facing * 10, player.ground_y, 80, -facing)
                    world.projectiles.append(shot)
                    world.step(config.FIXED_DT)
                    self.assertTrue(shot.deflected)
                self.assertEqual(player.hp, player.max_hp)
                world.controls.release("combat_s")
                world.step(config.FIXED_DT)
                self.assertEqual((player.sprite_row, player.vx), (3 if running else 2, facing * speed))

    def test_held_parry_switches_rows_with_depth_movement_shift_and_stop(self):
        world = equipped_world("sword")
        player = world.player
        x, y = player.x, player.ground_y
        world.controls.press("combat_s")
        world.controls.press("up")
        advance(world, 0.05)
        self.assertEqual((player.sprite_row, player.x), (9, x))
        self.assertGreater(player.ground_y, y)
        world.controls.press("right_shift")
        world.controls.press("left")
        world.step(config.FIXED_DT)
        self.assertEqual((player.sprite_row, player.facing), (10, -1))
        world.controls.release("right_shift")
        world.step(config.FIXED_DT)
        self.assertEqual(player.sprite_row, 9)
        world.controls.release("up")
        world.controls.release("left")
        advance(world, 0.2)
        self.assertEqual((player.state, player.sprite_row, player.vx, player.ground_vy), ("SWORD_PARRY", 6, 0, 0))
        self.assertIn(player.animation.frame, range(1, 6))

    @patch("projectiles.uniform")
    def test_parried_volley_spreads_immediately_while_enlarging_then_falls(self, roll_angle):
        angles = [radians(degrees) for degrees in (-72, -20, 8, 43, 76)]
        for kind in (ResearcherBullet, RifleBullet):
            for facing in (-1, 1):
                roll_angle.reset_mock()
                roll_angle.side_effect = angles
                world = equipped_world("sword")
                player = world.player
                player.invincible = False
                world.controls.press("combat_s")
                world.step(config.FIXED_DT)
                contact_x = (player.body.left - kind.half_width if facing == 1
                             else player.body.right + kind.half_width)
                shots = [kind(contact_x, player.ground_y, 80, facing) for _ in angles]
                world.projectiles.extend(shots)
                dt = config.FIXED_DT
                world.step(dt)
                for shot, angle in zip(shots, angles):
                    self.assertEqual(shot.facing, -facing)
                    self.assertAlmostEqual(shot.x, contact_x - facing * kind.ricochet_speed * cos(angle) * dt)
                    self.assertAlmostEqual(shot.height, 80 + kind.ricochet_speed * sin(angle) * dt
                                           - kind.gravity * dt**2 / 2)
                    self.assertGreater(shot.display_scale, kind.scale)
                self.assertEqual(player.hp, player.max_hp)
                first_scale = shots[0].display_scale
                world.controls.release("combat_s")
                advance(world, 2 / 60)
                near_peak_scale = shots[0].display_scale
                self.assertGreater(near_peak_scale, first_scale)
                self.assertAlmostEqual(near_peak_scale / kind.scale, 2.5, delta=0.05)
                advance(world, 0.05)
                for shot in shots:
                    self.assertTrue(kind.scale < shot.display_scale < near_peak_scale)
                self.assertFalse(world.effects or world.damage_numbers)
                next_shot = kind(player.x, player.ground_y, 80, facing)
                world.projectiles.append(next_shot)
                world.step(dt)
                self.assertFalse(next_shot.deflected)
                self.assertEqual(player.hp, player.max_hp - next_shot.damage)
                advance(world, 1.5)
                for shot in shots:
                    self.assertLess(shot.vy, 0)
                    self.assertEqual(shot.height, shot.half_height)
                self.assertEqual(shots[-1].display_scale, kind.scale)
                self.assertFalse(world.projectiles)
                self.assertEqual(roll_angle.call_args_list,
                                 [call(-kind.ricochet_max_angle, kind.ricochet_max_angle)] * len(shots))

    @patch("projectiles.uniform", return_value=0.0)
    def test_returning_volley_hits_first_enemy_in_lane_once_with_each_rounds_damage(self, _angle):
        for side in (-1, 1):
            for steps in (1, 60):
                with self.subTest(side=side, steps=steps):
                    world = equipped_world("sword")
                    player = world.player
                    player.invincible = False
                    world.controls.press("combat_s")
                    world.step(config.FIXED_DT)
                    x, y = player.x, player.ground_y
                    shooter = Enemy(x + side * 100, ground_y=y)
                    far = Enemy(x + side * 170, ground_y=y)
                    off_lane = Enemy(x + side * 70, ground_y=y + config.ATTACK_DEPTH_TOLERANCE + 1)
                    world.enemies = [far, off_lane, shooter]
                    rounds = [kind(x + side * 190, y, 80, -side, shooter=shooter)
                              for kind in (ResearcherBullet, RifleBullet, SniperBullet)]
                    world.projectiles.extend(rounds)
                    for _ in range(steps):
                        world.update_projectiles(0.6 / steps)
                    self.assertTrue(all(shot.deflected and shot.impact_target is shooter for shot in rounds))
                    self.assertEqual([shot.impact_damage for shot in rounds], [30, 5, 90])
                    self.assertCountEqual([number.damage for number in world.damage_numbers], [30, 5, 90])
                    self.assertEqual(shooter.hp, shooter.max_hp - 125)
                    self.assertEqual((far.hp, off_lane.hp, player.hp), (far.max_hp, off_lane.max_hp, player.max_hp))
                    self.assertFalse(world.projectiles)

    def test_point_blank_parry_hits_an_overlapping_enemy_on_the_emission_tick(self):
        world = equipped_world("sword")
        player = world.player
        player.invincible = False
        world.controls.press("combat_s")
        world.step(config.FIXED_DT)
        shooter = Researcher(player.x - Researcher.muzzle_x - ResearcherBullet.half_width,
                             1, ground_y=player.ground_y)
        victim = Enemy(player.x, ground_y=player.ground_y)
        world.enemies = [shooter, victim]
        shooter.start_attack()
        shooter.update_attack(shooter.aim_duration)
        world.update_projectiles(0)
        self.assertEqual(shooter.ammo, shooter.magazine_size - 1)
        self.assertEqual((victim.hp, player.hp), (victim.max_hp - 30, player.max_hp))
        self.assertEqual([number.damage for number in world.damage_numbers], [30])
        self.assertFalse(world.projectiles)

    @patch("projectiles.uniform", return_value=radians(64))
    def test_airborne_parry_falls_to_the_same_landing_point_across_update_sizes(self, _roll_angle):
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

    def test_parried_axe_flies_level_then_drops_at_its_range_or_the_map_edge(self):
        for direction in (-1, 1):
            for near_edge in (False, True):
                with self.subTest(direction=direction, near_edge=near_edge):
                    world = equipped_world("sword")
                    player = world.player
                    if near_edge:
                        player.x = player.previous_x = 140 if direction > 0 else world.stage.width - 140
                    world.controls.press("combat_s")
                    world.step(config.FIXED_DT)
                    contact_x = (player.body.left - EnemyAxeProjectile.half_width if direction > 0
                                 else player.body.right + EnemyAxeProjectile.half_width)
                    axe = EnemyAxeProjectile(contact_x, player.ground_y, 90, direction)
                    world.projectiles.append(axe)
                    world.update_projectiles(0.05)
                    self.assertEqual((axe.deflected, axe.facing, axe.height), (True, -direction, 90))
                    self.assertAlmostEqual(axe.x, contact_x - direction * 24)
                    world.update_projectiles(1.25)
                    self.assertEqual(world.projectiles, [])
                    item, = world.stage.drop_items
                    left, right = axe.horizontal_limits
                    landing_x = max(left, min(right, contact_x - direction * config.AXE_RETURN_RANGE))
                    self.assertAlmostEqual(item.x, landing_x)
                    self.assertFalse(item.grounded)
                    self.assertEqual(item.vy, 0)
                    advance(world, 1)
                    self.assertTrue(item.grounded)
                    self.assertAlmostEqual(item.x, landing_x)

    def test_returning_axe_pierces_each_enemy_once_including_the_thrower(self):
        for incoming in (-1, 1):
            for steps in (1, 60):
                with self.subTest(incoming=incoming, steps=steps):
                    world = equipped_world("sword")
                    player = world.player
                    player.invincible = False
                    world.controls.press("combat_s")
                    world.step(config.FIXED_DT)
                    edge = player.body.left if incoming > 0 else player.body.right
                    contact_x = edge - incoming * EnemyAxeProjectile.half_width
                    lane = player.ground_y
                    shooter = AxeEnemy(contact_x - incoming * 95, ground_y=lane)
                    shooter._set_armed(False)
                    pair = [Enemy(contact_x - incoming * 35, ground_y=lane) for _ in range(2)]
                    far = Enemy(contact_x - incoming * (config.AXE_RETURN_RANGE + 100), ground_y=lane)
                    off_lane = Enemy(shooter.x, ground_y=lane + config.AXE_RETURN_HIT_DEPTH + 1)
                    world.enemies = [shooter, far, off_lane, *pair]
                    axe = EnemyAxeProjectile(contact_x - incoming * 200, lane, 90, incoming, shooter=shooter)
                    world.projectiles.append(axe)
                    world.update_projectiles(160 / axe.speed)
                    self.assertTrue(all(enemy.hp == enemy.max_hp for enemy in world.enemies))
                    for _ in range(steps):
                        world.update_projectiles(1.5 / steps)
                    self.assertEqual([enemy.max_hp - enemy.hp for enemy in world.enemies], [50, 0, 0, 50, 50])
                    self.assertEqual(player.hp, player.max_hp)
                    self.assertEqual([number.damage for number in world.damage_numbers], [50, 50, 50])
                    self.assertEqual(len(world.effects), 3)
                    self.assertFalse(world.projectiles)
                    drop, = world.stage.drop_items
                    self.assertIs(drop.axe_owner, shooter)
                    self.assertAlmostEqual(drop.x, contact_x - incoming * config.AXE_RETURN_RANGE)

    def test_melee_hits_during_parry(self):
        world = equipped_world("sword")
        player = world.player
        player.invincible = False
        world.controls.press("combat_s")
        world.step(config.FIXED_DT)
        self.assertTrue(attacking_enemy(player.x - 80).try_hit(player))
        self.assertEqual((player.hp, player.state), (player.max_hp - 20, "HIT"))

    def test_releasing_s_before_axe_contact_takes_full_throw_damage(self):
        world = equipped_world("sword")
        player = world.player
        player.invincible = False
        world.controls.press("combat_s")
        world.step(config.FIXED_DT)
        world.controls.release("combat_s")
        axe = EnemyAxeProjectile(player.x, player.ground_y, 80, 1)
        world.projectiles.append(axe)
        world.step(config.FIXED_DT)
        self.assertFalse(axe.deflected)
        self.assertEqual((player.hp, player.state), (player.max_hp - 50, "HIT"))

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
