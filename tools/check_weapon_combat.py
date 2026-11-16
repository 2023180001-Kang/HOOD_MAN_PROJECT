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
          "0.75 scale and D poses without a second height offset.")


def measure_jump(game, kind, side, running):
    if kind is None:
        game.world = World()
    else:
        scene(game, kind, side=side)
    world, player = game.world, game.world.player
    player.x = 350 if side > 0 else config.WORLD_WIDTH - 350
    player.vx = side * (config.RUN_SPEED if running else config.WALK_SPEED)
    player.facing = side
    start = player.x
    direction = pico2d.SDLK_RIGHT if side > 0 else pico2d.SDLK_LEFT
    push_key(direction)
    if running:
        push_key(pico2d.SDLK_LSHIFT)
    if kind is not None:
        tap(game, pico2d.SDLK_d)
        for _ in range(30):
            if player.weapon_leap_phase == "AIR":
                break
            tick(game)
        assert player.weapon_leap_phase == "AIR" and player.jump_height == 0
    else:
        push_key(pico2d.SDLK_SPACE)
    observed = {"peak": 0.0, "count": 0}
    original_step = world.step

    def observe_step(dt):
        original_step(dt)
        observed["peak"] = max(observed["peak"], player.jump_height)
        observed["count"] = max(observed["count"], player.jump_count)
        if player.grounded:
            observed.setdefault("land_x", player.x)

    apex_captured = False
    with patch.object(world, "step", side_effect=observe_step):
        for frame in range(150):
            if kind is None and frame == 30:
                push_key(pico2d.SDLK_SPACE, down=False)
                push_key(pico2d.SDLK_SPACE)
            elif kind is not None and frame in (10, 20, 40):
                # Fresh D and Space during flight must not grant another boost.
                for key in (pico2d.SDLK_d, pico2d.SDLK_SPACE):
                    push_key(key, down=False)
                    push_key(key)
            tick(game)
            if (not apex_captured and player.jump_count == 2 and 0 < player.vy <= 30
                    and (kind is not None or side > 0)):
                label = kind or "reference"
                capture(game, f"weapon_double_jump_{label}_{side}_{'run' if running else 'walk'}_apex")
                apex_captured = True
            if "land_x" in observed:
                break
            if kind is not None:
                assert player.weapon_leap_phase == "AIR" and player.animation.frame in (2, 3)
                assert player.attack_box is None
    assert player.grounded and observed["count"] == 2
    release(game, direction, pico2d.SDLK_LSHIFT, pico2d.SDLK_SPACE, pico2d.SDLK_d)
    if kind is not None:
        assert player.weapon_leap_phase == "LANDING"
        capture(game, f"weapon_double_jump_{kind}_{side}_{'run' if running else 'walk'}_landed")
        tick(game, 30)
        assert player.active_move is None
    return observed["peak"], (observed["land_x"] - start) * side


def check_double_jump_range(game):
    for running in (False, True):
        for side in (-1, 1):
            reference = measure_jump(game, None, side, running)
            for kind in WEAPON_MOVES:
                actual = measure_jump(game, kind, side, running)
                assert all(abs(a - b) < 1e-6 for a, b in zip(actual, reference)), (kind, actual, reference)
            print(f"PASS: SDL D / real Space double jump, {'run' if running else 'walk'}, "
                  f"side {side}: peak {reference[0]:.3f}px, first-touchdown range {reference[1]:.1f}px; "
                  "both weapons match and repeated D/Space adds no extra jump.")
    for kind in WEAPON_MOVES:
        world = scene(game, kind)
        tap(game, pico2d.SDLK_d)
        tick(game, 20)
        assert world.player.weapon_leap_phase == "AIR" and world.player.weapon_leap_boost_pending
        tap(game, pico2d.SDLK_g)
        assert world.player.weapon_leap_phase is None and not world.player.weapon_leap_boost_pending
        tick(game, 120)
        assert world.player.grounded and world.player.weapon is None
    print("PASS: SDL midair G discard cancels the scheduled second boost and lands naturally.")


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
                    for _ in range(180 if move.jump_attack else 60):
                        previous_hp = enemy.hp
                        tick(game)
                        if previous_hp == enemy.hp:
                            continue
                        hits += 1
                        assert previous_hp - enemy.hp == move.damage
                        assert player.animation.frame in move.active_frames
                        if move.jump_attack:
                            assert player.grounded and player.weapon_leap_phase == "LANDING"
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
                                (pico2d.SDLK_s, 14, 150), (pico2d.SDLK_d, 119, 100)):
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
        check_double_jump_range(game)
        check_damage_effects_and_hud(game)
        check_switches_and_discard(game)
        benchmark(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
