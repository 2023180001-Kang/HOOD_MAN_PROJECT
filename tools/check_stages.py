"""Verify stage markers, travel and state continuity through actual SDL input."""

from copy import deepcopy
from pathlib import Path
import random
import sys
from time import perf_counter
from unittest.mock import patch

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from effects import HitEffect
from enemy import Enemy
from game import Game
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, tick
from world import World


def view_edge(game, side):
    game.world.player.x = (config.STAGE_ENTRY_MARGIN if side < 0 else
                           config.WORLD_WIDTH - config.STAGE_ENTRY_MARGIN)
    game.world.camera.update(0, game.world.player.x)


def check_markers(game):
    textures = dict(game.assets.images)
    backgrounds = []
    for index in range(len(config.STAGE_IMAGES)):
        game.world = World()
        game.world.stage_index = index
        baseline = {}
        for side in (-1, 1):
            view_edge(game, side)
            baseline[side] = render_image(game)
        backgrounds.append(baseline[1])
        push_key(pico2d.SDLK_n)
        tick(game)
        assert game.world.stage.arrow_sides == ((1,) if index == 0 else (-1, 1))
        for side in (-1, 1):
            view_edge(game, side)
            image = capture(game, f"stage_{index + 1}_{'left' if side < 0 else 'right'}_markers")
            top = int(config.SCREEN_HEIGHT - config.STAGE_ARROW_Y - 40)
            bottom = int(config.SCREEN_HEIGHT - config.STAGE_ARROW_Y + 40)
            region = (0, top, 190, bottom) if side < 0 else (1090, top, 1280, bottom)
            before = baseline[side].crop(region)
            after = image.crop(region)
            if index == 0 and side < 0:
                assert after.tobytes() == before.tobytes()
            else:
                gold = lambda pixels: sum(r > 120 and g > 80 and r > b * 1.5
                                          for r, g, b, _ in pixels)
                assert gold(after.get_flattened_data()) > gold(before.get_flattened_data()) + 50
        push_key(pico2d.SDLK_n, repeat=True)
        tick(game)
        assert game.world.stage.arrows_visible
        push_key(pico2d.SDLK_n, down=False)
        game.handle_events()
    assert len({image.crop((250, 200, 1000, 500)).tobytes() for image in backgrounds}) == 4
    push_key(pico2d.SDLK_F5)
    tick(game)
    assert game.world.stage_index == 0
    assert all(not stage.arrows_visible for stage in game.world.stages)
    assert all(game.assets.images[name] is image for name, image in textures.items())
    push_key(pico2d.SDLK_F5, down=False)
    game.handle_events()
    print("PASS: SDL N reveals the first stage right / remaining stages left+right arrows; "
          "four distinct backgrounds and shared textures verified.")


def check_motion_continuity(game):
    textures = dict(game.assets.images)
    for side in (-1, 1):
        for mode in ("walk", "run", "jump_up", "jump_down"):
            game.world = World()
            game.world.stage_index = 0 if side > 0 else 1
            direction_key = pico2d.SDLK_RIGHT if side > 0 else pico2d.SDLK_LEFT
            push_key(direction_key)
            if mode != "walk":
                push_key(pico2d.SDLK_LSHIFT)
            tick(game, 30)
            if mode.startswith("jump_"):
                push_key(pico2d.SDLK_SPACE)
                tick(game, 12)
                push_key(pico2d.SDLK_SPACE, down=False)
                push_key(pico2d.SDLK_SPACE)
                tick(game, 6 if mode == "jump_up" else 42)
                assert game.world.player.jump_count == 2
                assert (game.world.player.vy > 0) == (mode == "jump_up")
            player = game.world.player
            player.hp = 420
            player.x = (config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
                        if side > 0 else config.STAGE_EXIT_MARGIN)
            push_key(pico2d.SDLK_n)
            game.handle_events()
            reference = World()
            reference.player = deepcopy(player)
            reference.player.x = config.START_X
            reference.controls = deepcopy(game.world.controls)
            reference.elapsed = game.world.elapsed
            game.update(1 / 60)
            reference.update(1 / 60)
            assert game.world.stage_index == (1 if side > 0 else 0)
            assert game.world.player is player
            for attribute in ("state", "vx", "vy", "y", "jump_count", "hp", "facing"):
                assert getattr(player, attribute) == getattr(reference.player, attribute), (mode, attribute)
            assert player.animation.elapsed == reference.player.animation.elapsed
            assert game.world.controls.held == reference.controls.held
            assert game.world.elapsed == reference.elapsed
            assert not game.world.stage.arrows_visible
            assert all(game.assets.images[name] is image for name, image in textures.items())
            capture(game, f"stage_travel_{'next' if side > 0 else 'previous'}_{mode}")
            assert abs(player.x - player.previous_x) <= config.RUN_SPEED * config.FIXED_DT + 1e-6
            for key in (direction_key, pico2d.SDLK_LSHIFT, pico2d.SDLK_SPACE, pico2d.SDLK_n):
                push_key(key, down=False)
            game.handle_events()
    print("PASS: SDL next/previous travel preserves the same player, held direction/Shift/Space, "
          "walk/run speed, rising/falling double jump, HP and animation clock.")


