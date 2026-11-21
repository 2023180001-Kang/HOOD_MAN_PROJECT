"""Validate the 2.5D floor through real SDL input, rendering and bounded crowds."""

from math import hypot
from pathlib import Path
import random
import sys
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from enemy import Enemy
from game import Game
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, tick
from ui import ENEMY_BOUNDS_COLOR, PLAYER_BOUNDS_COLOR
from world import World


def release(keys):
    for key in keys:
        push_key(key, down=False)


def inside(world):
    assert world.stage.walkable.contains(world.player.x, world.player.ground_y, world.player.boundary_padding)
    assert all(world.stage.walkable.contains(enemy.x, enemy.ground_y, enemy.boundary_padding)
               for enemy in world.enemies)


def shot(game, name):
    # Exercise the same floor overlay that F4 enables in normal gameplay.
    visible = game.ui.floor_bounds_visible
    game.ui.floor_bounds_visible = True
    try:
        return capture(game, name)
    finally:
        game.ui.floor_bounds_visible = visible


def check_floor_toggle(game):
    game.world = World(item_rng=random.Random(23))
    assert not game.ui.floor_bounds_visible
    game.ui.details_visible = False  # F4 lines must also work when U hides help.

    def key(code, down=True, repeat=False):
        push_key(code, down=down, repeat=repeat)
        game.handle_events()
        game.update(0)  # Keep the scene frozen for exact on/off pixel comparisons.

    baseline = render_image(game)
    key(pico2d.SDLK_F4)
    assert game.ui.floor_bounds_visible and not game.world.player.invincible
    image = capture(game, "floor_bounds_enabled")
    for color in (PLAYER_BOUNDS_COLOR, ENEMY_BOUNDS_COLOR):
        assert sum(pixel[:3] == color for pixel in image.get_flattened_data()) > 500
    for repeat in (True, False):
        key(pico2d.SDLK_F4, repeat=repeat)
        assert game.ui.floor_bounds_visible
    key(pico2d.SDLK_F4, down=False)
    key(pico2d.SDLK_F4)
    assert not game.ui.floor_bounds_visible
    assert render_image(game).tobytes() == baseline.tobytes()
    capture(game, "floor_bounds_disabled")
    key(pico2d.SDLK_F4, down=False)
    key(pico2d.SDLK_F4)

    for camera_x in (0, 640, config.WORLD_WIDTH - config.SCREEN_WIDTH):
        game.world.camera.x = camera_x
        for shake_y in (-4, 0, 4):
            game.world.camera.offset_y = shake_y
            with patch.object(pico2d, "draw_line", wraps=pico2d.draw_line) as draw:
                if shake_y == 0:
                    capture(game, f"floor_bounds_camera_{camera_x:g}")
                else:
                    render_image(game)
            lines = [call.args[:4] for call in draw.call_args_list
                     if call.args[4:] == PLAYER_BOUNDS_COLOR]
            assert len(lines) == 4 * len(game.world.stage.floor_areas)
            for index, area in enumerate(game.world.stage.floor_areas):
                outline = lines[index * 4:(index + 1) * 4]
                xs = [x + camera_x for ax, _, bx, _ in outline for x in (ax, bx)]
                ys = [y + shake_y for _, ay, _, by in outline for y in (ay, by)]
                floor_bottom, floor_top = area.bounds[1::2]
                assert (min(xs), max(xs), min(ys), max(ys)) == (68, 2492, floor_bottom, floor_top)

    key(pico2d.SDLK_p)
    game.update(config.FIXED_DT)
    key(pico2d.SDLK_p, down=False)
    assert game.world.player.invincible and game.ui.floor_bounds_visible
    key(pico2d.SDLK_F4, down=False)
    key(pico2d.SDLK_F4)
    assert not game.ui.floor_bounds_visible and game.world.player.invincible
    key(pico2d.SDLK_F4, down=False)
    key(pico2d.SDLK_F4)
    key(pico2d.SDLK_F5)
    assert game.ui.floor_bounds_visible and not game.world.player.invincible
    key(pico2d.SDLK_F5, down=False)
    key(pico2d.SDLK_F4, down=False)
    key(pico2d.SDLK_F4)
    key(pico2d.SDLK_F4, down=False)
    game.ui.details_visible = True
    print("PASS: SDL F4 toggles real cyan/orange floor pixels on/off, suppresses held/repeated "
          "inputs, follows all camera views/shake, works with U hidden and survives F5; "
          "P invincibility remains an independent toggle.")


