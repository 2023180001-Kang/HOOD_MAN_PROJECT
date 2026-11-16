"""Verify Q/W/E/R/T, matched reactions and knockback in an actual SDL window."""

from pathlib import Path
import random
import sys
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from combat import MOVES, STRONG_MOVES
from drop_items import DropItem
from enemy import Enemy
from enemy02 import Enemy02
from game import Game
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, tick
from tools.check_weapon_combat import release
from tools.check_weapons import tap
from world import World


def scene(game, enemy_type=Enemy, side=1, weapon=None):
    game.world = World(item_rng=random.Random(5))
    world = game.world
    world.stage.drop_items = []
    if weapon is not None:
        world.stage.drop_items = [DropItem(weapon, world.player.x, world.player.ground_y)]
        tap(game, pico2d.SDLK_g)
        assert world.player.weapon == weapon
    world.player.facing, world.player.invincible = side, True
    enemy = enemy_type(world.player.x + side * 80, -side, ground_y=world.player.ground_y)
    enemy.animation.set_state("HIT")
    enemy.cooldown = 100
    world.enemies.append(enemy)
    return world, enemy


def check_source_clips(game):
    for move in STRONG_MOVES.values():
        for side in (-1, 1):
            world, enemy = scene(game, side=side)
            player = world.player
            player.start_move(move, side)
            enemy.take_strong_hit(move, side)
            for frame in range(8):
                player.animation.elapsed = (frame + 0.05) / move.fps
                enemy.animation.elapsed = (frame + 0.05) / config.STRONG_HIT_FPS
                player_image = game.assets.images[config.STRONG_ATTACK_IMAGE]
                enemy_image = game.assets.images[config.STRONG_HIT_IMAGE]
                with (patch.object(player_image, "clip_composite_draw",
                                   wraps=player_image.clip_composite_draw) as player_draw,
                      patch.object(enemy_image, "clip_composite_draw",
                                   wraps=enemy_image.clip_composite_draw) as enemy_draw):
                    if frame == max(move.active_frames):
                        capture(game, f"strong_source_{move.key}_{side}")
                    else:
                        render_image(game)
                for actor, name, row, draw in (
                        (player, config.STRONG_ATTACK_IMAGE, move.row, player_draw),
                        (enemy, config.STRONG_HIT_IMAGE, move.enemy_hit_row, enemy_draw)):
                    assert draw.call_count == 1
                    args = draw.call_args.args
                    tile = game.assets.frames[name][row - 1][frame]
                    scale = config.SPRITE_IMAGE_SCALES[name]
                    assert args[:4] == tuple(tile["clip"])
                    assert args[5] == ("h" if actor.facing < 0 else "")
                    assert args[8:10] == (tile["clip"][2] * scale, tile["clip"][3] * scale)
                    assert abs(args[7] - args[9] / 2 - actor.y
                               - tile["offset_y"] * scale) < 1e-7
    print("PASS: 5 player/reaction row pairs x 8 frames x 2 directions: "
          "exact source clips, 1.0x actor-sized art, shared feet anchors and airborne offsets.")


def check_inputs_damage_and_recovery(game):
    for weapon in (None, *config.WEAPON_POSE_IMAGES):
        for move in STRONG_MOVES.values():
            for enemy_type in (Enemy, Enemy02):
                for side in (-1, 1):
                    world, enemy = scene(game, enemy_type, side, weapon)
                    player = world.player
                    key = getattr(pico2d, f"SDLK_{move.key}")
                    push_key(key)
                    for _ in range(40):
                        tick(game)
                        if enemy.hp < 200:
                            break
                    assert enemy.hp == 150, (weapon, move.key, enemy_type, side, enemy.hp)
                    assert player.active_move is move and player.sprite_row == move.row
                    assert (enemy.state, enemy.sprite_image, enemy.animation.row) == (
                        "STRONG_HIT", config.STRONG_HIT_IMAGE, move.enemy_hit_row)
                    assert player.animation.frame in move.active_frames
                    assert [number.damage for number in world.damage_numbers] == [50]
                    assert world.effects[-1].image_name == config.PUNCH_KICK_HIT_IMAGE
                    assert world.camera.shake_remaining > 0
                    if move.key == "w":
                        assert enemy.vx * side > 0
                    else:
                        assert enemy.vx == 0
                    if weapon is None:
                        with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as font:
                            capture(game, f"strong_hit_{move.key}_{enemy_type.__name__}_{side}")
                        texts = [call.args[2] for call in font.call_args_list]
                        assert "강화 기본 공격 · 피해량" in texts
                        for listed in STRONG_MOVES.values():
                            assert f"{listed.key.upper()} {listed.name} (50)" in texts
                    start = enemy.x
                    push_key(key, repeat=True)
                    tick(game, 6)
                    assert enemy.hp == 150
                    if move.key == "w":
                        assert (enemy.x - start) * side > 25
                    if weapon is None and side > 0:
                        capture(game, f"strong_reaction_{move.key}_{enemy_type.__name__}")
                    for _ in range(60):
                        if enemy.state != "STRONG_HIT":
                            break
                        tick(game)
                    assert enemy.sprite_image == enemy.image_name and enemy.hp == 150
                    assert not enemy.knockback_started
                    assert player.active_move is None and player.weapon == weapon
                    assert player.sprite_image == config.WEAPON_POSE_IMAGES.get(weapon, config.PLAYER_IMAGE)
                    push_key(key, repeat=True)
                    tick(game, 10)
                    assert player.active_move is None and enemy.hp == 150
                    release(game, key)
    print("PASS: SDL Q/W/E/R/T with all three loadouts, both enemy types/directions: "
          "rows 1..5 -> 1/5/4/2/3, 50 damage once, W real knockback, hit effects/numbers/shake, "
          "held/repeated-key suppression, HUD labels and original-sprite/AI recovery.")