def check_round_trip_and_last_exit(game):
    game.world = World(rng=random.Random(1))
    player = game.world.player
    push_key(pico2d.SDLK_n)
    push_key(pico2d.SDLK_1)
    push_key(pico2d.SDLK_RIGHT)
    push_key(pico2d.SDLK_LSHIFT)
    for _ in range(240):
        tick(game)
        if game.world.stage_index == 1:
            break
    assert game.world.stage_index == 1 and game.world.player is player
    assert player.state == "RUN" and player.vx == 720
    assert not game.world.stage.arrows_visible  # Holding N must not reveal this map.
    first = game.world.stages[0]
    assert len(first.enemies) == 1
    first.enemies[0].take_damage(20)
    first_positions = [enemy.x for enemy in first.enemies]
    push_key(pico2d.SDLK_RIGHT, down=False)
    push_key(pico2d.SDLK_1, down=False)
    push_key(pico2d.SDLK_2)
    push_key(pico2d.SDLK_n, down=False)
    push_key(pico2d.SDLK_n)
    push_key(pico2d.SDLK_LEFT)
    tick(game)
    for index, enemy in enumerate(game.world.enemies):
        enemy.x = config.START_X + index * 100
    for _ in range(120):
        tick(game)
        if game.world.stage_index == 0:
            break
    assert game.world.stage_index == 0 and game.world.player is player
    assert player.state == "RUN" and player.vx < 0
    assert first.enemies[0].hp == 180 and first.spawner.spawned_count == 1
    assert first.enemies[0].x == first_positions[0]
    assert len(game.world.stages[1].enemies) == 2
    assert game.world.stage.arrow_sides == (1,)
    tick(game, 5)
    assert game.world.stage_index == 0
    assert player.vx == -720
    capture(game, "stage_return_running")
    for key in (pico2d.SDLK_LEFT, pico2d.SDLK_LSHIFT, pico2d.SDLK_2, pico2d.SDLK_n):
        push_key(key, down=False)
    game.handle_events()

    game.world = World()
    game.world.stage_index = len(config.STAGE_IMAGES) - 1
    player = game.world.player
    player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
    player.vx = 720
    push_key(pico2d.SDLK_n)
    push_key(pico2d.SDLK_RIGHT)
    push_key(pico2d.SDLK_LSHIFT)
    tick(game, 30)
    assert game.world.stage_index == len(config.STAGE_IMAGES) - 1
    assert player.x == config.WORLD_WIDTH - config.PLAYER_BOUNDARY_PADDING
    capture(game, "city_stage_2_last_boundary")
    push_key(pico2d.SDLK_F5)
    tick(game)
    assert game.world.stage_index == 0 and game.world.player.hp == 500
    assert all(not stage.arrows_visible and not stage.enemies for stage in game.world.stages)
    for key in (pico2d.SDLK_F5, pico2d.SDLK_RIGHT, pico2d.SDLK_LSHIFT, pico2d.SDLK_n):
        push_key(key, down=False)
    game.handle_events()
    print("PASS: SDL full sprint round trip keeps per-map enemies/HP/spawn counts, "
          "avoids return loops, bounds the final city exit, and F5 resets all four stages.")


