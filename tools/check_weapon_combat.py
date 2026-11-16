"""Verify equipped ASD attacks, source clips, HUD and existing effects through SDL."""

from pathlib import Path
import random
import sys
from time import perf_counter
from unittest.mock import patch

from PIL import ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from combat import MOVES, WEAPON_MOVES
from drop_items import DropItem
from enemy import Enemy
from enemy02 import Enemy02
from game import Game
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, tick
from tools.check_weapons import setup, tap
from world import World


def release(game, *keys):
    for key in keys:
        push_key(key, down=False)
    game.handle_events()


def scene(game, kind, enemy_type=None, side=1):
    world = setup(game, kind)
    tap(game, pico2d.SDLK_g)
    player = world.player
    player.facing, player.invincible = side, True
    if enemy_type is not None:
        enemy = enemy_type(player.x + side * 80, -side, ground_y=player.ground_y)
        enemy.animation.set_state("HIT")
        enemy.cooldown = 100
        world.enemies.append(enemy)
    return world


def check_clips(game):
    for kind, moves in WEAPON_MOVES.items():
        for key, move in moves.items():
            for side in (-1, 1):
                world = scene(game, kind, side=side)
                player = world.player
                tap(game, getattr(pico2d, f"SDLK_{move.key}"))
                assert player.active_move is move
                texture = game.assets.images[move.image_name]
                for frame in range(8):
                    player.animation.elapsed = (frame + 0.05) / move.fps
                    tile = game.assets.frames[move.image_name][move.row - 1][frame]
                    with patch.object(texture, "clip_composite_draw", wraps=texture.clip_composite_draw) as draw:
                        if side == 1 and (frame == move.active_frames[0] or move.key == "d" and frame == 2):
                            capture(game, f"weapon_attack_{kind}_{move.key}_frame_{frame}")
                        else:
                            render_image(game)
                    assert draw.call_count == 1
                    args = draw.call_args.args
                    assert args[:4] == tuple(tile["clip"])
                    assert args[5] == ("h" if side < 0 else "")
                    assert args[8:10] == (tile["clip"][2] * config.WEAPON_POSE_SCALE,
                                         tile["clip"][3] * config.WEAPON_POSE_SCALE)
                    assert abs(args[7] - args[9] / 2 - player.y
                               - tile.get("offset_y", 0) * config.WEAPON_POSE_SCALE) < 1e-8
    print("PASS: all 6 equipped attacks x 8 frames x 2 facings use exact new source clips, "
          "0.75 scale and preserved airborne D poses.")


def check_damage_effects_and_hud(game):
    for kind, moves in WEAPON_MOVES.items():
        for move in moves.values():
            for enemy_type in (Enemy, Enemy02):
                for side in (-1, 1):
                    world = scene(game, kind, enemy_type, side)
                    player, enemy = world.player, world.enemies[0]
                    key = getattr(pico2d, f"SDLK_{move.key}")
                    push_key(key)
                    hits = 0
                    for _ in range(60):
                        previous_hp = enemy.hp
                        tick(game)
                        if previous_hp == enemy.hp:
                            continue
                        hits += 1
                        assert previous_hp - enemy.hp == move.damage
                        assert player.animation.frame in move.active_frames
                        assert world.effects[-1].image_name == config.WEAPON_HIT_IMAGES[kind]
                        assert world.effects[-1].facing == side
                        assert world.damage_numbers[-1].damage == move.damage
                        assert world.camera.shake_remaining > 0
                        with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as font:
                            shown = capture(game, f"weapon_hit_{kind}_{move.key}_{enemy_type.__name__}_{side}")
                        texts = [call.args[2] for call in font.call_args_list]
                        assert f"{config.WEAPON_NAMES[kind]} 공격 · 피해량" in texts
                        for listed in player.moves.values():
                            assert f"{listed.key.upper()} {listed.name} ({listed.damage})" in texts
                        with patch.object(game.assets, "draw_hit_effect"):
                            baseline = render_image(game)
                        assert ImageChops.difference(shown.convert("RGB"),
                                                    baseline.convert("RGB")).getbbox() is not None
                    assert hits == 1 and enemy.hp == 200 - move.damage
                    assert player.active_move is None and player.state == "IDLE"
                    assert player.sprite_image == config.WEAPON_POSE_IMAGES[kind]
                    release(game, key)
    print("PASS: SDL G+ASD, both weapons/enemy types/facings: 10/40/50 damage once, "
          "correct source impact frames, existing hit-effect pixels, damage numbers/shake, "
          "equipped HUD labels and return to weapon IDLE.")


