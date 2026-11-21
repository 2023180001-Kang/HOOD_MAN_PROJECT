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
    if enemy_type is Enemy02:
        world.select_stage(3)
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
        for enemy_type in (Enemy, Enemy02):
            for side in (-1, 1):
                world, enemy = scene(game, enemy_type, side)
                player = world.player
                player.start_move(move, side)
                enemy.take_strong_hit(move, side)
                name, row = ((config.ENEMY02_IMAGE, 6) if enemy_type is Enemy02
                             else (config.STRONG_HIT_IMAGE, move.enemy_hit_row))
                assert (enemy.sprite_image, enemy.animation.row) == (name, row)
                for frame in range(8):
                    player.animation.elapsed = (frame + 0.05) / move.fps
                    enemy.animation.elapsed = (frame + 0.05) / config.STRONG_HIT_FPS
                    player_image = game.assets.images[config.STRONG_ATTACK_IMAGE]
                    enemy_image = game.assets.images[name]
                    with (patch.object(player_image, "clip_composite_draw",
                                       wraps=player_image.clip_composite_draw) as player_draw,
                          patch.object(enemy_image, "clip_composite_draw",
                                       wraps=enemy_image.clip_composite_draw) as enemy_draw):
                        if frame == max(move.active_frames):
                            suffix = "_Enemy02" if enemy_type is Enemy02 else ""
                            capture(game, f"strong_source_{move.key}_{side}{suffix}")
                        else:
                            render_image(game)
                    for actor, image_name, source_row, draw in (
                            (player, config.STRONG_ATTACK_IMAGE, move.row, player_draw),
                            (enemy, name, row, enemy_draw)):
                        assert draw.call_count == 1
                        args = draw.call_args.args
                        tile = game.assets.frames[image_name][source_row - 1][frame]
                        scale = config.SPRITE_IMAGE_SCALES.get(image_name, config.SPRITE_SCALE)
                        assert args[:4] == tuple(tile["clip"])
                        assert args[5] == ("h" if actor.facing < 0 else "")
                        assert args[8:10] == (tile["clip"][2] * scale, tile["clip"][3] * scale)
                        assert abs(args[7] - args[9] / 2 - actor.y
                                   - tile.get("offset_y", 0) * scale) < 1e-7
    print("PASS: 5 strong attacks x 2 enemy types x 8 frames x 2 directions: "
          "exact source clips/scales/anchors; city enemy02 keeps its own row-6 hit art.")


def check_inputs_damage_and_recovery(game):
    for weapon in (None, *config.WEAPON_POSE_IMAGES):
        for move in STRONG_MOVES.values():
            if move.key in "ewr":
                continue  # These attacks have dedicated input/state checks below.
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
                    image, row = ((config.ENEMY02_IMAGE, 6) if enemy_type is Enemy02
                                  else (config.STRONG_HIT_IMAGE, move.enemy_hit_row))
                    assert (enemy.state, enemy.sprite_image, enemy.animation.row) == (
                        "STRONG_HIT", image, row)
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
    print("PASS: SDL Q/T with all three loadouts, both enemy types/directions: "
          "matched reaction rows, 50 damage once, hit effects/numbers/shake, "
          "held/repeated-key suppression, HUD labels and original-sprite/AI recovery.")


