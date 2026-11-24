import unittest
from unittest.mock import Mock, patch

import pico2d
from sdl2 import (
    SDL_BUTTON_LEFT, SDL_BUTTON_MIDDLE, SDL_BUTTON_RIGHT, SDL_Event,
    SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST,
)

import config
from ar_soldier import ARSoldier
from axe_enemy import AxeEnemy
from combat import MOVES
from enemy import Enemy
from enemy02 import Enemy02
from game import Game
from main_menu import MainMenu
from player import Player
from projectiles import PlayerPistolBullet, ResearcherBullet, RifleBullet
from researcher import Researcher
from shield_soldier import ShieldSoldier
from tests.helpers import advance, tap
from tests.test_main_menu import mouse_event, process_menu_events
from tests.test_menu_return import key_event
from world import World


def armed_world():
    world = World()
    world.starting_weapon = "pistol"
    world.reset()
    return world


def press_fire(world):
    tap(world.controls, "combat_a")
    world.controls.release("combat_a")


class PistolShootingTests(unittest.TestCase):
    def test_r_tops_up_on_the_ground_and_in_midair(self):
        for jumping in (False, True):
            with self.subTest(jumping=jumping):
                world = armed_world()
                player = world.player
                player.pistol_ammo = 3
                if jumping:
                    tap(world.controls, "jump")
                    advance(world, 0.1)
                height = player.jump_height
                tap(world.controls, "combat_r")
                advance(world, 0.1)
                self.assertEqual((player.state, player.sprite_row, world.time_scale), ("RELOAD", 6, 1))
                if jumping:
                    self.assertGreater(player.jump_height, height)
                tap(world.controls, "combat_r")
                advance(world, 0.85)
                self.assertTrue(player.grounded)
                self.assertEqual((player.state, player.pistol_ammo), ("RELOAD", 3))
                advance(world, 0.05)
                self.assertEqual((player.state, player.pistol_ammo), ("IDLE", 7))

    def test_pistol_r_never_starts_the_raise_punch_or_queues_a_reload(self):
        world = armed_world()
        player = world.player
        tap(world.controls, "combat_r")
        world.update(config.FIXED_DT)
        self.assertEqual(player.state, "IDLE")
        player.pistol_ammo = 4
        tap(world.controls, "combat_f")
        world.update(config.FIXED_DT)
        tap(world.controls, "combat_r")
        world.update(config.FIXED_DT)
        self.assertEqual(player.state, "ATTACK_F")
        advance(world, 2)
        self.assertEqual((player.state, player.pistol_ammo), ("IDLE", 4))

    def test_hit_during_manual_reload_preserves_rounds_for_escape_and_shooting(self):
        world = armed_world()
        player = world.player
        player.pistol_ammo = 3
        tap(world.controls, "combat_r")
        advance(world, 0.5)
        player.take_damage(20)
        tap(world.controls, "jump")
        world.controls.press("left")
        advance(world, 0.75)
        self.assertEqual((player.state, player.facing, player.pistol_ammo), ("JUMP", -1, 3))
        press_fire(world)
        advance(world, 0.15)
        self.assertEqual((player.state, player.pistol_ammo), ("SHOOT", 2))

    def test_a_emits_once_at_the_first_flash_and_only_then_spends_ammo(self):
        world = armed_world()
        player = world.player
        press_fire(world)
        advance(world, 0.1, 120)
        self.assertEqual((player.state, player.sprite_row, player.pistol_ammo), ("SHOOT", 5, 7))
        self.assertFalse(world.projectiles)
        self.assertIsNone(player.take_projectile())
        advance(world, 0.025, 120)
        self.assertEqual(player.animation.frame, 2)
        self.assertEqual(player.pistol_ammo, 6)
        self.assertEqual(len(world.projectiles), 1)
        bullet = world.projectiles[0]
        self.assertIsInstance(bullet, PlayerPistolBullet)
        self.assertEqual((bullet.damage, bullet.facing, bullet.floor), (20, 1, player.floor))
        muzzle_x, muzzle_y = player.aim_line[:2]
        # First flash meets the barrel at (196, 110) in the cell, with feet at y=241.
        self.assertEqual((muzzle_x, muzzle_y), (player.x + 68 * config.SPRITE_SCALE,
                                               player.y + 131 * config.SPRITE_SCALE))
        self.assertAlmostEqual(bullet.x, muzzle_x + bullet.half_width)
        self.assertAlmostEqual(bullet.y, muzzle_y)
        self.assertIsNone(player.take_projectile())
        advance(world, 0.375, 120)
        self.assertEqual((player.state, player.pistol_ammo), ("IDLE", 6))

    def test_seven_a_presses_then_row_six_reloads_for_one_full_second(self):
        world = armed_world()
        player = world.player
        for shot in range(7):
            press_fire(world)
            advance(world, 0.5, 120)
            self.assertEqual(player.pistol_ammo, 6 - shot)
            self.assertEqual(player.state, "IDLE" if shot < 6 else "RELOAD")
        self.assertEqual((player.sprite_image, player.sprite_row, player.animation.frame),
                         (config.PLAYER_PISTOL_IMAGE, 6, 0))
        for _ in range(59):
            press_fire(world)  # Early presses are consumed, never queued.
            world.update(1 / 60)
            self.assertEqual(player.pistol_ammo, 0)
        world.update(1 / 60)
        self.assertEqual((player.state, player.pistol_ammo), ("IDLE", 7))
        advance(world, 0.6)
        self.assertEqual(player.pistol_ammo, 7)
        press_fire(world)
        advance(world, 0.15)
        self.assertEqual(player.pistol_ammo, 6)

    def test_holding_a_does_not_repeat_after_shooting_or_reloading(self):
        world = armed_world()
        world.controls.press("combat_a")
        advance(world, 3)
        self.assertEqual((world.player.state, world.player.pistol_ammo), ("IDLE", 6))
        world.player.pistol_ammo = 0
        advance(world, 2)
        self.assertEqual((world.player.state, world.player.pistol_ammo), ("IDLE", 7))

    def test_a_presses_in_blocked_states_are_consumed_without_a_later_shot(self):
        for state in ("HIT", "DYING", "DEAD", "RELOAD", "SHOOT", "melee", "stair"):
            with self.subTest(state=state):
                world = armed_world()
                player = world.player
                if state == "melee":
                    player.start_move(MOVES["combat_f"], 1)
                elif state == "stair":
                    player.staircase = object()
                else:
                    player.animation.set_state(state)
                press_fire(world)
                player.handle_input(world.controls)
                self.assertFalse(player.pistol_shot_pending)
                if state == "melee":
                    self.assertIs(player.active_move, MOVES["combat_f"])
                self.assertFalse(world.controls.pressed)
                player.staircase = None
                player.cancel_combat()
                player.animation.set_state("IDLE")
                advance(world, 0.6)
                self.assertEqual(player.pistol_ammo, 7)
                self.assertFalse(world.projectiles)

    def test_hit_before_flash_cancels_without_spending_and_uses_row_seven(self):
        world = armed_world()
        press_fire(world)
        advance(world, 0.1)
        world.player.take_damage(20)
        self.assertEqual(world.player.sprite_row, 7)
        advance(world, 1)
        self.assertEqual((world.player.state, world.player.pistol_ammo), ("IDLE", 7))
        self.assertFalse(world.projectiles)
        world.player.take_damage(500)
        self.assertEqual(world.player.sprite_row, 8)
        advance(world, 1)
        self.assertEqual((world.player.state, world.player.sprite_row), ("DEAD", 8))

    def test_reload_interruption_keeps_zero_and_restarts_after_hit_recovery(self):
        world = armed_world()
        player = world.player
        player.pistol_ammo = 0
        advance(world, 0.5)
        self.assertEqual(player.state, "RELOAD")
        player.take_damage(20)
        advance(world, 0.7)
        self.assertEqual((player.state, player.pistol_ammo), ("RELOAD", 0))
        self.assertLess(player.animation.elapsed, 0.1)
        advance(world, 0.8)
        self.assertEqual(player.pistol_ammo, 0)
        advance(world, 0.2)
        self.assertEqual((player.state, player.pistol_ammo), ("IDLE", 7))

    def test_jump_tapped_during_reload_hit_escapes_once_after_recovery(self):
        world = armed_world()
        player = world.player
        player.pistol_ammo = 0
        advance(world, 0.4)
        enemy = Enemy(player.x + 80, facing=-1, ground_y=player.ground_y)
        world.enemies.append(enemy)
        enemy.start_attack()
        enemy.animation.elapsed = min(enemy.attack_active_frames) / enemy.animation.definitions["ATTACK"][1]
        world.update(config.FIXED_DT)
        self.assertEqual(player.state, "HIT")

        world.controls.press("jump")
        world.controls.press("combat_a")
        world.update(config.FIXED_DT)
        world.controls.release("jump")
        self.assertEqual(player.jump_count, 0)
        advance(world, 0.7)
        self.assertEqual((player.state, player.jump_count, player.pistol_ammo), ("JUMP", 1, 0))
        self.assertGreater(player.jump_height, 0)
        self.assertFalse(world.projectiles)
        world.controls.press("left")
        advance(world, 0.1)
        self.assertEqual(player.facing, -1)
        self.assertLess(player.x, config.START_X)

    def test_can_turn_and_run_out_of_restarted_reload_then_refill_after_stopping(self):
        world = armed_world()
        player = world.player
        player.pistol_ammo = 0
        advance(world, 0.5)
        player.take_damage(20)
        advance(world, 0.9)
        self.assertEqual(player.state, "RELOAD")

        world.controls.press("left")
        world.controls.press("left_shift")
        world.update(config.FIXED_DT)
        self.assertEqual((player.state, player.facing, player.pistol_ammo), ("RUN", -1, 0))
        self.assertLess(player.x, config.START_X)
        advance(world, 1.2)
        self.assertEqual((player.state, player.pistol_ammo), ("RUN", 0))
        world.controls.release("left")
        advance(world, 0.95)
        self.assertEqual((player.state, player.pistol_ammo), ("RELOAD", 0))
        advance(world, 0.05)
        self.assertEqual((player.state, player.pistol_ammo), ("IDLE", 7))

    def test_walking_and_running_continue_through_the_entire_shot(self):
        for direction, sign in (("left", -1), ("right", 1)):
            for running in (False, True):
                with self.subTest(direction=direction, running=running):
                    world = armed_world()
                    player = world.player
                    world.controls.press(direction)
                    if running:
                        world.controls.press("left_shift")
                    advance(world, 0.4)
                    speed = sign * (config.RUN_SPEED if running else config.WALK_SPEED)
                    start_x = player.x
                    press_fire(world)
                    advance(world, 0.125, 120)
                    self.assertEqual((player.state, player.vx, player.pistol_ammo), ("SHOOT", speed, 6))
                    self.assertEqual((player.sprite_row, player.animation.frame), (10 if running else 9, 2))
                    self.assertAlmostEqual(player.x, start_x + speed * 0.125)
                    bullet, = world.projectiles
                    muzzle_x, muzzle_y = player.aim_line[:2]
                    forward, height = (78, 121) if running else (59, 127)
                    self.assertAlmostEqual(muzzle_x, player.x + sign * forward * config.SPRITE_SCALE)
                    self.assertAlmostEqual(muzzle_y, player.y + height * config.SPRITE_SCALE)
                    self.assertAlmostEqual(bullet.x, muzzle_x + sign * bullet.half_width)
                    self.assertAlmostEqual(bullet.y, muzzle_y)
                    advance(world, 0.25, 120)
                    self.assertEqual((player.sprite_row, player.animation.frame), (3 if running else 2, 6))
                    self.assertEqual(player.pistol_ammo, 6)
                    advance(world, 0.125, 120)
                    self.assertEqual(player.state, "RUN" if running else "WALK")
                    self.assertAlmostEqual(player.x, start_x + speed * 0.5)

    def test_walking_and_running_continue_through_manual_and_automatic_reload(self):
        for running in (False, True):
            for starting_ammo in (7, 1):
                with self.subTest(running=running, starting_ammo=starting_ammo):
                    world = armed_world()
                    player = world.player
                    player.pistol_ammo = starting_ammo
                    world.controls.press("right")
                    if running:
                        world.controls.press("left_shift")
                    advance(world, 0.3)
                    speed = config.RUN_SPEED if running else config.WALK_SPEED
                    press_fire(world)
                    advance(world, 0.5)
                    if starting_ammo > 1:
                        tap(world.controls, "combat_r")
                    start_x = player.x
                    advance(world, 0.5)
                    self.assertEqual((player.state, player.sprite_row, player.pistol_ammo),
                                     ("RELOAD", 12 if running else 11, starting_ammo - 1))
                    self.assertAlmostEqual(player.x, start_x + speed * 0.5)
                    advance(world, 0.5)
                    self.assertEqual((player.state, player.pistol_ammo), ("RUN" if running else "WALK", 7))
                    self.assertAlmostEqual(player.x, start_x + speed)

    def test_reload_switches_rows_without_restarting_as_gait_changes(self):
        world = armed_world()
        player = world.player
        player.pistol_ammo = 4
        tap(world.controls, "combat_r")
        advance(world, 0.2)
        self.assertEqual((player.sprite_row, player.animation.frame), (6, 1))
        world.controls.press("left")
        advance(world, 0.2)
        self.assertEqual((player.sprite_row, player.animation.frame, player.facing), (11, 3, -1))
        world.controls.press("left_shift")
        advance(world, 0.2)
        self.assertEqual((player.sprite_row, player.animation.frame), (12, 4))
        world.controls.release("left")
        advance(world, 0.2)
        self.assertEqual((player.sprite_row, player.animation.frame, player.pistol_ammo), (6, 6, 4))
        advance(world, 0.2)
        self.assertEqual((player.state, player.pistol_ammo), ("IDLE", 7))

    def test_turning_during_windup_uses_the_new_facing_and_depth_for_the_bullet(self):
        world = armed_world()
        player = world.player
        world.controls.press("right")
        advance(world, 0.2)
        press_fire(world)
        advance(world, 0.05, 120)
        initial_depth = player.ground_y
        world.controls.release("right")
        world.controls.press("left")
        world.controls.press("up")
        advance(world, 0.075, 120)
        bullet, = world.projectiles
        self.assertLess(player.vx, 0)
        self.assertGreater(player.ground_y, initial_depth)
        self.assertEqual((bullet.facing, bullet.ground_y), (-1, player.ground_y))
        self.assertAlmostEqual(bullet.x, player.aim_line[0] - bullet.half_width)

    def test_airborne_shooting_and_reloading_preserve_gravity(self):
        world = armed_world()
        player = world.player
        player.jump_height, player.vy, player.jump_count = 350, -20, 1
        player.animation.set_state("JUMP")
        world.controls.press("right")
        world.controls.press("up")
        press_fire(world)
        position = player.x, player.ground_y
        advance(world, 0.15)
        self.assertEqual((player.x, player.ground_y), position)
        self.assertLess(player.jump_height, 350)
        self.assertLess(player.vy, -20)
        tap(world.controls, "jump")
        world.update(config.FIXED_DT)
        self.assertEqual(player.jump_count, 1)
        player.pistol_ammo = 0
        advance(world, 0.4)
        self.assertEqual(player.state, "RELOAD")
        self.assertEqual((player.x, player.ground_y), position)

    def test_aim_line_follows_direction_depth_jump_and_world_edges(self):
        player = Player()
        self.assertIsNone(player.aim_line)
        player.equip_weapon("pistol")
        player.ground_y, player.jump_height = 180, 120
        for facing in (-1, 1):
            for x in (68, 1280, 2492):
                player.x, player.facing = x, facing
                height = player.y + 106 * config.SPRITE_SCALE  # First IDLE frame.
                self.assertEqual(player.aim_line, (
                    x + facing * 58 * config.SPRITE_SCALE, height,
                    max(0, min(config.WORLD_WIDTH, x + facing * config.PLAYER_PISTOL_RANGE)), height))
        for state in ("HIT", "RELOAD", "DYING", "DEAD"):
            player.animation.set_state(state)
            self.assertIsNone(player.aim_line)

    def test_aim_renderer_uses_the_researchers_red_dots_and_camera_coordinates(self):
        from assets import Assets

        player = armed_world().player
        line = player.aim_line
        with patch("pico2d.draw_circle") as draw:
            Assets.draw_researcher_aim(Mock(), player, 1000, 20)
        self.assertGreater(draw.call_count, 20)
        first = draw.call_args_list[0].args
        self.assertEqual(first, (line[0] - 1000, line[1] - 20, 2, 255, 45, 55))
        self.assertTrue(draw.call_args_list[0].kwargs["filled"])

    def test_equipment_switch_cancels_a_pending_shot_and_existing_melee_still_works(self):
        world = armed_world()
        press_fire(world)
        advance(world, 0.1)
        world.player.equip_weapon("steel_pipe")
        advance(world, 0.5)
        self.assertFalse(world.projectiles)
        self.assertEqual(world.player.pistol_ammo, 7)
        for weapon in ("steel_pipe", None):
            world.player.equip_weapon(weapon)
            tap(world.controls, "combat_a")
            world.update(config.FIXED_DT)
            self.assertIs(world.player.active_move, world.player.moves["combat_a"])
            self.assertEqual(world.player.pistol_ammo, 7)
        self.assertIs(world.player.active_move, MOVES["combat_a"])

    def test_mid_hit_pistol_swap_preserves_the_current_recovery_speed_and_clock(self):
        for original, replacement, fps in (("steel_pipe", "pistol", 40), ("pistol", "steel_pipe", 12)):
            world = World()
            player = world.player
            player.equip_weapon(original)
            player.take_damage(20)
            advance(world, 0.05)
            elapsed = player.animation.elapsed
            player.equip_weapon(replacement)
            self.assertEqual(player.animation.elapsed, elapsed)
            self.assertEqual(player.animation.definitions["HIT"][1], fps)
            self.assertEqual(player.sprite_row, 7 if replacement == "pistol" else 5)
            advance(world, 0.17 if fps == 40 else 0.65)
            self.assertEqual(player.state, "IDLE")
            player.take_damage(20)
            self.assertEqual(player.animation.definitions["HIT"][1],
                             12 if replacement == "pistol" else 40)

    def test_normal_stage_exit_is_blocked_during_shooting_and_reloading(self):
        for state in ("SHOOT", "RELOAD"):
            world = armed_world()
            player = world.player
            world.stage.arrows_visible = True
            player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
            player.animation.set_state(state)
            world.controls.press("right")
            self.assertFalse(world.try_stage_transition())
            self.assertEqual(world.stage_index, 0)

    def test_stage_change_loading_and_restart_preserve_or_reset_the_right_clocks(self):
        world = armed_world()
        press_fire(world)
        advance(world, 0.2)
        bullet = world.projectiles[0]
        ammo, elapsed = world.player.pistol_ammo, world.player.animation.elapsed
        snapshot = bullet.x, bullet.height, bullet.elapsed
        world.select_stage(1)
        self.assertEqual((world.player.pistol_ammo, world.player.animation.elapsed), (ammo, elapsed))
        advance(world, 0.5)
        world.select_stage(0)
        self.assertEqual((bullet.x, bullet.height, bullet.elapsed), snapshot)
        world.player.pistol_ammo = 0
        world.player.start_pistol_reload()
        world.pending_stage_index, world.stage_loading_remaining = 1, 2
        press_fire(world)
        world.update(1)
        self.assertEqual((world.player.pistol_ammo, world.player.animation.elapsed), (0, 0))
        self.assertFalse(world.controls.pressed)
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertEqual((world.player.weapon, world.player.pistol_ammo, world.player.state),
                         ("pistol", 7, "IDLE"))
        self.assertTrue(all(not stage.projectiles for stage in world.stages))

    def test_shooting_ammo_and_reload_are_identical_at_different_render_rates(self):
        results = []
        for fps in (30, 60, 120, 144):
            world = armed_world()
            for _ in range(7):
                press_fire(world)
                advance(world, 1, fps)
            self.assertEqual((world.player.pistol_ammo, world.player.state), (0, "RELOAD"))
            advance(world, 0.5, fps)
            results.append((world.player.pistol_ammo, world.player.state, len(world.projectiles)))
        self.assertTrue(all(result == (7, "IDLE", 0) for result in results))


