"""Exercise real SDL input, HP pixels, resource reuse, performance and quit."""

import ctypes
from math import ceil, hypot
from pathlib import Path
import random
import sys
from time import perf_counter
from unittest.mock import patch

from PIL import ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d
from sdl2 import SDL_Event, SDL_PushEvent
from sdl2 import SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST

import config
from collision import bodies_overlap
from combat import MOVES
from enemy import Enemy
from game import Game
from tools.check_render import capture, render_image
from world import World


def push_key(key, down=True, repeat=False):
    event = SDL_Event()
    event.type = pico2d.SDL_KEYDOWN if down else pico2d.SDL_KEYUP
    event.key.keysym.sym = key
    event.key.repeat = int(repeat)
    if SDL_PushEvent(ctypes.byref(event)) != 1:
        raise RuntimeError("SDL_PushEvent failed")


def tick(game, frames=1):
    for _ in range(frames):
        game.handle_events()
        game.update(1 / 60)


def check_input(game):
    game.world = World()
    push_key(pico2d.SDLK_RIGHT)
    push_key(pico2d.SDLK_LSHIFT)
    tick(game, 30)
    assert game.world.player.vx == config.RUN_SPEED
    assert game.world.player.state == "RUN"
    push_key(pico2d.SDLK_SPACE)
    tick(game)
    assert game.world.player.jump_count == 1
    push_key(pico2d.SDLK_SPACE, repeat=True)
    tick(game)
    assert game.world.player.jump_count == 1
    push_key(pico2d.SDLK_SPACE, down=False)
    push_key(pico2d.SDLK_SPACE)
    tick(game)
    assert game.world.player.jump_count == 2
    assert game.world.player.vy > config.DOUBLE_JUMP_SPEED

    textures = dict(game.assets.images)
    push_key(pico2d.SDLK_F5)
    tick(game)
    player = game.world.player
    assert player.hp == 500 and player.state == "IDLE"
    assert game.world.elapsed == 0
    push_key(pico2d.SDLK_F5, repeat=True)
    tick(game, 2)
    assert game.world.player is player
    push_key(pico2d.SDLK_F5, down=False)
    push_key(pico2d.SDLK_F5)
    tick(game)
    assert game.world.player is not player
    assert all(game.assets.images[name] is image for name, image in textures.items())
    for key in (pico2d.SDLK_F5, pico2d.SDLK_RIGHT, pico2d.SDLK_LSHIFT, pico2d.SDLK_SPACE):
        push_key(key, down=False)
    tick(game)
    print("PASS: SDL move/run/double-jump/key-repeat/restart; shared textures reused.")


def check_movement_tuning(game):
    game.world = World()
    game.world.player.x = 500
    push_key(pico2d.SDLK_RIGHT)
    tick(game, 20)
    assert game.world.player.vx == 300
    push_key(pico2d.SDLK_LSHIFT)
    tick(game, 30)
    assert game.world.player.vx == 720
    start = game.world.player.x
    push_key(pico2d.SDLK_RIGHT, down=False)
    push_key(pico2d.SDLK_LEFT)
    maximum_slide = 0.0
    for _ in range(6):
        tick(game)
        maximum_slide = max(maximum_slide, game.world.player.x - start)
    assert game.world.player.vx < 0
    assert maximum_slide < 35
    tick(game, 30)
    assert game.world.player.vx == -720
    push_key(pico2d.SDLK_LEFT, down=False)
    tick(game, 6)
    assert game.world.player.vx == 0
    push_key(pico2d.SDLK_LSHIFT, down=False)
    game.handle_events()
    print(f"PASS: SDL walk 300/run 720px/s; direction reversal within 0.1s, "
          f"forward slide {maximum_slide:.2f}px; released movement stops within 0.1s.")


