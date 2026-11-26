"""Exercise actual SDL G interactions, weapon poses, pickup hints and falling drops."""

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
from tools.check_drop_items import check_city_sidewalk_pixels, without_items
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, ready_enemy, tick
from world import World


def tap(game, key):
    push_key(key)
    tick(game)
    push_key(key, down=False)
    game.handle_events()


def setup(game, kind="combat_knife"):
    game.world = World(item_rng=random.Random(7))
    world = game.world
    world.stage.drop_items = [DropItem(kind, world.player.x + 30, world.player.ground_y)]
    return world


def check_pickup_hint_and_input(game):
    world = setup(game)
    item = world.pickup_item
    with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as text:
        shown = capture(game, "weapon_pickup_g_prompt")
    assert sum(call.args[2] == "G" for call in text.call_args_list) == 2
    with patch.object(game.ui, "draw_pickup_prompt"):
        baseline = render_image(game)
    assert ImageChops.difference(shown.convert("RGB"), baseline.convert("RGB")).getbbox() is not None
    push_key(pico2d.SDLK_g)
    tick(game)
    assert world.player.weapon == "combat_knife" and item not in world.stage.drop_items
    assert world.player.sprite_image == config.WEAPON_POSE_IMAGES["combat_knife"]
    for repeat in (True, False):
        push_key(pico2d.SDLK_g, repeat=repeat)
        tick(game, 6)
        assert world.player.weapon == "combat_knife" and not world.stage.drop_items
    push_key(pico2d.SDLK_g, down=False)
    game.handle_events()
    world.stage.drop_items.append(DropItem("steel_pipe", world.player.x, world.player.ground_y))
    tap(game, pico2d.SDLK_g)
    assert world.player.weapon == "steel_pipe"
    assert [drop.kind for drop in world.stage.drop_items] == ["combat_knife"]
    capture(game, "weapon_swap_to_pipe")
    tick(game, 30)
    assert world.stage.drop_items[0].grounded
    tap(game, pico2d.SDLK_g)
    assert world.player.weapon == "combat_knife"
    assert [drop.kind for drop in world.stage.drop_items] == ["steel_pipe"]
    tap(game, pico2d.SDLK_g)
    assert world.player.weapon is None
    assert sorted(drop.kind for drop in world.stage.drop_items) == ["combat_knife", "steel_pipe"]
    print("PASS: visible G hint pixels, SDL pickup, held/repeated G suppression, nearest-floor "
          "swap priority, conservation of both weapons and empty-floor discard.")


def check_pose_frames(game):
    for kind, name in config.WEAPON_POSE_IMAGES.items():
        world = setup(game, kind)
        tap(game, pico2d.SDLK_g)
        player = world.player
        texture = game.assets.images[name]
        assert (texture.w, texture.h) == (2048, config.WEAPON_SHEET_ROWS[kind] * 256)
        for facing in (-1, 1):
            player.facing = facing
            for state, row in config.WEAPON_POSE_ROWS[kind].items():
                player.animation.set_state(state)
                player.jump_height = 150 if state == "JUMP" else 0
                fps = player.animation.definitions[state][1]
                for frame in range(8):
                    game.handle_events()
                    player.animation.elapsed = (frame + 0.1) / fps
                    tile = game.assets.frames[name][row - 1][frame]
                    with patch.object(texture, "clip_composite_draw", wraps=texture.clip_composite_draw) as draw:
                        if frame == 3 and facing == 1:
                            capture(game, f"weapon_{kind}_{state.lower()}")
                        else:
                            render_image(game)
                    assert draw.call_count == 1
                    args = draw.call_args.args
                    assert args[:4] == tuple(tile["clip"])
                    assert args[5] == ("h" if facing < 0 else "")
                    assert args[8:10] == (tile["clip"][2] * config.WEAPON_POSE_SCALE,
                                         tile["clip"][3] * config.WEAPON_POSE_SCALE)
                    assert abs(args[7] - args[9] / 2 - player.y) < 1e-8
    print("PASS: equipped knife and pipe sheets, movement/hit/death poses x 8 frames x 2 facings, "
          "exact clips/0.75 scale/feet alignment; pipe death uses its ninth row.")