def check_air_kick_chain(game):
    for weapon in (None, *config.WEAPON_POSE_IMAGES):
        for enemy_type in (Enemy, Enemy02):
            for side in (-1, 1):
                world, enemy = scene(game, enemy_type, side, weapon)
                player = world.player
                push_key(pico2d.SDLK_e)
                for _ in range(40):
                    tick(game)
                    if player.air_kick_phase == "WAIT":
                        break
                assert (enemy.hp, player.air_kick_phase, player.animation.frame) == (150, "WAIT", 4)
                assert world.time_scale == config.AIR_KICK_TIME_SCALE and player.attack_box is None
                elapsed = world.elapsed
                for repeat in (True, False):
                    push_key(pico2d.SDLK_e, repeat=repeat)
                    tick(game, 15)
                    assert enemy.hp == 150 and player.air_kick_phase == "WAIT"
                assert abs(world.elapsed - elapsed - 0.5 * config.AIR_KICK_TIME_SCALE) < 1e-7
                if weapon is None:
                    with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as font:
                        capture(game, f"air_kick_wait_{enemy_type.__name__}_{side}")
                    assert any(call.args[2].startswith("슬로 대기 중:") for call in font.call_args_list)
                behind = enemy_type(player.x - side * 80, side, ground_y=player.ground_y)
                behind.animation.set_state("HIT")
                behind.cooldown = 100
                world.enemies.append(behind)
                direction = pico2d.SDLK_LEFT if side > 0 else pico2d.SDLK_RIGHT
                push_key(direction)
                tick(game)
                assert player.facing == -side
                release(game, pico2d.SDLK_e)
                tap(game, pico2d.SDLK_e)
                assert player.air_kick_phase == "KICK" and world.time_scale == 1
                for _ in range(20):
                    tick(game)
                    if behind.hp == 150:
                        break
                assert (enemy.hp, behind.hp) == (150, 150) and player.animation.frame == 5
                assert behind.animation.row == (6 if enemy_type is Enemy02 else 4)
                assert world.damage_numbers[-1].damage == 50
                if weapon is None:
                    capture(game, f"air_kick_followup_{enemy_type.__name__}_{side}")
                push_key(pico2d.SDLK_e)  # Early third input must not queue another kick.
                tick(game, 30)
                assert player.air_kick_phase is None and world.time_scale == 1
                assert player.active_move is None and player.weapon == weapon
                assert (enemy.hp, behind.hp) == (150, 150)
                release(game, direction, pico2d.SDLK_e)
    print("PASS: SDL E first kick -> 0.2x wait, left/right midair turn -> second kick; "
          "50 once per kick, automatic normal-time/loadout recovery after two, no queued third kick.")


def check_raise_punch(game):
    for weapon in (None, *config.WEAPON_POSE_IMAGES):
        for enemy_type in (Enemy, Enemy02):
            for side in (-1, 1):
                world, enemy = scene(game, enemy_type, side, weapon)
                player = world.player
                mover = enemy_type(player.x - side * 900, side, ground_y=player.ground_y)
                world.enemies.append(mover)
                start, elapsed = mover.x, world.elapsed
                push_key(pico2d.SDLK_r)
                tick(game, 30)
                simulated = 0.5 * config.R_RAISE_TIME_SCALE
                assert world.time_scale == config.R_RAISE_TIME_SCALE
                assert enemy.hp == 200 and player.attack_box is None
                assert abs(world.elapsed - elapsed - simulated) < 1e-7
                assert abs((mover.x - start) * side - mover.run_speed * simulated) < 1e-7
                assert abs(mover.animation.elapsed - simulated) < 1e-7
                assert abs(player.animation.elapsed - simulated) < 1e-7
                world.enemies.remove(mover)
                for repeat in (True, False):
                    push_key(pico2d.SDLK_r, repeat=repeat)
                    tick(game, 30)
                    assert player.raise_punch_phase == "RAISE" and enemy.hp == 200
                if weapon is None:
                    capture(game, f"raise_punch_prepare_{enemy_type.__name__}_{side}")
                release(game, pico2d.SDLK_r)
                tap(game, pico2d.SDLK_r)
                assert player.raise_punch_phase == "STRIKE" and enemy.hp == 150
                assert enemy.animation.row == (6 if enemy_type is Enemy02 else 2)
                assert world.time_scale == 1
                if weapon is None:
                    capture(game, f"raise_punch_strike_{enemy_type.__name__}_{side}")
                tick(game, 30)
                assert player.active_move is None and player.raise_punch_phase is None
                assert player.sprite_image == config.WEAPON_POSE_IMAGES.get(weapon, config.PLAYER_IMAGE)
    print("PASS: SDL first R slows the player, enemies and world clocks to 0.2x; "
          "fresh R releases 50 once with row 2 (street thug) / own row 6 (enemy02) and normal recovery.")


