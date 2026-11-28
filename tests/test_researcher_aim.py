import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pico2d

import config
from assets import Assets
from combat import STRONG_MOVES
from game import Game
from researcher import Researcher
from tests.helpers import advance, enter_kick_wait, tap
from tests.helpers import ManualSpawnWorld as World


def encounter(index=6, side=1, speed=1.0):
    world = World(item_rng=random.Random(23))
    world.select_stage(index)
    world.player.invincible = True
    enemy = Researcher(world.player.x + side * 300, -side,
                       ground_y=world.player.ground_y, attack_speed=speed)
    enemy.walkable = world.stage.walkable
    world.enemies.append(enemy)
    return world, enemy


class ResearcherAimTests(unittest.TestCase):
    def test_both_interiors_warn_for_half_a_second_before_firing_at_every_attack_speed(self):
        for index in (6, 7):
            for side in (-1, 1):
                for speed in (0.8, 1.0, 1.4):
                    with self.subTest(index=index, side=side, speed=speed):
                        world, enemy = encounter(index, side, speed)
                        world.step(config.FIXED_DT)
                        self.assertEqual(enemy.aim_remaining, 0.5)
                        warning = enemy.aim_line
                        self.assertIsNotNone(warning)
                        for _ in range(59):
                            world.step(config.FIXED_DT)
                            self.assertTrue(enemy.aiming)
                            self.assertEqual(enemy.animation.frame, 2)
                            self.assertEqual(enemy.ammo, 7)
                            self.assertFalse(world.projectiles)
                        world.step(config.FIXED_DT)
                        self.assertFalse(enemy.aiming)
                        self.assertIsNone(enemy.aim_line)
                        self.assertEqual((enemy.ammo, enemy.animation.frame), (6, 3))
                        self.assertEqual(len(world.projectiles), 1)
                        bullet = world.projectiles[0]
                        self.assertEqual(bullet.y, warning[1])
                        self.assertEqual(bullet.facing, enemy.facing)
                        self.assertEqual(bullet.x - bullet.facing * config.RESEARCHER_BULLET_HALF_WIDTH,
                                         warning[0])

    def test_animation_frame_changes_cannot_bypass_the_warning_or_spend_extra_ammo(self):
        world, enemy = encounter()
        enemy.start_attack()
        enemy.animation.elapsed = 3.05 / enemy.attack_fps
        self.assertIsNone(enemy.take_projectile())
        self.assertEqual(enemy.ammo, 7)
        enemy.update(0.5 - config.FIXED_DT, world.player)
        self.assertTrue(enemy.aiming)
        self.assertIsNone(enemy.take_projectile())
        enemy.update(config.FIXED_DT, world.player)
        self.assertIsNotNone(enemy.take_projectile())
        self.assertEqual(enemy.ammo, 6)
        for _ in range(10):
            self.assertIsNone(enemy.take_projectile())
        self.assertEqual(enemy.ammo, 6)

    def test_every_round_including_the_first_after_reload_gets_a_new_warning(self):
        for index in (6, 7):
            world, enemy = encounter(index)
            previous_ammo, started, shots, warnings = 7, None, 0, 0
            for _ in range(3000):
                was_aiming = enemy.aiming
                world.step(config.FIXED_DT)
                if enemy.aiming and not was_aiming:
                    started = world.elapsed
                    warnings += 1
                if enemy.ammo == previous_ammo - 1:
                    self.assertIsNotNone(started)
                    self.assertAlmostEqual(world.elapsed - started, 0.5)
                    self.assertIsNone(enemy.aim_line)
                    shots += 1
                    started = None
                if enemy.state == "RELOAD":
                    self.assertEqual(enemy.ammo, 0)
                    self.assertIsNone(enemy.aim_line)
                previous_ammo = enemy.ammo
                if shots == 8:
                    break
            self.assertEqual((shots, warnings, enemy.ammo), (8, 8, 6))

    def test_each_interruption_cancels_the_warning_without_firing_or_spending_ammo(self):
        for action in ("hit", "lethal", "strong", "knockback", "stop", "car", "reload"):
            with self.subTest(action=action):
                world, enemy = encounter()
                enemy.start_attack()
                enemy.update(0.2, world.player)
                if action in ("hit", "lethal"):
                    enemy.take_damage(10 if action == "hit" else enemy.hp)
                elif action == "strong":
                    enemy.take_strong_hit(STRONG_MOVES["combat_q"], 1)
                elif action == "knockback":
                    enemy.knockback(world.player.x)
                elif action == "stop":
                    enemy.stop()
                elif action == "car":
                    enemy.hit_by_car(1)
                else:
                    enemy.start_reload()
                self.assertEqual(enemy.aim_remaining, 0)
                self.assertIsNone(enemy.aim_line)
                self.assertIsNone(enemy.take_projectile())
                self.assertEqual(enemy.ammo, 7)

    def test_recovery_starts_a_full_warning_and_player_death_cancels_it(self):
        world, enemy = encounter()
        enemy.start_attack()
        enemy.update(0.4, world.player)
        enemy.take_damage(10)
        enemy.update(1, world.player)
        enemy.cooldown = 0
        enemy.update(config.FIXED_DT, world.player)
        self.assertEqual(enemy.aim_remaining, 0.5)
        world.player.invincible = False
        world.player.take_damage(500)
        world.handle_death()
        self.assertEqual(enemy.aim_remaining, 0)
        self.assertIsNone(enemy.aim_line)
        self.assertEqual(enemy.ammo, 7)

    def test_warning_uses_the_common_slow_motion_clock_instead_of_attack_speed(self):
        world, enemy = encounter(speed=1.4)
        enemy.start_attack()
        enter_kick_wait(world)
        for _ in range(299):
            world.step(config.FIXED_DT)
            self.assertTrue(enemy.aiming)
            self.assertEqual(enemy.ammo, 7)
            self.assertFalse(world.projectiles)
        self.assertAlmostEqual(world.time_scale, 0.2)
        world.step(config.FIXED_DT)
        self.assertEqual(enemy.aim_remaining, 0)
        self.assertEqual(enemy.ammo, 6)
        self.assertEqual(len(world.projectiles), 1)

    def test_inactive_stage_and_loading_pause_warning_and_f5_clears_it(self):
        for index in (6, 7):
            world, enemy = encounter(index)
            enemy.start_attack()
            advance(world, 0.2)
            snapshot = enemy.aim_remaining, enemy.animation.elapsed, enemy.ammo, enemy.aim_line
            world.select_stage(5)
            advance(world, 1)
            world.select_stage(index)
            self.assertEqual((enemy.aim_remaining, enemy.animation.elapsed, enemy.ammo, enemy.aim_line),
                             snapshot)
            world.pending_stage_index = 5
            world.stage_loading_remaining = 2
            world.update(1)
            self.assertEqual((enemy.aim_remaining, enemy.animation.elapsed, enemy.ammo, enemy.aim_line),
                             snapshot)
            tap(world.controls, "restart")
            world.update(config.FIXED_DT)
            self.assertFalse(any(stage.enemies or stage.projectiles for stage in world.stages))
            fresh = world.stages[index].spawner.spawn(1, 0)[0]
            self.assertEqual((fresh.aim_remaining, fresh.ammo), (0, 7))
            self.assertIsNone(fresh.aim_line)

    def test_warning_does_not_track_a_dodging_player_or_change_the_bullet_lane(self):
        world, enemy = encounter()
        enemy.start_attack()
        warning = enemy.aim_line
        world.controls.press("down")
        advance(world, 0.5)
        self.assertEqual((enemy.ammo, enemy.ground_y, enemy.facing), (6, 100, -1))
        self.assertGreater(abs(world.player.ground_y - enemy.ground_y), config.ATTACK_DEPTH_TOLERANCE)
        self.assertEqual(world.projectiles[0].y, warning[1])
        enemy.cooldown = 100
        advance(world, 0.4)
        self.assertEqual(world.player.hp, 500)
        self.assertFalse(world.effects)

    def test_world_space_red_dots_follow_the_camera_and_are_culled_offscreen(self):
        for facing in (-1, 1):
            enemy = Researcher(640, facing, ground_y=120)
            enemy.start_attack()
            for camera_x, camera_y in ((0, 0), (50, 35), (200, -20)):
                with patch("pico2d.draw_circle") as draw:
                    Assets.draw_researcher_aim(SimpleNamespace(), enemy, camera_x, camera_y)
                self.assertTrue(draw.call_count)
                previous_x = None
                for call in draw.call_args_list:
                    x, y, radius, *color = call.args
                    self.assertEqual(y, 120 + config.RESEARCHER_MUZZLE_HEIGHT - camera_y)
                    self.assertEqual(radius, config.RESEARCHER_AIM_DOT_RADIUS)
                    self.assertEqual(tuple(color), config.RESEARCHER_AIM_COLOR)
                    self.assertTrue(call.kwargs["filled"])
                    self.assertTrue(-radius <= x < config.SCREEN_WIDTH + radius)
                    if previous_x is not None:
                        self.assertEqual(x - previous_x, facing * config.RESEARCHER_AIM_DOT_SPACING)
                    previous_x = x
            with patch("pico2d.draw_circle") as draw:
                Assets.draw_researcher_aim(SimpleNamespace(), enemy, 0, 1000)
            draw.assert_not_called()
            enemy.take_damage(1)
            with patch("pico2d.draw_circle") as draw:
                Assets.draw_researcher_aim(SimpleNamespace(), enemy, 0, 0)
            draw.assert_not_called()

    def test_game_draws_warning_with_help_hidden_but_not_over_the_loading_screen(self):
        game = Game.__new__(Game)
        game.world, enemy = encounter()
        enemy.start_attack()
        game.assets, game.ui = Mock(), Mock()
        game.world.stage.draw = Mock()
        with patch.object(pico2d, "clear_canvas"):
            for visible in (True, False):
                game.ui.details_visible = visible
                game.assets.reset_mock()
                remaining = enemy.aim_remaining
                game.draw(present=False)
                game.assets.draw_researcher_aim.assert_called_once_with(
                    enemy, game.world.camera.render_x, game.world.camera.render_y)
                self.assertEqual(enemy.aim_remaining, remaining)
            game.assets.reset_mock()
            game.world.pending_stage_index = 5
            game.world.stage_loading_remaining = config.STAGE_INTRO_DURATION
            with patch.object(game, "draw_stage_intro") as intro:
                game.draw(present=False)
            intro.assert_called_once_with(config.FACTORY_EXTERIOR_INTRO, 0, False)
            game.world.pending_stage_index = 8
            game.world.stage_loading_remaining = config.STAGE_LOADING_DURATION
            with patch.object(game, "draw_stage_loading_screen") as loading:
                game.draw(present=False)
            loading.assert_called_once_with(False)
            game.assets.draw_researcher_aim.assert_not_called()
