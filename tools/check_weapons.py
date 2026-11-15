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
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, tick
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
        assert (texture.w, texture.h) == (2048, 1536)
        for facing in (-1, 1):
            player.facing = facing
            for state, row in (("IDLE", 1), ("WALK", 2), ("RUN", 3),
                               ("JUMP", 4), ("HIT", 5), ("DYING", 6)):
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
    print("PASS: both new equipped 256x256-cell sheets, all 6 rows x 8 frames x 2 facings, "
          "exact clips/0.75 scale/feet alignment; HIT uses row 5 and death row 6.")


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
            capture(game, f"weapon_{kind}_hidden_prompt")
        assert [call.args[2] for call in text.call_args_list] == ["500 / 500"]
        tap(game, pico2d.SDLK_u)
        tap(game, pico2d.SDLK_g)
        assert world.player.weapon == kind
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
    assert item.ground_y - config.DROP_ITEM_SHADOW_HALF_DEPTH >= config.GROUND_Y
    tick(game, 60)
    assert item.grounded
    capture(game, "weapon_city_discard_keeps_sidewalk")
    print("PASS: SDL Space + G releases both weapons in midair, gravity lands them without "
          "automatic reacquisition; U hides/restores the prompt, equipped travel/loading "
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
        check_air_drop_and_lifetime(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