def check_rush_flight(game):
    for weapon in (None, *config.WEAPON_POSE_IMAGES):
        for enemy_type in (Enemy, Enemy02):
            for side in (-1, 1):
                world, enemy = scene(game, enemy_type, side, weapon)
                player = world.player
                push_key(pico2d.SDLK_w)
                for _ in range(60):
                    tick(game)
                    if enemy.state == "RUSH_CARRIED":
                        break
                assert (enemy.hp, enemy.state) == (150, "RUSH_CARRIED")
                image, row = ((config.ENEMY02_IMAGE, 6) if enemy_type is Enemy02
                              else (config.STRONG_HIT_IMAGE, 5))
                assert (enemy.sprite_image, enemy.animation.row) == (image, row)
                assert player.rush_phase == "FLY" and player.animation.frame == 4
                start = player.x
                push_key(pico2d.SDLK_w, repeat=True)
                tick(game, 20)
                assert (player.x - start) * side > 200
                assert abs(enemy.x - player.x - side * config.RUSH_CARRY_DISTANCE) < 1e-7
                assert enemy.jump_height == player.jump_height and enemy.hp == 150
                if weapon is None:
                    capture(game, f"rush_carry_{enemy_type.__name__}_{side}")
                direction = pico2d.SDLK_LEFT if side > 0 else pico2d.SDLK_RIGHT
                push_key(direction)
                start = player.x
                tick(game, 10)
                flight_side = -side
                assert player.facing == flight_side and world.rush.direction == flight_side, (
                    weapon, enemy_type.__name__, side, player.state, player.rush_phase,
                    player.facing, world.controls.held)
                assert (player.x - start) * flight_side > 100
                assert abs(enemy.x - player.x - flight_side * config.RUSH_CARRY_DISTANCE) < 1e-7
                assert (enemy.facing, enemy.hp, enemy.state) == (-flight_side, 150, "RUSH_CARRIED")
                if weapon is None:
                    capture(game, f"rush_turn_{enemy_type.__name__}_{side}")
                release(game, direction)
                px, ex = player.x, enemy.x
                release(game, pico2d.SDLK_w)
                tick(game)
                assert player.x == px and player.vx == 0 and world.rush is None
                assert enemy.state == "RUSH_RELEASED" and (enemy.x - ex) * flight_side > 0
                assert (enemy.sprite_image, enemy.animation.row) == (image, row)
                if weapon is None:
                    capture(game, f"rush_release_{enemy_type.__name__}_{side}")
                for _ in range(60):
                    tick(game)
                    if enemy.vx == 0:
                        break
                assert 50 < (enemy.x - ex) * flight_side < 90
                stopped = enemy.x
                tick(game, 3)
                assert enemy.x == stopped and player.x == px
                if weapon is None:
                    capture(game, f"rush_stopped_{enemy_type.__name__}_{side}")
                tick(game, 30)
                assert player.active_move is None and player.weapon == weapon
                assert enemy.sprite_image == enemy.image_name and enemy.hp == 150
    print("PASS: SDL held W flies with fists forward, captures/contact-hits 50 once, "
          "left/right turns keep the captive in front without extra damage, "
          "KEYUP stops the player while the enemy slides 50..90px in the last flight direction, "
          "settles, then restores its own art/AI; all loadouts/types/directions verified.")


