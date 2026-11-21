"""Verify F3 door/shutter animation and map-aligned compositing in an SDL window."""

from pathlib import Path
import random
import sys
from unittest.mock import patch

from PIL import ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from game import Game
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, tick
from world import World


def backdrop(game, name=None):
    with (patch.object(game.assets, "draw_sprite"), patch.object(game.assets, "draw_drop_item"),
          patch.object(game.ui, "draw"), patch.object(game.ui, "draw_enemy_health"),
          patch.object(game.ui, "draw_pickup_prompt")):
        return capture(game, name) if name is not None else render_image(game)


def release(game, key):
    push_key(key, down=False)
    game.handle_events()


def check_endpoints(game, opened, label):
    world = game.world
    images = []
    background = game.assets.images[world.stage.image_name]
    bottom = config.GROUND_Y - config.STAGE_GROUND_Y
    for camera_x in (0, 640, config.WORLD_WIDTH - config.SCREEN_WIDTH):
        world.camera.x = camera_x
        world.camera.offset_x = world.camera.offset_y = 0
        image = backdrop(game, f"doors_{label}_{camera_x:g}")
        images.append(image.tobytes())
        for tile in (0, 1):
            for door in world.stage.doors:
                left, top, width, height = door.source_rect
                source_x, source_y = left + width / 2, top + height * 0.65
                x = tile * background.w + (background.w - source_x if tile else source_x) - camera_x
                y = config.SCREEN_HEIGHT - bottom - background.h + source_y
                if 1 <= x < config.SCREEN_WIDTH - 1 and 1 <= y < config.SCREEN_HEIGHT - 1:
                    pixel = image.getpixel((int(x), int(y)))
                    matches_pose = max(pixel[:3]) < 10 if opened else sum(pixel[:3]) > 40
                    assert matches_pose, (
                        door.kind, door.source_rect, tile, camera_x, opened, pixel)
    return images


def animate(game, opened):
    push_key(pico2d.SDLK_F3)
    tick(game)
    seen = set()
    captured = False
    expected_row = 1 if opened else 2
    for step in range(100):
        doors = game.world.stage.doors
        assert all(door.target_open == opened for door in doors)
        assert len({(door.state, door.row, door.frame) for door in doors}) == 1
        if not doors[0].moving:
            break
        seen.add((doors[0].row, doors[0].frame))
        if doors[0].frame == 3 and not captured:
            backdrop(game, "doors_opening" if opened else "doors_closing")
            captured = True
        if step in (3, 5):
            push_key(pico2d.SDLK_F3, repeat=step == 3)
        tick(game)
    assert seen == {(expected_row, frame) for frame in range(8)}, seen
    assert all(door.state == ("OPEN" if opened else "CLOSED") for door in doors)
    release(game, pico2d.SDLK_F3)


def check_source_clips(game):
    for row in (1, 2):
        for frame in range(8):
            for door in game.world.stage.doors:
                door.target_open = row == 1
                door.moving = True
                door.animation.set_state("OPENING" if row == 1 else "CLOSING")
                door.animation.elapsed = (frame + 0.1) / config.DOOR_FPS
            game.world.camera.x = 640  # Both the original and mirrored tile are visible.
            for name in config.DOOR_IMAGES.values():
                texture = game.assets.images[name]
                with patch.object(texture, "clip_composite_draw", wraps=texture.clip_composite_draw) as draw:
                    backdrop(game)
                assert draw.call_count == 2
                assert {call.args[5] for call in draw.call_args_list} == {"", "h"}
                assert all(call.args[:4] == (frame * 256, 512 - row * 256, 256, 256)
                           for call in draw.call_args_list)
    print("PASS: both sheets use all 16 exact source clips; both background tiles mirror "
          "the original hinges/header anchors without trimming or double offsets.")


