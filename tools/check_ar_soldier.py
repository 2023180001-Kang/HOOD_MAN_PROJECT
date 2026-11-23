"""Exercise automatic AR fire, twenty-round reloads and real pixels through SDL."""

from itertools import combinations
from math import hypot
from pathlib import Path
import random
import sys
from time import perf_counter
from unittest.mock import patch

from PIL import ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from ar_soldier import ARSoldier
from collision import bodies_overlap
from enemy_spacing import ranged_half_width
from game import Game
from projectiles import RifleBullet
from tools.check_damage_numbers import capture_number
from tools.check_render import capture, render_image
from tools.check_researcher import check_warning_pixels
from tools.check_runtime import push_key, release, tick
from world import World


def encounter(game, index=10, side=-1, *, speed=1, gap=300, protected=True):
    game.world = World(rng=random.Random(23), item_rng=random.Random(5))
    world = game.world
    world.select_stage(index)
    world.player.invincible = protected
    world.player.facing = side
    enemy = ARSoldier(world.player.x + side * gap, -side,
                      ground_y=world.player.ground_y, attack_speed=speed)
    enemy.walkable = world.stage.walkable
    world.enemies = [enemy]
    return world, enemy


def wait(game, predicate, frames=180):
    for _ in range(frames):
        tick(game)
        if predicate():
            return
    raise AssertionError("AR event did not occur")


def check_spawning(game):
    for index in (10, 11):
        for prefix in ("", "KP_"):
            for count in config.SPAWN_COUNTS:
                game.world = World(rng=random.Random(42))
                world = game.world
                world.select_stage(index)
                tick(game, 6)
                assert not world.enemies
                key = getattr(pico2d, f"SDLK_{prefix}{count}")
                push_key(key)
                tick(game)
                assert len(world.enemies) == world.spawner.spawned_count == count
                assert all(type(enemy) is ARSoldier and enemy.hp == 300 and enemy.ammo == 20
                           and enemy.attack_damage == 5
                           and world.stage.walkable.contains(enemy.x, enemy.ground_y, 88)
                           for enemy in world.enemies)
                push_key(key, repeat=True)
                tick(game)
                assert len(world.enemies) == count
                release(game, key)
        capture(game, f"ar_boss_{index - 9}_summons")
    print("PASS: both bosses/all 18 digit keys, exact counts, HP 300/ammo 20, repeat latch and floor bounds.")


def check_reload_fixed_sheet(game):
    assert config.AR_SOLDIER_IMAGE == "AR_soldier_pico2d_reload_fixed_2048x1792.png"
    image = game.assets.images[config.AR_SOLDIER_IMAGE]
    assert (image.w, image.h) == (2048, 1792)
    for archived in config.ARCHIVED_AR_SOLDIER_IMAGES:
        for name in (archived, archived.rsplit("/", 1)[-1]):
            assert name not in game.assets.images and name not in game.assets.frames
    game.ui.details_visible = False
    for side in (-1, 1):
        world, enemy = encounter(game, side=side)
        for state in ("IDLE", "WALK", "RUN", "ATTACK", "HIT", "RELOAD", "DYING"):
            enemy.animation.set_state(state)
            fps = enemy.animation.definitions[state][1]
            for frame in range(8):
                enemy.animation.elapsed = (frame + 0.05) / fps
                tile = game.assets.frames[enemy.sprite_image][enemy.animation.row - 1][frame]
                with patch.object(image, "clip_composite_draw", wraps=image.clip_composite_draw) as draw:
                    render_image(game)
                assert draw.call_count == 1
                args = draw.call_args.args
                assert args[:4] == tuple(tile["clip"])
                assert args[5] == ("h" if enemy.facing < 0 else "")
                assert abs(args[7] - args[9] / 2 - (enemy.y - world.camera.render_y)) < 1e-8
                if state == "ATTACK" and frame in config.AR_SOLDIER_FIRE_FRAMES:
                    capture(game, f"ar_corrected_fire_{enemy.facing}_{frame}")
                elif state == "RELOAD":
                    capture(game, f"ar_reload_fixed_{enemy.facing}_{frame}")
    print("PASS: reload-fixed sheet uses all 7x8x2 source clips/flips/feet, including all 8 reload poses; "
          "both archived originals are never loaded or included in metadata.")


