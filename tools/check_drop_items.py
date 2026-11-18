"""Verify floor drops, exact eight-frame clips and clear exits in a real SDL window."""

from math import ceil, floor
from pathlib import Path
import random
import sys
from unittest.mock import patch

from PIL import ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from drop_items import DropItem
from game import Game
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, tick
from world import World


def without_items(game):
    with patch.object(game.assets, "draw_drop_item"):
        return render_image(game)


def difference(image, baseline):
    return ImageChops.difference(image.convert("RGB"), baseline.convert("RGB"))


def check_city_sidewalk_pixels(game, image, baseline):
    # Measure against the artwork's paving, independently of the spawn bounds:
    # source rows 736..774 exclude the buildings, curb lip and roadway.
    source = game.assets.images["cityStage-1.png"]
    anchor = config.STAGE_GROUND_ANCHORS.get("cityStage-1.png", config.STAGE_GROUND_Y)
    bottom = config.GROUND_Y - anchor * config.STAGE_SCALE - game.world.camera.render_y
    sidewalk_bottom = bottom + (source.h - 774) * config.STAGE_SCALE
    sidewalk_top = bottom + (source.h - 736) * config.STAGE_SCALE
    delta = difference(image, baseline)
    assert delta.getbbox() is not None
    assert delta.crop((0, 0, config.SCREEN_WIDTH,
                       floor(config.SCREEN_HEIGHT - sidewalk_top) - 1)).getbbox() is None
    assert delta.crop((0, ceil(config.SCREEN_HEIGHT - sidewalk_bottom) + 1,
                       config.SCREEN_WIDTH, config.SCREEN_HEIGHT)).getbbox() is None


def check_sheets(game):
    game.world = World(item_rng=random.Random(1))
    world = game.world
    world.camera.offset_y = 5
    for kind, name in config.DROP_ITEM_IMAGES.items():
        texture = game.assets.images[name]
        assert (texture.w, texture.h) == (2048, 256)
        for facing in (-1, 1):
            item = DropItem(kind, world.player.x - 220, 112, facing)
            world.stage.drop_items = [item]
            baseline = without_items(game)
            contact_rows = []
            for frame in range(8):
                game.handle_events()
                item.elapsed = (frame + 0.1) / config.DROP_ITEM_FPS
                with patch.object(texture, "clip_composite_draw", wraps=texture.clip_composite_draw) as draw:
                    image = (capture(game, f"drop_{kind}_{facing}_frame_{frame}")
                             if frame == 3 else render_image(game))
                assert draw.call_count == 2
                shadow, body = [call.args for call in draw.call_args_list]
                top = config.DROP_ITEM_BODY_TOPS[kind][frame]
                height = config.DROP_ITEM_BODY_HEIGHTS[kind]
                assert shadow[:4] == (frame * 256, 256 - config.DROP_ITEM_SHADOW_TOP
                                      - config.DROP_ITEM_SHADOW_HEIGHT, 256,
                                      config.DROP_ITEM_SHADOW_HEIGHT)
                assert body[:4] == (frame * 256, 256 - top - height, 256, height)
                ground = item.ground_y - world.camera.render_y
                for args in (shadow, body):
                    assert args[5] == ("h" if facing < 0 else "")
                    assert args[6] == item.x - world.camera.render_x
                    assert args[8] == 128
                assert shadow[7] == ground
                assert body[7] - body[9] / 2 == ground
                assert body[9] == height * config.DROP_ITEM_SCALE
                delta = difference(image, baseline)
                assert delta.getbbox() is not None
                assert sum(pixel != (0, 0, 0) for pixel in delta.get_flattened_data()) > 300
                # Render the two parts separately to check actual rasterized
                # contact, rather than just trusting the draw-call coordinates.
                render = texture.clip_composite_draw
                with patch.object(texture, "clip_composite_draw", side_effect=lambda *args:
                                  render(*args) if args[3] == height else None):
                    body_box = difference(render_image(game), baseline).getbbox()
                with patch.object(texture, "clip_composite_draw", side_effect=lambda *args:
                                  render(*args) if args[3] == config.DROP_ITEM_SHADOW_HEIGHT else None):
                    shadow_box = difference(render_image(game), baseline).getbbox()
                ground_row = config.SCREEN_HEIGHT - ground
                assert abs(body_box[3] - ground_row) <= 1
                assert shadow_box[1] <= body_box[3] <= shadow_box[3]
                contact_rows.append(body_box[3])
            assert len(set(contact_rows)) == 1
    print("PASS: both sheets, 8 frames x 2 directions, separate exact weapon/shadow clips; "
          "actual weapon bottoms touch the floor/shadow at a fixed row without bobbing, "
          "including camera shake and 0.5 scale.")