def check_numeric_spawns(game):
    textures = dict(game.assets.images)
    game.world = World()
    tick(game, 600)
    for index in range(len(config.STAGE_IMAGES)):
        game.world.select_stage(index)
        tick(game)
        assert not game.world.enemies and game.world.spawner.spawned_count == 0
    assert all(not stage.enemies for stage in game.world.stages)
    sides = set()
    for prefix in ("", "KP_"):
        for number in range(1, 10):
            game.world = World(rng=random.Random(42))
            world = game.world
            source = (number - 1 + bool(prefix)) % len(world.stages)
            world.stage_index = source
            assert all(not stage.enemies and stage.spawner.spawned_count == 0 for stage in world.stages)
            player = world.player
            player.hp, player.invincible = 420, True
            key = getattr(pico2d, f"SDLK_{prefix}{number}")
            push_key(key)
            tick(game)
            assert world.stage_index == source and not world.stage_loading
            assert world.player is player and player.x == config.START_X and player.hp == 420
            enemies = tuple(world.enemies)
            assert len(enemies) == world.spawner.spawned_count == number
            for enemy in enemies:
                sides.add(enemy.facing)
                assert type(enemy) is world.spawner.enemy_type
                assert enemy.hp == 200 and enemy.spawned_at == config.FIXED_DT
                assert min(enemy.x, config.WORLD_WIDTH - enemy.x) <= (
                    enemy.boundary_padding + max(config.ENEMY_RUN_SPEEDS) / 60 + 1e-6)
                assert world.stage.spawn_area.contains(enemy.x, enemy.ground_y, enemy.boundary_padding)
            if number == 9:
                world.camera.x = 0
                capture(game, f"numeric_spawn_{'keypad' if prefix else 'top'}_9")
            push_key(key, repeat=True)
            tick(game, 6)
            assert tuple(world.enemies) == enemies and world.spawner.spawned_count == number
            push_key(key)  # A repeated KEYDOWN without KEYUP is also ignored.
            tick(game)
            assert len(world.enemies) == number
            push_key(key, down=False)
            push_key(key)
            tick(game)
            assert world.stage_index == source and player.hp == 420
            assert len(world.enemies) == world.spawner.spawned_count == number * 2
            assert all(enemy in world.enemies for enemy in enemies)
            assert all(game.assets.images[name] is image for name, image in textures.items())
            push_key(key, down=False)
            game.handle_events()
    assert sides == {-1, 1}

    game.world = World(rng=random.Random(42))
    push_key(pico2d.SDLK_2)
    push_key(pico2d.SDLK_5)
    tick(game)
    assert game.world.stage_index == 0 and len(game.world.enemies) == 7
    for key in (pico2d.SDLK_2, pico2d.SDLK_5):
        push_key(key, down=False)
    game.handle_events()
    for key in (pico2d.SDLK_0, pico2d.SDLK_KP_0):
        push_key(key)
    tick(game)
    assert game.world.stage_index == 0 and len(game.world.enemies) == 7
    for key in (pico2d.SDLK_0, pico2d.SDLK_KP_0):
        push_key(key, down=False)
    game.handle_events()
    game.world.player.take_damage(500)
    push_key(pico2d.SDLK_9)
    tick(game)
    assert game.world.stage_index == 0 and game.world.spawner.spawned_count == 7
    push_key(pico2d.SDLK_F5)
    tick(game)
    assert game.world.stage_index == 0 and game.world.player.hp == 500
    assert all(not stage.enemies and stage.spawner.spawned_count == 0 for stage in game.world.stages)
    push_key(pico2d.SDLK_F5, down=False)
    push_key(pico2d.SDLK_9, repeat=True)
    tick(game, 60)
    assert not game.world.enemies
    push_key(pico2d.SDLK_9, down=False)
    push_key(pico2d.SDLK_9)
    tick(game)
    assert game.world.stage_index == 0 and len(game.world.enemies) == 9
    push_key(pico2d.SDLK_9, down=False)
    game.handle_events()

    game.world = World()
    world = game.world
    world.stage_index = 1
    world.stage.arrows_visible = True
    world.player.x, world.player.vx = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN, config.RUN_SPEED
    assert world.try_stage_transition() and world.stage_loading
    push_key(pico2d.SDLK_9)
    tick(game)
    assert world.stage_index == 1 and world.stage_loading and world.pending_stage_index == 2
    assert all(not stage.enemies for stage in world.stages)
    capture(game, "numeric_spawn_ignored_loading")
    game.update(2)
    assert world.stage_index == 2 and not world.stage_loading and not world.enemies
    push_key(pico2d.SDLK_9, repeat=True)
    tick(game)
    assert not world.enemies
    push_key(pico2d.SDLK_9, down=False)
    push_key(pico2d.SDLK_9)
    tick(game)
    assert world.stage_index == 2 and len(world.enemies) == 9
    push_key(pico2d.SDLK_9, down=False)
    game.handle_events()
    print("PASS: SDL top-row/keypad 1-9 summon exactly that many random-side enemies; "
          "no automatic start/entry/F5 spawns or numeric stage travel, held/repeated/0 inputs ignored; "
          "2+5 adds seven, per-stage types/HP/resources and death/loading input consumption verified.")


