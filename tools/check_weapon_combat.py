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
from camera import Camera
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


def double_jump(game):
    tap(game, pico2d.SDLK_SPACE)
    tick(game, 3)
    tap(game, pico2d.SDLK_SPACE)
    assert game.world.player.jump_count == 2


def check_clips(game):
    for kind, moves in WEAPON_MOVES.items():
        for key, move in moves.items():
            for side in (-1, 1):
                world = scene(game, kind, side=side)
                player = world.player
                if move.jump_attack:
                    double_jump(game)
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
    print("PASS: equipped melee attacks x 8 frames x 2 facings use exact source clips, "
          "0.75 scale and D poses without a second height offset.")


def check_slow_aim_and_dive(game):
    for kind in config.WEAPON_AIRBORNE_ROWS:
        for side in (-1, 1):
            for enemy_type in (Enemy, Enemy02):
                world = scene(game, kind, side=side)
                player = world.player
                tap(game, pico2d.SDLK_d)
                assert player.grounded and player.active_move is None and world.time_scale == 1
                tap(game, pico2d.SDLK_SPACE)
                tap(game, pico2d.SDLK_d)
                assert player.jump_count == 1 and player.active_move is None
                tap(game, pico2d.SDLK_SPACE)
                enemy = enemy_type(player.x - side * 900, side, ground_y=player.ground_y)
                world.enemies.append(enemy)
                direction = pico2d.SDLK_RIGHT if side > 0 else pico2d.SDLK_LEFT
                opposite = pico2d.SDLK_LEFT if side > 0 else pico2d.SDLK_RIGHT
                push_key(direction)
                player.vx = side * config.WALK_SPEED
                start_x, enemy_x, elapsed = player.x, enemy.x, world.elapsed
                push_key(pico2d.SDLK_d)
                tick(game, 30)
                simulated = 0.5 * config.WEAPON_AIM_TIME_SCALE
                assert player.weapon_leap_phase == "AIM" and world.time_scale == config.WEAPON_AIM_TIME_SCALE
                assert world.camera.shake_remaining == 0
                assert abs((player.x - start_x) * side - config.WALK_SPEED * simulated) < 1e-7
                assert abs((enemy.x - enemy_x) * side - enemy.run_speed * simulated) < 1e-7
                assert abs(enemy.animation.elapsed - simulated) < 1e-7
                assert abs(world.elapsed - elapsed - simulated) < 1e-7
                for repeat in (True, False):
                    push_key(pico2d.SDLK_d, repeat=repeat)
                    tick(game, 3)
                    assert player.weapon_leap_phase == "AIM" and player.jump_count == 2
                release(game, direction, pico2d.SDLK_d)
                push_key(opposite)
                tick(game, 30)
                assert player.facing == -side and player.vx * side < 0
                assert player.attack_box is None and not world.effects
                label = f"{kind}_{side}_{enemy_type.__name__}"
                with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as font:
                    capture(game, f"weapon_slow_aim_{label}")
                assert any(call.args[2].startswith("슬로 모션: 방향키") for call in font.call_args_list)
                release(game, opposite)
                start_x, elapsed = player.x, world.elapsed
                tap(game, pico2d.SDLK_d)
                assert player.weapon_leap_phase == "DIVE" and player.facing == -side
                assert world.time_scale == config.WEAPON_DIVE_TIME_SCALE
                assert abs(world.elapsed - elapsed - config.WEAPON_DIVE_TIME_SCALE / 60) < 1e-7
                assert abs((player.x - start_x) * -side
                           - config.WEAPON_DIVE_SPEED * config.WEAPON_DIVE_TIME_SCALE / 60) < 1e-7
                assert player.vy < -config.WEAPON_DIVE_FALL_SPEED and player.jump_count == 2
                assert world.camera.shake_remaining == 0
                capture(game, f"weapon_fast_dive_{label}")
                tick(game, 45)
                assert player.grounded and player.active_move is None and world.time_scale == 1
        print(f"PASS: SDL {kind}, both facings/enemy types: Space x2 gates D, "
              "0.2x player/enemy movement and animation, held/repeated D suppression, "
              "midair turn, fresh D -> 2x forward dive and normal-time recovery.")


def check_damage_effects_and_hud(game):
    for kind, moves in WEAPON_MOVES.items():
        for move in moves.values():
            for enemy_type in (Enemy, Enemy02):
                for side in (-1, 1):
                    world = scene(game, kind, enemy_type, side)
                    player, enemy = world.player, world.enemies[0]
                    key = getattr(pico2d, f"SDLK_{move.key}")
                    if move.jump_attack:
                        double_jump(game)
                        tap(game, key)
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
                        if move.jump_attack:
                            assert player.grounded and player.weapon_leap_phase == "LANDING"
                        assert world.effects[-1].image_name == config.WEAPON_HIT_IMAGES[kind]
                        assert world.effects[-1].facing == side
                        assert world.damage_numbers[-1].damage == move.damage
                        assert world.camera.shake_remaining > 0
                        assert world.camera.shake_strength == (
                            config.WEAPON_DIVE_SHAKE_STRENGTH if move.jump_attack else config.SHAKE_STRENGTH)
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
                        if move.jump_attack:
                            previous = Camera(player.x)
                            previous.shake()
                            previous.update(config.SHAKE_DURATION - world.camera.shake_remaining, player.x)
                            assert abs(world.camera.offset_x - previous.offset_x * 2) < 1e-8
                            assert abs(world.camera.offset_y - previous.offset_y * 2) < 1e-8
                            with (patch.object(world.camera, "offset_x", previous.offset_x),
                                  patch.object(world.camera, "offset_y", previous.offset_y)):
                                weaker = capture(game, f"weapon_dive_shake_previous_{kind}_{enemy_type.__name__}_{side}")
                            assert ImageChops.difference(shown.convert("RGB"),
                                                        weaker.convert("RGB")).getbbox() is not None
                            assert shown.crop((126, 58, 516, 77)).tobytes() == weaker.crop(
                                (126, 58, 516, 77)).tobytes()
                    assert hits == 1 and enemy.hp == 200 - move.damage
                    assert player.active_move is None and player.state == "IDLE"
                    assert player.sprite_image == config.WEAPON_POSE_IMAGES[kind]
                    release(game, key)
    print("PASS: SDL equipped melee strikes, both enemy types and facings: configured damage once, "
           "correct source impact frames, existing hit-effect pixels, damage numbers/shake, "
           "equipped HUD labels and return to weapon IDLE.")
    print("PASS: double-jump D landing-hit shake is 16px/8px, exactly twice the previous "
          "8px/4px on both axes; same decay, real rendered differences and fixed HP pixels; "
          "weapon A/S remain 8px and AIM/airborne D have no new shake.")


