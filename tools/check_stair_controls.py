"""Real SDL pause/resume/reversal on stairs, exclusive queuing and reset."""

import ctypes
from math import hypot
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d
from sdl2 import SDL_Event, SDL_PushEvent, SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST

import config
from enemy import Enemy
from game import Game
from tests.helpers import archived_two_floor_map
from tools.check_render import capture
from tools.check_runtime import push_key, tick
from tools.check_two_floors import floor_bounds, release
from world import World


def begin(game, floor=0):
    for key in (pico2d.SDLK_UP, pico2d.SDLK_DOWN):
        release(game, key)
    game.world = World(rng=random.Random(41), item_rng=random.Random(5))
    world = game.world
    stair = world.stage.stairs[0]
    player = world.player
    player.floor = floor
    player.x, player.ground_y = stair.entrance(floor)
    player.invincible = True
    world.stage.constrain_actor(player)
    world.camera.x = 0
    forward = pico2d.SDLK_UP if floor == 0 else pico2d.SDLK_DOWN
    backward = pico2d.SDLK_DOWN if floor == 0 else pico2d.SDLK_UP
    push_key(forward)
    tick(game, 36)
    assert player.staircase is stair and player.state == "WALK"
    floor_bounds(world)
    return world, stair, forward, backward


def check_pause_and_turn(game):
    for floor in (0, 1):
        world, stair, forward, backward = begin(game, floor)
        player = world.player
        label = "up" if floor == 0 else "down"
        capture(game, f"stair_controls_{label}_moving")
        release(game, forward)
        before = player.x, player.ground_y, stair.progress
        tick(game, 45)
        assert (player.x, player.ground_y, stair.progress) == before
        assert player.state == "IDLE" and player.staircase is stair
        capture(game, f"stair_controls_{label}_paused")
        push_key(backward)
        previous = player.x, player.ground_y
        tick(game)
        assert stair.destination_floor == floor and stair.progress < before[2]
        assert hypot(player.x - previous[0], player.ground_y - previous[1]) <= config.STAIR_SPEED / 60 + 1e-8
        assert player.facing == (-1 if floor == 0 else 1)
        tick(game, 11)
        capture(game, f"stair_controls_{label}_reversed")
        # Both keys neutralize movement; releasing one immediately resumes the other.
        push_key(forward)
        stopped = player.x, player.ground_y, stair.progress
        tick(game, 20)
        assert (player.x, player.ground_y, stair.progress) == stopped
        release(game, backward)
        tick(game, 12)
        assert stair.progress > stopped[2] and stair.destination_floor == 1 - floor
        release(game, forward)
        paused = player.x, player.ground_y, stair.progress
        tick(game, 20)
        assert (player.x, player.ground_y, stair.progress) == paused
        push_key(backward)
        for _ in range(240):
            previous = player.x, player.ground_y
            tick(game)
            assert hypot(player.x - previous[0], player.ground_y - previous[1]) <= config.STAIR_SPEED / 60 + 1e-8
            floor_bounds(world)
            if player.staircase is None:
                break
        release(game, backward)
        assert player.staircase is None and player.floor == floor
        x, y = stair.entrance(floor)
        assert abs(player.x - x) < 1 and abs(player.ground_y - y) < 1
        assert not stair.occupants and stair.destination_floor is None
        capture(game, f"stair_controls_{label}_returned")
    print("PASS: SDL Up/Down from both floors pauses on release, resumes either way, "
          "reverses in place with matching facing, neutralizes opposing keys and "
          "returns to the source landing without teleporting.")


def check_exclusive_waiting(game):
    world, stair, forward, backward = begin(game)
    lower = Enemy(238, ground_y=136)
    upper = Enemy(500, ground_y=476)
    upper.floor, upper.descent_route = 1, "STAIRS"
    world.stage.constrain_actor(upper)
    world.enemies = [lower, upper]
    release(game, forward)
    tick(game, 60)
    assert lower in stair.queue and list(stair.occupants) == [world.player]
    capture(game, "stair_controls_waiters_paused")
    push_key(backward)
    tick(game)
    assert stair.destination_floor == 0 and upper in stair.queue
    assert list(stair.occupants) == [world.player]
    for _ in range(240):
        tick(game)
        floor_bounds(world)
        if world.player.staircase is None:
            break
        assert list(stair.occupants) == [world.player]
    release(game, backward)
    for _ in range(120):
        tick(game)
        if upper.staircase is stair:
            break
    assert world.player.floor == 0 and upper.staircase is stair
    capture(game, "stair_controls_waiter_resumed")
    print("PASS: paused/turning player remains exclusive; enemies wait, route toward "
          "the new destination on the reversal tick and enter after the player exits.")


def check_focus_and_restart(game):
    world, stair, _, backward = begin(game)
    player = world.player
    before = player.x, player.ground_y, stair.progress
    event = SDL_Event()
    event.type = SDL_WINDOWEVENT
    event.window.event = SDL_WINDOWEVENT_FOCUS_LOST
    assert SDL_PushEvent(ctypes.byref(event)) == 1
    tick(game, 12)
    assert not world.controls.held
    assert (player.x, player.ground_y, stair.progress) == before
    assert player.state == "IDLE"
    push_key(backward)
    tick(game, 8)
    assert stair.progress < before[2] and stair.destination_floor == 0
    release(game, backward)
    textures = dict(game.assets.images)
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert player.staircase is None and not stair.occupants and not stair.queue
    assert stair.destination_floor is None
    assert game.world.player.floor == 0 and game.world.player.staircase is None
    assert not game.world.enemies and len(game.world.stage.drop_items) == 15
    assert all(game.assets.images[name] is image for name, image in textures.items())
    capture(game, "stair_controls_restart")
    print("PASS: SDL focus loss pauses stairs immediately; a fresh opposite key "
          "resumes backward, and F5 clears paused/reversed stair state while "
          "restoring 15 items and reusing textures.")


@archived_two_floor_map()
def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        game.ui.floor_bounds_visible = True
        check_pause_and_turn(game)
        check_exclusive_waiting(game)
        check_focus_and_restart(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
