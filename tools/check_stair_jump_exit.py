"""Verify single-jump stair landings and immediate stair exits with real SDL."""

from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from game import Game
from tools.check_render import capture
from tools.check_runtime import push_key, tick
from tools.check_stair_controls import begin
from tools.check_two_floors import release
from world import World


def check_jump_entry(game):
    game.world = World(item_rng=random.Random(5))
    world = game.world
    player = world.player
    player.x, player.ground_y = 180, 136
    world.camera.update(0, player.x)
    push_key(pico2d.SDLK_RIGHT)
    push_key(pico2d.SDLK_SPACE)
    for _ in range(90):
        tick(game)
        if player.staircase is not None:
            break
    assert player.staircase is world.stage.stairs[0]
    assert player.jump_height == player.vy == player.jump_count == 0
    capture(game, "stair_jump_caught")
    tick(game, 12)
    assert player.staircase is not None
    release(game, pico2d.SDLK_RIGHT)
    release(game, pico2d.SDLK_SPACE)
    before = player.ground_y
    push_key(pico2d.SDLK_UP)
    tick(game, 12)
    assert player.ground_y > before
    release(game, pico2d.SDLK_UP)
    before = player.ground_y
    push_key(pico2d.SDLK_DOWN)
    tick(game, 6)
    assert player.ground_y < before
    release(game, pico2d.SDLK_DOWN)
    capture(game, "stair_jump_reversed")
    print("PASS: one real SDL Space + Right lands on the steps; holding the approach "
          "key does not eject the player, and Up/Down moves/reverses from that step.")


def check_exits(game):
    for floor in (0, 1):
        for key, label in ((pico2d.SDLK_SPACE, "jump"),
                           (pico2d.SDLK_LEFT, "left"), (pico2d.SDLK_RIGHT, "right")):
            world, stair, forward, _ = begin(game, floor)
            player = world.player
            feet, x = player.y, player.x
            push_key(key)
            tick(game)
            assert player.staircase is None and player not in stair.occupants
            assert abs(player.y - feet) < 12 and abs(player.x - x) < 2
            if key == pico2d.SDLK_SPACE:
                assert player.vy > 0 and player.jump_count == 1
            else:
                assert player.vy < 0 and player.y < feet
                assert player.vx * (-1 if key == pico2d.SDLK_LEFT else 1) > 0
            release(game, forward)
            if key == pico2d.SDLK_SPACE:
                push_key(pico2d.SDLK_LEFT)  # Steer clear instead of landing back on the steps.
            tick(game, 24 if key == pico2d.SDLK_SPACE else 8)
            capture(game, f"stair_exit_{floor + 1}_{label}")
            release(game, key)
            for _ in range(180):
                tick(game)
                if player.grounded and player.staircase is None:
                    break
            if key == pico2d.SDLK_SPACE:
                release(game, pico2d.SDLK_LEFT)
            assert player.grounded and player.hp == config.MAX_HP
            assert world.stage.area_for(player).contains(player.x, player.ground_y)
            assert not stair.occupants
    print("PASS: Space/Left/Right exits during ascent and descent preserve the current "
          "feet, unlock stairs immediately, allow steering and land without damage.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_jump_entry(game)
        check_exits(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
