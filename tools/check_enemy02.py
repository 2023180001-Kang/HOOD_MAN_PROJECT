"""Verify city spawns, both enemy02 attacks and reactions in an actual SDL window."""

from pathlib import Path
import random
import sys
from time import perf_counter
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from enemy import Enemy
from enemy02 import Enemy02
from game import Game
from tools.check_counters import release, start_follow_up, wait_for_hold
from tools.check_render import capture
from tools.check_runtime import push_key, tick
from traffic import Car
from world import World


def encounter(game, kind="clubs", side=1):
    game.world = World(rng=random.Random(23))
    world = game.world
    world.stage_index = 3
    enemy = world.enemies[0]
    world.enemies = [enemy]  # Isolate the selected attack's pixels and exact damage.
    enemy.x = enemy.previous_x = world.player.x + side * 80
    enemy.ground_y = enemy.previous_ground_y = world.player.ground_y
    enemy.facing = -side
    enemy.rng = Mock()
    enemy.rng.choice.return_value = kind
    enemy.start_attack()
    return world, enemy


def set_frame(world, enemy, frame):
    enemy.animation.elapsed = (frame + 0.05) / enemy.attack_fps
    enemy.update(0, world.player)


def check_city_selection(game):
    game.world = World(rng=random.Random(32))
    textures = dict(game.assets.images)
    for number in range(1, 11):
        key = getattr(pico2d, f"SDLK_{number % 10}")
        push_key(key)
        tick(game)
        release(game, key)
        world = game.world
        expected = Enemy02 if number in (3, 4) else Enemy
        assert world.stage_index == number - 1
        assert len(world.enemies) == world.spawner.spawned_count == 4
        assert all(type(enemy) is expected for enemy in world.enemies)
        assert all(world.stage.spawn_area.contains(enemy.x, enemy.ground_y, enemy.boundary_padding)
                   for enemy in world.enemies)
        if number in (3, 4):
            for side, camera_x in (("left", 0), ("right", config.WORLD_WIDTH - config.SCREEN_WIDTH)):
                world.camera.x = camera_x
                with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as draw:
                    capture(game, f"enemy02_city_{number - 2}_{side}")
                assert any("몽둥이 60 / 착지 80" in call.args[2] for call in draw.call_args_list)
        assert all(game.assets.images[name] is image for name, image in textures.items())
    print("PASS: SDL stages 3/4 use exactly four enemy02 actors; other stages keep the old type; "
          "spawn floors/texture reuse and the real 60/80 HUD text verified.")


def check_attack_rendering(game):
    texture = game.assets.images[config.ENEMY02_IMAGE]
    for side in (-1, 1):
        for kind, row in (("clubs", 4), ("slam", 5)):
            world, enemy = encounter(game, kind, side)
            for frame in range(8):
                set_frame(world, enemy, frame)
                tile = game.assets.frames[config.ENEMY02_IMAGE][row - 1][frame]
                with patch.object(texture, "clip_composite_draw", wraps=texture.clip_composite_draw) as draw:
                    capture(game, f"enemy02_{kind}_{side}_{frame}")
                args = draw.call_args.args
                assert args[:4] == tuple(tile["clip"])
                assert args[5] == ("h" if side > 0 else "")
                assert abs(args[7] - args[9] / 2 - enemy.y) < 1e-8
                height = (36 if frame == 2 else 19.5 if frame == 3 else 0) if kind == "slam" else 0
                assert enemy.jump_height == height
    print("PASS: both source attack rows, 8 frames x 2 facings, exact clips/flips and real "
          "36/19.5px airborne feet without a doubled render offset.")


def check_damage(game):
    for side in (-1, 1):
        for kind, before_active, damage in (("clubs", 2, 60), ("slam", 4, 80)):
            world, enemy = encounter(game, kind, side)
            set_frame(world, enemy, before_active)
            assert enemy.attack_box is None and world.player.hp == 500
            for _ in range(20):
                tick(game)
                if enemy.has_hit:
                    break
            assert world.player.hp == 500 - damage and enemy.has_hit
            assert len(world.effects) == 1 and not world.damage_numbers
            assert world.camera.shake_remaining > 0
            capture(game, f"enemy02_{kind}_{side}_impact")
            tick(game, 6)
            assert world.player.hp == 500 - damage
    world, enemy = encounter(game, "slam")
    set_frame(world, enemy, 5)
    push_key(pico2d.SDLK_p)
    tick(game)
    release(game, pico2d.SDLK_p)
    assert enemy.has_hit and world.player.hp == 500 and not world.effects
    print("PASS: both directions deal clubs=60 / landed slam=80 once per whole motion, "
          "with real blood/HP/shake; SDL P consumes a swing without damage/effects.")


