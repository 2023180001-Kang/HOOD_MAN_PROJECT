"""Actual SDL hits on stairs, knock-off reactions and mixed enemy descent routes."""

from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from enemy import Enemy
from game import Game
from tools.check_render import capture
from tools.check_runtime import push_key, tick
from world import World


def release(game, key):
    push_key(key, down=False)
    game.handle_events()


def check_stair_hits(game):
    game.world = World(rng=random.Random(41))
    world = game.world
    stair = world.stage.stairs[0]
    enemy = Enemy(238, ground_y=136)
    world.enemies = [enemy]
    stair.request(enemy)
    stair.start_next()
    stair.occupants[enemy] = stair.length - 90
    stair.update(0)
    player = world.player
    player.floor = 1
    player.x, player.ground_y = enemy.x - 65, 452
    world.stage.constrain_actor(player)
    world.camera.x = 0
    push_key(pico2d.SDLK_s)
    for _ in range(60):
        tick(game)
        if enemy.hp < 200:
            break
    release(game, pico2d.SDLK_s)
    assert enemy.hp == 160 and enemy.state == "HIT"
    assert enemy.staircase is stair
    assert world.damage_numbers[-1].damage == 40 and world.effects
    capture(game, "stair_combat_normal_hit")
    progress = stair.occupants[enemy]
    tick(game, 10)
    assert enemy.hp == 160 and stair.occupants[enemy] == progress
    push_key(pico2d.SDLK_q)
    for _ in range(60):
        tick(game)
        if enemy.hp < 160:
            break
    release(game, pico2d.SDLK_q)
    assert enemy.hp == 110 and enemy.state == "STRONG_HIT"
    assert enemy.falling_from_upper and enemy.staircase is None
    assert enemy not in stair.occupants
    capture(game, "stair_combat_strong_knockoff")
    tick(game, 12)
    assert enemy.vy < 0 and enemy.jump_height > 0
    capture(game, "stair_combat_hit_fall")
    tick(game, 80)
    assert not enemy.falling_from_upper and enemy.jump_height == 0
    print("PASS: real SDL S deals 40 to an ascending enemy in visible reach, shows "
          "damage/effects and pauses its stair progress; Q deals 50, releases its "
          "stair slot and applies the strong-hit reaction while falling without a teleport.")


def mixed_world(game):
    game.world = World(rng=random.Random(41))
    world = game.world
    world.player.x, world.camera.x = 640, 0
    enemies = [Enemy(650 + 80 * index, ground_y=476) for index in range(8)]
    for enemy in enemies:
        enemy.floor = 1
        world.stage.constrain_actor(enemy)
    world.enemies = enemies
    push_key(pico2d.SDLK_p)
    tick(game)
    release(game, pico2d.SDLK_p)
    return world, enemies


def check_random_descent(game):
    world, enemies = mixed_world(game)
    dropped = {enemy for enemy in enemies if enemy.descent_route == "DROP"}
    stairs = set(enemies) - dropped
    assert 0 < len(dropped) < len(enemies)
    captured = False
    for _ in range(600):
        tick(game)
        assert all(enemy.staircase is None for enemy in dropped)
        if (not captured and any(enemy.falling_from_upper and enemy.vy < 0 for enemy in dropped)
                and world.stage.stairs[0].occupants):
            capture(game, "enemy_mixed_stairs_and_drops")
            captured = True
        if all(enemy.floor == 0 and not enemy.falling_from_upper and enemy.staircase is None
               for enemy in enemies):
            break
    assert captured
    assert all(enemy.floor == 0 and not enemy.falling_from_upper and enemy.staircase is None
               for enemy in enemies)
    assert all(enemy.hp == 200 for enemy in enemies)
    assert all(enemy in world.enemies for enemy in stairs)
    tick(game, 120)
    assert any(enemy.state == "ATTACK" for enemy in enemies)
    capture(game, "enemy_mixed_descent_ground_pursuit")
    print(f"PASS: 8 upper-floor enemies split into {len(dropped)} direct drops and "
          f"{len(stairs)} stair users, keep their chosen routes, land without damage "
          "and resume ground pursuit/attacks.")


def check_restart(game):
    world, enemies = mixed_world(game)
    for _ in range(120):
        tick(game)
        if any(enemy.falling_from_upper for enemy in enemies):
            break
    assert any(enemy.falling_from_upper for enemy in enemies)
    textures = dict(game.assets.images)
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert not game.world.enemies and not game.world.stage.stairs[0].occupants
    assert len(game.world.stage.drop_items) == 15
    assert all(door.state == "CLOSED" for door in game.world.stage.doors)
    assert all(game.assets.images[name] is image for name, image in textures.items())
    capture(game, "stair_combat_drops_restart")
    print("PASS: SDL F5 during mixed-route descent clears enemies, falls and stair "
          "occupants while restoring 15 items/closed doors and reusing all textures.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        game.ui.floor_bounds_visible = True
        game.ui.details_visible = False
        check_stair_hits(game)
        check_random_descent(game)
        check_restart(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
