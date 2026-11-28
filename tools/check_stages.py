"""Verify stage markers, travel and state continuity through actual SDL input."""

from copy import deepcopy
from pathlib import Path
import random
import sys
from time import perf_counter
from unittest.mock import patch

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from effects import DamageNumber, HitEffect
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
        exits = [side for side in (-1, 1) if 0 <= index + side < len(config.STAGE_IMAGES)]
        if game.world.stage.factory_gate is not None:
            exits.remove(1)
        assert game.world.stage.arrow_sides == tuple(exits)
        for side in (-1, 1):
            view_edge(game, side)
            image = capture(game, f"stage_{index + 1}_{'left' if side < 0 else 'right'}_markers")
            top = int(config.SCREEN_HEIGHT - config.STAGE_ARROW_Y - 40)
            bottom = int(config.SCREEN_HEIGHT - config.STAGE_ARROW_Y + 40)
            region = (0, top, 190, bottom) if side < 0 else (1090, top, 1280, bottom)
            before = baseline[side].crop(region)
            after = image.crop(region)
            if side not in exits:
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
    assert len({image.crop((250, 200, 1000, 500)).tobytes() for image in backgrounds}) == len(config.STAGE_IMAGES)
    push_key(pico2d.SDLK_F5)
    tick(game)
    assert game.world.stage_index == 0
    assert all(not stage.arrows_visible for stage in game.world.stages)
    assert all(game.assets.images[name] is image for name, image in textures.items())
    push_key(pico2d.SDLK_F5, down=False)
    game.handle_events()
    print("PASS: SDL N reveals the available exits; "
          f"{len(config.STAGE_IMAGES)} distinct backgrounds and shared textures verified.")


def check_motion_continuity(game, first=0):
    textures = dict(game.assets.images)
    for side in (-1, 1):
        for mode in ("walk", "run", "jump_up", "jump_down"):
            game.world = World()
            game.world.stage_index = first if side > 0 else first + 1
            if game.world.stage.factory_gate is not None:
                continue  # Doorway travel is exercised by check_factory_exterior.
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
            assert game.world.stage_index == (first + 1 if side > 0 else first)
            assert game.world.player is player
            for attribute in ("state", "vx", "vy", "y", "jump_count", "hp", "facing"):
                assert getattr(player, attribute) == getattr(reference.player, attribute), (mode, attribute)
            assert player.animation.elapsed == reference.player.animation.elapsed
            assert game.world.controls.held == reference.controls.held
            assert game.world.elapsed == reference.elapsed
            assert not game.world.stage.arrows_visible
            assert all(game.assets.images[name] is image for name, image in textures.items())
            prefix = {2: "city_travel", 4: "factory_travel", 6: "factory_inside_travel",
                      8: "lab_travel", 10: "boss_travel"}.get(first, "stage_travel")
            capture(game, f"{prefix}_{'next' if side > 0 else 'previous'}_{mode}")
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
    game.world.enemies.extend(game.world.spawner.spawn(1, game.world.elapsed))
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
    game.world.enemies.extend(game.world.spawner.spawn(2, game.world.elapsed))
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
    for key in (pico2d.SDLK_LEFT, pico2d.SDLK_LSHIFT, pico2d.SDLK_n):
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
    capture(game, "boss_last_boundary")
    push_key(pico2d.SDLK_F5)
    tick(game)
    assert game.world.stage_index == 0 and game.world.player.hp == 500
    assert all(not stage.arrows_visible and not stage.enemies for stage in game.world.stages)
    for key in (pico2d.SDLK_F5, pico2d.SDLK_RIGHT, pico2d.SDLK_LSHIFT, pico2d.SDLK_n):
        push_key(key, down=False)
    game.handle_events()
    print("PASS: SDL full sprint round trip keeps per-map enemies/HP/spawn counts, "
          "avoids return loops, bounds the final boss exit, and F5 resets all stages.")