def check_air_conditioner_foreground(game):
    game.world = World(item_rng=random.Random(23))
    world = game.world
    background = game.assets.images[world.stage.image_name]
    protected_source = (1482, 375, 78, 60)
    left, top, width, height = protected_source
    views = 0
    for camera_x in (640, 1000, 1280):
        for camera_y in (0, 120.75):
            for shake_x, shake_y in ((0, 0), (5.387, 6.569), (-5.387, -6.569)):
                world.camera.x, world.camera.y = camera_x, camera_y
                world.camera.offset_x, world.camera.offset_y = shake_x, shake_y
                bottom = min(0, config.GROUND_Y - config.STAGE_GROUND_Y - world.camera.render_y)
                rendered_top = int(config.SCREEN_HEIGHT - bottom - background.h)
                boxes = []
                for tile in (0, 1):
                    source_left = background.w - left - width if tile else left
                    x = int(tile * background.w - world.camera.render_x) + source_left
                    y = rendered_top + top
                    boxes.append((x, y, x + width, y + height))
                for door in world.stage.doors:
                    door.moving = door.target_open = False
                with (patch.object(world.stage, "doors", []),
                      patch.dict(config.STAGE_DOOR_FOREGROUND_RECTS, {}, clear=True)):
                    original = backdrop(game)
                with patch.dict(config.STAGE_DOOR_FOREGROUND_RECTS, {}, clear=True):
                    covered = backdrop(game)
                assert all(covered.crop(box).tobytes() != original.crop(box).tobytes()
                           for box in boxes), (camera_x, camera_y, shake_x, shake_y)
                for row in (1, 2):
                    for frame in range(8):
                        for door in world.stage.doors:
                            door.target_open = row == 1
                            door.moving = True
                            door.animation.set_state("OPENING" if row == 1 else "CLOSING")
                            door.animation.elapsed = (frame + 0.1) / config.DOOR_FPS
                        image = backdrop(game)
                        for box in boxes:
                            assert image.crop(box).tobytes() == original.crop(box).tobytes(), (
                                camera_x, camera_y, shake_x, shake_y, row, frame, box)
                        if row == 1 and frame == 0:
                            difference = ImageChops.difference(
                                image.convert("RGB"), covered.convert("RGB"))
                            for box in boxes:
                                difference.paste((0, 0, 0), box)
                            assert difference.getbbox() is None
                views += 1
    game.world = World(item_rng=random.Random(23))
    game.world.camera.x = 1000
    image = backdrop(game, "shutter_ac_fixed")
    image.crop((280, 175, 920, 470)).resize((1280, 590)).save(
        ROOT / "artifacts" / "shutter_ac_fixed_detail.png")
    game.world = World(item_rng=random.Random(23))
    print(f"PASS: both air conditioners retain exact original pixels through all 16 shutter poses "
          f"and {views} scrolled/vertical/shaken views; the closed-door fix changes no pixels "
          "outside the foreground props, and the unprotected rendering reproduces the overlap.")


def check_numeric_spawns(game):
    expected = {("door", 0, 0): (291.5, 268),
                ("door", 1, 0): (1438.5, 266),
                ("door", 1, 1): (1905.5, 266)}
    observed_sources = set()
    for prefix in ("", "KP_"):
        for count in config.SPAWN_COUNTS:
            game.world = World(rng=random.Random(41), item_rng=random.Random(23))
            world = game.world
            world.player.invincible = True
            push_key(pico2d.SDLK_F3)
            tick(game, 45)
            release(game, pico2d.SDLK_F3)
            assert all(door.state == "OPEN" for door in world.stage.doors)
            assert not world.enemies
            assert {point.source: (point.x, point.ground_y)
                    for point in world.stage.open_door_spawns()} == expected
            spawn = world.spawner.spawn
            samples = []

            def record(batch, elapsed):
                enemies = spawn(batch, elapsed)
                samples.extend((enemy.spawn_source, enemy.x, enemy.ground_y, enemy.floor)
                               for enemy in enemies)
                return enemies

            key = getattr(pico2d, f"SDLK_{prefix}{count}")
            with patch.object(world.spawner, "spawn", side_effect=record):
                push_key(key)
                tick(game)
                assert len(world.enemies) == count
                push_key(key, repeat=True)
                tick(game, 2)
                assert len(world.enemies) == count
                release(game, key)
                push_key(key)
                tick(game)
                release(game, key)
                assert len(world.enemies) == world.spawner.spawned_count == count * 2
            for source, x, y, floor in samples:
                observed_sources.add(source)
                assert floor == 0
                if source[0] == "door":
                    assert (x, y) == expected[source], (source, x, y)
                else:
                    assert x in (88, 2472) and 56 <= y <= 268
            assert all(enemy.floor == 0 and enemy.staircase is None
                       and world.stage.walkable.contains(enemy.x, enemy.ground_y, 88)
                       for enemy in world.enemies)
            if count == 9:
                for camera_x in (0, 1280):
                    world.camera.x = camera_x
                    capture(game, f"flat_map_spawn_{prefix or 'top'}_{camera_x}")
            push_key(pico2d.SDLK_F3)
            tick(game)
            release(game, pico2d.SDLK_F3)
            assert not world.stage.open_door_spawns()
            later = world.spawner.spawn(9, world.elapsed)
            assert all(enemy.spawn_source[0] == "edge" for enemy in later)
    assert observed_sources == set(expected) | {("edge", -1), ("edge", 1)}
    print("PASS: all 18 SDL digit/keypad keys summon exact fresh-input counts at both edges, "
          "the ordinary door and original/mirrored shutters; exact spawn coordinates, floor 0, "
          "no auto-spawn, held/repeat suppression and immediate closing exclusion.")


