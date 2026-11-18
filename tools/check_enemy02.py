"""Verify city spawns, ranged leap slams and reactions in an actual SDL window."""

from pathlib import Path
import random
import sys
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from collision import bodies_overlap
from combat import MOVES
from enemy import Enemy
from enemy02 import Enemy02, leap_height
from game import Game
from tools.check_counters import release, start_follow_up, wait_for_hold
from tools.check_render import capture
from tools.check_runtime import push_key, tick
from world import World


def encounter(game, kind="clubs", side=1, *, start=True):
    game.world = World(rng=random.Random(23))
    world = game.world
    world.stage_index = 3
    enemy = world.spawner.spawn(1, world.elapsed)[0]
    world.enemies = [enemy]  # Isolate the selected attack's pixels and exact damage.
    enemy.x = enemy.previous_x = world.player.x + side * (400 if kind == "slam" else 80)
    enemy.ground_y = enemy.previous_ground_y = world.player.ground_y
    enemy.facing = -side
    if start and kind == "slam":
        assert enemy.start_leap(world.player)
    elif start:
        enemy.start_attack()
    return world, enemy


def set_frame(world, enemy, frame):
    if enemy.attack_kind == "slam" and frame >= 2:
        while enemy.leap_phase == "WINDUP":
            enemy.update(config.FIXED_DT, world.player)
        if frame in (2, 3):
            target_time = enemy.leap_duration * (0.25 if frame == 2 else 0.75)
            enemy.update(max(0.0, target_time - enemy.leap_elapsed), world.player)
        else:
            while enemy.leap_phase != "LANDING":
                enemy.update(config.FIXED_DT, world.player)
    enemy.animation.elapsed = (frame + 0.05) / enemy.attack_fps
    enemy.update(0, world.player)


def check_city_summons(game):
    game.world = World(rng=random.Random(32))
    textures = dict(game.assets.images)
    for number in range(1, 11):
        game.world.select_stage(number - 1)
        assert not game.world.enemies and game.world.spawner.spawned_count == 0
        push_key(pico2d.SDLK_4)
        tick(game)
        release(game, pico2d.SDLK_4)
        world = game.world
        expected = Enemy02 if number in (3, 4) else Enemy
        assert world.stage_index == number - 1
        assert len(world.enemies) == world.spawner.spawned_count == 4
        assert all(type(enemy) is expected for enemy in world.enemies)
        assert all(world.stage.spawn_area.contains(enemy.x, enemy.ground_y, enemy.boundary_padding)
                   for enemy in world.enemies)
        if number in (3, 4):
            for side, camera_x in (("left", 0), ("right", config.WORLD_WIDTH - config.SCREEN_WIDTH)):
                world.camera.x = camera_x
                with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as draw:
                    capture(game, f"enemy02_city_{number - 2}_{side}")
                assert any("몽둥이 60 / 착지 80" in call.args[2] for call in draw.call_args_list)
        assert all(game.assets.images[name] is image for name, image in textures.items())
    print("PASS: SDL 4 summons four enemy02 actors on city stages, old actors elsewhere; "
          "spawn floors/texture reuse and the real 60/80 HUD text verified.")


def check_attack_rendering(game):
    texture = game.assets.images[config.ENEMY02_IMAGE]
    for side in (-1, 1):
        for kind, row in (("clubs", 4), ("slam", 5)):
            world, enemy = encounter(game, kind, side)
            for frame in range(8):
                set_frame(world, enemy, frame)
                tile = game.assets.frames[config.ENEMY02_IMAGE][row - 1][frame]
                with patch.object(texture, "clip_composite_draw", wraps=texture.clip_composite_draw) as draw:
                    capture(game, f"enemy02_{kind}_{side}_{frame}")
                args = draw.call_args.args
                assert args[:4] == tuple(tile["clip"])
                assert args[5] == ("h" if side > 0 else "")
                assert abs(args[7] - args[9] / 2 - enemy.y) < 1e-8
                height = leap_height() * 0.75 if kind == "slam" and frame in (2, 3) else 0
                assert abs(enemy.jump_height - height) < 1e-7
    print("PASS: both source attack rows, 8 frames x 2 facings, exact clips/flips and real "
          "high-flight feet without a doubled render offset or premature landing pose.")


