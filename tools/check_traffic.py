"""Verify retired city traffic stays absent; legacy fixtures are opt-in helpers."""

from pathlib import Path
import random
import sys
from time import perf_counter
from unittest.mock import patch

from PIL import ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from enemy import Enemy
from game import Game
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, tick
from traffic import Car, Traffic
from world import World


def city(game, *, ground_y=148):
    """Manually construct a legacy vehicle scene; normal gameplay never does this."""
    game.world = World(rng=random.Random(5), traffic_rng=random.Random(5))
    game.world.stage_index = 2
    game.world.stage.traffic = Traffic(rng=random.Random(5))
    if config.CAR_IMAGE not in game.assets.images:
        game.assets.images[config.CAR_IMAGE] = pico2d.load_image(str(config.ROOT / config.CAR_IMAGE))
    game.world.player.ground_y = ground_y
    game.world.stage.traffic.spawn_remaining = 100
    return game.world


def car_at(world, x, direction=1, speed=None):
    if speed is None:
        speed = sum(config.CAR_SPEED_RANGE) / 2
    car = Car(x, direction, speed)
    world.stage.traffic.car = car
    return car


def release(game, *keys):
    for key in keys:
        push_key(key, down=False)
    game.handle_events()


def energy(first, second):
    difference = ImageChops.difference(first.convert("RGB"), second.convert("RGB"))
    return sum(sum(pixel) for pixel in difference.get_flattened_data())


