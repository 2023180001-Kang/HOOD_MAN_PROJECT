"""Verify SDL M selection, numeric summons, per-map state and mixed-enemy play."""

import ctypes
from pathlib import Path
import random
import sys
from time import perf_counter
from unittest.mock import patch

from PIL import ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d
from sdl2 import SDL_Event, SDL_PushEvent, SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST

import config
from axe_enemy import AxeEnemy
from enemy import Enemy
from enemy02 import Enemy02
from game import Game
from researcher import Researcher
from shield_soldier import ShieldSoldier
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, release, tick
from world import World


TYPES = (Enemy, Enemy, Enemy02, Enemy02, AxeEnemy, Enemy,
         Researcher, Researcher, ShieldSoldier, ShieldSoldier, Enemy, Enemy)


def tap(game, key):
    push_key(key)
    tick(game)
    release(game, key)


def fresh(game, index=8):
    game.world = World(rng=random.Random(23), item_rng=random.Random(5))
    game.world.select_stage(index)
    game.world.player.invincible = True
    return game.world


def select_source(game, source):
    for _ in range(source + 1):
        tap(game, pico2d.SDLK_m)
    assert game.world.stage.spawn_enemy_stage_index == source


def check_cycle_and_hud(game):
    textures = dict(game.assets.images)
    font = game.assets.font
    for index in range(1, len(config.STAGE_IMAGES)):
        world = fresh(game, index)
        assert world.stage.spawn_cycle_index is None and world.spawner.enemy_type is TYPES[index]
        for ordinal in range(13):
            tap(game, pico2d.SDLK_m)
            source = ordinal % len(TYPES)
            assert world.stage_index == index and world.stage.spawn_enemy_stage_index == source
            assert world.spawner.enemy_type is TYPES[source]
            assert not world.enemies and world.spawner.spawned_count == 0
            if index == 8 and ordinal in (0, 1, 2, 4, 6, 8, 11, 12):
                with patch.object(font, "draw", wraps=font.draw) as text:
                    image = capture(game, f"spawn_cycle_lab_m_{ordinal + 1}")
                assert any("M 소환 적 순환" in call.args[2] and f"{source + 1}번 맵" in call.args[2]
                           for call in text.call_args_list)
                draw_text = font.draw
                with patch.object(font, "draw", side_effect=lambda x, y, label, color:
                                  draw_text(x, y, label, color) if not label.startswith("M ") else None):
                    clean = render_image(game)
                box = ImageChops.difference(image.convert("RGB"), clean.convert("RGB")).getbbox()
                assert box is not None and box[0] >= 740 and 620 <= box[1] < box[3] <= 675, box
    world = fresh(game, 0)
    tap(game, pico2d.SDLK_2)
    enemies = tuple(world.enemies)
    for _ in range(15):
        tap(game, pico2d.SDLK_m)
    assert world.stage.spawn_cycle_index is None and world.spawner.enemy_type is Enemy
    assert tuple(world.enemies) == enemies and world.spawner.spawned_count == 2
    capture(game, "spawn_cycle_first_map_fixed")
    assert all(game.assets.images[name] is texture for name, texture in textures.items())
    print("PASS: all 11 nonfirst maps use M to select stage 1, then all 12 stage entries and wrap; "
          "M never spawns, duplicate native types keep separate source entries, HUD pixels update; "
          "first-map M is fixed and textures are reused.")


def check_repeat_and_numbers(game):
    world = fresh(game)
    push_key(pico2d.SDLK_m)
    tick(game)
    for repeat in (True, False):
        push_key(pico2d.SDLK_m, repeat=repeat)
        tick(game, 10)
        assert world.stage.spawn_enemy_stage_index == 0 and not world.enemies
    release(game, pico2d.SDLK_m)
    tap(game, pico2d.SDLK_m)
    assert world.stage.spawn_enemy_stage_index == 1
    for source, expected in enumerate(TYPES):
        for prefix in ("", "KP_"):
            world = fresh(game)
            select_source(game, source)
            key = getattr(pico2d, f"SDLK_{prefix}3")
            tap(game, key)
            assert len(world.enemies) == world.spawner.spawned_count == 3
            assert all(type(enemy) is expected and enemy.hp == expected.max_hp
                       and world.stage.spawn_area.contains(enemy.x, enemy.ground_y,
                                                           enemy.boundary_padding)
                       for enemy in world.enemies)
    for prefix in ("", "KP_"):
        for count in config.SPAWN_COUNTS:
            world = fresh(game)
            source = 6 if prefix else 8
            select_source(game, source)
            key = getattr(pico2d, f"SDLK_{prefix}{count}")
            push_key(key)
            tick(game)
            assert len(world.enemies) == count and all(type(enemy) is TYPES[source] for enemy in world.enemies)
            push_key(key, repeat=True)
            tick(game, 3)
            assert len(world.enemies) == count
            release(game, key)
            tap(game, key)
            assert len(world.enemies) == world.spawner.spawned_count == count * 2
    world = fresh(game, 6)
    for key in (pico2d.SDLK_2, pico2d.SDLK_m, pico2d.SDLK_KP_5):
        push_key(key)
    tick(game)
    for key in (pico2d.SDLK_2, pico2d.SDLK_m, pico2d.SDLK_KP_5):
        release(game, key)
    assert len(world.enemies) == 7 and all(type(enemy) is Enemy for enemy in world.enemies)
    print("PASS: SDL M held/repeated KEYDOWN cannot skip a source; all 12 sources work with both "
          "numeric rows, all 18 count keys retain counts/latching/additional batches, "
          "and same-tick M + 2 + keypad-5 creates seven newly selected actors.")