def check_warning(game):
    game.ui.details_visible = False
    for index in (10, 11):
        for side in (-1, 1):
            for speed in (0.8, 1.4):
                world, enemy = encounter(game, index, side, speed=speed)
                tick(game)
                assert enemy.aiming and enemy.ammo == 20 and enemy.animation.frame == 1
                check_warning_pixels(game)
                capture(game, f"ar_warning_{index}_{side}_{speed}")
                tick(game, 29)
                assert enemy.aiming and not world.projectiles
                tick(game)
                assert enemy.ammo == 19
                assert len(world.projectiles) == 1 and isinstance(world.projectiles[0], RifleBullet)
                assert world.projectiles[0].y == enemy.y + config.AR_SOLDIER_MUZZLE_HEIGHT
                capture(game, f"ar_fired_{index}_{side}_{speed}")
                tick(game, 6)
                assert enemy.ammo == 18 and not enemy.aiming and enemy.animation.frame == 3
                assert len(world.projectiles) == 2
                capture(game, f"ar_automatic_stream_{index}_{side}_{speed}")
    world, enemy = encounter(game, gap=620)
    tick(game)
    assert not enemy.aiming and not world.projectiles
    wait(game, lambda: enemy.aiming)
    assert enemy.ammo == 20 and not world.projectiles
    print("PASS: full 0.5s red-dot warning, then 0.1s automatic fire/two visible rounds, "
          "both bosses/facings/speed endpoints; range entry starts a new warning.")


def check_twenty_rounds(game):
    for index in (10, 11):
        for side in (-1, 1):
            world, enemy = encounter(game, index, side)
            shots, warnings, frames_seen = [], [], set()
            started, refilled = None, False
            for _ in range(360):
                previous_ammo, was_aiming = enemy.ammo, enemy.aiming
                tick(game)
                if enemy.aiming and not was_aiming:
                    warnings.append(world.elapsed)
                if enemy.ammo == previous_ammo - 1:
                    if len(shots) % 20 == 0:
                        assert abs(world.elapsed - warnings[-1] - enemy.aim_duration) < 1e-8
                    else:
                        assert abs(world.elapsed - shots[-1] - 0.1) < 1e-8
                    shots.append(world.elapsed)
                    assert enemy.animation.frame == 2 + (len(shots) - 1) % 4
                if enemy.state == "RELOAD":
                    assert len(shots) == 20 and enemy.ammo == 0 and enemy.animation.row == 6
                    assert enemy.aim_line is None
                    frames_seen.add(enemy.animation.frame)
                    if started is None:
                        started = world.elapsed
                        capture(game, f"ar_auto_empty_reload_{index}_{side}")
                if started is not None and enemy.ammo == 20 and not refilled:
                    assert abs(world.elapsed - started - 1) < 1 / 60
                    refilled = True
                    capture(game, f"ar_auto_refilled_{index}_{side}")
                if len(shots) == 21:
                    break
            assert (len(shots), len(warnings), refilled, enemy.ammo) == (21, 2, True, 19)
            assert abs(shots[19] - shots[0] - 1.9) < 1e-8
            assert frames_seen == set(range(8))
    print("PASS: both bosses/facings fire 20 rounds at 10/s after one 0.5s warning, loop row-4 frames 2..5, "
          "then all 8 row-6 frames/1s refill and a new 0.5s warning before round 21.")


def check_depth_evasion_and_pursuit(game):
    for index in (10, 11):
        for side in (-1, 1):
            for key, direction in ((pico2d.SDLK_UP, 1), (pico2d.SDLK_DOWN, -1)):
                world, enemy = encounter(game, index, side, gap=200)
                tick(game, 15)
                assert enemy.aiming
                before = enemy.x, enemy.ground_y, enemy.aim_line
                push_key(key)
                tick(game)
                assert enemy.aiming and enemy.aim_cancel_remaining > 0
                assert abs(world.player.ground_y - enemy.ground_y) < 32
                check_warning_pixels(game)
                for _ in range(29):
                    tick(game)
                    assert enemy.aiming and not world.projectiles and enemy.ammo == 20
                    assert (enemy.x, enemy.ground_y, enemy.aim_line) == before
                capture(game, f"ar_depth_cancel_delay_{index}_{side}_{direction}")
                tick(game)
                assert not enemy.aiming and enemy.aim_cancel_remaining == 0
                assert enemy.ground_vy == direction * 120
                capture(game, f"ar_depth_cancelled_{index}_{side}_{direction}")
                release(game, key)
                wait(game, lambda: enemy.aiming)
                assert enemy.ammo == 20 and not world.projectiles
                tick(game, 29)
                assert enemy.aiming and enemy.ammo == 20
                tick(game)
                assert enemy.ammo == 19
            for run_speed in config.ENEMY_RUN_SPEEDS:
                world, enemy = encounter(game, index, side, gap=800)
                enemy.run_speed = run_speed
                enemy.ground_y -= 80
                before = enemy.x, enemy.ground_y
                tick(game)
                assert abs(hypot(enemy.vx, enemy.ground_vy) - run_speed) < 1e-8
                assert abs(hypot(enemy.x - before[0], enemy.ground_y - before[1]) - run_speed / 60) < 1e-8
    print("PASS: SDL up/down during aiming delays cancellation by 0.5s with no shot or lane tracking, "
          "then resumes original 120px/s walking and a new 0.5s warning. All run speeds/diagonals are unchanged.")


