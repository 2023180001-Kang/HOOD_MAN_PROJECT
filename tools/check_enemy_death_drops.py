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
from drop_items import DropItem, MetalClubDrop
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
        item = MetalClubDrop(world.player.x - 220, 90, facing, jump_height=70)
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
            angle, left, base, right, _ = config.METAL_CLUB_ITEM_HORIZONTAL_POSES[frame]
            scale = config.METAL_CLUB_ITEM_SCALE
            assert args[:4] == (frame * 256, 256 - bottom, 256, bottom - top)
            assert args[4] == angle * facing
            assert args[5] == ("h" if facing < 0 else "")
            assert args[6] == item.x - world.camera.render_x - (left + right) * scale / 2 * facing
            assert abs(args[7] + base * scale
                       - item.ground_y - item.jump_height + world.camera.render_y) < 1e-9
            delta = ImageChops.difference(image.convert("RGB"), baseline.convert("RGB"))
            box = delta.getbbox()
            assert box is not None
            assert box[2] - box[0] >= 3 * (box[3] - box[1])
            assert abs(box[3] - (config.SCREEN_HEIGHT - item.ground_y - item.jump_height
                                + world.camera.render_y)) <= 2
    item.jump_height = 70
    capture(game, "metal_club_airborne")
    world.stage.drop_items = [
        DropItem("combat_knife", world.player.x - 360, 90),
        DropItem("steel_pipe", world.player.x - 240, 90),
        MetalClubDrop(world.player.x - 120, 90),
    ]
    capture(game, "metal_club_horizontal_comparison")
    print("PASS: supplied MetalClub 1536x256 sheet, all 6 airborne frames/both facings; "
          "horizontal silhouettes, mirrored rotations, exact clips, 0.25 scale, "
          "floor contact and camera offsets; knife/pipe/club align on the same floor.")


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
    position = item.x, item.ground_y
    with patch.object(game.assets, "draw_sprite"), patch.object(game.ui, "draw"):
        baseline = render_image(game).convert("RGB")
        for _ in range(12):
            tick(game, 10)
            assert item.frame == 0 and (item.x, item.ground_y) == position
            assert ImageChops.difference(render_image(game).convert("RGB"), baseline).getbbox() is None
    capture(game, "metal_club_grounded_still")
    print("PASS: landed MetalClub stays on frame 0 at the same position; "
          "rendered pixels remain identical across 2 seconds of simulation.")
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
    floor = int(config.STAGE_IMAGE in config.STAGE_UPPER_FLOOR_BOUNDS)
    world, _ = kill_with_s(game, floor=floor)
    assert len(clubs(world)) == 1
    item = clubs(world)[0]
    assert item.floor == floor
    tick(game, 40)
    assert item.grounded and item.floor == floor and item.frame == 0
    capture(game, f"metal_club_floor_{floor}")
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
    print("PASS: dual-club enemy excluded; death drops/lands on its victim's floor; "
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
