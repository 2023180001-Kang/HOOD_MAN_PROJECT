import random
import unittest
from math import hypot

import pico2d

import config
from ar_soldier import ARSoldier
from projectiles import SniperBullet
from sniper import Sniper
from sword_enemy import SwordEnemy
from tests.test_main_menu import process_menu_events
from tests.test_menu_return import key_event, scene
from world import World


def encounter():
    world = World(rng=random.Random(5))
    world.select_stage(len(world.stages) - 1)
    world.controls.press("sniper_spawn")
    world.controls.press("spawn_1")
    world.step(config.FIXED_DT)
    sniper, = world.enemies
    sniper.x = sniper.previous_x = world.player.x - 700
    sniper.ground_y = sniper.previous_ground_y = world.player.ground_y - 50
    return world, sniper


class SniperTests(unittest.TestCase):
    def test_v_prefix_only_on_last_stage_with_both_number_rows(self):
        game = scene()
        world = game.world

        def key(symbol):
            process_menu_events(game, key_event(symbol), key_event(symbol, down=False), menu_screen=False)
            world.step(config.FIXED_DT)

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
        world, sniper = encounter()
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

    def test_reticle_tracks_a_moving_player_and_a_fired_round_can_be_dodged(self):
        world, sniper = encounter()
        p = world.player
        world.controls.press("right")
        world.controls.press("jump")
        for _ in range(18):
            prev = sniper.visible_target
            world.step(config.FIXED_DT)
            x, y = sniper.visible_target
            self.assertAlmostEqual(hypot(x - prev[0], y - prev[1]), config.SNIPER_TRACK_SPEED * config.FIXED_DT)
        world.controls.release("right")
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