def check_dive_afterimages(game):
    for kind in config.WEAPON_AIRBORNE_ROWS:
        for side in (-1, 1):
            world = scene(game, kind, side=side)
            double_jump(game)
            tap(game, pico2d.SDLK_d)
            tick(game, 60)
            assert world.player.weapon_leap_phase == "AIM" and not world.afterimages
            push_key(pico2d.SDLK_RIGHT if side > 0 else pico2d.SDLK_LEFT)
            tap(game, pico2d.SDLK_d)
            tick(game, 2)
            assert world.player.weapon_leap_phase == "DIVE" and len(world.afterimages) >= 3
            echoes = tuple(world.afterimages)
            ages = [echo.elapsed for echo in echoes]
            world.camera.shake()
            texture = game.assets.images[config.WEAPON_POSE_IMAGES[kind]]
            with (patch.object(game.assets, "draw_sprite", wraps=game.assets.draw_sprite) as draw,
                  patch.object(texture, "opacify", wraps=texture.opacify) as alpha):
                shown = capture(game, f"weapon_dive_afterimages_{kind}_{side}")
            calls = draw.call_args_list
            assert len(calls) == len(echoes) + 1
            for call, echo in zip(calls[:-1], echoes):
                assert call.args == (echo.image_name, echo.row, echo.frame,
                                     echo.x - world.camera.render_x, echo.y - world.camera.render_y,
                                     echo.facing)
                assert call.kwargs["opacity"] == echo.opacity
            assert calls[-1].kwargs["opacity"] == 1.0
            assert alpha.call_args.args == (1.0,)
            assert [echo.elapsed for echo in echoes] == ages
            with patch.object(world.stage, "afterimages", []):
                baseline = render_image(game)
            assert ImageChops.difference(shown.convert("RGB"), baseline.convert("RGB")).getbbox() is not None
            with patch.object(game.ui, "details_visible", False):
                hidden_hud = render_image(game)
                with patch.object(world.stage, "afterimages", []):
                    hidden_baseline = render_image(game)
            assert ImageChops.difference(hidden_hud.convert("RGB"),
                                         hidden_baseline.convert("RGB")).getbbox() is not None
            tick(game, 45)
            assert world.player.active_move is None and not world.afterimages
            release(game, pico2d.SDLK_LEFT, pico2d.SDLK_RIGHT)
    print("PASS: SDL second-D dives leave frozen weapon silhouettes in both directions; "
          "real trail pixels, camera/shake coordinates, old-to-new draw order, restored "
          "texture alpha, HUD-independent display and post-landing fade verified.")


def check_switches_and_discard(game):
    for kind in WEAPON_MOVES:
        world = scene(game, kind, Enemy)
        enemy = world.enemies[0]
        for key, frames, damage in ((pico2d.SDLK_a, 15, world.player.moves["combat_a"].damage),
                                    (pico2d.SDLK_s, 15, world.player.moves["combat_s"].damage)):
            hp = enemy.hp - damage
            tap(game, key)
            tick(game, frames)
            assert enemy.hp == hp, (kind, key, enemy.hp)
        tick(game, 15)
        assert world.player.weapon is None and len(world.projectiles) == 1
        capture(game, f"weapon_combo_{kind}")
        world = scene(game, kind, Enemy)
        enemy = world.enemies[0]
        if kind in config.WEAPON_AIRBORNE_ROWS:
            double_jump(game)
            tap(game, pico2d.SDLK_d)
        else:
            tap(game, pico2d.SDLK_s)
        tick(game, 3)
        tap(game, pico2d.SDLK_g)
        tick(game, 90)
        assert world.player.weapon is None and world.player.active_move is None
        assert world.time_scale == 1 and world.player.grounded
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
    assert game.world.camera.shake_strength == config.SHAKE_STRENGTH
    assert game.world.camera.shake_remaining == 0
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
        actions = {0: pico2d.SDLK_SPACE, 8: pico2d.SDLK_SPACE, 16: pico2d.SDLK_d,
                   45: pico2d.SDLK_d, 75: pico2d.SDLK_a, 100: pico2d.SDLK_s,
                   125: pico2d.SDLK_SPACE, 137: pico2d.SDLK_SPACE,
                   144: pico2d.SDLK_d, 165: pico2d.SDLK_d}
        if frame in actions:
            key = actions[frame]
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
        check_slow_aim_and_dive(game)
        check_damage_effects_and_hud(game)
        check_dive_afterimages(game)
        check_switches_and_discard(game)
        benchmark(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