def check_player_action_inputs(game):
    for action, move in MOVES.items():
        game.world = World()
        player = game.world.player
        key = getattr(pico2d, f"SDLK_{move.key}")
        push_key(key)
        windup_frames = ceil(2 / move.fps * 60)
        impact_frames = ceil(4 / move.fps * 60)
        last_active_frame = ceil(8 / move.fps * 60) - 1
        tick(game, windup_frames)
        assert player.attack_box is None
        tick(game, impact_frames - windup_frames)
        assert game.world.player is player
        assert player.active_move == move and player.animation.row == move.row
        assert player.sprite_image == config.COMBAT_IMAGE
        assert player.attack_box is not None
        capture(game, f"player_move_{move.key}")
        push_key(key, repeat=True)
        tick(game, last_active_frame - impact_frames)
        assert player.active_move == move
        tick(game, 2)
        assert player.state == "IDLE" and player.active_move is None
        tick(game, 30)
        assert player.state == "IDLE" and player.active_move is None
        push_key(key, down=False)
        tick(game)
        assert player.state == "IDLE" and player.active_move is None
    for key_name in "qwerhjkl":
        game.world = World()
        push_key(getattr(pico2d, f"SDLK_{key_name}"))
        tick(game, 24)
        assert game.world.player.state == "IDLE" and game.world.player.active_move is None
        push_key(getattr(pico2d, f"SDLK_{key_name}"), down=False)
        game.handle_events()
    print("PASS: SDL A jab 32 FPS/~0.250s, S straight 20 FPS/~0.400s, "
          "D/F kicks 14 FPS/~0.571s; windup/active/recovery and held-key limits verified; "
          "Q/W/E/R and counters without an eligible attacker do not start an action.")


def check_player_attack_switches(game):
    for first in "asdf":
        for second in "asdf":
            if first == second:
                continue
            keys = [getattr(pico2d, f"SDLK_{letter}") for letter in (first, second)]
            game.world = World()
            push_key(keys[0])
            tick(game)
            push_key(keys[1])
            tick(game)
            player = game.world.player
            assert player.state == f"ATTACK_{second.upper()}" and player.animation.frame == 0
            push_key(keys[0], repeat=True)
            tick(game)
            assert player.state == f"ATTACK_{second.upper()}"
            for sequence in ((keys[0], keys[1]), (keys[0], keys[1], keys[0])):
                game.world = World()
                for key in sequence:
                    push_key(key, down=False)
                    push_key(key)
                tick(game)
                expected = second if len(sequence) == 2 else first
                assert game.world.player.state == f"ATTACK_{expected.upper()}"
                assert not game.world.controls.pressed
            for key in keys:
                push_key(key, down=False)
            game.handle_events()

    game.world = World()
    enemy = Enemy(config.START_X + 80, -1)
    enemy.cooldown = 100
    game.world.enemies = [enemy]
    push_key(pico2d.SDLK_a)
    tick(game, 4)
    for previous, key_name, hp in (("a", "s", 160), ("s", "d", 110), ("d", "f", 50)):
        push_key(getattr(pico2d, f"SDLK_{key_name}"))
        tick(game)
        assert game.world.player.state == f"ATTACK_{key_name.upper()}"
        assert game.world.player.animation.frame == 0
        tick(game, ceil(4 / MOVES[f"combat_{key_name}"].fps * 60) - 1)
        assert enemy.hp == hp
        capture(game, f"attack_switch_{previous}_to_{key_name}")
    tick(game, 40)
    assert game.world.player.state == "IDLE" and enemy.hp == 50
    for key_name in "asdf":
        push_key(getattr(pico2d, f"SDLK_{key_name}"), down=False)
    game.handle_events()
    print("PASS: SDL all 12 attack switches respond on the next tick; "
          "same-tick inputs select the latest fresh press, including release/repress; "
          "A windup cancels into S/D/F with HP 200->160->110->50 and no held-key loops.")


