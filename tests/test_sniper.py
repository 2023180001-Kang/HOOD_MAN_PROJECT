import random
import unittest

import pico2d

import config
from ar_soldier import ARSoldier
from projectiles import SniperBullet
from sniper import Sniper
from sword_enemy import SwordEnemy
from tests.test_main_menu import process_menu_events
from tests.test_menu_return import key_event, scene
from world import World


def encounter(stage_index=0):
    world = World(rng=random.Random(5))
    world.select_stage(stage_index)
    world.controls.press("sniper_spawn")
    world.controls.press("spawn_1")
    world.step(config.FIXED_DT)
    sniper, = world.enemies
    sniper.x = sniper.previous_x = world.player.x - 700
    sniper.ground_y = sniper.previous_ground_y = world.player.ground_y - 50
    return world, sniper


class SniperTests(unittest.TestCase):
    def test_v_prefix_on_normal_stages_and_final_boss_with_both_number_rows(self):
        game = scene()
        world = game.world

        def key(symbol):
            process_menu_events(game, key_event(symbol), key_event(symbol, down=False), menu_screen=False)
            world.step(config.FIXED_DT)

        for index, image in enumerate(config.STAGE_IMAGES):
            if image in config.BOSS_STAGE_IMAGES:
                continue
            with self.subTest(stage=index + 1):
                world.select_stage(index)
                key(pico2d.SDLK_v)
                key(pico2d.SDLK_KP_2)
                key(pico2d.SDLK_1)
                self.assertEqual([type(e) for e in world.enemies], [Sniper, Sniper, world.spawner.enemy_type])
        world.select_stage(len(world.stages) - 2)
        key(pico2d.SDLK_v)
        key(pico2d.SDLK_1)
        self.assertEqual([type(e) for e in world.enemies], [ARSoldier])
        world.select_stage(len(world.stages) - 1)
        key(pico2d.SDLK_v)
        key(pico2d.SDLK_KP_3)
        key(pico2d.SDLK_1)
        key(pico2d.SDLK_c)
        key(pico2d.SDLK_1)
        key(pico2d.SDLK_v)
        key(pico2d.SDLK_2)
        self.assertEqual([type(e) for e in world.enemies], [Sniper] * 3 + [ARSoldier, SwordEnemy] + [Sniper] * 2)
        self.assertTrue(all(e.hp == e.max_hp == 250 for e in world.enemies if isinstance(e, Sniper)))
        process_menu_events(game, key_event(pico2d.SDLK_c), key_event(pico2d.SDLK_v), menu_screen=False)
        key(pico2d.SDLK_1)
        key(pico2d.SDLK_KP_2)
        self.assertEqual([type(e) for e in world.enemies[-3:]], [Sniper] * 3)

    def test_tracking_lock_four_hits_stillness_and_full_reload(self):
        world, sniper = encounter(len(config.STAGE_IMAGES) - 1)
        dt = config.FIXED_DT
        p = world.player
        start_x = sniper.x
        for remaining in (3, 2, 1, 0):
            tracking = []
            for _ in range(240):
                world.step(dt)
                if world.projectiles:
                    break
                if sniper.visible_target:
                    tracking.append(sniper.visible_target)
            self.assertGreater(len(set(tracking)), 2)
            shot, = world.projectiles
            self.assertIsInstance(shot, SniperBullet)
            self.assertIs(shot.shooter, sniper)
            self.assertEqual(sniper.visible_target, (p.x, p.y + config.PLAYER_HEIGHT * 0.6))
            self.assertEqual((sniper.state, sniper.animation.frame, sniper.ammo), ("ATTACK", 3, remaining))
            self.assertGreater(sniper.x, start_x)
            position = sniper.x, sniper.ground_y
            for _ in range(round(1.5 / dt) - 1):
                world.step(dt)
                self.assertEqual((sniper.x, sniper.ground_y), position)
                self.assertEqual((sniper.state, sniper.ammo), ("ATTACK", remaining))
            self.assertIsNone(sniper.visible_target)
            self.assertEqual(p.hp, p.max_hp - (4 - remaining) * 90)
            world.step(dt)
        self.assertEqual((sniper.state, sniper.ammo), ("RELOAD", 0))
        for _ in range(round(2 / dt) - 1):
            world.step(dt)
            self.assertEqual((sniper.state, sniper.ammo, sniper.visible_target), ("RELOAD", 0, None))
            self.assertFalse(world.projectiles)
        world.step(dt)
        self.assertEqual((sniper.state, sniper.ammo), ("IDLE", 4))
        world.step(dt)
        self.assertIsNotNone(sniper.visible_target)

    def test_reticle_speeds_up_with_actual_running_speed(self):
        world, sniper = encounter()
        p = world.player
        for vx, depth_speed, expected in ((0, 0, 480), (300, 0, 780), (0, -720, 1200), (432, 576, 1200)):
            with self.subTest(velocity=(vx, depth_speed)):
                p.vx, p.ground_vy = vx, depth_speed
                start = (p.x - 200, p.y + config.PLAYER_HEIGHT * 0.6)
                sniper.reticle = start
                sniper.track_player(config.FIXED_DT, p)
                self.assertAlmostEqual(sniper.reticle[0] - start[0], expected * config.FIXED_DT)

    def test_reticle_locks_and_fires_during_single_and_running_double_jumps(self):
        for double_jump in (False, True):
            with self.subTest(double_jump=double_jump):
                world, sniper = encounter()
                p = world.player
                if double_jump:
                    world.controls.press("right")
                    world.controls.press("left_shift")
                world.controls.press("jump")
                world.step(config.FIXED_DT)
                if double_jump:
                    world.controls.release("jump")
                    world.controls.press("jump")
                for _ in range(100):
                    world.step(config.FIXED_DT)
                    if world.projectiles:
                        break
                shot, = world.projectiles
                self.assertGreater(p.jump_height, 0)
                self.assertEqual(p.jump_count, 2 if double_jump else 1)
                self.assertEqual(sniper.visible_target, (p.x, p.y + config.PLAYER_HEIGHT * 0.6))
                self.assertEqual(sniper.locked_target, (p.x, p.ground_y, p.jump_height + config.PLAYER_HEIGHT * 0.6))
                self.assertGreater(shot.vy, 0)

    def test_a_fired_round_can_be_dodged(self):
        world, sniper = encounter()
        p = world.player
        for _ in range(240):
            world.step(config.FIXED_DT)
            if world.projectiles:
                break
        shot, = world.projectiles
        aim = sniper.locked_target
        self.assertEqual(aim, (p.x, p.ground_y, p.jump_height + config.PLAYER_HEIGHT * 0.6))
        p.ground_y = p.previous_ground_y = p.ground_y + 100
        shot.update(2, p)
        self.assertTrue(shot.finished)
        self.assertEqual(p.hp, p.max_hp)

    def test_damage_interrupts_tracking_and_death_removes_the_warning(self):
        world, sniper = encounter()
        self.assertIsNotNone(sniper.visible_target)
        sniper.take_damage(10)
        self.assertIsNone(sniper.visible_target)
        world.step(config.FIXED_DT)
        self.assertFalse(world.projectiles)
        sniper.take_damage(240)
        for _ in range(180):
            world.step(config.FIXED_DT)
        self.assertIsNone(sniper.visible_target)
        self.assertFalse(world.projectiles)
        self.assertEqual(sniper.ammo, 4)
