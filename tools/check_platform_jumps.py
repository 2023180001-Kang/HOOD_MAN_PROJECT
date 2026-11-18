"""Real SDL double-jump steering, one-way upper landing and gravity-driven falls."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from game import Game
from tools.check_render import capture
from tools.check_runtime import push_key, tick
from world import World


def release(game, *keys):
    for key in keys:
        push_key(key, down=False)
    game.handle_events()


def second_jump(game):
    push_key(pico2d.SDLK_SPACE)
    tick(game, 3)
    release(game, pico2d.SDLK_SPACE)
    push_key(pico2d.SDLK_SPACE)
    tick(game)
    release(game, pico2d.SDLK_SPACE)
    assert game.world.player.jump_count == 2


def check_jump_and_drop(game, direction, running):
    game.world = World()
    game.world.player.x = 1100
    player = game.world.player
    initial = pico2d.SDLK_RIGHT if direction > 0 else pico2d.SDLK_LEFT
    reverse = pico2d.SDLK_LEFT if direction > 0 else pico2d.SDLK_RIGHT
    push_key(initial)
    if running:
        push_key(pico2d.SDLK_LSHIFT)
    second_jump(game)
    release(game, initial)
    push_key(reverse)
    push_key(pico2d.SDLK_UP)
    label = "run" if running else "walk"
    maximum = player.y
    for frame in range(180):
        previous_y = player.y
        tick(game)
        assert abs(player.y - previous_y) < 28  # No floor-height teleport.
        maximum = max(maximum, player.y)
        assert player.staircase is None and game.world.stage.stairs[0].occupant is None
        if frame == 35:
            assert player.floor == 0 and player.y > 452
            capture(game, f"platform_jump_{label}_ascending")
        if player.floor == 1:
            break
    assert player.floor == 1 and player.grounded
    assert player.facing == -direction
    assert player.jump_count == 0
    assert 452 <= player.ground_y < 456
    assert maximum + config.PLAYER_HEIGHT <= config.SCREEN_HEIGHT
    capture(game, f"platform_jump_{label}_landed")
    release(game, pico2d.SDLK_UP)
    tick(game, 4)
    push_key(pico2d.SDLK_DOWN)
    for _ in range(60):
        previous_y = player.y
        tick(game)
        if player.falling_from_upper:
            assert abs(player.y - previous_y) < 8
            break
    assert player.floor == 0 and player.falling_from_upper
    assert player.jump_height > 300
    capture(game, f"platform_drop_{label}_start")
    release(game, pico2d.SDLK_DOWN)
    tick(game, 12)
    assert player.falling_from_upper and player.vy < 0
    capture(game, f"platform_drop_{label}_falling")
    previous_vy = player.vy
    push_key(pico2d.SDLK_SPACE)
    tick(game)
    release(game, pico2d.SDLK_SPACE)
    assert player.vy < previous_vy and player.jump_count == 2
    for _ in range(120):
        tick(game)
        if player.grounded:
            break
    assert player.floor == 0 and player.grounded and not player.falling_from_upper
    assert player.jump_count == 0 and player.hp == config.MAX_HP
    release(game, reverse, pico2d.SDLK_LSHIFT)
    capture(game, f"platform_drop_{label}_landed")
    print(f"PASS: SDL {label} double jump + direction reversal/Up lands on floor 2; "
          "Down off its front edge falls continuously to floor 1 with air steering, "
          "no extra jump, no damage and no staircase use.")


def check_no_automatic_landing_and_restart(game):
    game.world = World()
    second_jump(game)
    maximum = 0
    for _ in range(150):
        tick(game)
        maximum = max(maximum, game.world.player.y)
        assert game.world.player.floor == 0
    assert maximum > 452 and game.world.player.grounded
    player = game.world.player
    player.floor, player.ground_y = 1, 452
    game.world.stage.constrain_actor(player)
    push_key(pico2d.SDLK_DOWN)
    tick(game)
    release(game, pico2d.SDLK_DOWN)
    assert player.falling_from_upper
    textures = dict(game.assets.images)
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    player = game.world.player
    assert player.floor == 0 and player.grounded
    assert not player.falling_from_upper and not player.upper_landing_requested
    assert len(game.world.stage.drop_items) == 15 and not game.world.enemies
    assert all(door.state == "CLOSED" for door in game.world.stage.doors)
    assert all(game.assets.images[name] is texture for name, texture in textures.items())
    capture(game, "platform_jump_restart")
    print("PASS: a double jump without Up returns to floor 1; F5 during a fall clears "
          "all platform state and restores closed doors/15 items while reusing textures.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        game.ui.floor_bounds_visible = True
        game.ui.details_visible = False
        check_jump_and_drop(game, 1, False)
        check_jump_and_drop(game, -1, True)
        check_no_automatic_landing_and_restart(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
