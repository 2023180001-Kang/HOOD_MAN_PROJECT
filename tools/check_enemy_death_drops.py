"""Verify single-club death-only drops and the supplied six-frame sheet in SDL."""

from pathlib import Path
import random
import sys
from unittest.mock import patch

from PIL import ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from drop_items import MetalClubDrop
from enemy import Enemy
from enemy02 import Enemy02
from game import Game
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, tick
from world import World


def release(game, key):
    push_key(key, down=False)
    game.handle_events()


def clubs(world):
    return [item for item in world.stage.drop_items if isinstance(item, MetalClubDrop)]


def check_source_frames(game):
    game.world = World()
    world = game.world
    texture = game.assets.images[config.METAL_CLUB_ITEM_IMAGE]
    assert (texture.w, texture.h) == (1536, 256)
    world.camera.offset_x, world.camera.offset_y = 4, -3
    for facing in (-1, 1):
        item = MetalClubDrop(world.player.x - 220, 90, facing)
        world.stage.drop_items = [item]
        with patch.object(game.assets, "draw_drop_item"):
            baseline = render_image(game)
        for frame, (top, bottom) in enumerate(config.METAL_CLUB_ITEM_BODY_BOUNDS):
            item.elapsed = (frame + 0.1) / config.DROP_ITEM_FPS
            with patch.object(texture, "clip_composite_draw", wraps=texture.clip_composite_draw) as draw:
                image = (capture(game, f"metal_club_source_{facing}")
                         if frame == 3 else render_image(game))
            draw.assert_called_once()
            args = draw.call_args.args
            assert args[:4] == (frame * 256, 256 - bottom, 256, bottom - top)
            assert args[5] == ("h" if facing < 0 else "")
            assert args[6] == item.x - world.camera.render_x
            assert args[7] - args[9] / 2 == item.ground_y - world.camera.render_y
            delta = ImageChops.difference(image.convert("RGB"), baseline.convert("RGB"))
            box = delta.getbbox()
            assert box is not None
            assert abs(box[3] - (config.SCREEN_HEIGHT - item.ground_y
                                + world.camera.render_y)) <= 2
    item.jump_height = 70
    capture(game, "metal_club_airborne")
    print("PASS: supplied MetalClub 1536x256 sheet, all 6 frames/both facings; "
          "exact clips, 0.25 scale, fixed floor contact and camera offsets; airborne drawing works.")


def kill_with_s(game, enemy_type=Enemy, *, floor=0):
    game.world = World(rng=random.Random(41), item_rng=random.Random(5))
    world = game.world
    world.player.floor = floor
    world.player.x, world.player.ground_y = 1050, 476 if floor else 100
    world.stage.constrain_actor(world.player)
    enemy = enemy_type(world.player.x + 70, -1, ground_y=world.player.ground_y)
    enemy.floor = floor
    enemy.hp, enemy.cooldown = 40, 100
    enemy.animation.set_state("HIT")
    world.stage.constrain_actor(enemy)
    world.enemies = [enemy]
    assert not clubs(world) and len(world.stage.drop_items) == 15
    push_key(pico2d.SDLK_s)
    for _ in range(60):
        tick(game)
        if not enemy.alive:
            break
    release(game, pico2d.SDLK_s)
    assert not enemy.alive
    return world, enemy


def check_death_and_no_pickup(game):
    world, enemy = kill_with_s(game)
    assert len(clubs(world)) == 1 and len(world.stage.drop_items) == 16
    item = clubs(world)[0]
    assert item.jump_height > 0 and not item.collectible
    assert item.image_name == config.METAL_CLUB_ITEM_IMAGE
    capture(game, "metal_club_death_drop")
    tick(game, 12)
    assert item.vy < 0 and item.jump_height > 0
    capture(game, "metal_club_death_falling")
    tick(game, 360)
    assert enemy not in world.enemies and item.grounded
    assert clubs(world) == [item]
    capture(game, "metal_club_death_landed")
    # Isolate the new non-collectible club from the existing collectible layout.
    world.stage.drop_items[:] = [item]
    world.player.x, world.player.ground_y = item.x, item.ground_y
    world.player.vx = world.player.ground_vy = 0
    assert world.pickup_item is None
    push_key(pico2d.SDLK_g)
    tick(game)
    release(game, pico2d.SDLK_g)
    assert world.player.weapon is None and clubs(world) == [item]
    assert world.pickup_item is None
    capture(game, "metal_club_no_pickup")
    print("PASS: SDL S kills a single-club enemy and emits exactly one MetalClub; "
          "it falls, survives corpse fade and stays non-collectible with no G prompt/equipment.")


def check_type_floor_and_restart(game):
    world, _ = kill_with_s(game, Enemy02)
    assert not clubs(world) and len(world.stage.drop_items) == 15
    world, _ = kill_with_s(game, floor=1)
    assert len(clubs(world)) == 1
    item = clubs(world)[0]
    assert item.floor == 1
    tick(game, 40)
    assert item.grounded and item.floor == 1
    capture(game, "metal_club_upstairs")
    textures = dict(game.assets.images)
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert not game.world.enemies
    for stage in game.world.stages:
        assert len(stage.drop_items) == 15
        assert not any(isinstance(drop, MetalClubDrop) for drop in stage.drop_items)
    assert all(game.assets.images[name] is image for name, image in textures.items())
    capture(game, "metal_club_restart")
    print("PASS: dual-club enemy excluded; upper-floor death drops/lands on its own floor; "
          "F5 clears death drops, restores 15 initial items and reuses every texture.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        game.ui.details_visible = False
        check_source_frames(game)
        game.ui.details_visible = True
        check_death_and_no_pickup(game)
        check_type_floor_and_restart(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