def check_player_damage_and_enemy_health(game):
    for key_name, damage in zip("asdf", (10, 40, 50, 60)):
        game.world = World()
        enemy = Enemy(config.START_X + 80, -1)
        enemy.cooldown = 100
        game.world.enemies = [enemy]
        key = getattr(pico2d, f"SDLK_{key_name}")
        push_key(key)
        tick(game, ceil(4 / MOVES[f"combat_{key_name}"].fps * 60))
        assert enemy.hp == 200 - damage and enemy.state == "HIT"
        assert len(game.world.effects) == 1
        assert game.world.camera.shake_remaining > 0
        if key_name == "a":
            verify_hit_effect_pixels(game, "punch_kick_hit_player_to_enemy", config.PUNCH_KICK_HIT_IMAGE)
        if key_name in "sdf":
            capture(game, f"player_damage_{key_name}")
        tick(game, 20)
        assert enemy.hp == 200 - damage
        push_key(key, down=False)
        game.handle_events()

    game.world = World()
    enemy = Enemy(config.START_X + 80, -1)
    game.world.enemies = [enemy]
    for hp, expected in ((200, 48), (100, 24), (0, 0)):
        if enemy.hp != hp:
            enemy.take_damage(enemy.hp - hp)
        image = capture(game, f"enemy_hp_{hp}")
        red_width = max(
            sum(image.getpixel((x, y))[0] > 160 and image.getpixel((x, y))[1] < 90
                and image.getpixel((x, y))[2] < 90 for x in range(690, 751))
            for y in range(420, 501)
        )
        assert abs(red_width - expected) <= 2, (hp, red_width)

    game.world = World()
    enemy = Enemy(config.START_X + 80, -1)
    enemy.cooldown = 100
    game.world.enemies = [enemy]
    for _ in range(4):
        push_key(pico2d.SDLK_f)
        tick(game, 48)
        push_key(pico2d.SDLK_f, down=False)
        game.handle_events()
    tick(game, 60)
    assert enemy.hp == 0 and enemy.state == "DEAD" and enemy.animation.frame == 7
    capture(game, "enemy_defeated")
    print("PASS: SDL A/S/D/F deal 10/40/50/60 once; red enemy HP bars "
          "are full/half/hidden at 200/100/0; four right kicks defeat an enemy.")


def verify_hit_effect_pixels(game, name, expected_image):
    image = capture(game, name)
    effects = game.world.effects
    assert effects and all(effect.image_name == expected_image for effect in effects)
    try:
        game.world.effects = []
        clean = render_image(game)
    finally:
        game.world.effects = effects
    difference = ImageChops.difference(image.convert("RGB"), clean.convert("RGB"))
    changed_pixels = sum(max(pixel) > 25 for pixel in
                         difference.crop((480, 400, 871, 651)).get_flattened_data())
    assert changed_pixels > 20, (name, changed_pixels)


