"""Verify retired H/J/K/L inputs, unloaded archive art and unchanged combat in SDL."""

from pathlib import Path
import random
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from game import Game, KEYS
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, release, tick
from world import World


def encounter(game, index=0, side=1, gap=80):
    game.world = World(rng=random.Random(41), item_rng=random.Random(23))
    world = game.world
    world.select_stage(index)
    enemy = world.spawner.spawn(1, world.elapsed)[0]
    world.enemies.append(enemy)
    enemy.x = enemy.previous_x = world.player.x + side * gap
    enemy.ground_y = enemy.previous_ground_y = world.player.ground_y
    enemy.facing = -side
    return world, enemy


def check_ignored_keys_and_hud(game):
    for key in "hjkl":
        assert getattr(pico2d, f"SDLK_{key}") not in KEYS
    retired = {name for path in config.ARCHIVED_COUNTER_IMAGES
               for name in (path, (config.ROOT / path).name)}
    assert not retired & game.assets.images.keys()
    assert not retired & game.assets.frames.keys()
    assert len(game.assets.frames) == 24
    assert sum(len(row) for rows in game.assets.frames.values() for row in rows) == 1224
    for index in range(len(config.STAGE_IMAGES)):
        game.world = World(item_rng=random.Random(23))
        game.world.select_stage(index)
        baseline = render_image(game).tobytes()
        for key in "hjkl":
            keycode = getattr(pico2d, f"SDLK_{key}")
            push_key(keycode)
            game.handle_events()
            assert not game.world.controls.held and not game.world.controls.pressed
            push_key(keycode, repeat=True)
            game.handle_events()
            assert render_image(game).tobytes() == baseline
            release(game, keycode)
        with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as text:
            if index in (0, 2, 4, 6):
                capture(game, f"removed_counters_hud_{index}")
            else:
                render_image(game)
        labels = [call.args[2] for call in text.call_args_list]
        assert not any(word in label for label in labels
                       for word in ("반격", "제압 유지", "후속 공격", "쳐내고 연타", "잡아 메치기", "회전 발차기"))
        assert any("적 공격" in label or "적 권총" in label for label in labels)
    print("PASS: all 12 maps ignore fresh/held/repeated H/J/K/L without changing rendered pixels "
          "or buffering actions; counter HUD/art/64 clips are absent, enemy damage help remains.")


def check_no_melee_or_bullet_protection(game):
    for index, damage in ((0, 20), (2, 30), (4, 40)):
        for side in (-1, 1):
            for key in "hjkl":
                world, enemy = encounter(game, index, side)
                enemy.start_attack()
                enemy.animation.elapsed = 2.05 / enemy.attack_fps
                keycode = getattr(pico2d, f"SDLK_{key}")
                push_key(keycode)
                for _ in range(30):
                    tick(game)
                    if world.player.hp < 500:
                        break
                release(game, keycode)
                assert world.player.hp == 500 - damage and world.player.state == "HIT"
                assert enemy.hp == enemy.max_hp and enemy.jump_height == 0
                assert len(world.effects) == 1
                assert world.effects[0].image_name == config.CLUB_HIT_IMAGE
                if side == 1 and key == "h":
                    capture(game, f"removed_counters_melee_{index}")
    for index in (6, 7):
        for key in "hjkl":
            world, enemy = encounter(game, index, gap=300)
            enemy.start_attack()
            enemy.animation.elapsed = 1.05 / enemy.attack_fps
            keycode = getattr(pico2d, f"SDLK_{key}")
            push_key(keycode)
            for _ in range(90):
                tick(game)
                if world.player.hp < 500:
                    break
            release(game, keycode)
            assert (world.player.hp, world.player.state, enemy.hp, enemy.ammo) == (470, "IDLE", 200, 6)
            assert world.effects[-1].image_name == config.CLUB_HIT_IMAGE
            if key == "h":
                capture(game, f"removed_counters_bullet_{index}")
    print("PASS: H/J/K/L cannot interrupt or protect against both-side thug/city/axe attacks "
          "(20/30/40) or either factory researcher's bullet (30 damage and impact); no hidden 80 damage.")


def check_a_and_existing_actions(game):
    for weapon in (None, *config.WEAPON_POSE_IMAGES):
        world, enemy = encounter(game)
        world.player.invincible = True
        world.player.equip_weapon(weapon)
        enemy.cooldown = 100
        for key in "hjkl":
            push_key(getattr(pico2d, f"SDLK_{key}"))
        push_key(pico2d.SDLK_a)
        move = world.player.moves["combat_a"]
        tick(game, int(60 * move.active_frames[0] / move.fps) + 1)
        assert enemy.hp == 200 - move.damage and [number.damage for number in world.damage_numbers] == [move.damage]
        assert world.player.active_move == world.player.moves["combat_a"]
        capture(game, f"removed_counters_a_{weapon or 'unarmed'}")
        release(game, pico2d.SDLK_a)
        for key in "hjkl":
            release(game, getattr(pico2d, f"SDLK_{key}"))
    game.world = World()
    world = game.world
    push_key(pico2d.SDLK_r)
    tick(game)
    release(game, pico2d.SDLK_r)
    for key in "hjkl":
        push_key(getattr(pico2d, f"SDLK_{key}"))
        tick(game)
        release(game, getattr(pico2d, f"SDLK_{key}"))
        assert world.player.raise_punch_phase == "RAISE" and world.time_scale == 0.2
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert world.player.hp == 500 and world.player.active_move is None and world.time_scale == 1
    assert not world.controls.held and not world.controls.pressed
    print("PASS: A remains a normal 10-damage strike for all equipment, H/J/K/L cannot cancel "
          "R slow preparation, and F5 resets without any grip/follow-up state.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_ignored_keys_and_hud(game)
        check_no_melee_or_bullet_protection(game)
        check_a_and_existing_actions(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