def check_hit_recovery(game):
    for kind, name in config.WEAPON_POSE_IMAGES.items():
        for facing in (-1, 1):
            world = setup(game, kind)
            tap(game, pico2d.SDLK_g)
            player = world.player
            player.facing = facing
            world.enemies = [ready_enemy(player.x - 80)]
            tick(game)
            assert (player.hp, player.state, player.weapon) == (480, "HIT", kind)
            assert (player.sprite_image, player.sprite_row) == (name, config.WEAPON_POSE_ROWS[kind]["HIT"])
            frames = {player.animation.frame}
            for frame in range(15):
                if frame == 5:
                    elapsed = player.animation.elapsed
                    world.enemies.append(ready_enemy(player.x + 80, -1))
                tick(game)
                if frame == 5:
                    assert player.hp == 460 and player.animation.elapsed > elapsed
                    capture(game, f"weapon_{kind}_quick_hit_{facing}")
                if player.state != "HIT":
                    break
                frames.add(player.animation.frame)
                assert (player.sprite_image, player.sprite_row) == (name, config.WEAPON_POSE_ROWS[kind]["HIT"])
                render_image(game)
            assert frames == set(range(8)), (kind, facing, frames)
            assert (player.state, player.weapon, player.facing, player.hp) == ("IDLE", kind, facing, 460)
            assert (frame + 1) / 60 <= 0.25
            assert (player.sprite_image, player.sprite_row) == (name, 1)
            texture = game.assets.images[name]
            with patch.object(texture, "clip_composite_draw", wraps=texture.clip_composite_draw) as draw:
                capture(game, f"weapon_{kind}_quick_hit_idle_{facing}")
            tile = game.assets.frames[name][0][player.animation.frame]
            assert draw.call_count == 1 and draw.call_args.args[:4] == tuple(tile["clip"])
            assert draw.call_args.args[5] == ("h" if facing < 0 else "")
            player.take_damage(config.MAX_HP)
            tick(game, 15)
            death_row = config.WEAPON_POSE_ROWS[kind].get("DYING", 5)
            assert (player.state, player.sprite_row, player.hp) == ("DYING", death_row, 0)
            tick(game, 60)
            assert player.state == "DEAD"
    print("PASS: SDL G pickup + real enemy hits for both weapons/facings: all 8 HIT poses "
          "play in about 0.2s before the exact equipped IDLE returns; staggered hits deal "
          "500->480->460 without restarting recovery, and lethal hits stay in death states.")


def check_air_drop_and_lifetime(game):
    textures = dict(game.assets.images)
    for kind in config.WEAPON_POSE_IMAGES:
        world = setup(game, kind)
        tap(game, pico2d.SDLK_g)
        tap(game, pico2d.SDLK_SPACE)
        tick(game, 12)
        assert world.player.jump_height > 0 and world.player.weapon == kind
        tap(game, pico2d.SDLK_g)
        assert world.player.weapon is None and len(world.stage.drop_items) == 1
        item = world.stage.drop_items[0]
        assert item.jump_height > 0 and item.vy < 0
        assert world.pickup_item is None
        capture(game, f"weapon_{kind}_air_discard")
        previous = item.jump_height
        tick(game, 6)
        assert item.jump_height < previous
        tick(game, 60)
        assert item.grounded and world.pickup_item is item
        capture(game, f"weapon_{kind}_discard_landed")
        tap(game, pico2d.SDLK_u)
        with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as text:
            capture(game, f"weapon_{kind}_prompt_with_help_hidden")
        assert [call.args[2] for call in text.call_args_list] == ["G", "G", "500 / 500", "P 무적 OFF"]
        original_x = world.player.x
        world.player.x = item.x + config.WEAPON_PICKUP_RANGE + 1
        with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as text:
            render_image(game)
        assert all(call.args[2] != "G" for call in text.call_args_list)
        world.player.x = original_x
        tap(game, pico2d.SDLK_g)
        assert world.player.weapon == kind
        tap(game, pico2d.SDLK_u)
        world.select_stage(1)
        assert world.player.weapon == kind
        world.stage.arrows_visible = True
        world.player.x, world.player.vx = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN, config.RUN_SPEED
        assert world.try_stage_transition() and world.stage_loading
        tap(game, pico2d.SDLK_g)
        game.update(config.STAGE_LOADING_DURATION)
        assert world.stage_index == 2 and world.player.weapon == kind
        tap(game, pico2d.SDLK_F5)
        assert game.world.player.weapon is None
        assert all(drop.grounded for stage in game.world.stages for drop in stage.drop_items)
        assert all(game.assets.images[name] is texture for name, texture in textures.items())
    world = setup(game)
    world.select_stage(2)
    world.stage.traffic = None
    world.stage.drop_items.clear()
    world.player.weapon = "steel_pipe"
    world.player.ground_y = config.CAR_GROUND_Y
    tap(game, pico2d.SDLK_g)
    item = world.stage.drop_items[0]
    assert item.ground_y - config.DROP_ITEM_SHADOW_HALF_DEPTH >= 203
    assert item.ground_y + config.DROP_ITEM_HEIGHT <= 241
    tick(game, 60)
    assert item.grounded
    baseline = without_items(game)
    image = capture(game, "weapon_city_discard_keeps_sidewalk")
    check_city_sidewalk_pixels(game, image, baseline)
    print("PASS: SDL Space + G releases both weapons in midair, gravity lands them without "
          "automatic reacquisition; the nearby pickup hint works with help hidden, equipped travel/loading "
          "persists, loading G is consumed, F5 clears equipment/falling drops with texture "
          "reuse, and city road discards still land on the sidewalk.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_pickup_hint_and_input(game)
        check_pose_frames(game)
        check_hit_recovery(game)
        check_air_drop_and_lifetime(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