def check_received_damage_and_effects(game):
    game.world = World()
    game.world.enemies = [ready_enemy(config.START_X - 80)]
    tick(game, 7)
    assert game.world.player.hp == 480 and len(game.world.effects) == 1
    verify_hit_effect_pixels(game, "club_hit_enemy_to_player", config.CLUB_HIT_IMAGE)
    game.world.enemies.clear()
    tick(game, 30)
    assert not game.world.effects

    for side in (-1, 1):
        game.world = World()
        push_key(pico2d.SDLK_h)
        tick(game)
        assert game.world.player.state == "IDLE" and game.world.player.active_move is None
        game.world.enemies = [ready_enemy(game.world.player.x + side * 80, -side)]
        tick(game)
        assert game.world.player.hp == 480 and game.world.player.state == "HIT"
        assert len(game.world.effects) == 1 and game.world.camera.shake_remaining > 0
        verify_hit_effect_pixels(game, f"failed_counter_h_hit_{'left' if side < 0 else 'right'}",
                                 config.CLUB_HIT_IMAGE)
        push_key(pico2d.SDLK_h, down=False)
        tick(game)

    game.world = World()
    push_key(pico2d.SDLK_h)
    push_key(pico2d.SDLK_RIGHT)
    push_key(pico2d.SDLK_LSHIFT)
    tick(game, 30)
    assert game.world.player.state == "RUN" and game.world.player.vx == config.RUN_SPEED
    capture(game, "failed_counter_h_running")
    push_key(pico2d.SDLK_SPACE)
    tick(game)
    assert game.world.player.jump_count == 1
    for key in (pico2d.SDLK_h, pico2d.SDLK_RIGHT, pico2d.SDLK_LSHIFT, pico2d.SDLK_SPACE):
        push_key(key, down=False)
    game.handle_events()
    print("PASS: SDL H without a timed attacker does not block; running/jumping and both-side attacks "
          "deal 20 with club-hit effects/shake; hit effects expire normally.")


def running_jump_distance(game, record=False, running=True):
    game.world = World()
    game.world.player.x = 350
    push_key(pico2d.SDLK_RIGHT)
    if running:
        push_key(pico2d.SDLK_LSHIFT)
    tick(game, 30)
    start = game.world.player.x
    push_key(pico2d.SDLK_SPACE)
    tick(game, 30)
    push_key(pico2d.SDLK_SPACE, down=False)
    push_key(pico2d.SDLK_SPACE)
    tick(game)
    assert game.world.player.jump_count == 2
    for frame in range(180):
        tick(game)
        if record and frame == 20:
            capture(game, "running_double_jump")
        if game.world.player.grounded:
            break
    assert game.world.player.grounded
    assert game.world.player.x < config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH
    distance = game.world.player.x - start
    for key in (pico2d.SDLK_RIGHT, pico2d.SDLK_LSHIFT, pico2d.SDLK_SPACE):
        push_key(key, down=False)
    game.handle_events()
    return distance


def check_jump_range(game):
    with patch.object(config, "RUN_DOUBLE_JUMP_SPEED", 780.0):
        previous_run = running_jump_distance(game)
    improved = running_jump_distance(game, record=True)
    with patch.object(config, "DOUBLE_JUMP_SPEED", 600.0):
        previous_walk = running_jump_distance(game, running=False)
    walking = running_jump_distance(game, running=False)
    assert improved - previous_run > 150
    assert walking - previous_walk > 60
    print(f"PASS: SDL double jump walk {previous_walk:.1f}px -> {walking:.1f}px; "
          f"run {previous_run:.1f}px -> {improved:.1f}px (+{improved - previous_run:.1f}px).")


