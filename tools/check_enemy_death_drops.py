"""Verify enemy weapon drops and G interactions through SDL."""

from pathlib import Path
import random
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from drop_items import DropItem
from enemy import Enemy
from enemy02 import Enemy02
from game import Game
from sniper import Sniper
from tools.check_render import capture
from tools.check_runtime import push_key, release, tick
from world import World


def tap(game, key):
    push_key(key)
    tick(game)
    release(game, key)


def kill_with_s(game, enemy_type=Enemy, *, selected=False):
    game.world = World(rng=random.Random(41), item_rng=random.Random(5))
    world = game.world
    world.player.invincible = True
    if selected:
        world.select_stage(8)
        tap(game, pico2d.SDLK_m)
        assert world.spawner.enemy_type is Enemy and not world.enemies
        tap(game, pico2d.SDLK_1)
        enemy = world.enemies[0]
        assert type(enemy) is Enemy
    else:
        enemy = enemy_type(0)
        world.enemies = [enemy]
    world.player.x, world.player.ground_y = 1050, 100
    world.stage.constrain_actor(world.player)
    enemy.x, enemy.ground_y = world.player.x + 70, world.player.ground_y
    enemy.facing, enemy.hp, enemy.cooldown = -1, 15, 100
    enemy.animation.set_state("HIT")
    world.stage.constrain_actor(enemy)
    items = list(world.stage.drop_items)
    assert len(items) == 15
    push_key(pico2d.SDLK_s)
    for _ in range(60):
        tick(game)
        if not enemy.alive:
            break
    release(game, pico2d.SDLK_s)
    assert not enemy.alive and enemy.state == "DYING"
    assert world.stage.drop_items[:len(items)] == items
    assert [number.damage for number in world.damage_numbers] == [15]
    return world, enemy, items


def check_death_drops(game):
    assert "HoodMan_MetalClub_Item_6frames_1536x256.png" not in game.assets.images
    for enemy_type, selected, name, expected in (
        (Enemy, False, "single_club", ["steel_club"]),
        (Enemy02, False, "dual_club", []),
        (Sniper, False, "sniper", []),
        (Enemy, True, "m_selected", ["steel_club"]),
    ):
        world, enemy, items = kill_with_s(game, enemy_type, selected=selected)
        drops = world.stage.drop_items[len(items):]
        assert [drop.kind for drop in drops] == expected
        with patch.object(game.assets, "draw_drop_item",
                          wraps=game.assets.draw_drop_item) as draw:
            capture(game, f"enemy_drop_{name}_death")
        assert all(any(call.args[0] is drop for call in draw.call_args_list) for drop in drops)
        tick(game, 360)
        assert enemy not in world.enemies and world.stage.drop_items == items + drops
        assert all(drop.grounded for drop in drops)
        capture(game, f"enemy_drop_{name}_faded")
    print("PASS: clubs drop once and land. Dual-club enemies and snipers leave no item.")


def check_existing_weapons_and_restart(game):
    world = game.world
    world.stage.drop_items.clear()
    assert world.pickup_item is None
    tap(game, pico2d.SDLK_g)
    assert world.player.weapon is None and not world.stage.drop_items
    world.stage.drop_items.append(DropItem(
        "combat_knife", world.player.x + 10, world.player.ground_y))
    tap(game, pico2d.SDLK_g)
    assert world.player.weapon == "combat_knife" and not world.stage.drop_items
    world.stage.drop_items.append(DropItem(
        "steel_pipe", world.player.x + 10, world.player.ground_y))
    tap(game, pico2d.SDLK_g)
    assert world.player.weapon == "steel_pipe"
    tap(game, pico2d.SDLK_g)
    assert world.player.weapon is None
    tick(game, 60)
    assert len(world.stage.drop_items) == 2
    assert {item.kind for item in world.stage.drop_items} == set(config.DROP_ITEM_IMAGES)
    assert all(item.grounded for item in world.stage.drop_items)
    capture(game, "no_enemy_drop_existing_weapons")
    textures = dict(game.assets.images)
    tap(game, pico2d.SDLK_F5)
    assert len(world.enemies) == config.STAGE_ENCOUNTER_SIZE and world.player.weapon is None
    for stage in world.stages:
        assert len(stage.drop_items) == 15
        assert {item.kind for item in stage.drop_items} == set(config.DROP_ITEM_IMAGES)
    assert all(game.assets.images[name] is image for name, image in textures.items())
    capture(game, "no_enemy_drop_restart")
    print("PASS: empty G remains a no-op; knife/pipe pickup, swap, discard/fall still work; "
          "F5 restores 15 weapons per stage and reuses existing textures.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_death_drops(game)
        check_existing_weapons_and_restart(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
