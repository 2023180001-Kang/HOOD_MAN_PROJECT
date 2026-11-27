import unittest

import pico2d

import config
from enemy import Enemy
from enemy02 import leap_height
from sword_enemy import SwordEnemy
from tests.test_main_menu import process_menu_events
from tests.test_menu_return import key_event, scene
from world import World


class SwordEnemyTests(unittest.TestCase):
    def test_c_qualifies_the_next_number_or_each_fresh_number_while_held(self):
        game = scene()
        world = game.world

        def keys(*events):
            process_menu_events(game, *events, menu_screen=False)
            world.update(config.FIXED_DT)

        c, one, two = pico2d.SDLK_c, pico2d.SDLK_1, pico2d.SDLK_KP_2
        keys(key_event(c), key_event(c, down=False))
        self.assertEqual(len(world.enemies), 4)
        keys(key_event(two), key_event(two, repeat=True), key_event(two), key_event(two, down=False),
             key_event(one), key_event(one, down=False))
        self.assertEqual([type(e) for e in world.enemies[4:]], [SwordEnemy, SwordEnemy, Enemy])
        keys(key_event(c), key_event(one), key_event(one, down=False),
             key_event(two), key_event(two, down=False), key_event(c, down=False))
        self.assertEqual([type(e) for e in world.enemies[7:]], [SwordEnemy] * 3)
        self.assertIs(world.spawner.enemy_type, Enemy)

    def test_prefix_is_cleared_on_restart_and_training_still_selects_opponents(self):
        game = scene()

        def keys(*events):
            process_menu_events(game, *events, menu_screen=False)
            game.update(config.FIXED_DT)

        keys(key_event(pico2d.SDLK_c), key_event(pico2d.SDLK_F5))
        keys(key_event(pico2d.SDLK_1))
        self.assertEqual([type(e) for e in game.world.enemies], [Enemy] * 5)
        game.world.training = True
        game.world.reset()
        keys(key_event(pico2d.SDLK_c), key_event(pico2d.SDLK_2), key_event(pico2d.SDLK_KP_PLUS))
        self.assertEqual(game.world.stage.target.opponent.name, "쌍몽둥이")

    def test_basic_slash_hits_once_for_30(self):
        world = World()
        enemy = SwordEnemy(world.player.x - 80)
        world.enemies.append(enemy)
        enemy.start_attack()
        for _ in range(80):
            world.step(config.FIXED_DT)
            if enemy.state != "ATTACK":
                break
            self.assertEqual((enemy.sprite_image, enemy.animation.row), (config.SWORD_ENEMY_IMAGE, 4))
        self.assertEqual(world.player.hp, 470)

    def test_fifth_row_reaches_double_jump_height_and_hits_only_on_landing(self):
        for side in (-1, 1):
            world = World()
            enemy = SwordEnemy(world.player.x + side * 400, -side)
            world.enemies.append(enemy)
            self.assertTrue(enemy.start_leap(world.player))
            heights, frames, hits = [], set(), []
            for _ in range(240):
                previous_hp = world.player.hp
                world.step(config.FIXED_DT)
                if enemy.leap_phase is None:
                    break
                self.assertEqual((enemy.sprite_image, enemy.animation.row), (config.SWORD_ENEMY_IMAGE, 5))
                heights.append(enemy.jump_height)
                frames.add(enemy.animation.frame)
                if world.player.hp != previous_hp:
                    hits.append((previous_hp - world.player.hp, enemy.leap_phase, enemy.jump_height))
            self.assertAlmostEqual(max(heights), leap_height(), delta=0.02)
            self.assertEqual(frames, set(range(8)))
            self.assertEqual(hits, [(40, "LANDING", 0)])

    def test_meeting_a_jumping_player_replaces_the_landing_strike_with_one_slash(self):
        for side in (-1, 1):
            with self.subTest(side=side):
                world = World()
                player = world.player
                enemy, = world.spawner.spawn(1, 0, enemy_type=SwordEnemy)
                enemy.x = enemy.previous_x = player.x + side * 400
                enemy.ground_y = enemy.previous_ground_y = player.ground_y
                world.enemies.append(enemy)
                for _ in range(60):
                    world.step(config.FIXED_DT)
                world.controls.press("jump")
                for _ in range(120):
                    world.step(config.FIXED_DT)
                    if enemy.air_contact_attack:
                        break
                self.assertTrue(enemy.air_contact_attack and enemy.has_hit)
                self.assertGreater(min(player.jump_height, enemy.jump_height), 0)
                self.assertEqual((enemy.attack_kind, enemy.animation.row, player.hp), ("slash", 4, 470))
                self.assertIsNone(enemy.leap_phase)
                for _ in range(84):
                    world.step(config.FIXED_DT)
                self.assertEqual((enemy.jump_height, player.hp), (0, 470))
