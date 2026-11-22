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


def tap(game, key):
    push_key(key)
    tick(game)
    push_key(key, down=False)
    game.handle_events()


def check_city_sidewalk_pixels(game, image, baseline):
    # Measure against the artwork's paving, independently of the spawn bounds:
    # New source rows 656..694 exclude the buildings, curb lip and roadway.
    name = config.CITY_STAGE_IMAGES[0]
    source = game.assets.images[name]
    anchor = config.STAGE_GROUND_ANCHORS.get(name, config.STAGE_GROUND_Y)
    bottom = config.GROUND_Y - anchor * config.STAGE_SCALE - game.world.camera.render_y
    sidewalk_bottom = bottom + (source.h - 694) * config.STAGE_SCALE
    sidewalk_top = bottom + (source.h - 656) * config.STAGE_SCALE
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
    # The attack/help panels cover part of the upper walkway, so inspect the
    # floor pixels with the existing U-hide mode rather than testing the HUD.
    details_visible = game.ui.details_visible
    game.ui.details_visible = False
    arrow_edge = ceil(config.STAGE_EXIT_MARGIN + config.STAGE_ARROW_WIDTH / 2
                      + config.STAGE_ARROW_SWAY_AMPLITUDE)
    counts = []
    for index, stage in enumerate(world.stages):
        assert world.select_stage(index)
        stage.arrows_visible = True
        counts.append(len(stage.drop_items))
        assert counts[-1] == 15
        assert {item.kind for item in stage.drop_items} == {"combat_knife", "steel_pipe"}
        areas = (stage.drop_spawn_area, *stage.floor_areas[1:])
        # Frame the complete foreground too; expanded floors can reach y=-44.
        # Inspect the real camera-transformed pixels, not an assumed camera_y=0.
        world.player.ground_y = world.player.previous_ground_y = min(area.bounds[1] for area in areas)
        stage.constrain_actor(world.player)
        for floor_index, area in enumerate(areas):
            items = [item for item in stage.drop_items if item.floor == floor_index]
            assert len(items) == (8 - floor_index if len(areas) == 2 else 15)
            assert {item.kind for item in items} == set(config.DROP_ITEM_IMAGES)
        for side in (-1, 1):
            game.handle_events()
            world.player.x = 80 if side < 0 else config.WORLD_WIDTH - 80
            world.update_camera(0)
            baseline = without_items(game)
            image = capture(game, f"drop_stage_{index + 1}_{'left' if side < 0 else 'right'}")
            delta = difference(image, baseline)
            box = delta.getbbox()
            assert box is not None
            draw_item = game.assets.draw_drop_item
            for floor_index, area in enumerate(areas):
                with patch.object(game.assets, "draw_drop_item", side_effect=lambda item, cx, cy:
                                  draw_item(item, cx, cy) if item.floor == floor_index else None):
                    floor_delta = difference(render_image(game), baseline)
                box = floor_delta.getbbox()
                assert box is not None
                _, bottom, _, top = area.bounds
                assert box[1] >= floor(config.SCREEN_HEIGHT - top + world.camera.render_y) - 1
                assert box[3] <= ceil(config.SCREEN_HEIGHT - bottom + world.camera.render_y) + 1
            if stage.image_name == config.CITY_STAGE_IMAGES[0]:
                check_city_sidewalk_pixels(game, image, baseline)
            exit_box = ((0, 0, arrow_edge + 1, config.SCREEN_HEIGHT) if side < 0 else
                        (config.SCREEN_WIDTH - arrow_edge - 1, 0,
                         config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
            assert delta.crop(exit_box).getbbox() is None
            for item in stage.drop_items:
                x = item.x - world.camera.render_x
                if 64 <= x <= config.SCREEN_WIDTH - 64:
                    y = config.SCREEN_HEIGHT - item.ground_y + world.camera.render_y
                    crop = delta.crop((floor(x - config.DROP_ITEM_HALF_WIDTH),
                                       floor(y - config.DROP_ITEM_HEIGHT),
                                       ceil(x + config.DROP_ITEM_HALF_WIDTH),
                                       ceil(y + config.DROP_ITEM_SHADOW_HALF_DEPTH)))
                    assert crop.getbbox() is not None, (stage.image_name, item.floor, item.x, item.ground_y)
    game.ui.details_visible = details_visible
    print(f"PASS: all {len(world.stages)} stage layouts have 15 total drops ({counts}); actual floor pixels "
          "fit each floor (all 15 on the flat first map), the new first city's "
          "weapons/shadows stay on the sidewalk with no road "
          "pixels, both exit areas stay clear, and both map halves render correctly.")


def check_floor_pickup(game, floor=0, index=0):
    prefix = {0: f"drop_floor_{floor}", 1: f"second_alley_floor_{floor}"}.get(
        index, f"drop_stage_{index + 1}_floor_{floor}")
    for kind in config.DROP_ITEM_IMAGES:
        game.world = World(item_rng=random.Random(20261119))
        world = game.world
        world.select_stage(index)
        item = next(item for item in world.stage.drop_items if item.floor == floor and item.kind == kind)
        player = world.player
        player.floor = floor
        player.x = player.previous_x = item.x
        player.ground_y = player.previous_ground_y = item.ground_y
        world.stage.constrain_actor(player)
        world.update_camera(0)
        assert world.pickup_item is item
        with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as text:
            capture(game, f"{prefix}_{kind}_pickup")
        assert any(call.args[2] == "G" for call in text.call_args_list)
        tap(game, pico2d.SDLK_g)
        assert (player.floor, player.weapon) == (floor, kind)
        assert item not in world.stage.drop_items and len(world.stage.drop_items) == 14
        capture(game, f"{prefix}_{kind}_equipped")
        tap(game, pico2d.SDLK_g)
        discarded = world.stage.drop_items[-1]
        assert player.weapon is None and discarded.floor == floor and not discarded.grounded
        tick(game, 60)
        assert discarded.grounded and world.pickup_item is discarded
        tap(game, pico2d.SDLK_g)
        assert player.weapon == kind and discarded not in world.stage.drop_items
        items = world.stage.drop_items
        clocks = [item.elapsed for item in items]
        world.select_stage(0 if index else 1)
        tick(game, 30)
        world.select_stage(index)
        assert world.stage.drop_items is items and len(items) == 14
        assert [item.elapsed for item in items] == clocks
    print(f"PASS: stage {index + 1}, generated floor-{floor} knife/pipe show G, equip through real SDL G, "
          "discard/fall/re-equip on that floor, and stay depleted/paused across stage visits.")


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
    assert [sum(item.floor == floor for item in game.world.stage.drop_items)
            for floor in (0, 1)] == ([8, 7] if game.world.stage.upper_walkable else [15, 0])
    city = game.world.stages[config.STAGE_IMAGES.index(config.CITY_STAGE_IMAGES[0])]
    assert all(item.ground_y - config.DROP_ITEM_SHADOW_HALF_DEPTH >= 203
               and item.ground_y + config.DROP_ITEM_HEIGHT <= 241
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
          "and restores every first-map floor with shared textures; city drops stay above "
          "the curb in both views.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_sheets(game)
        check_all_stages(game)
        check_floor_pickup(game)
        check_floor_pickup(game, index=1)
        check_floor_pickup(game, index=5)
        check_floor_pickup(game, index=6)
        check_floor_pickup(game, index=8)
        check_floor_pickup(game, index=9)
        check_floor_pickup(game, index=10)
        check_floor_pickup(game, index=11)
        check_restart(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