def check_burst_interruptions(game):
    world, enemy = encounter(game, gap=80)
    wait(game, lambda: enemy.ammo == 19)
    push_key(pico2d.SDLK_s)
    wait(game, lambda: enemy.hp < 300)
    release(game, pico2d.SDLK_s)
    ammo = enemy.ammo
    assert enemy.state == "HIT" and ammo < 20
    tick(game, 12)
    assert enemy.ammo == ammo and not enemy.aiming
    wait(game, lambda: enemy.aiming)
    assert enemy.ammo == ammo and enemy.animation.frame == 1
    capture(game, "ar_auto_hit_restarts_warning")

    world, enemy = encounter(game)
    wait(game, lambda: enemy.ammo == 19)
    tick(game, 3)
    snapshot = enemy.ammo, enemy.fire_remaining, enemy.animation.elapsed
    world.select_stage(9)
    tick(game, 30)
    world.select_stage(10)
    assert (enemy.ammo, enemy.fire_remaining, enemy.animation.elapsed) == snapshot
    world.pending_stage_index, world.stage_loading_remaining = 9, 2
    tick(game, 30)
    assert (enemy.ammo, enemy.fire_remaining, enemy.animation.elapsed) == snapshot
    world.select_stage(10)
    tick(game, 2)
    assert enemy.ammo == 19
    tick(game)
    assert enemy.ammo == 18
    print("PASS: SDL S interrupts active automatic fire; recovery starts a new warning. "
          "Inactive/loading stages freeze the fire interval without catch-up shots.")


def check_health(game):
    for hp, width in ((300, 48), (150, 24), (75, 12), (0, 0)):
        world, enemy = encounter(game)
        enemy.hp = hp
        for details in (True, False):
            game.ui.details_visible = details
            image = render_image(game).convert("RGB")
            tile = game.assets.frames[enemy.sprite_image][enemy.animation.row - 1][enemy.animation.frame]
            left = round(enemy.x - world.camera.render_x - 24)
            bottom = enemy.y - world.camera.render_y + tile["clip"][3] * 0.75 + 10
            row = config.SCREEN_HEIGHT - round(bottom) - 2
            widths = [sum(image.getpixel((x, y)) == (215, 38, 45) for x in range(left, left + 48))
                      for y in range(row - 2, row + 3)]
            assert max(widths) == width, (hp, details, widths)
        capture(game, f"ar_hp_{hp}")
    print("PASS: actual red bar 48/24/12/hidden pixels for 300/150/75/0, also with U hidden.")


def check_hits(game):
    game.ui.details_visible = True
    world, enemy = encounter(game, gap=80)
    enemy.cooldown = 100
    push_key(pico2d.SDLK_s)
    wait(game, lambda: enemy.hp < 300)
    release(game, pico2d.SDLK_s)
    assert enemy.hp == 260 and enemy.animation.row == 5
    world.update_camera(config.SHAKE_DURATION)
    capture_number(game, "ar_hit_fifth_row")
    for index in (10, 11):
        for side in (-1, 1):
            world, enemy = encounter(game, index, side, protected=False)
            wait(game, lambda: world.player.hp < 500)
            assert world.player.hp == 495 and world.player.state == "HIT"
            assert len(world.effects) == 1 and world.effects[0].image_name == config.CLUB_HIT_IMAGE
            assert world.camera.shake_remaining > 0
            capture(game, f"ar_impact_{index}_{side}")
    print("PASS: real S hit uses own row 5; rifle deals 5 once with player HIT/effect/shake.")