def check_full_alley_floor(game, index=0):
    if index == 1:
        assert config.SECOND_STAGE_IMAGE in game.assets.images
        assert config.ARCHIVED_SECOND_STAGE_IMAGE not in game.assets.images
        assert "newStage-2.png" not in game.assets.images
    bottom, top, source_top, source_bottom, prefix = (
        (-3, 277, 620, 900, "first_floor_full") if index == 0 else
        (-44, 239, 658, 941, "second_alley_floor300")
    )
    visible, details = game.ui.floor_bounds_visible, game.ui.details_visible
    game.ui.floor_bounds_visible, game.ui.details_visible = True, False
    try:
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for running in (False, True):
                for side in (-1, 1):
                    for depth in (-1, 1):
                        game.world = World(item_rng=random.Random(23))
                        game.world.select_stage(index)
                        world, player = game.world, game.world.player
                        assert world.stage.walkable.bounds == (0, bottom, 2560, top)
                        player.equip_weapon(weapon)
                        player.x = player.previous_x = 300 if side < 0 else 2260
                        keys = (pico2d.SDLK_LEFT if side < 0 else pico2d.SDLK_RIGHT,
                                pico2d.SDLK_DOWN if depth < 0 else pico2d.SDLK_UP)
                        if running:
                            keys += (pico2d.SDLK_LSHIFT,)
                        for key in keys:
                            push_key(key)
                        for _ in range(90):
                            tick(game)
                            inside(world)
                        release(keys)
                        game.handle_events()
                        assert (player.x, player.ground_y, player.jump_height, player.floor) == (
                            68 if side < 0 else 2492, bottom if depth < 0 else top, 0, 0)
                        assert 0 <= player.y - world.camera.render_y < config.SCREEN_HEIGHT
                        with patch.object(pico2d, "draw_line", wraps=pico2d.draw_line) as draw:
                            if weapon is None:
                                capture(game, f"{prefix}_{'run' if running else 'walk'}_{side}_{depth}")
                            else:
                                render_image(game)
                        endpoints = {point for call in draw.call_args_list
                                     if call.args[4:] == PLAYER_BOUNDS_COLOR
                                     for point in (call.args[:2], call.args[2:4])}
                        assert (player.x - world.camera.render_x,
                                player.ground_y - world.camera.render_y) in endpoints
                        source_y = (config.GROUND_Y - config.STAGE_GROUND_Y
                                    + config.STAGE_IMAGE_HEIGHT - player.ground_y)
                        assert source_y == (source_bottom if depth < 0 else source_top)
        game.world = World(item_rng=random.Random(23))
        game.world.select_stage(index)
        world, player = game.world, game.world.player
        player.x = player.previous_x = 68
        player.ground_y = player.previous_ground_y = bottom
        push_key(pico2d.SDLK_RIGHT)
        push_key(pico2d.SDLK_LSHIFT)
        for frame in range(240):
            tick(game)
            inside(world)
            assert player.ground_y == bottom and player.grounded
            if frame == 120:
                capture(game, f"{prefix}_front_traverse")
        release((pico2d.SDLK_RIGHT, pico2d.SDLK_LSHIFT))
        game.handle_events()
        assert player.x == 2492
        for depth in (bottom, top):
            player.ground_y = player.previous_ground_y = depth
            direction = pico2d.SDLK_DOWN if depth == bottom else pico2d.SDLK_UP
            push_key(direction)
            push_key(pico2d.SDLK_LSHIFT)
            for _ in range(2):
                push_key(pico2d.SDLK_SPACE)
                tick(game, 3)
                release((pico2d.SDLK_SPACE,))
                game.handle_events()
            assert player.jump_count == 2
            tick(game, 20)
            assert player.ground_y == depth and player.jump_height > 0 and player.floor == 0
            capture(game, f"{prefix}_jump_{'front' if depth == bottom else 'rear'}")
            tick(game, 100)
            assert player.grounded and player.ground_y == depth and player.floor == 0
            assert player.staircase is None
            release((direction, pico2d.SDLK_LSHIFT))
            game.handle_events()
        push_key(pico2d.SDLK_F5)
        tick(game)
        release((pico2d.SDLK_F5,))
        game.handle_events()
        assert world.stage_index == 0
        assert world.stages[index].walkable.bounds == (0, bottom, 2560, top)
        world.select_stage(index)
        assert world.stage.walkable.bounds == (0, bottom, 2560, top)
        assert not world.enemies and len(world.stage.drop_items) == 15
        assert game.ui.floor_bounds_visible and not world.player.invincible
        capture(game, f"{prefix}_restarted")
    finally:
        game.ui.floor_bounds_visible, game.ui.details_visible = visible, details
        game.world = World()
    print(f"PASS: alley {index + 1}, all three loadouts walk/run to all four full-floor corners; "
          f"F4 matches real feet at source rows {source_top}/{source_bottom}, the formerly "
          "blocked front band is traversable across both map tiles, double jumps land at "
          "both depth edges without hidden stairs, and F5 keeps the expanded floor.")