class PistolBulletTests(unittest.TestCase):
    def test_nearest_living_enemy_is_hit_once_in_either_direction_regardless_of_list_order(self):
        for facing in (-1, 1):
            near, far, dead = (Enemy(1280 + facing * gap) for gap in (150, 260, 80))
            dead.take_damage(500)
            bullet = PlayerPistolBullet(1280, 100, 80, facing)
            self.assertTrue(bullet.update(0.5, [far, dead, near]))
            self.assertIs(bullet.impact_target, near)
            self.assertEqual((near.hp, far.hp, bullet.impact_damage), (180, 200, 20))
            self.assertFalse(bullet.update(1, [far, near]))
            self.assertEqual((near.hp, far.hp), (180, 200))

    def test_depth_height_floor_and_stair_filters_match_existing_pistol_ballistics(self):
        for situation in ("depth_edge", "depth_out", "jump", "floor", "stair"):
            enemy = Enemy(1400)
            if situation == "jump":
                enemy.jump_height = enemy.previous_jump_height = 200
            elif situation == "floor":
                enemy.floor = 1
            elif situation == "stair":
                enemy.staircase = object()
            depth = 32 if situation == "depth_edge" else 32.01 if situation == "depth_out" else 0
            bullet = PlayerPistolBullet(1280, 100 + depth, 80, 1)
            self.assertEqual(bullet.update(0.3, [enemy]), situation == "depth_edge")
            self.assertEqual(enemy.hp, 180 if situation == "depth_edge" else 200)

    def test_fast_sweep_hits_a_crossing_enemy_only_at_the_same_depth_and_time(self):
        for approaches in (True, False):
            enemy = Enemy(1400)
            enemy.previous_ground_y, enemy.ground_y = ((140, 60) if approaches else (300, 100))
            bullet = PlayerPistolBullet(1280, 100, 80, 1)
            self.assertEqual(bullet.update(0.3, [enemy]), approaches)

    def test_every_enemy_type_receives_twenty_and_real_guard_damage_is_reported(self):
        for kind in (Enemy, Enemy02, AxeEnemy, Researcher, ARSoldier, ShieldSoldier):
            world = armed_world()
            enemy = kind(1400)
            world.enemies = [enemy]
            bullet = PlayerPistolBullet(1280, 100, 80, 1)
            world.projectiles.append(bullet)
            world.update_projectiles(0.3)
            self.assertEqual(enemy.hp, enemy.max_hp - 20)
            self.assertEqual(world.damage_numbers[0].damage, 20)
            self.assertEqual(len(world.effects), 1)
            self.assertGreater(world.camera.shake_remaining, 0)
            self.assertFalse(world.projectiles)
            self.assertEqual(world.player.hp, 500)
        world = armed_world()
        guard = ShieldSoldier(1400)
        guard.start_guard()
        world.enemies = [guard]
        world.projectiles.append(PlayerPistolBullet(1280, 100, 80, 1))
        world.update_projectiles(0.3)
        self.assertEqual((guard.hp, world.damage_numbers[0].damage), (390, 10))

    def test_lethal_bullet_reports_remaining_hp_and_never_pierces(self):
        world = armed_world()
        near, far = Enemy(1400), Enemy(1500)
        near.hp = 7
        world.enemies = [near, far]
        world.projectiles.append(PlayerPistolBullet(1280, 100, 80, 1))
        world.update_projectiles(0.5)
        self.assertEqual((near.hp, near.state, far.hp), (0, "DYING", 200))
        self.assertEqual(world.damage_numbers[0].damage, 7)
        world.update_projectiles(1)
        self.assertEqual(len(world.effects), 1)

    def test_player_and_enemy_rounds_keep_their_own_targets_and_damage(self):
        world = armed_world()
        enemy = Enemy(1450)
        world.enemies = [enemy]
        world.projectiles.extend((
            PlayerPistolBullet(1320, 100, 80, 1),
            ResearcherBullet(1200, 100, 80, 1),
            RifleBullet(1200, 100, 80, 1),
        ))
        world.update_projectiles(0.3)
        self.assertEqual((enemy.hp, world.player.hp), (180, 465))
        self.assertEqual(world.player.pistol_ammo, 7)

    def test_player_bullets_keep_researcher_flight_and_survive_player_death(self):
        world = armed_world()
        bullet = PlayerPistolBullet(300, 100, 80, 1)
        world.projectiles.append(bullet)
        world.player.take_damage(500)
        world.update_projectiles(1.3)
        self.assertIn(bullet, world.projectiles)
        self.assertTrue(bullet.falling)
        self.assertAlmostEqual(bullet.x, 1470)
        self.assertAlmostEqual(bullet.height, 80 - 900 * 0.05 ** 2 / 2)
        world.update_projectiles(0.5)
        self.assertFalse(world.projectiles)
        self.assertTrue(bullet.finished)

    def test_new_bullets_do_not_sweep_an_enemys_position_from_before_they_existed(self):
        enemy = Enemy(1500)
        enemy.previous_x = 1280
        bullet = PlayerPistolBullet(1280, 100, 80, 1)
        self.assertFalse(bullet.update(0, [enemy]))
        self.assertEqual(enemy.hp, 200)


