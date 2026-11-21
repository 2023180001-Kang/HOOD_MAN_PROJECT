"""Exercise open-door spawning and single-file stairs through real SDL input."""

from pathlib import Path
from math import hypot
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from enemy import Enemy
from game import Game
from tests.helpers import archived_two_floor_map
from tools.check_render import capture
from tools.check_runtime import push_key, tick
from world import World


def release(game, key):
    push_key(key, down=False)
    game.handle_events()


def floor_bounds(world):
    for actor in [world.player, *world.enemies]:
        if actor.staircase is not None:
            assert actor in actor.staircase.occupants
        else:
            assert world.stage.area_for(actor).contains(actor.x, actor.ground_y,
                                                        actor.boundary_padding)
    for stair in world.stage.stairs:
        progress = list(stair.occupants.values())
        assert all(a - b >= config.STAIR_FOLLOW_DISTANCE - 1e-8
                   for a, b in zip(progress, progress[1:]))
        assert all(actor is world.player or actor.floor == 1 - stair.destination_floor
                   for actor in stair.occupants)
        if world.player in stair.occupants:
            assert len(stair.occupants) == 1


def check_spawns(game):
    game.world = World(rng=random.Random(41))
    push_key(pico2d.SDLK_F3)
    push_key(pico2d.SDLK_p)
    push_key(pico2d.SDLK_F4)
    tick(game, 50)
    for key in (pico2d.SDLK_F3, pico2d.SDLK_p, pico2d.SDLK_F4):
        release(game, key)
    assert all(door.state == "OPEN" for door in game.world.stage.doors)
    assert not game.world.enemies
    push_key(pico2d.SDLK_9)
    push_key(pico2d.SDLK_KP_8)
    tick(game)
    assert len(game.world.enemies) == 17
    assert any(enemy.floor == 1 for enemy in game.world.enemies)
    assert any(enemy.spawn_source[0] == "door" for enemy in game.world.enemies)
    assert any(enemy.spawn_source[0] == "edge" for enemy in game.world.enemies)
    floor_bounds(game.world)
    for camera_x in (0, 1280):
        game.world.camera.x = camera_x
        capture(game, f"two_floors_door_spawn_{camera_x}")
    push_key(pico2d.SDLK_9, repeat=True)
    tick(game)
    assert len(game.world.enemies) == 17
    release(game, pico2d.SDLK_9)
    release(game, pico2d.SDLK_KP_8)
    push_key(pico2d.SDLK_KP_9)
    tick(game)
    release(game, pico2d.SDLK_KP_9)
    assert len(game.world.enemies) == 26
    push_key(pico2d.SDLK_F3)
    tick(game)
    release(game, pico2d.SDLK_F3)
    assert not game.world.stage.open_door_spawns()
    print("PASS: real F3 + number/keypad inputs spawn exact batches at edges/open doors "
          "on both floors; mirrored doors, key-repeat suppression and immediate closing exclusion.")


def check_player(game):
    game.world = World()
    player = game.world.player
    player.x, player.ground_y = 238, 110
    push_key(pico2d.SDLK_UP)
    tick(game)
    assert player.staircase is not None
    tick(game, 55)
    floor_bounds(game.world)
    capture(game, "two_floors_player_climbing")
    for _ in range(180):
        tick(game)
        if player.staircase is None:
            break
    release(game, pico2d.SDLK_UP)
    assert player.floor == 1 and player.staircase is None
    assert abs(player.ground_y - 476) < 1
    capture(game, "two_floors_player_upstairs")
    push_key(pico2d.SDLK_RIGHT)
    tick(game, 50)
    release(game, pico2d.SDLK_RIGHT)
    tick(game, 15)
    assert player.x > 700 and player.floor == 1
    for key, expected_y in ((pico2d.SDLK_UP, 502), (pico2d.SDLK_DOWN, 478)):
        push_key(key)
        tick(game, 30 if key == pico2d.SDLK_UP else 8)
        release(game, key)
        assert abs(player.ground_y - expected_y) < 5
        assert player.floor == 1
        floor_bounds(game.world)
    push_key(pico2d.SDLK_SPACE)
    tick(game, 6)
    release(game, pico2d.SDLK_SPACE)
    assert player.jump_height > 0 and player.floor == 1
    capture(game, "two_floors_upstairs_jump")
    tick(game, 100)
    player.x, player.ground_y = 500, 476
    player.vx = player.ground_vy = 0
    push_key(pico2d.SDLK_DOWN)
    tick(game)
    assert player.staircase is not None
    tick(game, 55)
    capture(game, "two_floors_player_descending")
    for _ in range(180):
        tick(game)
        if player.staircase is None:
            break
    release(game, pico2d.SDLK_DOWN)
    floor_bounds(game.world)
    assert player.floor == 0 and abs(player.ground_y - 136) < 1
    print("PASS: SDL Up/Down follows the visible stairs in both directions; upstairs "
          "left/right/up/down and jumping stay on the independent upper walkway.")