def check_rush_horizontal_inputs(game):
    inputs = (("up",), ("down",), ("up", "down"),
              ("left", "up"), ("left", "down"), ("right", "up"), ("right", "down"),
              ("left", "right", "up", "down"), ())
    arrows = (pico2d.SDLK_LEFT, pico2d.SDLK_RIGHT, pico2d.SDLK_UP, pico2d.SDLK_DOWN)
    for enemy_type in (Enemy, Enemy02):
        for side in (-1, 1):
            world, enemy = scene(game, enemy_type, side)
            player = world.player
            push_key(pico2d.SDLK_w)
            for _ in range(60):
                tick(game)
                if enemy.state == "RUSH_CARRIED":
                    break
            assert enemy.state == "RUSH_CARRIED"
            depth = player.ground_y
            for keys in inputs:
                release(game, *arrows)
                for key in keys:
                    push_key(getattr(pico2d, f"SDLK_{key.upper()}"))
                game.handle_events()
                direction = world.controls.direction or player.facing
                before = player.x
                tick(game)
                assert player.facing == direction and world.rush.direction == direction
                assert (player.ground_y, enemy.ground_y) == (depth, depth)
                assert (player.vx, player.ground_vy) == (direction * config.RUSH_SPEED, 0)
                assert enemy.ground_vy == 0
                assert abs(player.x - before - direction * config.RUSH_SPEED / 60) < 1e-7
                assert abs(enemy.x - player.x - direction * config.RUSH_CARRY_DISTANCE) < 1e-7
                player_image = game.assets.images[player.sprite_image]
                enemy_image = game.assets.images[enemy.sprite_image]
                with (patch.object(player_image, "clip_composite_draw",
                                   wraps=player_image.clip_composite_draw) as player_draw,
                      patch.object(enemy_image, "clip_composite_draw",
                                   wraps=enemy_image.clip_composite_draw) as enemy_draw):
                    if enemy_type is Enemy and side == 1 and keys in (("up",), ("down",), ("left", "up")):
                        capture(game, "rush_horizontal_" + "_".join(keys))
                    else:
                        render_image(game)
                for actor, draw in ((player, player_draw), (enemy, enemy_draw)):
                    args = draw.call_args.args
                    row = player.sprite_row if actor is player else actor.animation.row
                    tile = game.assets.frames[actor.sprite_image][row - 1][actor.animation.frame]
                    scale = config.SPRITE_IMAGE_SCALES.get(actor.sprite_image, config.SPRITE_SCALE)
                    assert args[4] == 0
                    assert args[5] == ("h" if actor.facing < 0 else "")
                    assert abs(args[6] - (actor.x - world.camera.render_x
                                         + tile["offset_x"] * scale * actor.facing)) < 1e-7
                    assert abs(args[7] - (actor.y - world.camera.render_y
                                         + (tile["clip"][3] / 2 + tile["offset_y"]) * scale)) < 1e-7
                assert enemy.hp == 150 and len(world.damage_numbers) <= 1
            direction = player.facing
            release(game, *arrows)
            tick(game)
            assert player.facing == direction
            px, py, ex, ey = player.x, player.ground_y, enemy.x, enemy.ground_y
            release(game, pico2d.SDLK_w)
            tick(game)
            assert (player.x, player.ground_y) == (px, py)
            assert (enemy.x - ex) * direction > 0
            assert enemy.ground_y == ey and enemy.ground_vy == 0
            assert world.rush is None
    print("PASS: SDL held W stays horizontal with up/down, diagonal and opposing inputs; "
          "full left/right speed and unrotated poses, same-depth captives, "
          "last-direction retention and horizontal-only release, both enemy types/facings.")


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
        if frame == 0:
            push_key(pico2d.SDLK_w)
        elif frame == 50:
            push_key(pico2d.SDLK_w, down=False)
        elif frame in (65, 90, 115, 145, 165):
            key = getattr(pico2d, f"SDLK_{ {65: 'e', 90: 'e', 115: 'r', 145: 'r', 165: 'q'}[frame]}")
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
        check_air_kick_chain(game)
        check_raise_punch(game)
        check_rush_flight(game)
        check_rush_horizontal_inputs(game)
        check_switches_death_and_restart(game)
        benchmark(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
