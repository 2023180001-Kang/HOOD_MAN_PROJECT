"""Check enemy02 pavement support and walking foot alignment in actual city scenes."""

from pathlib import Path
import random
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from game import Game
from tools.check_render import capture
from tools.check_runtime import push_key, tick
from traffic import Car
from world import World


def walking_scene(game, index, side):
    game.world = World(rng=random.Random(32))
    world = game.world
    world.stage_index = index
    world.stage.traffic = None  # Inspect pavement alignment without road deaths.
    world.player.invincible = True
    for number, enemy in enumerate(world.enemies):
        enemy.x = enemy.previous_x = world.player.x + side * (220 + number * 5)
        enemy.ground_y = enemy.previous_ground_y = config.GROUND_Y
        enemy.facing = -side
    return world


def check_walking(game):
    texture = game.assets.images[config.ENEMY02_IMAGE]
    for index in (2, 3):
        for side in (-1, 1):
            world = walking_scene(game, index, side)
            tick(game, 45)
            depths = [round(enemy.ground_y, 3) for enemy in world.enemies]
            print(f"City {index - 1}, side {side}: walking feet={depths}; player={world.player.ground_y:g}")
            capture(game, f"city_walk_{index - 1}_{side}_natural")
            assert all(enemy.state == "WALK" for enemy in world.enemies)
            assert all(enemy.ground_y >= config.GROUND_Y - 1e-8 for enemy in world.enemies), depths
            for frame in range(8):
                game.handle_events()
                for enemy in world.enemies:
                    enemy.animation.elapsed = (frame + 0.1) / 10
                with patch.object(texture, "clip_composite_draw", wraps=texture.clip_composite_draw) as draw:
                    capture(game, f"city_walk_{index - 1}_{side}_frame_{frame}")
                actors = sorted(world.enemies, key=lambda actor: actor.ground_y, reverse=True)
                assert len(draw.call_args_list) == len(actors) == 4
                for call, enemy in zip(draw.call_args_list, actors):
                    args = call.args
                    rendered_feet = args[7] - args[9] / 2
                    assert abs(rendered_feet - (enemy.y - world.camera.render_y)) < 1e-7
                    assert world.stage.walkable.contains(enemy.x, enemy.ground_y, enemy.boundary_padding)
    print("PASS: four walking enemies stay on the pavement in both cities/facings; "
          "all eight walk frames use the same physical foot reference as the player.")


def check_road_pursuit(game):
    world = walking_scene(game, 2, -1)
    push_key(pico2d.SDLK_DOWN)
    tick(game, 30)
    push_key(pico2d.SDLK_DOWN, down=False)
    game.handle_events()
    assert world.player.ground_y < config.GROUND_Y
    tick(game, 90)
    victim = min(world.enemies, key=lambda enemy: enemy.ground_y)
    assert victim.ground_y <= config.CAR_GROUND_Y + config.CAR_DEPTH_TOLERANCE
    # Walking support must not create immunity to the existing road hazard.
    traffic = World().stages[2].traffic
    traffic.car = Car(victim.x, 1, 1400)
    world.stage.traffic = traffic
    tick(game)
    assert victim.hp == 0 and victim.car_hit
    capture(game, "city_walk_road_pursuit")
    print("PASS: SDL down still lures enemies onto the road, where a car can hit them.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_walking(game)
        check_road_pursuit(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