def check_switches_death_and_restart(game):
    world, enemy = scene(game)
    tap(game, pico2d.SDLK_a)
    for letter in "qwert":
        tap(game, getattr(pico2d, f"SDLK_{letter}"))
        assert world.player.active_move is STRONG_MOVES[f"combat_{letter}"]
        assert world.player.animation.frame == 0
    push_key(pico2d.SDLK_q)
    push_key(pico2d.SDLK_f)
    tick(game)
    assert world.player.active_move is MOVES["combat_f"]
    release(game, pico2d.SDLK_q, pico2d.SDLK_f)
    world, enemy = scene(game, weapon="steel_pipe")
    tap(game, pico2d.SDLK_w)
    tap(game, pico2d.SDLK_g)
    tick(game, 36)
    assert world.player.weapon is None and world.player.active_move is None and enemy.hp == 200
    for enemy_type in (Enemy, Enemy02):
        world, enemy = scene(game, enemy_type)
        for expected_hp in (150, 100, 50, 0):
            enemy.x = world.player.x + 80
            enemy.cooldown = 100
            tap(game, pico2d.SDLK_t)
            for _ in range(40):
                if enemy.hp == expected_hp:
                    break
                tick(game)
            assert (enemy.hp, enemy.state) == (expected_hp, "STRONG_HIT")
            while enemy.state == "STRONG_HIT":
                tick(game)
        assert enemy.state == "DYING" and enemy.sprite_image == enemy.image_name
        tick(game, 60)
        assert enemy.state == "DEAD" and not enemy.alive
        capture(game, f"strong_uppercut_defeated_{enemy_type.__name__}")
    world, enemy = scene(game)
    tap(game, pico2d.SDLK_r)
    tap(game, pico2d.SDLK_u)
    assert not game.ui.details_visible
    capture(game, "strong_attack_hidden_help")
    tap(game, pico2d.SDLK_u)
    textures = dict(game.assets.images)
    tap(game, pico2d.SDLK_F5)
    assert game.world.player.active_move is None and not game.world.enemies
    assert all(game.assets.images[name] is texture for name, texture in textures.items())
    print("PASS: fresh basic/strong switches and latest SDL input, G discard cancels windup, "
          "four uppercuts defeat both enemy types after the matched reaction, "
          "normal death art, U display and F5 texture reuse.")


def benchmark(game):
    game.world = World(rng=random.Random(5), item_rng=random.Random(5))
    game.world.player.invincible = True
    game.world.controls.press("spawn_4")
    tick(game)
    frame = 0
    original_draw = game.draw

    def attacking_draw(present=True):
        nonlocal frame
        original_draw(present)
        if frame % 30 == 0:
            key = getattr(pico2d, f"SDLK_{'qwert'[frame // 30 % 5]}")
            push_key(key)
            push_key(key, down=False)
        frame += 1

    start = perf_counter()
    with patch.object(game, "draw", side_effect=attacking_draw):
        frames = game.run(max_frames=180)
    seconds = perf_counter() - start
    assert frames == 180 and len(game.world.enemies) == 4
    print(f"BENCHMARK: QWERT + 4 enemies/reactions/HP/effects/HUD, "
          f"{frames} frames / {seconds:.3f}s = {frames / seconds:.2f} FPS.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_source_clips(game)
        check_inputs_damage_and_recovery(game)
        check_switches_death_and_restart(game)
        benchmark(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