def check_counters_and_death(game):
    for key in "hjkl":
        world, enemy = encounter(game)
        set_frame(world, enemy, 1)
        keycode = getattr(pico2d, f"SDLK_{key}")
        push_key(keycode)
        tick(game)
        release(game, keycode)
        wait_for_hold(game)
        assert enemy.sprite_image == config.ENEMY02_IMAGE
        capture(game, f"enemy02_counter_{key}_hold")
        start_follow_up(game)
        for _ in range(180):
            tick(game)
            assert enemy.sprite_image == config.ENEMY02_IMAGE
            if world.counter is None and enemy.counter_move is None:
                break
        assert enemy.hp == 120 and enemy.state == "IDLE"
    world, enemy = encounter(game)
    enemy.take_damage(200)
    tick(game, 60)
    assert (enemy.state, enemy.animation.row, enemy.animation.frame) == ("DEAD", 7, 7)
    assert enemy.sprite_image == config.ENEMY02_IMAGE
    capture(game, "enemy02_defeated")
    enemy.corpse_elapsed = 3.5
    texture = game.assets.images[config.ENEMY02_IMAGE]
    with patch.object(texture, "opacify", wraps=texture.opacify) as alpha:
        capture(game, "enemy02_corpse_half")
    assert [call.args[0] for call in alpha.call_args_list] == [0.5, 1.0]
    print("PASS: all four SDL counter/carry/A follow-ups preserve enemy02's identity and "
          "single 80 damage; own row-7 death/fade and shared texture alpha restoration verified.")


def check_city_car(game):
    world, enemy = encounter(game)
    world.stage_index = 2
    world.enemies = [enemy]
    world.player.ground_y = enemy.ground_y = config.CAR_GROUND_Y
    enemy.x = enemy.previous_x = world.player.x
    world.stage.traffic.car = Car(world.player.x, 1, 1400)
    world.player.invincible = True
    tick(game)
    assert world.player.hp == enemy.hp == 0 and enemy.state == "CAR_HIT"
    assert enemy.sprite_image == config.ENEMY02_IMAGE and enemy.animation.row == 7
    capture(game, "enemy02_car_hit")
    tick(game, 60)
    assert (enemy.state, enemy.animation.row, enemy.animation.frame) == ("DEAD", 7, 7)
    capture(game, "enemy02_car_dead")
    print("PASS: city road collision still kills player/new enemy immediately, including P; "
          "enemy02 keeps its own fall and final pose.")


def check_natural_encounter_and_restart(game):
    game.world = World(rng=random.Random(19))
    world = game.world
    world.stage_index = 3
    world.player.invincible = True
    seen = set()
    spawn_state = world.spawner.rng.getstate()
    for _ in range(480):
        tick(game)
        seen.update(enemy.attack_kind for enemy in world.enemies if enemy.state == "ATTACK")
    assert seen == {"clubs", "slam"}
    assert len(world.enemies) == world.spawner.spawned_count == 4
    assert world.player.hp == 500 and world.spawner.rng.getstate() == spawn_state
    capture(game, "enemy02_city_combat")
    start = perf_counter()
    frames = game.run(max_frames=180)
    seconds = perf_counter() - start
    assert frames == 180 and len(world.enemies) == 4
    print(f"BENCHMARK: 4 enemy02 actors + random attacks/jump/HP/UI: "
          f"{frames} frames / {seconds:.3f}s = {frames / seconds:.2f} FPS.")
    old_enemies = [enemy for stage in world.stages for enemy in stage.enemies]
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert game.world.stage_index == 0 and game.world.player.hp == 500
    for index, stage in enumerate(game.world.stages):
        assert len(stage.enemies) == stage.spawner.spawned_count == 4
        expected = Enemy02 if index in (2, 3) else Enemy
        assert all(type(enemy) is expected and enemy not in old_enemies and enemy.hp == 200
                   for enemy in stage.enemies)
    print("PASS: natural four-enemy city combat selects both attacks without touching spawn RNG; "
          "SDL F5 creates fresh full-health groups with the correct stage-specific type.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_city_selection(game)
        check_attack_rendering(game)
        check_damage(game)
        check_counters_and_death(game)
        check_city_car(game)
        check_natural_encounter_and_restart(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
