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
from tools.check_render import capture
from tools.check_runtime import push_key, tick
from world import World


def release(keys):
    for key in keys:
        push_key(key, down=False)


def inside(world):
    assert world.stage.walkable.contains(world.player.x, world.player.ground_y, world.player.boundary_padding)
    assert all(world.stage.walkable.contains(enemy.x, enemy.ground_y, enemy.boundary_padding)
               for enemy in world.enemies)


def shot(game, name):
    # Diagnostic lines are capture-only; production rendering has no overlay.
    stage = game.world.stage
    draw_stage = stage.draw

    def with_floor(*args, **kwargs):
        draw_stage(*args, **kwargs)
        left, bottom, right, top = stage.walkable.bounds
        cx, cy = game.world.camera.render_x, game.world.camera.render_y
        pico2d.draw_rectangle(left - cx, bottom - cy, right - cx, top - cy, 90, 210, 145)

    with patch.object(stage, "draw", side_effect=with_floor):
        return capture(game, name)


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
    reference = World()
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
            assert player.jump_height > 200 and player.ground_y == 148
            shot(game, "belt_jump_at_floor_boundary")
    assert game.world.player.grounded and game.world.player.ground_y == 148
    release((pico2d.SDLK_UP, pico2d.SDLK_LSHIFT, pico2d.SDLK_SPACE))
    game.handle_events()
    print("PASS: SDL upward run + double jump keeps the exact original height/velocity curve, "
          "third input ignored; landing returns to the moved floor at y=148.")


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
    assert (near.hp, far.hp) == (180, 200)
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
    player.x, player.ground_y = config.WORLD_WIDTH - 85, 145
    player.jump_height, player.vy, player.jump_count = 120, 300, 2
    player.vx = 720
    for key in (pico2d.SDLK_n, pico2d.SDLK_RIGHT, pico2d.SDLK_LSHIFT):
        push_key(key)
    tick(game)
    assert game.world.stage_index == 1 and game.world.player is player
    assert player.ground_y == 116 and player.jump_count == 2
    assert abs(player.jump_height - 124.625) < 1e-8 and player.vy == 270
    inside(game.world)
    shot(game, "belt_transition_next")
    release((pico2d.SDLK_n, pico2d.SDLK_RIGHT))
    push_key(pico2d.SDLK_n)
    push_key(pico2d.SDLK_LEFT)
    player.x, player.vx = 85, -720
    tick(game)
    assert game.world.stage_index == 0 and game.world.player is player
    assert player.ground_y == 116 and player.jump_count == 2 and player.vy == 240
    inside(game.world)
    shot(game, "belt_transition_previous")
    release((pico2d.SDLK_n, pico2d.SDLK_LEFT, pico2d.SDLK_LSHIFT))
    game.handle_events()
    print("PASS: SDL N/run/airborne travel in both directions preserves the Player and jump "
          "while projecting floor y=145 to the second stage's y<=116; camera remains independent.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_movement(game)
        check_jump(game)
        check_depth_and_order(game)
        check_crowds(game)
        check_travel(game)
        game.world = World(rng=random.Random(10))
        push_key(pico2d.SDLK_p)
        push_key(pico2d.SDLK_9)
        tick(game)
        release((pico2d.SDLK_p, pico2d.SDLK_9))
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
