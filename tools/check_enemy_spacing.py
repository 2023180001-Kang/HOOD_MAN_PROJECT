"""Exercise grouped melee in a real pico2d window, with SDL input and captures."""

from pathlib import Path
from math import hypot
import sys
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from enemy import Enemy
from enemy_spacing import sprite_extents
from game import Game
from tools.check_render import capture
from tools.check_runtime import push_key, tick
from world import World


def add_group(game, count, side, distance=500):
    enemies = [Enemy(game.world.player.x + side * distance, -side,
                     run_speed=config.ENEMY_RUN_SPEEDS[index % 4]) for index in range(count)]
    game.world.enemies.extend(enemies)
    return enemies


def capture_group(game, name):
    with patch.object(game.assets, "draw_sprite", wraps=game.assets.draw_sprite) as draw:
        image = capture(game, name)
    calls = [call for call in draw.call_args_list if call.args[0] == config.ENEMY_IMAGE]
    assert len(calls) == len(game.world.enemies)
    feet = [call.args[4] for call in calls]
    assert feet == sorted(feet, reverse=True), "Back lanes must render before front lanes"
    for enemy in game.world.enemies:
        tile = game.assets.frames[config.ENEMY_IMAGE][enemy.animation.row - 1][enemy.animation.frame]
        x = round(enemy.x - game.world.camera.render_x)
        y = config.SCREEN_HEIGHT - round(enemy.y - game.world.camera.render_y
                                         + tile["clip"][3] * config.SPRITE_SCALE
                                         + config.ENEMY_HP_BAR_GAP + 2)
        # Real floor lanes and camera shake are fractional; SDL rasterization
        # may choose either adjacent row. Still require a full visible red bar.
        red = max(sum(image.getpixel((column, row))[:3] == (215, 38, 45)
                      for column in range(x - 22, x + 22)) for row in range(y - 2, y + 3))
        assert red >= 40, (name, enemy.formation_slot, red)


def check_case(game, counts, label, *, wall=False):
    game.world = World()
    if wall:
        game.world.player.x = game.world.player.previous_x = (100 if counts[0][0] < 0 else 2460)
        game.world.camera.update(0, game.world.player.x)
    groups = [(side, add_group(game, count, side, distance=65 if wall else 500))
              for side, count in counts]
    push_key(pico2d.SDLK_p)
    tick(game)
    push_key(pico2d.SDLK_p, down=False)
    game.handle_events()
    assert game.world.player.invincible
    hits = set()
    for _ in range(480):
        before = [(enemy.x, enemy.depth, enemy.state, enemy.has_hit) for enemy in game.world.enemies]
        tick(game)
        for enemy, (x, depth, state, hit) in zip(game.world.enemies, before):
            if enemy.state == "ATTACK" and enemy.has_hit and not hit:
                hits.add(enemy)
            if state == enemy.state == "ATTACK":
                assert hypot(enemy.x - x, enemy.depth - depth) <= config.ENEMY_ATTACK_SEPARATION_SPEED / 60 + 1e-8
            assert game.world.stage.walkable.contains(enemy.x, enemy.ground_y, enemy.boundary_padding)
        for side, enemies in groups:
            assert all((enemy.x - game.world.player.x) * side >= 61 - 1e-8 for enemy in enemies)
    assert hits == set(game.world.enemies), "Every enemy, including rear slots, must land a swing"
    for _, enemies in groups:
        for index, first in enumerate(enemies):
            for second in enemies[index + 1:]:
                assert ((abs(first.x - second.x) >= 50 or abs(first.depth - second.depth) >= 8)
                        if not wall else abs(first.depth - second.depth) >= 1)
    capture_group(game, f"enemy_spacing_{label}")

    # Synchronize only this proof of simultaneous real damage; natural approach,
    # independent cooldowns and the final positions were exercised above.
    for enemy in game.world.enemies:
        enemy.animation.set_state("ATTACK")
        enemy.animation.elapsed = 4 / config.ENEMY_ANIMATIONS["ATTACK"][1]
        enemy.has_hit = False
        enemy.cooldown = 1
    push_key(pico2d.SDLK_p)
    tick(game)
    push_key(pico2d.SDLK_p, down=False)
    game.handle_events()
    expected = 500 - len(game.world.enemies) * config.ENEMY_DAMAGE
    assert game.world.player.hp == expected
    assert all(enemy.has_hit for enemy in game.world.enemies)
    tick(game, 6)
    assert game.world.player.hp == expected
    if label in ("left_8", "right_8", "both_8"):
        capture_group(game, f"enemy_spacing_{label}_simultaneous_hit")
        push_key(pico2d.SDLK_p)
        tick(game, 40)
        push_key(pico2d.SDLK_p, down=False)
        direction = pico2d.SDLK_LEFT if counts[0][0] < 0 else pico2d.SDLK_RIGHT
        push_key(direction)
        push_key(pico2d.SDLK_a)
        tick(game, 11)
        enemies = groups[0][1]
        assert all(enemy.hp == 180 for enemy in enemies), "Every slot must be counterable by A"
        assert len(game.world.damage_numbers) == len(enemies)
        capture(game, f"enemy_spacing_{label}_counter")
        push_key(direction, down=False)
        push_key(pico2d.SDLK_a, down=False)
        game.handle_events()
    print(f"PASS: {label}: all {len(game.world.enemies)} independently attack; "
          f"distinct projected positions/HP-bar pixels; simultaneous HP 500->{expected}, "
          "no repeated swing damage or attack teleports.")


def check_existing_overlap(game):
    game.world = World()
    game.world.player.invincible = True
    enemies = add_group(game, 8, 1, distance=80)
    for enemy in enemies:
        enemy.animation.set_state("ATTACK")
        enemy.animation.elapsed = 0.1
        enemy.cooldown = 1
    capture(game, "enemy_spacing_overlap_before")
    for _ in range(15):
        positions = [enemy.x for enemy in enemies]
        tick(game)
        assert all(abs(enemy.x - x) <= 18 / 60 + 1e-8 for enemy, x in zip(enemies, positions))
        assert all(enemy.state == "ATTACK" and enemy.facing == -1 for enemy in enemies)
    capture(game, "enemy_spacing_overlap_easing")
    tick(game, 240)
    capture_group(game, "enemy_spacing_overlap_resolved")
    print("PASS: preexisting 8-way attack overlap eases at <=0.3 horizontal px/render tick, "
          "without restarting or turning the committed attack.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        left, right = sprite_extents()
        print(f"Occupied enemy envelope: {left:.2f}..{right:.2f}px, width {right - left:.2f}px.")
        for side, name in ((-1, "left"), (1, "right")):
            for count in (2, 3, 5, 8):
                check_case(game, ((side, count),), f"{name}_{count}")
        check_case(game, ((-1, 8), (1, 8)), "both_8")
        check_case(game, ((-1, 8),), "left_wall_8", wall=True)
        check_case(game, ((1, 8),), "right_wall_8", wall=True)
        check_existing_overlap(game)
        push_key(pico2d.SDLK_F5)
        tick(game)
        assert not game.world.enemies and game.world.player.hp == 500
        push_key(pico2d.SDLK_F5, down=False)
        game.handle_events()
        game.world.player.invincible = True
        add_group(game, 8, -1, 200)
        add_group(game, 8, 1, 200)
        start = perf_counter()
        frames = game.run(max_frames=180)
        seconds = perf_counter() - start
        assert frames == 180
        print(f"BENCHMARK: {frames} frames / {seconds:.3f}s = {frames / seconds:.2f} FPS; "
              "16 enemies, depth sorting, independent attacks and HP bars.")
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