def check_preservation_and_lifecycle(game):
    world = fresh(game)
    tap(game, pico2d.SDLK_2)
    shields = tuple(world.enemies)
    shields[0].take_damage(40)
    tap(game, pico2d.SDLK_m)
    tap(game, pico2d.SDLK_1)
    assert tuple(world.enemies[:2]) == shields and [enemy.hp for enemy in shields] == [360, 400]
    assert all(type(enemy) is ShieldSoldier for enemy in shields)
    assert type(world.enemies[-1]) is Enemy and world.enemies[-1].hp == 200
    capture(game, "spawn_cycle_existing_shields_and_new_thug")
    world.select_stage(6)
    assert world.stage.spawn_cycle_index is None and world.spawner.enemy_type is Researcher
    tap(game, pico2d.SDLK_m)
    world.select_stage(8)
    assert world.stage.spawn_enemy_stage_index == 0 and world.enemies[:2] == list(shields)
    tap(game, pico2d.SDLK_m)
    assert world.stage.spawn_enemy_stage_index == 1

    world = fresh(game)
    push_key(pico2d.SDLK_m)
    game.handle_events(title_screen=True)
    game.update(config.FIXED_DT)
    release(game, pico2d.SDLK_m)
    assert world.stage.spawn_cycle_index is None
    push_key(pico2d.SDLK_m)
    push_key(pico2d.SDLK_9)
    event = SDL_Event()
    event.type = SDL_WINDOWEVENT
    event.window.event = SDL_WINDOWEVENT_FOCUS_LOST
    assert SDL_PushEvent(ctypes.byref(event)) == 1
    tick(game)
    assert world.stage.spawn_cycle_index is None and not world.enemies
    assert not world.controls.held and not world.controls.pressed
    select_source(game, 2)
    world.player.x, world.player.vx = config.STAGE_EXIT_MARGIN, -config.RUN_SPEED
    push_key(pico2d.SDLK_LEFT)
    tap(game, pico2d.SDLK_n)
    assert world.stage_loading
    push_key(pico2d.SDLK_m)
    push_key(pico2d.SDLK_9)
    tick(game, 30)
    assert world.stages[8].spawn_enemy_stage_index == 2
    with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as text:
        capture(game, "spawn_cycle_loading_ignores_m")
    assert not text.called
    game.update(2)
    release(game, pico2d.SDLK_LEFT)
    release(game, pico2d.SDLK_9)
    push_key(pico2d.SDLK_m)  # Held across loading: no fresh press.
    tick(game)
    assert world.stage_index == 7 and world.stage.spawn_cycle_index is None and not world.enemies
    release(game, pico2d.SDLK_m)
    tap(game, pico2d.SDLK_m)
    assert world.stage.spawn_enemy_stage_index == 0
    world.player.invincible = False
    world.player.take_damage(500)
    tap(game, pico2d.SDLK_m)
    assert world.stage.spawn_enemy_stage_index == 0
    tap(game, pico2d.SDLK_F5)
    assert world.stage_index == 0 and world.player.hp == 500
    assert all(stage.spawn_cycle_index is None and stage.spawn_enemy_stage_index == stage.index
               and stage.spawner.enemy_type is TYPES[stage.index]
               and not stage.enemies and stage.spawner.spawned_count == 0 for stage in world.stages)
    print("PASS: M leaves old shields/HP intact while new numbers create thugs; selections are "
          "independent per map and survive revisits; focus loss/title/death/loading consume M without "
          "reservation, held loading input does not replay, F5 restores all native selections.")


def check_mixed_combat(game):
    world = fresh(game, 6)
    originals = dict(game.assets.images)
    for source in range(9):
        tap(game, pico2d.SDLK_m)
        if source in (0, 2, 4, 6, 8):
            tap(game, pico2d.SDLK_1)
    assert {type(enemy) for enemy in world.enemies} == {Enemy, Enemy02, AxeEnemy, Researcher, ShieldSoldier}
    for index, enemy in enumerate(world.enemies):
        enemy.x = enemy.previous_x = world.player.x + (-1 if index % 2 else 1) * (350 + index * 20)
        enemy.ground_y = enemy.previous_ground_y = world.player.ground_y + (index % 3 - 1) * 16
    spawn_rng = world.spawner.rng.getstate()
    for _ in range(900):
        tick(game)
        assert all(world.stage.walkable.contains(enemy.x, enemy.ground_y, enemy.boundary_padding)
                   and enemy.hp == enemy.max_hp for enemy in world.enemies)
    assert world.player.hp == 500 and world.spawner.rng.getstate() == spawn_rng
    capture(game, "spawn_cycle_five_types_factory_combat")
    tap(game, pico2d.SDLK_u)
    assert not game.ui.details_visible
    source = world.stage.spawn_enemy_stage_index
    tap(game, pico2d.SDLK_m)
    assert world.stage.spawn_enemy_stage_index == source + 1
    tap(game, pico2d.SDLK_u)
    assert game.ui.details_visible
    start = perf_counter()
    frames = game.run(max_frames=180)
    seconds = perf_counter() - start
    assert all(game.assets.images[name] is texture for name, texture in originals.items())
    print(f"BENCHMARK: five mixed thug/city/axe/researcher/shield actors + combat/HP/HUD: "
          f"{frames} frames / {seconds:.3f}s = {frames / seconds:.2f} FPS.")
    print("PASS: all five enemy classes coexist and naturally fight on the expanded first factory "
          "interior floor, retain own HP/art, stay bounded and preserve spawn RNG; U hides help "
          "without disabling M selection.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_cycle_and_hud(game)
        check_repeat_and_numbers(game)
        check_preservation_and_lifecycle(game)
        check_mixed_combat(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
