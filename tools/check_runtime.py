"""Exercise real SDL input, HP pixels, resource reuse, performance and quit."""

import ctypes
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d
from sdl2 import SDL_Event, SDL_PushEvent
from sdl2 import SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST

import config
from enemy import Enemy
from game import Game
from tools.check_render import capture
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
    game.world = World(spawn_schedule=())
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
    push_key(pico2d.SDLK_r)
    tick(game)
    player = game.world.player
    assert player.hp == 500 and player.state == "IDLE"
    assert game.world.elapsed == 0
    push_key(pico2d.SDLK_r, repeat=True)
    tick(game, 2)
    assert game.world.player is player
    push_key(pico2d.SDLK_r, down=False)
    push_key(pico2d.SDLK_r)
    tick(game)
    assert game.world.player is not player
    assert all(game.assets.images[name] is image for name, image in textures.items())
    for key in (pico2d.SDLK_r, pico2d.SDLK_RIGHT, pico2d.SDLK_LSHIFT, pico2d.SDLK_SPACE):
        push_key(key, down=False)
    tick(game)
    print("PASS: SDL move/run/double-jump/key-repeat/restart; shared textures reused.")


def check_movement_tuning(game):
    game.world = World(spawn_schedule=())
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


def running_jump_distance(game, record=False):
    game.world = World(spawn_schedule=())
    game.world.player.x = 350
    push_key(pico2d.SDLK_RIGHT)
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
    with patch.multiple(config, RUN_SPEED=360.0, WALK_SPEED=180.0,
                        ACCELERATION=1000.0, FRICTION=1200.0,
                        RUN_DOUBLE_JUMP_SPEED=600.0):
        original = running_jump_distance(game)
    with patch.object(config, "RUN_DOUBLE_JUMP_SPEED", config.DOUBLE_JUMP_SPEED):
        unboosted = running_jump_distance(game)
    improved = running_jump_distance(game, record=True)
    assert improved > original * 2
    assert improved - unboosted > 100
    print(f"PASS: SDL running double jump {original:.1f}px -> {improved:.1f}px "
          f"({improved / original:.2f}x), +{improved - unboosted:.1f}px over unboosted at 720px/s.")


def ready_enemy(x, facing=1):
    enemy = Enemy(x, facing)
    enemy.animation.set_state("ATTACK")
    enemy.animation.elapsed = 4 / config.ENEMY_ANIMATIONS["ATTACK"][1]
    enemy.cooldown = config.ENEMY_ATTACK_INTERVAL
    return enemy


def check_crowd_damage(game):
    game.world = World(spawn_schedule=())
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

    game.world = World(spawn_schedule=())
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
    push_key(pico2d.SDLK_r)
    tick(game)
    assert game.world.player.hp == 500 and not game.world.enemies
    push_key(pico2d.SDLK_r, down=False)
    game.handle_events()
    print("PASS: four enemies deal 80; HIT accepts another enemy's 20 without "
          "animation reset; spent swings do not repeat; R clears combat state.")


def check_hp_pixels(game):
    game.world = World(spawn_schedule=())
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
    game.world = World(spawn_schedule=())
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
    print("PASS: window focus loss clears held movement and pending inputs.")


def check_natural_game(game):
    game.world = World()
    for frame in range(3600):
        game.update(1 / 60)
        if frame % 120 == 0:
            game.draw()
        if game.world.player.state == "DEAD":
            break
    assert game.world.spawner.spawned_count == 4
    assert game.world.player.hp == 0
    assert game.world.player.state == "DEAD"
    assert all(enemy.knockback_started for enemy in game.world.enemies)
    capture(game, "natural_death")
    print(f"PASS: natural spawn/chase/attack/death after {game.world.elapsed:.2f} simulated seconds.")


def benchmark(game):
    game.world = World(spawn_schedule=())
    game.world.enemies = [Enemy(config.START_X - 80), Enemy(config.START_X - 80),
                          Enemy(config.START_X + 80, -1), Enemy(config.START_X + 80, -1)]
    start = perf_counter()
    frames = game.run(max_frames=180)
    seconds = perf_counter() - start
    assert frames == 180
    assert len(game.world.enemies) == 4
    print(f"BENCHMARK: {frames} frames / {seconds:.3f}s = {frames / seconds:.2f} FPS; "
          f"4 enemies + attacks + HP + shake, target {config.TARGET_FPS} FPS.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_input(game)
        check_movement_tuning(game)
        check_jump_range(game)
        check_crowd_damage(game)
        check_focus_loss(game)
        check_hp_pixels(game)
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
