import ctypes
import hashlib
import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pico2d
from sdl2 import SDL_Event

import config
from assets import Assets
from axe_enemy import AxeEnemy
from enemy import Enemy
from enemy02 import Enemy02
from game import Game, KEYS
from player import Player
from researcher import Researcher
from tests.helpers import advance
from ui import UI
from world import World


def scene():
    game = Game.__new__(Game)
    game.world = World(rng=random.Random(41))
    game.ui = UI()
    game.running = True
    game._menu_requested = False
    game._escape_held = False
    return game


def send_keys(game, keys="hjkl", *, down=True, repeat=False):
    """Exercise the real SDL-to-action handler without opening a window."""
    events = []
    for key in keys:
        event = SDL_Event()
        event.type = pico2d.SDL_KEYDOWN if down else pico2d.SDL_KEYUP
        event.key.keysym.sym = getattr(pico2d, f"SDLK_{key}")
        event.key.repeat = int(repeat)
        events.append(event)

    def poll(pointer):
        if not events:
            return 0
        event = events.pop(0)
        ctypes.memmove(pointer, ctypes.byref(event), ctypes.sizeof(event))
        return 1

    with patch("game.SDL_PollEvent", side_effect=poll):
        game.handle_events()


class RemovedCounterTests(unittest.TestCase):
    def test_hjkl_have_no_key_bindings_or_pending_actions_even_when_held_or_repeated(self):
        game = scene()
        for key in "hjkl":
            self.assertNotIn(getattr(pico2d, f"SDLK_{key}"), KEYS)
        for down, repeat in ((True, False), (True, True), (True, False), (False, False)):
            send_keys(game, down=down, repeat=repeat)
            self.assertFalse(game.world.controls.held)
            self.assertFalse(game.world.controls.pressed)
        advance(game.world, 2)
        self.assertEqual((game.world.player.hp, game.world.player.state), (500, "IDLE"))
        self.assertFalse(game.world.enemies)

    def test_hjkl_do_not_block_enemy_attacks_or_grant_protection(self):
        for enemy_type, damage, frame in ((Enemy, 20, 4), (Enemy02, 30, 3), (AxeEnemy, 40, 4)):
            for side in (-1, 1):
                for key in "hjkl":
                    game = scene()
                    world = game.world
                    enemy = enemy_type(world.player.x + side * 80, -side)
                    enemy.start_attack()
                    enemy.animation.elapsed = frame / enemy.attack_fps
                    world.enemies = [enemy]
                    send_keys(game, key)
                    world.step(config.FIXED_DT)
                    self.assertEqual((world.player.hp, world.player.state), (500 - damage, "HIT"))
                    self.assertEqual(enemy.hp, enemy.max_hp)
                    self.assertEqual(len(world.effects), 1)
                    self.assertEqual(world.effects[0].image_name, config.CLUB_HIT_IMAGE)
                    self.assertFalse(world.damage_numbers)

    def test_a_with_retired_keys_is_the_normal_ten_damage_attack_for_every_weapon(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for key in "hjkl":
                game = scene()
                world = game.world
                world.player.invincible = True
                world.player.equip_weapon(weapon)
                enemy = Enemy(world.player.x + 80, -1)
                enemy.cooldown = 100
                world.enemies = [enemy]
                send_keys(game, key + "a")
                advance(world, 0.12, 120)
                self.assertEqual(enemy.hp, 190)
                self.assertEqual([number.damage for number in world.damage_numbers], [10])
                self.assertEqual(world.player.active_move, world.player.moves["combat_a"])
                self.assertFalse(world.controls.held & {f"counter_{key}" for key in "hjkl"})

    def test_hjkl_do_not_cancel_or_replace_strong_attack_slow_motion(self):
        game = scene()
        send_keys(game, "r")
        game.world.step(config.FIXED_DT)
        for key in "hjkl":
            send_keys(game, key)
            game.world.step(config.FIXED_DT)
            self.assertEqual(game.world.player.raise_punch_phase, "RAISE")
            self.assertEqual(game.world.time_scale, config.R_RAISE_TIME_SCALE)
        self.assertFalse(game.world.controls.pressed)

    def test_hjkl_during_loading_death_and_restart_never_buffer_a_later_action(self):
        for mode in ("loading", "dead", "restart"):
            game = scene()
            if mode == "loading":
                game.world.pending_stage_index = 1
                game.world.stage_loading_remaining = 0.1
            elif mode == "dead":
                game.world.player.take_damage(500)
            send_keys(game)
            advance(game.world, 0.2)
            game.world.reset()
            advance(game.world, 1)
            self.assertEqual((game.world.player.hp, game.world.player.state), (500, "IDLE"))
            self.assertFalse(game.world.controls.held)
            self.assertFalse(game.world.controls.pressed)
            self.assertFalse(game.world.enemies)

    def test_no_actor_or_world_registers_counter_capture_hold_or_followup_states(self):
        self.assertFalse(hasattr(World(), "try_start_counter"))
        self.assertFalse(hasattr(World(), "counter"))
        for actor in (Player(), Enemy(1000), Enemy02(1000), AxeEnemy(1000), Researcher(1000)):
            self.assertFalse(hasattr(actor, "counter_move"))
            self.assertFalse(hasattr(actor, "start_counter"))
            self.assertFalse(any(state.startswith(("COUNTER_", "HOLD_", "SUBDUED_", "HELD_"))
                                 for state in actor.animation.definitions))

    def test_both_original_counter_sheets_are_archived_byte_identically(self):
        expected = (
            "6959b54db40722cc350e904c3076f82170c9e098eb5bdb25b00cad515b257cb6",
            "3316618fac627a1a0e01ed4aa4e7da4d3a3e07dd38706c901f932a30f2279022",
        )
        for name, digest in zip(config.ARCHIVED_COUNTER_IMAGES, expected):
            path = config.ROOT / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            self.assertFalse((config.ROOT / path.name).exists())

    def test_archived_counter_art_is_not_loaded_or_in_active_frame_metadata(self):
        with patch("pico2d.load_image", return_value=Mock()), patch("pico2d.load_font"):
            assets = Assets()
        retired = {name for path in config.ARCHIVED_COUNTER_IMAGES
                   for name in (path, (config.ROOT / path).name)}
        self.assertFalse(retired & assets.images.keys())
        self.assertFalse(retired & assets.frames.keys())
        self.assertEqual(len(assets.frames), 24)
        self.assertEqual(sum(len(row) for rows in assets.frames.values() for row in rows), 1224)

    def test_hud_has_no_counter_keys_techniques_hold_or_followup_help_on_any_stage(self):
        game = scene()
        assets = SimpleNamespace(font=Mock(), images={config.HP_IMAGE: Mock(w=700, h=80)})
        for index in range(len(game.world.stages)):
            game.world.select_stage(index)
            assets.font.reset_mock()
            with patch("pico2d.draw_rectangle"):
                game.ui.draw(assets, game.world)
            lines = [call.args[2] for call in assets.font.draw.call_args_list]
            self.assertFalse(any(word in line for line in lines
                                 for word in ("반격", "제압 유지", "후속 공격", "쳐내고 연타",
                                              "잡아 메치기", "회전 발차기")))
            self.assertTrue(any("적 공격" in line or "적 권총" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