def check_transition_art(image, entering_city):
    actual = image.convert("RGB")
    if not entering_city:
        with Image.open(config.ROOT / config.STAGE_LOADING_IMAGE) as supplied:
            assert ImageChops.difference(actual, supplied.convert("RGB")).getbbox() is None
        return
    art = config.DARK_CITY_INTRO
    with Image.open(config.ROOT / art.background) as supplied:
        expected = supplied.convert("RGB").resize(actual.size, Image.Resampling.NEAREST)
    with Image.open(config.ROOT / art.title) as sheet:
        first = sheet.crop((0, 0, sheet.width // 4, sheet.height // 2))
    x = (actual.width - first.width) // 2
    y = (actual.height - first.height) // 2 - art.title_offset_y
    expected.paste(first, (x, y), first)
    # SDL and Pillow round scaling and translucent pixels slightly differently.
    difference = ImageChops.difference(actual, expected)
    assert max(ImageStat.Stat(difference).mean) < 2
    assert max(ImageStat.Stat(difference.crop((x, y, x + first.width, y + first.height))).mean) < 2


def check_city_loading(game):
    game.world = World()
    game.world.stages[2].traffic = None  # Isolate saved enemy HP from random road deaths.
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
                check_transition_art(image, entering_city=True)
                timing["start"] = perf_counter()
                for key in (pico2d.SDLK_SPACE, pico2d.SDLK_a, pico2d.SDLK_p):
                    push_key(key)
                push_key(pico2d.SDLK_n, down=False)
                push_key(pico2d.SDLK_n)
            assert snapshot == frozen[0]
        elif world.stage_index == 2:
            timing.setdefault("end", perf_counter())

    with patch.object(game, "draw", side_effect=observe):
        assert game.run(max_frames=300) == 300
    duration = timing["end"] - timing["start"]
    assert 4.5 <= duration < 4.75, duration
    assert game.world.stage_index == 2 and not game.world.stage_loading
    assert game.world.player is player and player.hp == 420 and player.invincible
    assert player.jump_count == 0 and player.active_move is None
    assert not game.world.enemies and not game.world.stage.arrows_visible
    assert all(game.assets.images[name] is image for name, image in textures.items())
    capture(game, "city_stage_1_entered")
    game.world.enemies.extend(game.world.spawner.spawn(1, game.world.elapsed))
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
    assert len(game.world.enemies) == config.STAGE_ENCOUNTER_SIZE
    assert all(not stage.enemies for stage in game.world.stages[1:])
    assert all(not stage.arrows_visible for stage in game.world.stages)
    for key in (pico2d.SDLK_F5, pico2d.SDLK_LEFT, pico2d.SDLK_LSHIFT, pico2d.SDLK_n,
                pico2d.SDLK_SPACE, pico2d.SDLK_a, pico2d.SDLK_9, pico2d.SDLK_p, pico2d.SDLK_1):
        push_key(key, down=False)
    game.handle_events()
    print(f"PASS: WHEN intro and fade took {duration:.3f}s with gameplay frozen; "
          f"changed_first_map -> {config.SECOND_STAGE_IMAGE} -> {config.CITY_STAGE_IMAGES}, "
          "ignored loading actions, "
          "HP/motion/resource reuse, city return and F5 cancellation verified.")


def check_stage_background(game, index, prefix):
    game.world = World()
    game.world.stage_index = index
    name = game.world.stage.image_name
    with Image.open(config.ROOT / name) as source:
        assert source.size == (1672, 941)
        supplied = source.convert("RGB")
    tiled = Image.new("RGB", (supplied.width * 2, supplied.height))
    tiled.paste(supplied, (0, 0))
    tiled.paste(supplied.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (supplied.width, 0))
    for camera_x in (0, 640, config.WORLD_WIDTH - config.SCREEN_WIDTH):
        game.world.camera.x = camera_x
        game.world.camera.offset_x = 0
        for shake_y in (-8, 0, 8):
            game.world.camera.offset_y = shake_y
            anchor = config.STAGE_GROUND_ANCHORS.get(name, config.STAGE_GROUND_Y)
            bottom = config.GROUND_Y - anchor - shake_y
            bottom = min(0, max(config.SCREEN_HEIGHT - supplied.height, bottom))
            top = int(supplied.height + bottom - config.SCREEN_HEIGHT)
            expected = tiled.crop((camera_x, top,
                                   camera_x + config.SCREEN_WIDTH, top + config.SCREEN_HEIGHT))
            with (patch.object(game.assets, "draw_sprite"),
                  patch.object(game.assets, "draw_stage_door"),
                  patch.object(game.assets, "draw_drop_item"),
                  patch.object(game.ui, "draw_pickup_prompt"),
                  patch.object(game.ui, "draw"), patch.object(game.ui, "draw_enemy_health")):
                image = capture(game, f"{prefix}_background_{camera_x}_{shake_y}")
            assert ImageChops.difference(image.convert("RGB"), expected).getbbox() is None
    print(f"PASS: {name} 1672x941 original-size pixels and mirrored tiling "
          "fill left/center/right views during vertical shake without blank strips.")


def check_factory_loading(game, first=3):
    textures = dict(game.assets.images)
    region = {3: "factory", 5: "factory_inside", 7: "lab", 9: "boss"}[first]
    for side in (1, -1):
        game.world = World()
        world = game.world
        source_index = first if side > 0 else first + 1
        destination = source_index + side
        entering_city = config.STAGE_IMAGES[destination] in config.CITY_STAGE_IMAGES
        wait_seconds = config.STAGE_INTRO_DURATION if entering_city else config.STAGE_LOADING_DURATION
        world.stage_index = source_index
        source, target = world.stage, world.stages[destination]
        player = world.player
        player.x = (config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN if side > 0
                    else config.STAGE_EXIT_MARGIN)
        player.vx = side * config.RUN_SPEED
        player.hp, player.invincible = 420, True
        player.ground_y = 116
        player.jump_height, player.vy, player.jump_count = 140, 300, 2
        player.animation.set_state("JUMP")
        player.animation.elapsed = 0.2
        for stage, hp in ((source, 160), (target, 120)):
            enemy = Enemy(1800, ground_y=100)
            enemy.hp = hp
            stage.enemies.append(enemy)
            stage.effects.append(HitEffect(1500, 180, 1))
            stage.damage_numbers.append(DamageNumber(1500, 250, 40))
        direction = pico2d.SDLK_RIGHT if side > 0 else pico2d.SDLK_LEFT
        for key in (direction, pico2d.SDLK_LSHIFT, pico2d.SDLK_n):
            push_key(key)
        timing, frozen = {}, []
        original_draw = game.draw

        def observe(present=True):
            original_draw(present)
            if world.stage_loading:
                snapshot = (world.elapsed, player.x, player.ground_y, player.hp,
                            player.jump_height, player.vy, player.animation.elapsed,
                            tuple((stage.enemies[0].x, stage.enemies[0].animation.elapsed,
                                   stage.effects[0].elapsed, stage.damage_numbers[0].elapsed)
                                  for stage in (source, target)))
                if not frozen:
                    frozen.append(snapshot)
                    with patch.object(game, "draw", original_draw):
                        image = capture(game, f"stage_loading_to_{region}" if side > 0
                                        else f"stage_loading_return_from_{region}")
                    check_transition_art(image, entering_city)
                    timing["start"] = perf_counter()
                for key in (pico2d.SDLK_SPACE, pico2d.SDLK_a, pico2d.SDLK_p):
                        push_key(key)
                assert snapshot == frozen[0]
            elif world.stage_index == destination and "end" not in timing:
                timing["end"] = perf_counter()
                assert world.player is player and (player.hp, player.invincible) == (420, True)
                assert (player.jump_height, player.vy, player.jump_count) == (140, 300, 2)
                assert player.vx == side * config.RUN_SPEED and player.animation.elapsed == 0.2
                assert not target.arrows_visible and len(target.enemies) == 1
                assert target.enemies[0].hp == 120 and source.enemies[0].hp == 160
                with patch.object(game, "draw", original_draw):
                    capture(game, f"{region}_entered" if side > 0 else f"returned_from_{region}")

        with patch.object(game, "draw", side_effect=observe):
            frames = round((wait_seconds + 0.5) * config.TARGET_FPS)
            assert game.run(max_frames=frames) == frames
        duration = timing["end"] - timing["start"]
        assert wait_seconds <= duration < wait_seconds + 0.25, duration
        assert world.stage_index == destination and len(target.enemies) == 1
        assert player.active_move is None and player.hp == 420 and player.invincible
        assert all(game.assets.images[name] is image for name, image in textures.items())
        for key in (direction, pico2d.SDLK_LSHIFT, pico2d.SDLK_n, pico2d.SDLK_SPACE,
                    pico2d.SDLK_a, pico2d.SDLK_9, pico2d.SDLK_p):
            push_key(key, down=False)
        game.handle_events()
        print(f"PASS: {source.image_name} -> {target.image_name} "
              f"presents the transition for {duration:.3f}s; "
              "player/jump/HP/input and both scenes' objects survive the frozen transition.")
    game.world = World()
    game.world.stage_index = first
    game.world.player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
    game.world.player.vx = config.RUN_SPEED
    push_key(pico2d.SDLK_n)
    tick(game)
    assert game.world.stage_loading and game.world.pending_stage_index == first + 1
    push_key(pico2d.SDLK_F5)
    tick(game)
    assert game.world.stage_index == 0 and not game.world.stage_loading
    assert len(game.world.enemies) == config.STAGE_ENCOUNTER_SIZE
    assert all(not stage.enemies for stage in game.world.stages[1:])
    assert all(not stage.arrows_visible for stage in game.world.stages)
    for key in (pico2d.SDLK_n, pico2d.SDLK_F5):
        push_key(key, down=False)
    game.handle_events()
    print(f"PASS: SDL F5 cancels pending {region} entry and resets all scenes.")


def check_factory_exterior(game):
    world = game.world = World(rng=random.Random(13))
    world.reset(stage_index=config.STAGE_IMAGES.index(config.FACTORY_EXTERIOR_IMAGE))
    player = world.player
    player.x = config.FACTORY_GATE_RECT[0] + config.FACTORY_GATE_RECT[2] / 2
    world.update_camera(0)
    closed = capture(game, "factory_gate_closed").convert("RGB")

    # Stand in line with the door, but well out on the pavement.
    world.spawn_enemies(1)
    for enemy in world.enemies[:-1]:
        enemy.take_damage(enemy.hp)
    game.update(config.FIXED_DT)
    assert not world.stage_loading and world.stage.factory_gate.frame == 0
    last = world.enemies[-1]
    last.hp, last.cooldown = 1, 10
    last.x, last.ground_y = player.x - 80, player.ground_y
    player.facing = -1
    push_key(pico2d.SDLK_a)
    for _ in range(60):
        tick(game)
        if world.opening_factory_exit:
            break
    push_key(pico2d.SDLK_a, down=False)
    game.handle_events()
    assert not last.alive
    assert world.opening_factory_exit and not world.stage_loading
    x = player.x
    push_key(pico2d.SDLK_RIGHT)
    tick(game, 40)
    assert player.x > x and world.opening_factory_exit
    push_key(pico2d.SDLK_RIGHT, down=False)
    push_key(pico2d.SDLK_SPACE)
    tick(game)
    assert player.jump_height > 0
    push_key(pico2d.SDLK_SPACE, down=False)
    tick(game, 39)
    middle = capture(game, "factory_gate_opening").convert("RGB")
    tick(game, 81)
    assert world.stage.factory_gate.finished and not world.stage_loading
    opened = capture(game, "factory_gate_open").convert("RGB")

    # Check the shutter face itself, above the actors and away from the HUD.
    panel = (480, 140, 800, 390)
    for first, second in ((closed, middle), (middle, opened)):
        changed = ImageChops.difference(first.crop(panel), second.crop(panel)).convert("L")
        assert sum(changed.histogram()[4:]) > 12000
    tick(game, 300)
    assert world.stage.image_name == config.FACTORY_EXTERIOR_IMAGE and not world.stage_loading
    push_key(pico2d.SDLK_UP)
    for _ in range(120):
        tick(game)
        if world.entering_factory_gate:
            break
    push_key(pico2d.SDLK_UP, down=False)
    game.handle_events()
    assert world.entering_factory_gate
    threshold = capture(game, "factory_gate_threshold").convert("RGB")
    game.update(0.5)
    fading = capture(game, "factory_gate_fading").convert("RGB")
    # Halfway through the fade, the entire original frame (including HUD) is half as bright.
    expected = threshold.point(lambda value: value // 2)
    error = ImageChops.difference(expected, fading)
    assert max(high for _, high in error.getextrema()) <= 2
    game.update(0.5)
    assert world.entering_factory_gate
    assert capture(game, "factory_gate_black").convert("RGB").getbbox() is None
    game.update(config.FIXED_DT)
    assert world.stage.image_name == config.FACTORY_OUTSIDE_IMAGE
    assert world.player is player and not world.enemies
    assert capture(game, "factory_gate_dock").convert("RGB").getbbox()
    for _ in range(round(config.STAGE_ENCOUNTER_DELAY / config.FIXED_DT)):
        game.update(config.FIXED_DT)
    assert len(world.enemies) == config.STAGE_ENCOUNTER_SIZE
    print("PASS: movement and jumping during gate opening, then a one-second fade at the doorway.")


def check_indoor_backgrounds(game, first=6):
    region = {6: "factory_inside", 8: "lab", 10: "boss"}[first]
    if first == 8:
        assert config.STAGE_IMAGES[8:10] == config.LAB_STAGE_IMAGES == (
            "labStage-1_floor300_1672x941.png", "labStage-2_floor300_1672x941.png")
        for archived in config.ARCHIVED_LAB_STAGE_IMAGES:
            assert archived not in game.assets.images and Path(archived).name not in game.assets.images
    elif first == 10:
        assert config.STAGE_IMAGES[10:] == config.BOSS_STAGE_IMAGES == (
            "bossStage_floor300_1672x941.png", "bossStage-2_floor300_1672x941.png")
        for archived in config.ARCHIVED_BOSS_STAGE_IMAGES:
            assert archived not in game.assets.images and Path(archived).name not in game.assets.images
    for index in (first, first + 1):
        game.world = World()
        game.world.stage_index = index
        with Image.open(config.ROOT / game.world.stage.image_name) as source:
            assert source.size == (1672, 941)
            supplied = source.convert("RGB")
        tiled = Image.new("RGB", (supplied.width * 2, supplied.height))
        tiled.paste(supplied, (0, 0))
        tiled.paste(supplied.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (supplied.width, 0))
        for camera_x in (0, 640, config.WORLD_WIDTH - config.SCREEN_WIDTH):
            game.world.camera.x = camera_x
            game.world.camera.offset_x = 0
            for shake_y in (-8, 0, 8):
                game.world.camera.offset_y = shake_y
                anchor = config.STAGE_GROUND_ANCHORS.get(game.world.stage.image_name,
                                                        config.STAGE_GROUND_Y)
                bottom = config.GROUND_Y - anchor - shake_y
                top = int(supplied.height + bottom - config.SCREEN_HEIGHT)
                expected = tiled.crop((camera_x, top,
                                       camera_x + config.SCREEN_WIDTH, top + config.SCREEN_HEIGHT))
                with (patch.object(game.assets, "draw_sprite"), patch.object(game.ui, "draw"),
                      patch.object(game.assets, "draw_drop_item"),
                      patch.object(game.ui, "draw_pickup_prompt"),
                      patch.object(game.ui, "draw_enemy_health")):
                    image = capture(game, f"{region}_{index - first + 1}_background_{camera_x}_{shake_y}")
                assert ImageChops.difference(image.convert("RGB"), expected).getbbox() is None
    print(f"PASS: {config.STAGE_IMAGES[first:first + 2]} keep original-size background pixels, "
          "mirrored tiling, floor alignment and full viewport coverage during shake.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_stage_background(game, 0, "changed_first_map")
        check_stage_background(game, 1, "second_alley_floor300")
        check_stage_background(game, 2, "city_ground_300_1")
        check_stage_background(game, 3, "city_ground_300_2")
        check_markers(game)
        check_motion_continuity(game)
        check_motion_continuity(game, first=2)
        check_motion_continuity(game, first=4)
        check_motion_continuity(game, first=6)
        check_motion_continuity(game, first=8)
        check_motion_continuity(game, first=10)
        check_round_trip_and_last_exit(game)
        check_city_loading(game)
        check_stage_background(game, 5, "factory_loading_dock_no_stairs")
        check_factory_loading(game)
        check_factory_exterior(game)
        check_factory_loading(game, first=5)
        check_indoor_backgrounds(game)
        check_factory_loading(game, first=7)
        check_indoor_backgrounds(game, first=8)
        check_factory_loading(game, first=9)
        check_indoor_backgrounds(game, first=10)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