def check_all_stages(game):
    game.world = World(item_rng=random.Random(20261115))
    world = game.world
    arrow_edge = ceil(config.STAGE_EXIT_MARGIN + config.STAGE_ARROW_WIDTH / 2
                      + config.STAGE_ARROW_SWAY_AMPLITUDE)
    counts = []
    for index, stage in enumerate(world.stages):
        assert world.select_stage(index)
        stage.arrows_visible = True
        counts.append(len(stage.drop_items))
        assert counts[-1] == 15
        assert {item.kind for item in stage.drop_items} == {"combat_knife", "steel_pipe"}
        _, bottom, _, top = stage.drop_spawn_area.bounds
        for side in (-1, 1):
            game.handle_events()
            world.player.x = 80 if side < 0 else config.WORLD_WIDTH - 80
            world.camera.update(0, world.player.x)
            baseline = without_items(game)
            image = capture(game, f"drop_stage_{index + 1}_{'left' if side < 0 else 'right'}")
            delta = difference(image, baseline)
            box = delta.getbbox()
            assert box is not None
            assert box[1] >= floor(config.SCREEN_HEIGHT - top) - 1
            assert box[3] <= ceil(config.SCREEN_HEIGHT - bottom) + 1
            if stage.image_name == "cityStage-1.png":
                check_city_sidewalk_pixels(game, image, baseline)
            exit_box = ((0, 0, arrow_edge + 1, config.SCREEN_HEIGHT) if side < 0 else
                        (config.SCREEN_WIDTH - arrow_edge - 1, 0,
                         config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
            assert delta.crop(exit_box).getbbox() is None
            for item in stage.drop_items:
                x = item.x - world.camera.render_x
                if 64 <= x <= config.SCREEN_WIDTH - 64:
                    y = config.SCREEN_HEIGHT - item.ground_y
                    crop = delta.crop((floor(x - config.DROP_ITEM_HALF_WIDTH),
                                       floor(y - config.DROP_ITEM_HEIGHT),
                                       ceil(x + config.DROP_ITEM_HALF_WIDTH),
                                       ceil(y + config.DROP_ITEM_SHADOW_HALF_DEPTH)))
                    assert crop.getbbox() is not None
    print(f"PASS: all {len(world.stages)} stage layouts have 15 total drops ({counts}); actual floor pixels "
          "fit each map, cityStage-1 weapons/shadows stay on the sidewalk with no road "
          "pixels, both exit areas stay clear, and both map halves render correctly.")


def check_restart(game):
    textures = dict(game.assets.images)
    previous = [stage.drop_items for stage in game.world.stages]
    push_key(pico2d.SDLK_F5)
    tick(game)
    push_key(pico2d.SDLK_F5, down=False)
    game.handle_events()
    assert game.world.stage_index == 0
    assert all(stage.drop_items is not old and len(stage.drop_items) == 15
               for stage, old in zip(game.world.stages, previous))
    city = game.world.stages[config.STAGE_IMAGES.index("cityStage-1.png")]
    assert all(item.ground_y - config.DROP_ITEM_SHADOW_HALF_DEPTH >= 123
               and item.ground_y + config.DROP_ITEM_HEIGHT <= 161
               and city.walkable.contains(item.x, item.ground_y)
               for item in city.drop_items)
    assert all(game.assets.images[name] is texture for name, texture in textures.items())
    capture(game, "drop_items_restarted")
    assert game.world.select_stage(config.STAGE_IMAGES.index(city.image_name))
    for side in (-1, 1):
        game.world.player.x = 80 if side < 0 else config.WORLD_WIDTH - 80
        game.world.camera.update(0, game.world.player.x)
        baseline = without_items(game)
        image = capture(game, f"city_sidewalk_drops_restarted_{'left' if side < 0 else 'right'}")
        check_city_sidewalk_pixels(game, image, baseline)
    print(f"PASS: actual SDL F5 replaces all {len(game.world.stages)} item lists "
          "and reuses both shared textures; city drops stay above the curb in both views.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_sheets(game)
        check_all_stages(game)
        check_restart(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