def ready(enemies):
    for enemy in enemies:
        enemy.animation.set_state("ATTACK")
        enemy.animation.elapsed = 4 / config.ENEMY_ANIMATIONS["ATTACK"][1]
        enemy.has_hit = False
        enemy.cooldown = 1


def check_movement(game):
    directions = ((pico2d.SDLK_LEFT,), (pico2d.SDLK_RIGHT,), (pico2d.SDLK_UP,), (pico2d.SDLK_DOWN,),
                  (pico2d.SDLK_RIGHT, pico2d.SDLK_UP), (pico2d.SDLK_RIGHT, pico2d.SDLK_DOWN),
                  (pico2d.SDLK_LEFT, pico2d.SDLK_UP), (pico2d.SDLK_LEFT, pico2d.SDLK_DOWN))
    for running in (False, True):
        for keys in directions:
            game.world = World()
            for key in keys + ((pico2d.SDLK_LSHIFT,) if running else ()):
                push_key(key)
            tick(game, 6 if running else 9)
            player = game.world.player
            assert abs(hypot(player.vx, player.ground_vy) - (240 if running else 300)) < 1e-8
            assert player.state == ("RUN" if running else "WALK")
            inside(game.world)
            if keys == (pico2d.SDLK_RIGHT, pico2d.SDLK_UP):
                shot(game, "belt_diagonal_run" if running else "belt_diagonal_walk")
            release(keys + (pico2d.SDLK_LSHIFT,))
            game.handle_events()
    game.world = World()
    push_key(pico2d.SDLK_RIGHT)
    push_key(pico2d.SDLK_LSHIFT)
    tick(game, 30)
    assert game.world.player.vx == 720
    release((pico2d.SDLK_RIGHT, pico2d.SDLK_LSHIFT))
    game.handle_events()
    print("PASS: SDL all four cardinal/four diagonal directions, normalized walk 300px/s; "
          "run acceleration norm 240px/s at 0.1s and horizontal run reaches 720px/s.")