def check_crowd_escape(game):
    for direction in (-1, 1):
        for running in (False, True):
            game.world = World()
            game.world.enemies = [Enemy(config.START_X + side * gap, -side)
                                  for side in (-1, 1) for gap in (61, 82, 103, 124)]
            direction_key = pico2d.SDLK_RIGHT if direction > 0 else pico2d.SDLK_LEFT
            push_key(direction_key)
            if running:
                push_key(pico2d.SDLK_LSHIFT)
            push_key(pico2d.SDLK_SPACE)
            tick(game, 3)
            push_key(pico2d.SDLK_SPACE, down=False)
            push_key(pico2d.SDLK_SPACE)
            for frame in range(120):
                tick(game)
                assert game.world.player.hp == 500
                assert all(not bodies_overlap(game.world.player, enemy)
                           for enemy in game.world.enemies)
                assert game.world.player.y + config.PLAYER_HEIGHT < config.SCREEN_HEIGHT
                if frame == 20:
                    capture(game, f"crowd_escape_{direction}_{'run' if running else 'walk'}")
                if game.world.player.grounded:
                    break
            assert game.world.player.grounded
            assert all((game.world.player.x - enemy.x) * direction > 61
                       for enemy in game.world.enemies)
            for key in (direction_key, pico2d.SDLK_LSHIFT, pico2d.SDLK_SPACE):
                push_key(key, down=False)
            game.handle_events()
    print("PASS: SDL quick double jump escapes eight surrounding enemies left/right, "
          "walking/running, without damage/body overlap or exceeding the screen top.")


def ready_enemy(x, facing=1):
    enemy = Enemy(x, facing)
    enemy.animation.set_state("ATTACK")
    enemy.animation.elapsed = 4 / config.ENEMY_ANIMATIONS["ATTACK"][1]
    enemy.cooldown = config.ENEMY_ATTACK_INTERVAL
    return enemy


def check_crowd_damage(game):
    game.world = World()
    game.world.enemies = [ready_enemy(config.START_X - 80),
                          ready_enemy(config.START_X - 80),
                          ready_enemy(config.START_X + 80, -1),
                          ready_enemy(config.START_X + 80, -1)]
    tick(game)
    assert game.world.player.hp == 420
    assert all(enemy.has_hit for enemy in game.world.enemies)
    capture(game, "crowd_hit")
    tick(game, 6)
    assert game.world.player.hp == 420

    game.world = World()
    game.world.enemies = [ready_enemy(config.START_X - 80)]
    tick(game)
    assert game.world.player.hp == 480
    tick(game, 12)
    elapsed = game.world.player.animation.elapsed
    assert game.world.player.state == "HIT"
    game.world.enemies.append(ready_enemy(config.START_X + 80, -1))
    tick(game)
    assert game.world.player.hp == 460
    assert game.world.player.animation.elapsed > elapsed
    capture(game, "staggered_hit")
    push_key(pico2d.SDLK_F5)
    tick(game)
    assert game.world.player.hp == 500 and not game.world.enemies
    push_key(pico2d.SDLK_F5, down=False)
    game.handle_events()
    print("PASS: four enemies deal 80; HIT accepts another enemy's 20 without "
          "animation reset; spent swings do not repeat; F5 clears combat state.")