def check_driving_frames(game):
    for direction in (-1, 1):
        world = city(game)
        car = car_at(world, world.player.x + 280, direction)
        world.stage.traffic.car = None
        background = render_image(game)
        world.stage.traffic.car = car
        image = game.assets.images[config.CAR_IMAGE]
        assert (image.w, image.h) == (2048, 512)
        for frame in range(8):
            car.animation.elapsed = (frame + 0.1) / config.CAR_FPS
            with patch.object(image, "clip_composite_draw", wraps=image.clip_composite_draw) as draw:
                rendered = capture(game, f"traffic_drive_{direction}_{frame}")
            args = draw.call_args.args
            assert args[:4] == (frame % 4 * 512, 256 - frame // 4 * 256, 512, 256)
            assert args[5] == ("h" if direction < 0 else "")
            assert energy(rendered, background) > 100000
            assert args[7] - (config.CAR_GROUND_ANCHOR - 128) * config.CAR_SCALE == config.CAR_GROUND_Y
    world = city(game)
    world.stage.traffic.spawn_remaining = config.CAR_INITIAL_DELAY
    directions = set()
    for _ in range(60 * 45):
        tick(game)
        car = world.stage.traffic.car
        if car is not None:
            directions.add(car.facing)
    assert directions == {-1, 1} and world.player.hp == 500
    print("PASS: all eight 4x2 vehicle frames, both horizontal flips, wheel/road anchor, "
          "and seeded natural traffic in both directions; sidewalk remains safe.")


def check_sidewalk_spawns(game):
    for side in (-1, 1):
        world = city(game, ground_y=124)
        world.player.x = 300 if side < 0 else config.WORLD_WIDTH - 300
        edge = (config.ENEMY_BOUNDARY_PADDING if side < 0 else
                config.WORLD_WIDTH - config.ENEMY_BOUNDARY_PADDING)
        car = car_at(world, edge, -side, speed=config.CAR_SPEED_RANGE[1])
        push_key(pico2d.SDLK_4)
        tick(game)
        release(game, pico2d.SDLK_4)
        assert len(world.enemies) == 4
        assert all(enemy.hp == config.ENEMY_MAX_HP and not enemy.car_hit for enemy in world.enemies)
        assert all(enemy.ground_y - car.ground_y > config.CAR_DEPTH_TOLERANCE
                   for enemy in world.enemies)
        assert any(abs(enemy.x - car.x) < config.CAR_HALF_WIDTH for enemy in world.enemies)
        capture(game, "traffic_sidewalk_spawn_left" if side < 0 else "traffic_sidewalk_spawn_right")
    print("PASS: SDL 4 summons four enemies on the city sidewalk and they survive cars already "
          "passing through either spawn edge.")


def check_impacts_and_fade(game):
    for direction in (-1, 1):
        world = city(game, ground_y=config.CAR_GROUND_Y)
        enemy = Enemy(world.player.x + direction * 100, -direction, ground_y=config.CAR_GROUND_Y)
        world.enemies.append(enemy)
        car_at(world, world.player.x, direction)
        push_key(pico2d.SDLK_p)
        tick(game)
        release(game, pico2d.SDLK_p)
        assert world.player.hp == enemy.hp == 0
        assert world.player.state == enemy.state == "CAR_HIT"
        assert not world.player.invincible and world.death_handled
        seen = [set(), set()]
        captured = set()
        while world.player.state != "DEAD" or enemy.state != "DEAD":
            for actor, frames in zip((world.player, enemy), seen):
                frames.add(actor.animation.frame)
            if world.player.animation.frame in (0, 3, 5, 7):
                frame = world.player.animation.frame
                if frame not in captured:
                    capture(game, f"traffic_hit_{direction}_{frame}")
                    captured.add(frame)
            tick(game)
        assert seen == [set(range(8)), set(range(8))]
        with patch.object(game.assets, "draw_sprite", wraps=game.assets.draw_sprite) as draw:
            capture(game, f"traffic_dead_{direction}")
        assert {call.args[0] for call in draw.call_args_list} == {
            config.PLAYER_CAR_HIT_IMAGE, config.ENEMY_CAR_HIT_IMAGE}
        assert all(call.args[1:3] == (1, 7) for call in draw.call_args_list)
        world.stage.traffic.car = None
        world.stage.traffic.spawn_remaining = 100
        world.effects.clear()
        world.damage_numbers.clear()
        world.camera.update(1, world.player.x)
        enemy.x = world.player.x + 260
        world.enemies.clear()
        background = render_image(game)
        world.enemies.append(enemy)
        values = []
        for elapsed, label in ((3, "hold"), (3.5, "half"), (4, "gone")):
            enemy.corpse_elapsed = elapsed
            values.append(energy(capture(game, f"traffic_corpse_{direction}_{label}"), background))
        assert values[0] > 0 and 0.35 < values[1] / values[0] < 0.65 and values[2] == 0
        tick(game)
        assert enemy not in world.enemies
    print("PASS: both-direction player/enemy instant HP zero (including SDL P mode), "
          "eight fatal frames, matching last poses, 3s hold/1s fade and removal pixels.")


def check_road_input_jump_and_restart(game):
    world = city(game, ground_y=100)
    car_at(world, world.player.x, speed=1)
    tick(game)
    assert world.player.hp == 500
    push_key(pico2d.SDLK_DOWN)
    for _ in range(30):
        tick(game)
        if not world.player.alive:
            break
    assert world.player.state == "CAR_HIT"
    capture(game, "traffic_step_into_road")
    release(game, pico2d.SDLK_DOWN)
    textures = dict(game.assets.images)
    push_key(pico2d.SDLK_F5)
    tick(game)
    assert world is game.world and world.stage_index == 0
    assert world.player.hp == 500 and world.player.sprite_image == config.PLAYER_IMAGE
    assert world.stages[2].traffic is None
    assert all(game.assets.images[name] is image for name, image in textures.items())
    release(game, pico2d.SDLK_F5)
    world = city(game, ground_y=config.CAR_GROUND_Y)
    car_at(world, world.player.x - 450, speed=config.CAR_SPEED_RANGE[1])
    push_key(pico2d.SDLK_SPACE)
    tick(game, 6)
    release(game, pico2d.SDLK_SPACE)
    push_key(pico2d.SDLK_SPACE)
    tick(game, 20)
    assert world.player.hp == 500 and world.player.jump_height > config.CAR_HEIGHT
    capture(game, "traffic_double_jump_clearance")
    tick(game, 50)
    assert world.player.hp == 500
    release(game, pico2d.SDLK_SPACE)
    print("PASS: real SDL down enters the fatal road lane, F5 resets traffic/death and reuses "
          "textures, double jump clears a passing car.")


def benchmark(game):
    world = city(game)
    world.player.invincible = True
    world.enemies = [Enemy(world.player.x + offset, ground_y=148) for offset in (-200, -100, 100)]
    world.enemies.append(Enemy(world.player.x + 80, ground_y=config.CAR_GROUND_Y))
    car_at(world, world.player.x - 450)
    start = perf_counter()
    frames = game.run(max_frames=180)
    seconds = perf_counter() - start
    assert frames == 180 and world.player.hp == 500
    capture(game, "traffic_benchmark")
    print(f"BENCHMARK: city traffic + 4 enemies + vehicle death/effects/UI: "
          f"{frames} frames / {seconds:.3f}s = {frames / seconds:.2f} FPS.")


def check_removed_traffic(game):
    game.world = World(rng=random.Random(5), item_rng=random.Random(5))
    world = game.world
    assert all(stage.traffic is None for stage in world.stages)
    assert config.CAR_IMAGE not in game.assets.images
    archived = config.ROOT / config.CAR_IMAGE
    assert archived.parent == config.ROOT / "before_sheets" and archived.is_file()
    assert not (config.ROOT / archived.name).exists()
    textures = dict(game.assets.images)

    world.select_stage(2)
    world.player.ground_y = config.CAR_GROUND_Y
    tick(game, 30 * 60)
    assert world.player.hp == 500 and not world.player.car_hit
    assert world.stage.traffic is None and not world.effects
    for side in (-1, 1):
        world.player.x = 100 if side < 0 else config.WORLD_WIDTH - 100
        world.camera.update(0, world.player.x)
        with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as font:
            capture(game, f"city_no_traffic_{'left' if side < 0 else 'right'}")
        assert not any("도로 주의!" in call.args[2] for call in font.call_args_list)

    push_key(pico2d.SDLK_p)
    push_key(pico2d.SDLK_4)
    tick(game)
    release(game, pico2d.SDLK_p, pico2d.SDLK_4)
    tick(game, 8 * 60)
    assert world.player.hp == 500 and world.player.invincible
    assert len(world.enemies) == 4
    assert all(enemy.hp == 200 and not enemy.car_hit for enemy in world.enemies)
    assert len(world.stage.drop_items) == 15 and world.stage.traffic is None
    capture(game, "city_no_traffic_enemies")

    world.select_stage(3)
    tick(game, 30)
    world.select_stage(2)
    assert world.stage.traffic is None
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert world.stage_index == 0 and world.player.hp == 500
    assert all(stage.traffic is None for stage in world.stages)
    assert all(game.assets.images[name] is image for name, image in textures.items())
    world.select_stage(2)
    world.player.ground_y = config.CAR_GROUND_Y
    tick(game, 5 * 60)
    assert world.player.hp == 500 and world.stage.traffic is None
    capture(game, "city_no_traffic_after_restart")
    print("PASS: archived car sheet is absent from runtime textures; city road stays safe "
          "for 30s, both views omit vehicles/warnings, four enemies and 15 drops remain, "
          "P still works, and revisits/F5 never restore traffic.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_removed_traffic(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