def check_switches_and_discard(game):
    for kind in WEAPON_MOVES:
        world = scene(game, kind, Enemy)
        enemy = world.enemies[0]
        for key, frames, hp in ((pico2d.SDLK_a, 5, 190),
                                (pico2d.SDLK_s, 14, 150), (pico2d.SDLK_d, 25, 100)):
            tap(game, key)
            tick(game, frames)
            assert enemy.hp == hp, (kind, key, enemy.hp)
        capture(game, f"weapon_combo_{kind}")
        world = scene(game, kind, Enemy)
        enemy = world.enemies[0]
        tap(game, pico2d.SDLK_d)
        tick(game, 3)
        tap(game, pico2d.SDLK_g)
        tick(game, 36)
        assert world.player.weapon is None and world.player.active_move is None
        assert enemy.hp == 200 and not world.effects
        tap(game, pico2d.SDLK_a)
        assert world.player.active_move is MOVES["combat_a"]
        assert world.player.sprite_image == config.COMBAT_IMAGE
        capture(game, f"weapon_discard_cancels_{kind}")
        other = "steel_pipe" if kind == "combat_knife" else "combat_knife"
        world.stage.drop_items = [DropItem(other, world.player.x, world.player.ground_y)]
        push_key(pico2d.SDLK_g)
        push_key(pico2d.SDLK_a)
        tick(game)
        assert world.player.active_move is WEAPON_MOVES[other]["combat_a"]
        release(game, pico2d.SDLK_g, pico2d.SDLK_a)
        capture(game, f"weapon_swap_attack_to_{other}")
        tap(game, pico2d.SDLK_f)
        assert world.player.active_move is MOVES["combat_f"]
    textures = dict(game.assets.images)
    tap(game, pico2d.SDLK_F5)
    assert game.world.player.weapon is None and game.world.player.moves is MOVES
    assert all(game.assets.images[name] is image for name, image in textures.items())
    print("PASS: real ASD combo switching; G discard cancels pending damage/restores unarmed A, "
          "same-update G+A selects the new weapon, F remains the kick, and F5 reuses textures.")


def benchmark(game):
    game.world = World(rng=random.Random(7), item_rng=random.Random(7))
    game.world.stage.drop_items = [DropItem("steel_pipe", game.world.player.x, game.world.player.ground_y)]
    tap(game, pico2d.SDLK_g)
    tap(game, pico2d.SDLK_p)
    tap(game, pico2d.SDLK_4)
    original_draw = game.draw
    frame = 0

    def attacking_draw(present=True):
        nonlocal frame
        original_draw(present)
        if frame % 30 == 0:
            key = (pico2d.SDLK_a, pico2d.SDLK_s, pico2d.SDLK_d)[frame // 30 % 3]
            push_key(key)
            push_key(key, down=False)
        frame += 1

    start = perf_counter()
    with patch.object(game, "draw", side_effect=attacking_draw):
        frames = game.run(max_frames=180)
    seconds = perf_counter() - start
    assert frames == 180 and len(game.world.enemies) == 4
    print(f"BENCHMARK: equipped pipe ASD + 4 enemies/HUD/effects, "
          f"{frames} frames / {seconds:.3f}s = {frames / seconds:.2f} FPS.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_clips(game)
        check_damage_effects_and_hud(game)
        check_switches_and_discard(game)
        benchmark(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