def check_enemy_run_chase(game):
    game.world = World()
    push_key(pico2d.SDLK_4)
    tick(game)
    push_key(pico2d.SDLK_4, down=False)
    game.handle_events()
    old_enemies = list(game.world.enemies)
    assert [enemy.run_speed for enemy in old_enemies] == list(config.ENEMY_RUN_SPEEDS)
    for enemy in old_enemies:
        enemy.x = config.START_X - config.ENEMY_RUN_STOP_DISTANCE
        enemy.ground_y = game.world.player.ground_y
    tick(game)
    assert all(enemy.state == "WALK" for enemy in old_enemies)
    for key in (pico2d.SDLK_RIGHT, pico2d.SDLK_LSHIFT, pico2d.SDLK_SPACE):
        push_key(key)
    tick(game, 30)
    assert game.world.player.y > config.GROUND_Y
    assert all(enemy.state == "RUN" for enemy in old_enemies)
    push_key(pico2d.SDLK_SPACE, down=False)
    push_key(pico2d.SDLK_SPACE)
    tick(game, 42)
    assert all(enemy.state == "RUN" and enemy.animation.row == 3 for enemy in old_enemies)
    assert all(abs(hypot(enemy.vx, enemy.ground_vy) - speed) < 1e-8
               for enemy, speed in zip(old_enemies, config.ENEMY_RUN_SPEEDS))
    assert len({enemy.x for enemy in old_enemies}) == 4
    capture(game, "enemy_run_chase")
    for key in (pico2d.SDLK_RIGHT, pico2d.SDLK_LSHIFT, pico2d.SDLK_SPACE):
        push_key(key, down=False)
    tick(game, 120)
    assert all(not enemy.running for enemy in old_enemies)
    assert all(enemy.state in ("WALK", "ATTACK", "IDLE") for enemy in old_enemies)
    capture(game, "enemy_chase_arrival")
    push_key(pico2d.SDLK_F5)
    tick(game)
    assert not game.world.enemies and game.world.spawner.spawned_count == 0
    push_key(pico2d.SDLK_F5, down=False)
    push_key(pico2d.SDLK_4)
    tick(game)
    push_key(pico2d.SDLK_4, down=False)
    game.handle_events()
    assert [enemy.run_speed for enemy in game.world.enemies] == list(config.ENEMY_RUN_SPEEDS)
    assert all(enemy.hp == 200 for enemy in game.world.enemies)
    assert all(enemy not in old_enemies for enemy in game.world.enemies)
    print("PASS: SDL sprint/double-jump escape triggers 360/420/480/540px/s chases "
          "with row 3; arrivals walk/attack; F5 restores the speed profiles.")


def check_nearby_death_knockback(game):
    game.world = World()
    game.world.player.hp = 20
    near_left = ready_enemy(config.START_X - 80)
    near_right = Enemy(config.START_X + 140, -1)
    far_left = Enemy(config.START_X - 300)
    far_right = Enemy(config.START_X + 500, -1, run_speed=540)
    game.world.enemies = [near_left, near_right, far_left, far_right]
    tick(game)
    assert game.world.player.hp == 0 and game.world.player.state == "DYING"
    assert near_left.knockback_started and near_right.knockback_started
    assert not far_left.knockback_started and not far_right.knockback_started
    far_positions = (far_left.x, far_right.x)
    far_facings = (far_left.facing, far_right.facing)
    assert far_left.vx == far_right.vx == 0
    assert not any(enemy.running for enemy in game.world.enemies)
    tick(game, 12)
    capture(game, "nearby_death_knockback")
    tick(game, 90)
    assert (far_left.x, far_right.x) == far_positions
    assert (far_left.facing, far_right.facing) == far_facings
    assert far_left.attack_box is None and far_right.attack_box is None
    assert game.world.player.state == "DEAD"
    capture(game, "nearby_death_settled")

    game.world = World()
    game.world.player.hp = 20
    game.world.player.y += 140
    diagonal = ready_enemy(config.START_X + 88, -1)
    game.world.enemies = [diagonal]
    tick(game)  # The attack reaches the feet, but sqrt(88^2 + 140^2) exceeds 160.
    assert game.world.player.hp == 0
    assert not diagonal.knockback_started
    position = diagonal.x
    capture(game, "airborne_death_outside_radius")
    tick(game, 90)
    assert game.world.player.grounded and game.world.player.state == "DEAD"
    assert not diagonal.knockback_started and diagonal.x == position
    print("PASS: fatal attack knocks back two nearby enemies; two distant enemies "
          "stop in place; airborne death uses the 2D radius once, without landing retrigger.")


