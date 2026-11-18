"""Verify F3 door/shutter animation and map-aligned compositing in an SDL window."""

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
                assert draw.call_count == (6 if name == config.DOOR_IMAGES["door"] else 2)
                assert {call.args[5] for call in draw.call_args_list} == {"", "h"}
                assert all(call.args[:4] == (frame * 256, 512 - row * 256, 256, 256)
                           for call in draw.call_args_list)
    print("PASS: both sheets use all 16 exact source clips; both background tiles mirror "
          "the original hinges/header anchors without trimming or double offsets.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        game.world = World(item_rng=random.Random(23))
        assert game.world.stage.image_name == "HoodMan_2F_Map_1672x941.png"
        assert all(door.state == "CLOSED" for door in game.world.stage.doors)
        assert (config.ROOT / "changed_first_map.png").is_file()
        assert (config.ROOT / "newStage.png").is_file()
        capture(game, "doors_gameplay_start")
        closed = check_endpoints(game, False, "initial_closed")
        animate(game, True)
        check_endpoints(game, True, "open")
        animate(game, False)
        assert check_endpoints(game, False, "closed_again") == closed
        check_source_clips(game)

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
