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
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, release, tick
from ui import PLAYER_BOUNDS_COLOR
from world import World


def walking_scene(game, index, side):
    game.world = World(rng=random.Random(32))
    world = game.world
    world.stage_index = index
    world.stage.traffic = None  # Inspect pavement alignment without road deaths.
    world.player.invincible = True
    world.player.ground_y = world.player.previous_ground_y = world.stage.spawn_area.bounds[1]
    world.enemies.extend(world.spawner.spawn(4, world.elapsed))
    for number, enemy in enumerate(world.enemies):
        enemy.x = enemy.previous_x = world.player.x + side * (220 + number * 5)
        enemy.ground_y = enemy.previous_ground_y = world.stage.spawn_area.bounds[1]
        enemy.facing = -side
    return world


def check_full_city_floors(game):
    assert config.STAGE_IMAGES[2:4] == config.CITY_STAGE_IMAGES
    assert all(name in game.assets.images for name in config.CITY_STAGE_IMAGES)
    assert all(name not in game.assets.images and Path(name).name not in game.assets.images
               for name in config.ARCHIVED_CITY_STAGE_IMAGES)
    visible, details = game.ui.floor_bounds_visible, game.ui.details_visible
    game.ui.floor_bounds_visible, game.ui.details_visible = False, False
    try:
        push_key(pico2d.SDLK_F4)
        tick(game)
        release(game, pico2d.SDLK_F4)
        assert game.ui.floor_bounds_visible
        for index, top, source_top in ((2, 247, 650), (3, 279, 618)):
            for weapon in (None, *config.WEAPON_POSE_IMAGES):
                for running in (False, True):
                    for side in (-1, 1):
                        for depth in (-1, 1):
                            game.world = World(item_rng=random.Random(23))
                            world = game.world
                            world.select_stage(index)
                            player = world.player
                            assert world.stage.walkable.bounds == (0, -44, 2560, top)
                            assert not world.stage.stairs and world.stage.upper_walkable is None
                            player.equip_weapon(weapon)
                            player.x = player.previous_x = 300 if side < 0 else 2260
                            keys = (pico2d.SDLK_LEFT if side < 0 else pico2d.SDLK_RIGHT,
                                    pico2d.SDLK_DOWN if depth < 0 else pico2d.SDLK_UP)
                            if running:
                                keys += (pico2d.SDLK_LSHIFT,)
                            for key in keys:
                                push_key(key)
                            for _ in range(90):
                                tick(game)
                                assert world.stage.walkable.contains(player.x, player.ground_y, 68)
                            for key in keys:
                                release(game, key)
                            assert (player.x, player.ground_y, player.floor, player.jump_height) == (
                                68 if side < 0 else 2492, -44 if depth < 0 else top, 0, 0)
                            assert player.y - world.camera.render_y >= 0
                            with patch.object(pico2d, "draw_line", wraps=pico2d.draw_line) as draw:
                                if weapon is None:
                                    capture(game, f"city_ground_300_{index - 1}_{'run' if running else 'walk'}_{side}_{depth}")
                                else:
                                    render_image(game)
                            endpoints = {point for call in draw.call_args_list
                                         if call.args[4:] == PLAYER_BOUNDS_COLOR
                                         for point in (call.args[:2], call.args[2:4])}
                            assert (player.x - world.camera.render_x,
                                    player.ground_y - world.camera.render_y) in endpoints
                            assert 897 - player.ground_y == (941 if depth < 0 else source_top)
            for depth in (-44, top):
                game.world = World(item_rng=random.Random(23))
                world = game.world
                world.select_stage(index)
                player = world.player
                player.x = player.previous_x = 68
                player.ground_y = player.previous_ground_y = depth
                push_key(pico2d.SDLK_RIGHT)
                push_key(pico2d.SDLK_LSHIFT)
                for frame in range(240):
                    tick(game)
                    assert player.ground_y == depth and player.grounded
                    if frame == 120:
                        capture(game, f"city_ground_300_{index - 1}_traverse_{depth}")
                release(game, pico2d.SDLK_RIGHT)
                release(game, pico2d.SDLK_LSHIFT)
                assert player.x == 2492
                for _ in range(2):
                    push_key(pico2d.SDLK_SPACE)
                    tick(game, 3)
                    release(game, pico2d.SDLK_SPACE)
                assert player.jump_count == 2
                tick(game, 120)
                assert player.grounded and (player.ground_y, player.floor) == (depth, 0)
                assert world.stage.traffic is None
                capture(game, f"city_ground_300_{index - 1}_landed_{depth}")
        push_key(pico2d.SDLK_F5)
        tick(game)
        release(game, pico2d.SDLK_F5)
        assert world.stage_index == 0 and game.ui.floor_bounds_visible
        for index, top in ((2, 247), (3, 279)):
            world.select_stage(index)
            assert world.stage.image_name == config.CITY_STAGE_IMAGES[index - 2]
            assert world.stage.walkable.bounds == (0, -44, 2560, top)
            assert not world.enemies and len(world.stage.drop_items) == 15
            assert world.stage.traffic is None
            capture(game, f"city_ground_300_{index - 1}_restarted")
    finally:
        game.ui.floor_bounds_visible, game.ui.details_visible = visible, details
    print("PASS: both new city backgrounds are in route order and old art is not loaded; "
          "48 loadout/walk/run/corner cases match F4, both sidewalk/road depth edges "
          "are traversable across original/mirrored tiles, double jumps land there, "
          "and F5 keeps the full floors without traffic or ghost platforms.")


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
            assert all(enemy.ground_y >= world.stage.spawn_area.bounds[1] - 1e-8
                       for enemy in world.enemies), depths
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
    for index in (2, 3):
        world = walking_scene(game, index, -1)
        push_key(pico2d.SDLK_DOWN)
        tick(game, 30)
        release(game, pico2d.SDLK_DOWN)
        assert world.player.ground_y < config.GROUND_Y
        tick(game, 90)
        victim = min(world.enemies, key=lambda enemy: enemy.ground_y)
        assert victim.ground_y <= config.CAR_GROUND_Y + config.CAR_DEPTH_TOLERANCE
        tick(game)
        assert world.stage.traffic is None and victim.hp == 200 and not victim.car_hit
        capture(game, f"city_walk_{index - 1}_road_pursuit")
    print("PASS: SDL down lures enemies onto both city roads without restoring retired vehicles.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_full_city_floors(game)
        check_walking(game)
        check_road_pursuit(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