def check_tracking_leap(game):
    game.world = World()
    game.world.stage_index = 3
    game.world.enemies.clear()
    push_key(pico2d.SDLK_SPACE)
    tick(game)
    while game.world.player.vy > 0:
        tick(game)
    release(game, pico2d.SDLK_SPACE)
    push_key(pico2d.SDLK_SPACE)
    tick(game)
    reference_peak = game.world.player.jump_height
    while game.world.player.vy > 0:
        tick(game)
        reference_peak = max(reference_peak, game.world.player.jump_height)
    capture(game, "enemy02_player_double_jump_reference")
    release(game, pico2d.SDLK_SPACE)
    peaks = []
    for side in (-1, 1):
        world, enemy = encounter(game, "slam", side, start=False)
        tick(game)
        assert enemy.leap_phase == "WINDUP" and enemy.attack_kind == "slam"
        capture(game, f"enemy02_leap_{side}_windup")
        peak, apex_captured = 0.0, False
        origin, target = None, None
        for _ in range(180):
            tick(game)
            if enemy.leaping:
                origin, target = enemy.leap_origin, enemy.leap_target
                assert target == (config.START_X, config.GROUND_Y)
                peak = max(peak, enemy.jump_height)
                assert enemy.attack_box is None and world.player.hp == 500
                if enemy.vy <= 0 and not apex_captured:
                    capture(game, f"enemy02_leap_{side}_apex")
                    apex_captured = True
            elif enemy.leap_phase == "LANDING":
                assert enemy.leap_blocked and not bodies_overlap(world.player, enemy)
                assert abs(enemy.x - world.player.x) <= 61 + 1e-7
                assert (target[0] - origin[0]) * -side > 0
                capture(game, f"enemy02_leap_{side}_landed")
                break
        assert apex_captured and abs(peak - reference_peak) < 1
        peaks.append(peak)
        for _ in range(20):
            tick(game)
            if enemy.has_hit:
                break
        assert world.player.hp == 420 and enemy.has_hit
        capture(game, f"enemy02_leap_{side}_impact")
        tick(game, 6)
        assert world.player.hp == 420
    world, enemy = encounter(game, "slam", side=-1)
    while not enemy.leaping:
        tick(game)
    target = enemy.leap_target
    push_key(pico2d.SDLK_RIGHT)
    push_key(pico2d.SDLK_LSHIFT)
    while enemy.leaping:
        tick(game)
        assert enemy.leap_target == target and world.player.hp == 500
    release(game, pico2d.SDLK_RIGHT)
    release(game, pico2d.SDLK_LSHIFT)
    tick(game, 20)
    assert world.player.hp == 500
    capture(game, "enemy02_leap_dodged")
    print(f"PASS: normal SDL player double-jump peak {reference_peak:.3f}px; enemy leap peaks "
           f"{peaks[0]:.3f}/{peaks[1]:.3f}px; both directions target the player's takeoff "
           "position, stop at an occupied body edge and deal 80 after landing; "
           "SDL running evades the committed landing point.")


def check_midair_collisions(game):
    for index in (2, 3):
        for side in (-1, 1):
            world, enemy = encounter(game, "slam", side)
            world.stage_index = index
            world.enemies = [enemy]
            world.stage.traffic = None
            tick(game, 30)
            assert enemy.leaping
            push_key(pico2d.SDLK_SPACE)
            for _ in range(90):
                tick(game)
                if enemy.air_contact_attack:
                    break
            assert enemy.air_contact_attack and enemy.has_hit
            assert enemy.jump_height > 0 and world.player.jump_height > 0
            assert world.player.hp == 440
            assert (enemy.attack_kind, enemy.animation.row) == ("clubs", 4)
            assert not bodies_overlap(world.player, enemy)
            assert len(world.effects) == 1
            capture(game, f"enemy02_air_contact_city_{index - 1}_{side}")
            release(game, pico2d.SDLK_SPACE)
            tick(game, 42)
            assert world.player.hp == 440 and enemy.jump_height == 0
    for action in ("invincible", "player_jab"):
        world, enemy = encounter(game, "slam", side=-1)
        while not enemy.leaping:
            tick(game)
        enemy.update(enemy.leap_duration / 2 - enemy.leap_elapsed, world.player)
        player = world.player
        player.x = player.previous_x = enemy.x + 60
        player.jump_height = player.previous_jump_height = enemy.jump_height
        player.jump_count = 2
        player.facing = -1
        player.animation.set_state("JUMP")
        if action == "invincible":
            player.invincible = True
        else:
            player.start_move(MOVES["combat_a"], -1)
            player.animation.elapsed = 3 / MOVES["combat_a"].fps
        tick(game)
        assert player.hp == 500
        if action == "invincible":
            assert enemy.has_hit and not world.effects
        else:
            assert enemy.hp == 190 and enemy.state == "HIT"
            assert len(world.effects) == 1
        capture(game, f"enemy02_air_contact_{action}")
    print("PASS: real SDL jumps meet enemy leaps on both city maps/directions, block body "
          "pass-through and trigger one row-4 normal hit (60), with no later landing 80; "
          "P immunity and airborne player-jab priority also verified.")


def check_damage(game):
    for side in (-1, 1):
        for kind, before_active, damage in (("clubs", 2, 60), ("slam", 4, 80)):
            world, enemy = encounter(game, kind, side)
            set_frame(world, enemy, before_active)
            assert enemy.attack_box is None and world.player.hp == 500
            for _ in range(20):
                tick(game)
                if enemy.has_hit:
                    break
            assert world.player.hp == 500 - damage and enemy.has_hit
            assert len(world.effects) == 1 and not world.damage_numbers
            assert world.camera.shake_remaining > 0
            capture(game, f"enemy02_{kind}_{side}_impact")
            tick(game, 6)
            assert world.player.hp == 500 - damage
    world, enemy = encounter(game, "slam")
    set_frame(world, enemy, 5)
    push_key(pico2d.SDLK_p)
    tick(game)
    release(game, pico2d.SDLK_p)
    assert enemy.has_hit and world.player.hp == 500 and not world.effects
    print("PASS: both directions deal clubs=60 / landed slam=80 once per whole motion, "
          "with real hit effects/HP/shake; SDL P consumes a swing without damage/effects.")