class PistolInputTests(unittest.TestCase):
    def setUp(self):
        self.game = Game.__new__(Game)
        self.game.world, self.game.menu = armed_world(), MainMenu()
        self.game.running, self.game._menu_requested, self.game._escape_held = True, False, False

    def process(self, *events, menu_screen=False):
        return process_menu_events(self.game, *events, menu_screen=menu_screen)

    def test_gameplay_mouse_buttons_do_not_fire(self):
        for button in (SDL_BUTTON_LEFT, SDL_BUTTON_MIDDLE, SDL_BUTTON_RIGHT):
            self.process(mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, 800, 300, button),
                         mouse_event(pico2d.SDL_MOUSEBUTTONUP, 800, 300, button))
        advance(self.game.world, 0.15)
        self.assertEqual((self.game.world.player.state, self.game.world.player.pistol_ammo), ("IDLE", 7))
        self.assertFalse(self.game.world.projectiles)

    def test_a_fires_once_until_released_and_pressed_again(self):
        down = key_event(pico2d.SDLK_a)
        self.process(down, down)
        advance(self.game.world, 2)
        self.assertEqual(self.game.world.player.pistol_ammo, 6)
        self.process(key_event(pico2d.SDLK_a, repeat=True))
        advance(self.game.world, 0.6)
        self.assertEqual(self.game.world.player.pistol_ammo, 6)
        self.process(key_event(pico2d.SDLK_a, down=False), down)
        advance(self.game.world, 0.15)
        self.assertEqual(self.game.world.player.pistol_ammo, 5)

    def test_menu_and_escape_batches_cannot_leave_a_pending_shot(self):
        down = key_event(pico2d.SDLK_a)
        self.process(down, menu_screen=True)
        self.assertFalse(self.game.world.controls.pressed)
        self.process(down, key_event(), down)
        self.assertTrue(self.game._menu_requested)
        self.assertFalse(self.game.world.controls.held)
        self.assertFalse(self.game.world.controls.pressed)

    def test_focus_loss_clears_pending_and_held_fire_key(self):
        event = SDL_Event()
        event.type, event.window.event = SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST
        self.process(key_event(pico2d.SDLK_a), event)
        self.assertNotIn("combat_a", self.game.world.controls.held)
        self.assertNotIn("combat_a", self.game.world.controls.pressed)
        advance(self.game.world, 0.6)
        self.assertEqual(self.game.world.player.pistol_ammo, 7)


if __name__ == "__main__":
    unittest.main()