def check_hp_pixels(game):
    game.world = World()
    shots = {}
    for hp in (500, 480, 460, 420, 250, 0):
        game.world.player.hp = hp
        shots[hp] = capture(game, f"verified_hp_{hp}")
    for hp, image in shots.items():
        blue_pixels = sum(
            image.getpixel((x, 68))[2] > image.getpixel((x, 68))[0] + 30
            for x in range(125, 518)
        )
        assert abs(blue_pixels - 392.25 * hp / 500) <= 2, (hp, blue_pixels)
        assert image.crop((35, 40, 100, 95)).tobytes() == shots[500].crop((35, 40, 100, 95)).tobytes()
    game.world.player.hp = 250
    game.world.player.x = 100
    game.world.camera.shake()
    game.world.camera.update(0.03, 100)
    shaken = capture(game, "verified_ui_fixed")
    assert shaken.crop((126, 58, 516, 77)).tobytes() == shots[250].crop((126, 58, 516, 77)).tobytes()
    print("PASS: rendered HP fill 100%/96%/92%/84%/50%/0%; portrait and HUD position unchanged.")


def check_focus_loss(game):
    game.world = World()
    push_key(pico2d.SDLK_RIGHT)
    push_key(pico2d.SDLK_LSHIFT)
    tick(game, 30)
    event = SDL_Event()
    event.type = SDL_WINDOWEVENT
    event.window.event = SDL_WINDOWEVENT_FOCUS_LOST
    assert SDL_PushEvent(ctypes.byref(event)) == 1
    tick(game)
    assert not game.world.controls.held, "Focus loss left movement keys held"
    tick(game, 30)
    assert game.world.player.vx == 0
    push_key(pico2d.SDLK_a)
    push_key(pico2d.SDLK_9)
    assert SDL_PushEvent(ctypes.byref(event)) == 1
    tick(game)
    assert game.world.player.active_move is None and not game.world.enemies
    assert game.world.stage_index == 0
    assert not game.world.controls.held and not game.world.controls.pressed
    print("PASS: window focus loss clears movement, pending attacks and numeric summons.")


def check_natural_game(game):
    game.world = World(rng=random.Random(1))
    push_key(pico2d.SDLK_4)
    tick(game)
    push_key(pico2d.SDLK_4, down=False)
    game.handle_events()
    for frame in range(3600):
        game.update(1 / 60)
        if frame % 120 == 0:
            game.draw()
        if game.world.player.state == "DEAD":
            break
    assert game.world.spawner.spawned_count == 4
    assert game.world.player.hp == 0
    assert game.world.player.state == "DEAD"
    assert any(enemy.knockback_started for enemy in game.world.enemies)
    assert all(enemy.vx == 0 and not enemy.running for enemy in game.world.enemies)
    capture(game, "natural_death")
    print(f"PASS: numeric spawn/chase/attack/death after {game.world.elapsed:.2f} simulated seconds.")


def benchmark(game):
    game.world = World()
    game.world.enemies = [
        Enemy(config.START_X + (-600 if index % 2 == 0 else 600),
              facing=1 if index % 2 == 0 else -1, run_speed=speed)
        for index, speed in enumerate(config.ENEMY_RUN_SPEEDS)
    ]
    start = perf_counter()
    frames = game.run(max_frames=180)
    seconds = perf_counter() - start
    assert frames == 180
    assert len(game.world.enemies) == 4
    print(f"BENCHMARK: {frames} frames / {seconds:.3f}s = {frames / seconds:.2f} FPS; "
          f"4 enemies + run/walk/attacks + HP + shake, target {config.TARGET_FPS} FPS.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_numeric_spawns(game)
        check_input(game)
        check_movement_tuning(game)
        check_player_action_inputs(game)
        check_player_attack_switches(game)
        check_player_damage_and_enemy_health(game)
        check_received_damage_and_effects(game)
        check_jump_range(game)
        check_crowd_escape(game)
        check_crowd_damage(game)
        check_nearby_death_knockback(game)
        check_focus_loss(game)
        check_hp_pixels(game)
        check_enemy_run_chase(game)
        check_natural_game(game)
        benchmark(game)
        event = SDL_Event()
        event.type = pico2d.SDL_QUIT
        assert SDL_PushEvent(ctypes.byref(event)) == 1
        assert game.run(max_frames=5) == 0
        assert not game.running
        print("PASS: SDL_QUIT stops the game loop normally.")
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