def check_counters_and_death(game):
    for key in "hjkl":
        world, enemy = encounter(game)
        set_frame(world, enemy, 1)
        keycode = getattr(pico2d, f"SDLK_{key}")
        push_key(keycode)
        tick(game)
        release(game, keycode)
        wait_for_hold(game)
        assert enemy.sprite_image == config.ENEMY02_IMAGE
        capture(game, f"enemy02_counter_{key}_hold")
        start_follow_up(game)
        for _ in range(180):
            tick(game)
            assert enemy.sprite_image == config.ENEMY02_IMAGE
            if world.counter is None and enemy.counter_move is None:
                break
        assert enemy.hp == 120 and enemy.state == "IDLE"
    world, enemy = encounter(game)
    enemy.take_damage(200)
    tick(game, 60)
    assert (enemy.state, enemy.animation.row, enemy.animation.frame) == ("DEAD", 7, 7)
    assert enemy.sprite_image == config.ENEMY02_IMAGE
    capture(game, "enemy02_defeated")
    enemy.corpse_elapsed = 3.5
    texture = game.assets.images[config.ENEMY02_IMAGE]
    with patch.object(texture, "opacify", wraps=texture.opacify) as alpha:
        capture(game, "enemy02_corpse_half")
    assert [call.args[0] for call in alpha.call_args_list] == [0.5, 1.0]
    print("PASS: all four SDL counter/carry/A follow-ups preserve enemy02's identity and "
          "single 80 damage; own row-7 death/fade and shared texture alpha restoration verified.")


def check_city_road(game):
    world, enemy = encounter(game)
    world.stage_index = 2
    world.enemies = [enemy]
    world.player.ground_y = enemy.ground_y = config.CAR_GROUND_Y
    enemy.x = enemy.previous_x = world.player.x
    world.player.invincible = True
    tick(game, 60)
    assert world.stage.traffic is None and (world.player.hp, enemy.hp) == (500, 200)
    assert not world.player.car_hit and not enemy.car_hit
    assert enemy.sprite_image == config.ENEMY02_IMAGE
    capture(game, "enemy02_city_road_no_traffic")
    print("PASS: retired city traffic stays absent; road pursuit keeps enemy02's own art "
          "and causes no vehicle deaths.")


def check_natural_encounter_and_restart(game):
    game.world = World(rng=random.Random(19))
    world = game.world
    world.stage_index = 3
    world.player.invincible = True
    push_key(pico2d.SDLK_4)
    tick(game)
    release(game, pico2d.SDLK_4)
    seen = set()
    spawn_state = world.spawner.rng.getstate()
    for _ in range(480):
        tick(game)
        seen.update(enemy.attack_kind for enemy in world.enemies if enemy.state == "ATTACK")
    assert seen == {"clubs", "slam"}
    assert len(world.enemies) == world.spawner.spawned_count == 4
    assert world.player.hp == 500 and world.spawner.rng.getstate() == spawn_state
    capture(game, "enemy02_city_combat")
    start = perf_counter()
    frames = game.run(max_frames=180)
    seconds = perf_counter() - start
    assert frames == 180 and len(world.enemies) == 4
    print(f"BENCHMARK: 4 enemy02 actors + ranged leaps/close attacks/HP/UI: "
          f"{frames} frames / {seconds:.3f}s = {frames / seconds:.2f} FPS.")
    old_enemies = [enemy for stage in world.stages for enemy in stage.enemies]
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert game.world.stage_index == 0 and game.world.player.hp == 500
    assert all(not stage.enemies and stage.spawner.spawned_count == 0 for stage in game.world.stages)
    for index in (0, 3):
        game.world.select_stage(index)
        push_key(pico2d.SDLK_4)
        tick(game)
        release(game, pico2d.SDLK_4)
    for index, stage in enumerate(game.world.stages):
        assert len(stage.enemies) == stage.spawner.spawned_count == (4 if index in (0, 3) else 0)
        expected = Enemy02 if index in (2, 3) else Enemy
        assert all(type(enemy) is expected and enemy not in old_enemies and enemy.hp == 200
                   for enemy in stage.enemies)
    print("PASS: natural four-enemy city combat uses ranged leaps/close attacks without touching spawn RNG; "
          "SDL F5 clears all groups and fresh numeric input summons the correct full-health type.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_city_summons(game)
        check_attack_rendering(game)
        check_tracking_leap(game)
        check_midair_collisions(game)
        check_damage(game)
        check_counters_and_death(game)
        check_city_road(game)
        check_natural_encounter_and_restart(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