def check_enemy_queue_and_reset(game):
    game.world = World()
    game.world.player.x, game.world.player.ground_y = 238, 136
    push_key(pico2d.SDLK_UP)
    push_key(pico2d.SDLK_p)
    tick(game)
    release(game, pico2d.SDLK_p)
    enemies = [Enemy(238 + 100 * index, ground_y=112) for index in range(5)]
    game.world.enemies = enemies
    saw_queue = False
    entered = []
    maximum = 0
    captured_column = False
    for frame in range(1200):
        tick(game)
        floor_bounds(game.world)
        if game.world.player.floor == 1 and game.world.player.staircase is None:
            if "up" in game.world.controls.held:
                release(game, pico2d.SDLK_UP)
            game.world.player.x = max(game.world.player.x, 1000)
        stair = game.world.stage.stairs[0]
        if len(stair.queue) >= 2:
            saw_queue = True
        for actor in stair.occupants:
            if actor in enemies and actor not in entered:
                entered.append(actor)
        maximum = max(maximum, len(stair.occupants))
        if len(stair.occupants) >= 3 and not captured_column:
            camera_x = game.world.camera.x
            game.world.camera.x = 0
            capture(game, "two_floors_enemy_column")
            game.world.camera.x = camera_x
            captured_column = True
        if frame == 80:
            capture(game, "two_floors_enemy_queue")
        if len(entered) == 5 and all(enemy.floor == 1 for enemy in enemies):
            break
    assert saw_queue and len(entered) == 5 and maximum >= 3
    assert all(enemy.floor == 1 and enemy.staircase is None for enemy in enemies)
    tick(game, 180)
    capture(game, "two_floors_upstairs_combat")
    assert any(enemy.state == "ATTACK" for enemy in enemies)
    textures = dict(game.assets.images)
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert game.world.player.floor == 0
    assert not game.world.enemies and len(game.world.stage.drop_items) == 15
    assert all(door.state == "CLOSED" for door in game.world.stage.doors)
    assert not game.world.stage.stairs[0].queue
    assert game.world.stage.stairs[0].occupant is None
    assert game.ui.floor_bounds_visible
    assert all(game.assets.images[name] is image for name, image in textures.items())
    capture(game, "two_floors_restart")
    print("PASS: the player travels alone; 5 enemies follow upstairs with 100px gaps, "
          "at least 3 use the stairs together, and resume combat. F5 restores floor 1/closed doors/15 items "
          "without reloading textures; P and F4 remain independent.")


def check_descending_approach(game):
    for speed in config.ENEMY_RUN_SPEEDS:
        game.world = World()
        world = game.world
        world.player.x, world.camera.x = 640, 0
        enemy = Enemy(1000, ground_y=495, run_speed=speed)
        enemy.floor = 1
        world.stage.constrain_actor(enemy)
        world.enemies = [enemy]
        stair = world.stage.stairs[0]
        start_distance = stair.distance_to_entry(enemy)
        entry_time = None
        for frame in range(300):
            tick(game)
            floor_bounds(world)
            if enemy.staircase is not None:
                if entry_time is None:
                    entry_time = world.elapsed
                    if speed == config.ENEMY_RUN_SPEEDS[0]:
                        capture(game, "stairs_descending_entry")
            elif enemy.floor == 1:
                assert abs(hypot(enemy.vx, enemy.ground_vy) - speed) < 1e-6
                assert enemy.running and enemy.state == "RUN"
                if frame == 36 and speed == config.ENEMY_RUN_SPEEDS[0]:
                    capture(game, "stairs_descending_approach")
            else:
                break
        assert entry_time is not None
        assert entry_time <= (start_distance - config.STAIR_ENTRY_RADIUS) / speed + 3 / 60
        assert enemy.floor == 0 and enemy.staircase is None
    print("PASS: descending enemies retain their 360/420/480/540px/s RUN approach all the "
          "way to stair entry, without the old 360px walking slowdown or idle-pose slide.")


def check_descending_column(game):
    game.world = World()
    world = game.world
    world.player.x, world.camera.x = 640, 0
    world.player.invincible = True
    enemies = [Enemy(500 + 100 * index, ground_y=476,
                     run_speed=config.ENEMY_RUN_SPEEDS[index % 4]) for index in range(6)]
    for enemy in enemies:
        enemy.floor = 1
        enemy.descent_route = "STAIRS"  # This fixture specifically validates the stair column.
        world.stage.constrain_actor(enemy)
    world.enemies = enemies
    maximum, captured = 0, False
    for _ in range(600):
        tick(game)
        floor_bounds(world)
        stair = world.stage.stairs[0]
        maximum = max(maximum, len(stair.occupants))
        if len(stair.occupants) >= 3 and not captured:
            capture(game, "two_floors_enemy_column_down")
            captured = True
        if all(enemy.floor == 0 and enemy.staircase is None for enemy in enemies):
            break
    assert maximum >= 3
    assert all(enemy.floor == 0 and enemy.staircase is None for enemy in enemies)
    assert not stair.occupants and stair.destination_floor is None
    print("PASS: 6 enemies descend in a spaced, single-direction column with at least "
          "3 simultaneous travellers; each keeps separate progress and lands on floor 1.")


@archived_two_floor_map()
def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        game.ui.details_visible = False
        check_spawns(game)
        check_player(game)
        check_descending_approach(game)
        check_descending_column(game)
        check_enemy_queue_and_reset(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