def check_bullet_pixels(game):
    world, _ = encounter(game)
    world.enemies.clear()
    for facing in (-1, 1):
        bullet = RifleBullet(world.player.x - 200, 100, 81, facing)
        world.projectiles[:] = [bullet]
        for frame in range(8):
            bullet.elapsed = (frame + 0.05) / bullet.fps
            with patch.object(game.assets, "draw_projectile"):
                baseline = render_image(game)
            with patch.object(game.assets.images[bullet.image_name], "clip_composite_draw",
                              wraps=game.assets.images[bullet.image_name].clip_composite_draw) as draw:
                image = render_image(game)
            assert draw.call_count == 1
            assert draw.call_args.args[8] <= 16 and draw.call_args.args[9] <= 6
            assert ImageChops.difference(image.convert("RGB"), baseline.convert("RGB")).getbbox() is not None
        capture(game, f"ar_rifle_bullet_{facing}")
    print("PASS: all 8 rifle clips/both directions render at the intended small size.")


def check_pause_restart(game):
    world, enemy = encounter(game)
    enemy.ammo = 0
    enemy.start_reload()
    tick(game, 18)
    snapshot = enemy.ammo, enemy.animation.elapsed
    world.select_stage(9)
    tick(game, 60)
    world.select_stage(10)
    assert (enemy.ammo, enemy.animation.elapsed) == snapshot
    world.pending_stage_index, world.stage_loading_remaining = 9, 2
    tick(game, 30)
    assert (enemy.ammo, enemy.animation.elapsed) == snapshot
    textures = dict(game.assets.images)
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert world.stage_index == 0
    assert all(not stage.enemies and not stage.projectiles for stage in world.stages)
    assert all(game.assets.images[name] is image for name, image in textures.items())
    print("PASS: reload pauses across visits/loading; F5 clears shots/enemies and reuses textures.")


def check_ar_spacing(game):
    for index in (10, 11):
        world, _ = encounter(game, index)
        world.enemies.clear()
        seen_reload = False
        for wave in range(2):
            push_key(pico2d.SDLK_9)
            tick(game)
            release(game, pico2d.SDLK_9)
            assert len(world.enemies) == (wave + 1) * 9
            for frame in range(360):
                before = [(e.x, e.ground_y) for e in world.enemies]
                tick(game)
                for enemy, (x, y) in zip(world.enemies, before):
                    assert hypot(enemy.x - x, enemy.ground_y - y) <= enemy.run_speed / 60 + 1e-8
                    assert world.stage.walkable.contains(enemy.x, enemy.ground_y, enemy.boundary_padding)
                    assert not bodies_overlap(enemy, world.player)
                for first, second in combinations(world.enemies, 2):
                    assert not bodies_overlap(first, second)
                    if all(e.state in ("ATTACK", "RELOAD") for e in (first, second)):
                        assert (abs(first.x - second.x) >= ranged_half_width(first) + ranged_half_width(second) - 1e-8
                                or abs(first.ground_y - second.ground_y) >= config.AR_SOLDIER_SPACING_DEPTH - 1e-8)
                seen_reload |= any(enemy.state == "RELOAD" for enemy in world.enemies)
                if frame in (0, 179, 359):
                    capture(game, f"ar_spacing_{index}_{len(world.enemies)}_{frame}")
        assert any(enemy.ammo < 20 for enemy in world.enemies) and seen_reload
    print("PASS: SDL 9+9 AR summons remain separated throughout approach, fire/reload and reinforcements; "
          "both bosses keep every footprint inside the floor without player overlap.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_reload_fixed_sheet(game)
        check_spawning(game)
        check_warning(game)
        check_twenty_rounds(game)
        check_depth_evasion_and_pursuit(game)
        check_burst_interruptions(game)
        check_health(game)
        check_hits(game)
        check_bullet_pixels(game)
        check_pause_restart(game)
        check_ar_spacing(game)
        game.world = World(rng=random.Random(42))
        game.world.select_stage(10)
        game.world.player.invincible = True
        push_key(pico2d.SDLK_9)
        tick(game)
        release(game, pico2d.SDLK_9)
        push_key(pico2d.SDLK_9)
        tick(game)
        release(game, pico2d.SDLK_9)
        start = perf_counter()
        frames = game.run(max_frames=180)
        seconds = perf_counter() - start
        print(f"BENCHMARK: 18 AR soldiers: {frames} frames / {seconds:.3f}s = {frames / seconds:.2f} FPS.")
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