def check_jump(game):
    game.world = World()
    game.world.select_stage(1)  # Exercise the second alley's rear edge without upper floors.
    floor_top = game.world.stage.walkable.bounds[3]
    reference = World()
    reference.select_stage(1)
    for key in (pico2d.SDLK_UP, pico2d.SDLK_LSHIFT, pico2d.SDLK_SPACE):
        push_key(key)
    for key in ("right", "left_shift", "jump"):
        reference.controls.press(key)
    for frame in range(100):
        if frame in (3, 6):
            push_key(pico2d.SDLK_SPACE, down=False)
            push_key(pico2d.SDLK_SPACE)
            reference.controls.release("jump")
            reference.controls.press("jump")
        tick(game)
        reference.update(1 / 60)
        player = game.world.player
        assert (player.jump_height, player.vy, player.jump_count) == (
            reference.player.jump_height, reference.player.vy, reference.player.jump_count)
        inside(game.world)
        if frame == 30:
            assert player.jump_height > 200 and player.ground_y == floor_top
            shot(game, "belt_jump_at_floor_boundary")
    assert game.world.player.grounded and game.world.player.ground_y == floor_top
    release((pico2d.SDLK_UP, pico2d.SDLK_LSHIFT, pico2d.SDLK_SPACE))
    game.handle_events()
    print("PASS: SDL upward run + double jump keeps the exact original height/velocity curve, "
          f"third input ignored; landing returns to the moved floor at y={floor_top:g}.")


def check_depth_and_order(game):
    game.world = World()
    player = game.world.player
    near, far = Enemy(player.x + 80, -1, ground_y=116), Enemy(player.x + 90, -1, ground_y=56)
    game.world.enemies = [near, far]
    for enemy in game.world.enemies:
        enemy.cooldown = 100
        enemy.animation.set_state("HIT")  # Hold fixtures still to isolate depth, not AI approach.
    push_key(pico2d.SDLK_a)
    tick(game, 9)
    assert (near.hp, far.hp) == (190, 200)
    assert len(game.world.damage_numbers) == 1
    shot(game, "belt_depth_player_attack")
    release((pico2d.SDLK_a,))
    game.handle_events()

    game.world = World()
    player = game.world.player
    near, far = Enemy(player.x - 80, 1, ground_y=116), Enemy(player.x + 80, -1, ground_y=56)
    game.world.enemies = [near, far]
    ready(game.world.enemies)
    tick(game)
    assert player.hp == 480 and near.has_hit and not far.has_hit
    shot(game, "belt_depth_enemy_attack")

    game.world = World()
    player = game.world.player
    back, front = Enemy(player.x - 20, ground_y=130), Enemy(player.x + 20, ground_y=70)
    game.world.enemies = [front, back]
    for jump_height in (0, 240):
        player.jump_height = jump_height
        with patch.object(game.assets, "draw_sprite", wraps=game.assets.draw_sprite) as draw:
            shot(game, "belt_depth_order_jump" if jump_height else "belt_depth_order_ground")
        drawn_x = [round(call.args[3] + game.world.camera.render_x) for call in draw.call_args_list]
        assert drawn_x == [round(back.x), round(player.x), round(front.x)]
    print("PASS: SDL A hits depth +16 but misses -44; enemy attacks use the same depth filter; "
          "ground-y render order stays back/player/front even with jump_height=240.")


def check_crowds(game):
    for stage_index in (0, 1):
        for count in (2, 5, 10):
            for sx, sy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
                game.world = World()
                game.world.stage_index = stage_index
                left, bottom, right, top = game.world.stage.walkable.bounds
                player = game.world.player
                player.x = left + 100 if sx < 0 else right - 100
                player.ground_y = bottom if sy < 0 else top
                game.world.enemies = [Enemy(player.x + sx * 65, -sx, ground_y=player.ground_y)
                                      for _ in range(count)]
                ready(game.world.enemies)
                push_key(pico2d.SDLK_p)
                tick(game)
                release((pico2d.SDLK_p,))
                game.handle_events()
                for frame in range(240):
                    if frame == 90:
                        for enemy in game.world.enemies[:2]:
                            enemy.knockback(player.x, enemy.ground_y - sy * 50)
                    if frame == 120:
                        game.world.enemies[-1].take_damage(20)
                    tick(game)
                    inside(game.world)
                assert player.hp == 500
                if count == 10:
                    shot(game, f"belt_stage_{stage_index + 1}_corner_{sx}_{sy}_10")
            print(f"PASS: actual stage {stage_index + 1}, {count} enemies, all four corners: "
                  "attack separation, HIT and outward 2D knockback stay in the walkable region.")

    game.world = World()
    game.world.enemies = [Enemy(config.START_X + side * 500, -side, ground_y=56,
                               run_speed=config.ENEMY_RUN_SPEEDS[index % 4])
                         for side in (-1, 1) for index in range(10)]
    push_key(pico2d.SDLK_p)
    tick(game)
    release((pico2d.SDLK_p,))
    game.handle_events()
    consumed = set()
    for _ in range(480):
        before = [enemy.has_hit for enemy in game.world.enemies]
        tick(game)
        inside(game.world)
        consumed.update(enemy for enemy, was in zip(game.world.enemies, before)
                        if enemy.state == "ATTACK" and enemy.has_hit and not was)
    assert consumed == set(game.world.enemies)
    ready(game.world.enemies)
    push_key(pico2d.SDLK_p)
    tick(game)
    release((pico2d.SDLK_p,))
    game.handle_events()
    assert game.world.player.hp == 100 and all(enemy.has_hit for enemy in game.world.enemies)
    shot(game, "belt_twenty_simultaneous_hits")
    print("PASS: all 20 natural arrivals consume valid swings; a separate synchronized "
          "active-frame proof applies all 20 attacks together, HP 500->100.")