def check_city_loading(game):
    game.world = World()
    player = game.world.player
    textures = dict(game.assets.images)
    player.x, player.vx = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN, config.RUN_SPEED
    player.hp, player.invincible = 420, True
    for key in (pico2d.SDLK_RIGHT, pico2d.SDLK_LSHIFT, pico2d.SDLK_n):
        push_key(key)
    tick(game)
    assert game.world.stage_index == 1 and not game.world.stage_loading
    source = game.world.stage
    source.enemies.append(Enemy(1200))
    source.effects.append(HitEffect(1200, 180, 1))
    player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
    push_key(pico2d.SDLK_n, down=False)
    push_key(pico2d.SDLK_n)
    timing = {}
    frozen = []
    original_draw = game.draw

    def observe(present=True):
        original_draw(present)
        world = game.world
        if world.stage_loading:
            snapshot = (world.elapsed, player.x, player.ground_y, player.hp,
                        player.jump_height, player.animation.elapsed,
                        source.enemies[0].x, source.enemies[0].animation.elapsed,
                        source.effects[0].elapsed)
            if not frozen:
                frozen.append(snapshot)
                with patch.object(game, "draw", original_draw):
                    image = capture(game, "stage_loading_to_city")
                with Image.open(config.ROOT / config.STAGE_LOADING_IMAGE) as supplied:
                    assert ImageChops.difference(image.convert("RGB"),
                                                supplied.convert("RGB")).getbbox() is None
                timing["start"] = perf_counter()
                for key in (pico2d.SDLK_SPACE, pico2d.SDLK_a, pico2d.SDLK_9, pico2d.SDLK_p):
                    push_key(key)
                push_key(pico2d.SDLK_n, down=False)
                push_key(pico2d.SDLK_n)
            assert snapshot == frozen[0]
        elif world.stage_index == 2:
            timing.setdefault("end", perf_counter())

    with patch.object(game, "draw", side_effect=observe):
        assert game.run(max_frames=150) == 150
    duration = timing["end"] - timing["start"]
    assert 2.0 <= duration < 2.25, duration
    assert game.world.stage_index == 2 and not game.world.stage_loading
    assert game.world.player is player and player.hp == 420 and player.invincible
    assert player.jump_count == 0 and player.active_move is None
    assert not game.world.enemies and not game.world.stage.arrows_visible
    assert all(game.assets.images[name] is image for name, image in textures.items())
    capture(game, "city_stage_1_entered")
    push_key(pico2d.SDLK_1)
    tick(game)
    city_first = game.world.stage
    city_enemy = city_first.enemies[0]
    city_enemy.take_damage(40)
    push_key(pico2d.SDLK_n, down=False)
    push_key(pico2d.SDLK_n)
    player.x, player.vx = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN, config.RUN_SPEED
    tick(game)
    assert game.world.stage_index == 3 and not game.world.stage_loading
    assert game.world.player is player and player.hp == 420
    capture(game, "city_stage_2_entered")
    push_key(pico2d.SDLK_RIGHT, down=False)
    push_key(pico2d.SDLK_LEFT)
    push_key(pico2d.SDLK_n, down=False)
    push_key(pico2d.SDLK_n)
    player.x, player.vx = config.STAGE_EXIT_MARGIN, -config.RUN_SPEED
    tick(game)
    assert game.world.stage is city_first and not game.world.stage_loading
    assert city_first.enemies[0] is city_enemy and city_enemy.hp == 160
    player.x, player.vx = config.STAGE_EXIT_MARGIN, -config.RUN_SPEED
    tick(game)
    assert game.world.stage_loading and game.world.pending_stage_index == 1
    capture(game, "stage_loading_return_from_city")
    game.update(config.STAGE_LOADING_DURATION)
    assert game.world.stage is source and game.world.player is player
    assert player.x == config.WORLD_WIDTH - config.STAGE_ENTRY_MARGIN
    player.x, player.vx = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN, config.RUN_SPEED
    assert game.world.try_stage_transition()
    push_key(pico2d.SDLK_F5)
    tick(game)
    assert not game.world.stage_loading and game.world.stage_loading_remaining == 0
    assert game.world.stage_index == 0 and game.world.player.hp == 500
    assert all(not stage.enemies and not stage.arrows_visible for stage in game.world.stages)
    for key in (pico2d.SDLK_F5, pico2d.SDLK_LEFT, pico2d.SDLK_LSHIFT, pico2d.SDLK_n,
                pico2d.SDLK_SPACE, pico2d.SDLK_a, pico2d.SDLK_9, pico2d.SDLK_p, pico2d.SDLK_1):
        push_key(key, down=False)
    game.handle_events()
    print(f"PASS: supplied loading image stays visible for {duration:.3f}s with gameplay frozen; "
          "newStage -> newStage-2 -> cityStage-1 -> cityStage-2, ignored loading actions, "
          "HP/motion/resource reuse, city return and F5 cancellation verified.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_markers(game)
        check_motion_continuity(game)
        check_round_trip_and_last_exit(game)
        check_city_loading(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