def check_single_floor_and_revisit(game):
    game.world = World(item_rng=random.Random(23))
    world = game.world
    world.player.x = world.player.previous_x = 238  # Former invisible staircase.
    push_key(pico2d.SDLK_UP)
    push_key(pico2d.SDLK_LSHIFT)
    tick(game, 45)
    release(game, pico2d.SDLK_LSHIFT)
    assert world.player.ground_y == 268 and world.player.staircase is None
    push_key(pico2d.SDLK_SPACE)
    tick(game, 3)
    release(game, pico2d.SDLK_SPACE)
    push_key(pico2d.SDLK_SPACE)
    tick(game)
    release(game, pico2d.SDLK_SPACE)
    assert world.player.jump_count == 2
    for _ in range(120):
        tick(game)
        assert world.player.floor == 0 and world.player.staircase is None
        assert not world.player.falling_from_upper
    release(game, pico2d.SDLK_UP)
    assert world.player.grounded and world.player.ground_y == 268
    assert len(world.stage.drop_items) == 15
    assert all(item.floor == 0 and item.grounded for item in world.stage.drop_items)
    capture(game, "flat_map_jump_landed")
    push_key(pico2d.SDLK_F3)
    tick(game, 10)
    release(game, pico2d.SDLK_F3)
    doors = world.stage.doors
    snapshot = [(door.state, door.animation.elapsed) for door in doors]
    world.select_stage(1)
    tick(game, 30)
    world.select_stage(0)
    assert world.stage.doors is doors
    assert [(door.state, door.animation.elapsed) for door in doors] == snapshot
    tick(game, 40)
    assert all(door.state == "OPEN" for door in doors)
    print("PASS: SDL up/run and double-jump at the former stairs stay on the flat floor; "
          "15 floor-0 items, inactive door-clock pause and identical door objects on revisit.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        game.world = World(item_rng=random.Random(23))
        assert game.world.stage.image_name == "changed_first_map_no_door.png"
        assert [door.kind for door in game.world.stage.doors] == ["door", "warehouse_shutter"]
        assert game.world.stage.stairs == [] and game.world.stage.upper_walkable is None
        assert all(item.floor == 0 for item in game.world.stage.drop_items)
        assert (config.ROOT / config.ARCHIVED_TWO_FLOOR_IMAGE).is_file()
        assert config.ARCHIVED_TWO_FLOOR_IMAGE not in game.assets.images
        assert all(door.state == "CLOSED" for door in game.world.stage.doors)
        assert (config.ROOT / "changed_first_map.png").is_file()
        assert (config.ROOT / "newStage.png").is_file()
        check_air_conditioner_foreground(game)
        capture(game, "doors_gameplay_start")
        closed = check_endpoints(game, False, "initial_closed")
        animate(game, True)
        check_endpoints(game, True, "open")
        animate(game, False)
        assert check_endpoints(game, False, "closed_again") == closed
        check_source_clips(game)
        check_numeric_spawns(game)
        check_single_floor_and_revisit(game)

        game.world = World()
        push_key(pico2d.SDLK_p)
        push_key(pico2d.SDLK_F4)
        tick(game)
        release(game, pico2d.SDLK_p)
        release(game, pico2d.SDLK_F4)
        animate(game, True)
        assert game.world.player.invincible and game.ui.floor_bounds_visible
        textures = dict(game.assets.images)
        push_key(pico2d.SDLK_F5)
        tick(game)
        release(game, pico2d.SDLK_F5)
        assert all(door.state == "CLOSED" for door in game.world.stage.doors)
        assert all(game.assets.images[name] is texture for name, texture in textures.items())
        assert len(game.world.stage.drop_items) == 15 and game.world.stage.traffic is None
        capture(game, "doors_restart_closed")
        print("PASS: SDL F3 opens/closes every door together through 8 frames, ignores held/repeated "
              "presses, covers/reveals every opening in all views, restores the identical closed "
              "pixels, preserves P/F4, and F5 resets to closed while reusing textures.")
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