def check_travel(game):
    game.world = World()
    player = game.world.player
    source_top = game.world.stage.walkable.bounds[3]
    player.x, player.ground_y = config.WORLD_WIDTH - 85, source_top
    player.jump_height, player.vy, player.jump_count = 120, 300, 2
    player.vx = 720
    for key in (pico2d.SDLK_n, pico2d.SDLK_RIGHT, pico2d.SDLK_LSHIFT):
        push_key(key)
    tick(game)
    assert game.world.stage_index == 1 and game.world.player is player
    assert player.ground_y == 239 and player.jump_count == 2
    assert abs(player.jump_height - 124.625) < 1e-8 and player.vy == 270
    inside(game.world)
    shot(game, "belt_transition_next")
    release((pico2d.SDLK_n, pico2d.SDLK_RIGHT))
    push_key(pico2d.SDLK_n)
    push_key(pico2d.SDLK_LEFT)
    player.x, player.vx = 85, -720
    tick(game)
    assert game.world.stage_index == 0 and game.world.player is player
    assert player.ground_y == 239 and player.jump_count == 2 and player.vy == 240
    inside(game.world)
    shot(game, "belt_transition_previous")
    release((pico2d.SDLK_n, pico2d.SDLK_LEFT, pico2d.SDLK_LSHIFT))
    game.handle_events()
    print("PASS: SDL N/run/airborne travel in both directions preserves the Player and jump "
          f"while projecting floor y={source_top:g} to the second stage's y<=239; "
          "camera remains independent.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_floor_toggle(game)
        check_full_alley_floor(game)
        check_full_alley_floor(game, index=1)
        check_movement(game)
        check_jump(game)
        check_depth_and_order(game)
        check_crowds(game)
        check_travel(game)
        game.world = World(rng=random.Random(10))
        game.world.enemies.extend(game.world.spawner.spawn(9, game.world.elapsed))
        push_key(pico2d.SDLK_p)
        tick(game)
        release((pico2d.SDLK_p,))
        game.handle_events()
        game.world.enemies.append(Enemy(config.START_X + 200, -1, ground_y=120))
        start = perf_counter()
        frames = game.run(max_frames=180)
        seconds = perf_counter() - start
        assert frames == 180 and len(game.world.enemies) == 10
        inside(game.world)
        print(f"BENCHMARK: 10 enemies, 2D AI/Separation/bounds/depth sorting: "
              f"{frames} frames / {seconds:.3f}s = {frames / seconds:.2f} FPS.")
        push_key(pico2d.SDLK_F5)
        tick(game)
        assert not game.world.enemies and game.world.player.ground_y == config.GROUND_Y
        assert game.world.player.jump_height == game.world.player.ground_vy == 0
        release((pico2d.SDLK_F5,))
        game.handle_events()
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
