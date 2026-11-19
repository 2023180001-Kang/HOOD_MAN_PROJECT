"""Check upstairs jumps, full sprite visibility and scrolling background pixels."""

from pathlib import Path
import random
import sys
from unittest.mock import patch

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from game import Game
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, tick
from tools.check_two_floors import release
from world import World


def visible_sprite(game):
    player, camera = game.world.player, game.world.camera
    tile = game.assets.frames[player.sprite_image][player.sprite_row - 1][player.animation.frame]
    scale = config.SPRITE_IMAGE_SCALES.get(player.sprite_image, config.SPRITE_SCALE)
    bottom = player.y - camera.render_y + tile.get("offset_y", 0) * scale
    top = bottom + tile["clip"][3] * scale
    assert 0 <= bottom <= top <= config.SCREEN_HEIGHT
    assert 0 <= camera.render_x <= config.WORLD_WIDTH - config.SCREEN_WIDTH
    image = render_image(game)
    with patch.object(game.assets, "draw_sprite"):
        background = render_image(game)
    box = ImageChops.difference(image.convert("RGB"), background.convert("RGB")).getbbox()
    assert box is not None
    assert abs((box[3] - box[1]) - tile["clip"][3] * scale) <= 2


def check_jumps(game):
    game.ui.details_visible = True  # Visibility must also hold with the default help panels.
    variants = (("normal", False, None), ("double", True, None),
                ("running_left", True, pico2d.SDLK_LEFT),
                ("running_right", True, pico2d.SDLK_RIGHT))
    for weapon in (None, *config.WEAPON_POSE_IMAGES):
        for label, second, lateral in variants:
            game.world = World(item_rng=random.Random(5))
            world, player = game.world, game.world.player
            player.floor = 1
            player.x = (68 if lateral == pico2d.SDLK_LEFT else
                        2492 if lateral == pico2d.SDLK_RIGHT else 1280)
            player.ground_y = 502
            player.equip_weapon(weapon)
            world.stage.constrain_actor(player)
            world.update_camera(0)
            if lateral is not None:
                push_key(lateral)
                push_key(pico2d.SDLK_LSHIFT)
            push_key(pico2d.SDLK_SPACE)
            previous_vy, maximum = 0, 0
            for frame in range(120):
                if second and frame == 21:
                    release(game, pico2d.SDLK_SPACE)
                    push_key(pico2d.SDLK_SPACE)
                tick(game)
                maximum = max(maximum, world.camera.y)
                feet = player.y - world.camera.render_y
                assert 0 <= feet and feet + config.CAMERA_PLAYER_HEIGHT <= config.SCREEN_HEIGHT
                if previous_vy > 0 >= player.vy:
                    visible_sprite(game)
                    capture(game, f"camera_upstairs_{weapon or 'unarmed'}_{label}_apex")
                previous_vy = player.vy
            assert player.grounded and player.floor == 1
            assert maximum > (300 if second else 100)
            for key in (pico2d.SDLK_SPACE, pico2d.SDLK_LSHIFT,
                        pico2d.SDLK_LEFT, pico2d.SDLK_RIGHT):
                release(game, key)
    print("PASS: real SDL upstairs normal/double/running jumps with all 3 equipment "
          "states and both map edges keep the complete rasterized sprite visible; "
          "jump speeds/floor/landing remain unchanged.")


def check_extended_background(game):
    game.world = World()
    world = game.world
    with Image.open(config.ROOT / world.stage.image_name) as image:
        source = image.convert("RGB")
    tiled = Image.new("RGB", (source.width * 2, source.height))
    tiled.paste(source, (0, 0))
    tiled.paste(source.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (source.width, 0))
    for camera_x in (0, 640, 1280):
        world.camera.x, world.camera.y = camera_x, 400
        world.camera.offset_x = world.camera.offset_y = 0
        bottom = config.GROUND_Y - config.STAGE_GROUND_Y - world.camera.render_y
        visible_height = int(source.height + bottom)
        headroom = config.SCREEN_HEIGHT - visible_height
        expected = Image.new("RGB", (config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        edge = tiled.crop((camera_x, 0, camera_x + config.SCREEN_WIDTH, 1))
        expected.paste(edge.resize((config.SCREEN_WIDTH, headroom)), (0, 0))
        expected.paste(tiled.crop((camera_x, 0, camera_x + config.SCREEN_WIDTH, visible_height)),
                       (0, headroom))
        with (patch.object(game.assets, "draw_sprite"),
              patch.object(game.assets, "draw_stage_door"),
              patch.object(game.assets, "draw_drop_item"),
              patch.object(game.ui, "draw_pickup_prompt"),
              patch.object(game.ui, "draw"), patch.object(game.ui, "draw_enemy_health")):
            actual = capture(game, f"camera_roof_extension_{camera_x}")
        assert ImageChops.difference(actual.convert("RGB"), expected).getbbox() is None
    print("PASS: left/center/right high-camera backgrounds match original/mirrored "
          "map pixels exactly, with only the top edge extended and no blank strip "
          "or world/background misalignment.")
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert game.world.camera.y == game.world.camera.render_y == 0
    capture(game, "camera_reset_ground_floor")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_jumps(game)
        check_extended_background(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
