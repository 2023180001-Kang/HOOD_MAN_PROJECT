"""Actual SDL verification of factory researchers, pistol bullets and reloads."""

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
from game import Game
from researcher import Researcher
from tools.check_counters import release, start_follow_up, wait_for_hold
from tools.check_damage_numbers import capture_number
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, tick
from world import World


def encounter(game, *, index=6, side=1, gap=300, invincible=False, weapon=None):
    game.world = World(rng=random.Random(23), item_rng=random.Random(5))
    world = game.world
    world.select_stage(index)
    world.player.invincible = invincible
    world.player.facing = side
    world.player.equip_weapon(weapon)
    enemy = world.spawner.spawn(1, world.elapsed)[0]
    world.enemies = [enemy]
    enemy.x = enemy.previous_x = world.player.x + side * gap
    enemy.ground_y = enemy.previous_ground_y = world.player.ground_y
    enemy.facing = -side
    return world, enemy


def wait(game, predicate, frames=180):
    for _ in range(frames):
        tick(game)
        if predicate():
            return
    raise AssertionError("Researcher event did not occur")


def check_summons(game):
    textures = dict(game.assets.images)
    for index in (6, 7):
        for prefix in ("", "KP_"):
            for count in config.SPAWN_COUNTS:
                game.world = World(rng=random.Random(42))
                world = game.world
                world.select_stage(index)
                tick(game, 12)
                assert not world.enemies and not world.projectiles
                key = getattr(pico2d, f"SDLK_{prefix}{count}")
                push_key(key)
                tick(game)
                assert len(world.enemies) == world.spawner.spawned_count == count
                assert all(type(enemy) is Researcher and enemy.hp == 200 and enemy.ammo == 7
                           for enemy in world.enemies)
                assert all(world.stage.walkable.contains(enemy.x, enemy.ground_y,
                                                         enemy.boundary_padding)
                           for enemy in world.enemies)
                push_key(key, repeat=True)
                tick(game, 6)
                assert len(world.enemies) == count
                release(game, key)
                push_key(key)
                tick(game)
                release(game, key)
                assert len(world.enemies) == count * 2
        for label, x in (("left", 0), ("right", config.WORLD_WIDTH - config.SCREEN_WIDTH)):
            game.world.camera.x = x
            capture(game, f"researcher_spawn_{index}_{label}")
    assert all(game.assets.images[name] is image for name, image in textures.items())
    print("PASS: both factory interiors, all 18 digit/keypad inputs, exact counts/HP-200/ammo-7, "
          "repeat latch, fresh input, boundaries and shared textures.")


def check_source_and_bullet_pixels(game):
    world, enemy = encounter(game, side=-1)
    texture = game.assets.images[config.RESEARCHER_IMAGE]
    for facing in (-1, 1):
        enemy.facing = facing
        for state, row in (("IDLE", 1), ("WALK", 2), ("RUN", 3), ("ATTACK", 4),
                           ("RELOAD", 5), ("HIT", 6), ("DYING", 7)):
            enemy.animation.set_state(state)
            fps = enemy.animation.definitions[state][1]
            for frame in range(8):
                enemy.animation.elapsed = (frame + 0.05) / fps
                tile = game.assets.frames[enemy.image_name][row - 1][frame]
                with patch.object(texture, "clip_composite_draw",
                                  wraps=texture.clip_composite_draw) as draw:
                    render_image(game)
                assert draw.call_args.args[:4] == tuple(tile["clip"])
                assert draw.call_args.args[5] == ("h" if facing < 0 else "")
        enemy.start_attack()
        enemy.animation.elapsed = 3.05 / enemy.attack_fps
        bullet = enemy.take_projectile()
        assert bullet is not None
        world.projectiles[:] = [bullet]
        for frame in range(8):
            bullet.elapsed = (frame + 0.05) / config.RESEARCHER_BULLET_FPS
            with patch.object(game.assets.images[bullet.image_name], "clip_composite_draw",
                              wraps=game.assets.images[bullet.image_name].clip_composite_draw) as draw:
                image = capture(game, f"researcher_bullet_{facing}_{frame}")
            args = draw.call_args.args
            assert args[5] == ("h" if facing < 0 else "")
            assert args[8] <= 26 and args[9] <= 7
            assert abs(args[6] + facing * args[8] / 2
                       - (bullet.impact_x - world.camera.render_x)) < 1e-8
            with patch.object(game.assets, "draw_projectile"):
                clean = render_image(game)
            box = ImageChops.difference(image.convert("RGB"), clean.convert("RGB")).getbbox()
            assert box is not None and box[2] - box[0] <= 27 and box[3] - box[1] <= 8, box
        world.projectiles.clear()
    print("PASS: researcher 7x8x2 exact source clips, 8 bullet frames x 2 directions, "
          "real bullet pixels, about 10x5px copper body and backward trail at the muzzle.")


def check_health_and_damage(game):
    for hp, expected in ((200, 48), (100, 24), (0, 0)):
        world, enemy = encounter(game, gap=80, invincible=True)
        enemy.hp = hp
        for details in (True, False):
            game.ui.details_visible = details
            image = render_image(game).convert("RGB")
            tile = game.assets.frames[enemy.image_name][0][0]
            left = round(enemy.x - world.camera.render_x - 24)
            bottom = enemy.y - world.camera.render_y + tile["clip"][3] * config.SPRITE_SCALE + 10
            row = config.SCREEN_HEIGHT - round(bottom) - 2
            widths = [sum(1 for x in range(left, left + 48)
                          if (lambda rgb: rgb[0] > 180 and rgb[1] < 75 and rgb[2] < 90)(
                              image.getpixel((x, y))))
                      for y in range(row - 2, row + 3)]
            assert max(widths) == expected, (hp, details, widths)
        capture(game, f"researcher_hp_{hp}")
    game.ui.details_visible = True
    for index in (6, 7):
        for side in (-1, 1):
            for key in "asdf":
                world, enemy = encounter(game, index=index, side=side, gap=80, invincible=True)
                enemy.cooldown = 100
                expected = world.player.moves[f"combat_{key}"].damage
                keycode = getattr(pico2d, f"SDLK_{key}")
                push_key(keycode)
                wait(game, lambda: enemy.hp < 200)
                release(game, keycode)
                assert enemy.hp == 200 - expected and enemy.ammo == 7
                assert [number.damage for number in world.damage_numbers] == [expected]
                assert enemy.sprite_image == config.RESEARCHER_IMAGE and enemy.animation.row == 6
                assert world.effects[-1].image_name == config.PUNCH_KICK_HIT_IMAGE
                world.update_camera(config.SHAKE_DURATION)
                capture_number(game, f"researcher_damage_{index}_{side}_{key}")
                tick(game, 2)
                assert enemy.hp == 200 - expected
    print("PASS: actual red HP fill 48/24/hidden at 200/100/0 including U-hide; SDL ASDF in "
          "both interiors/directions shows exact numbers, own hit row and existing impact.")


def check_magazines_and_hits(game):
    for index in (6, 7):
        for side in (-1, 1):
            world, enemy = encounter(game, index=index, side=side)
            shots, reloads, impacts = 0, 0, 0
            previous_ammo, previous_hp = 7, 500
            reload_frames = set()
            reload_captured = False
            for _ in range(1200):
                tick(game)
                if enemy.ammo < previous_ammo:
                    assert enemy.ammo == previous_ammo - 1 and enemy.animation.row == 4
                    shots += 1
                    assert shots <= 7 * (reloads + 1)
                    if shots == 1:
                        capture(game, f"researcher_shot_{index}_{side}")
                if enemy.state == "RELOAD":
                    assert enemy.ammo == 0 and enemy.animation.row == 5
                    reload_frames.add(enemy.animation.frame)
                    if enemy.animation.frame == 4 and not reload_captured:
                        capture(game, f"researcher_reload_{index}_{side}")
                        reload_captured = True
                if enemy.ammo > previous_ammo:
                    assert previous_ammo == 0 and enemy.ammo == 7
                    assert shots == 7 * (reloads + 1) and reload_frames == set(range(8))
                    reloads += 1
                    reload_frames.clear()
                    capture(game, f"researcher_refilled_{index}_{side}_{reloads}")
                if world.player.hp < previous_hp:
                    assert previous_hp - world.player.hp == 30 and world.player.state == "HIT"
                    assert world.effects[-1].image_name == config.CLUB_HIT_IMAGE
                    assert world.camera.shake_remaining > 0
                    impacts += 1
                    if impacts == 1:
                        tick(game, 4)  # Inspect the existing impact after its first frame.
                        image = capture(game, f"researcher_impact_{index}_{side}")
                        with patch.object(game.assets, "draw_hit_effect"):
                            clean = render_image(game)
                        assert ImageChops.difference(image.convert("RGB"),
                                                     clean.convert("RGB")).getbbox() is not None
                previous_ammo, previous_hp = enemy.ammo, world.player.hp
                if reloads == 2:
                    break
            assert (shots, reloads, impacts, enemy.ammo, world.player.hp) == (14, 2, 14, 7, 80)
    print("PASS: both maps x both directions naturally fire exactly 7, play every row-5 reload "
          "frame with zero ammo, refill 7, and repeat; 14 real hits deal 420 total with HIT/effects.")


def check_dodges_and_invincibility(game):
    for action in ("jump", "depth", "invincible"):
        world, enemy = encounter(game, gap=400)
        if action == "invincible":
            push_key(pico2d.SDLK_p)
            tick(game)
            release(game, pico2d.SDLK_p)
        wait(game, lambda: enemy.ammo == 6)
        enemy.cooldown = 100
        key = pico2d.SDLK_SPACE if action == "jump" else pico2d.SDLK_DOWN
        if action != "invincible":
            push_key(key)
        tick(game, 20)
        if action != "invincible":
            release(game, key)
        assert world.player.hp == 500 and not world.effects
        capture(game, f"researcher_dodge_{action}")
    world, enemy = encounter(game)
    world.player.hp = 20
    wait(game, lambda: not world.player.alive)
    assert world.player.hp == 0 and world.player.state == "DYING"
    capture(game, "researcher_bullet_lethal")
    print("PASS: actual SDL jump, depth movement and P avoid bullet damage/effects; "
          "a lethal bullet starts normal DYING rather than HIT.")


def check_counters_and_restart(game):
    for key in "hjkl":
        world, enemy = encounter(game, gap=80, invincible=True)
        enemy.start_attack()
        enemy.animation.elapsed = 1.05 / enemy.attack_fps
        keycode = getattr(pico2d, f"SDLK_{key}")
        push_key(keycode)
        tick(game)
        release(game, keycode)
        wait_for_hold(game)
        assert enemy.ammo == 7 and enemy.sprite_image == config.RESEARCHER_IMAGE
        start_follow_up(game)
        wait(game, lambda: enemy.hp == 120)
        capture(game, f"researcher_counter_{key}")
        wait(game, lambda: world.counter is None and enemy.counter_move is None)
        assert enemy.ammo == 7 and enemy.state == "IDLE"
    world, enemy = encounter(game, invincible=True)
    wait(game, lambda: bool(world.projectiles))
    saved = world.projectiles[0]
    snapshot = saved.x, saved.elapsed, enemy.ammo, enemy.animation.elapsed
    world.select_stage(5)
    tick(game, 30)
    world.select_stage(6)
    assert world.projectiles[0] is saved
    assert (saved.x, saved.elapsed, enemy.ammo, enemy.animation.elapsed) == snapshot
    textures = dict(game.assets.images)
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert world.stage_index == 0 and world.player.hp == 500
    assert all(not stage.enemies and not stage.projectiles for stage in world.stages)
    world.select_stage(7)
    push_key(pico2d.SDLK_1)
    tick(game)
    release(game, pico2d.SDLK_1)
    assert (world.enemies[0].hp, world.enemies[0].ammo) == (200, 7)
    assert all(game.assets.images[name] is image for name, image in textures.items())
    print("PASS: HJKL/A keep researcher appearance/ammo, inactive bullets pause, and SDL F5 "
          "clears all stages before new HP-200/ammo-7 summons, reusing textures.")


def check_performance(game):
    game.world = World(rng=random.Random(42))
    world = game.world
    world.select_stage(7)
    world.player.invincible = True
    push_key(pico2d.SDLK_4)
    tick(game)
    release(game, pico2d.SDLK_4)
    tick(game, 480)
    assert len(world.enemies) == 4
    capture(game, "researcher_factory_combat")
    start = perf_counter()
    frames = game.run(max_frames=180)
    seconds = perf_counter() - start
    print(f"BENCHMARK: 4 researchers + bullets/firing/reloads/HP/UI: "
          f"{frames} frames / {seconds:.3f}s = {frames / seconds:.2f} FPS.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_summons(game)
        check_source_and_bullet_pixels(game)
        check_health_and_damage(game)
        check_magazines_and_hits(game)
        check_dodges_and_invincibility(game)
        check_counters_and_restart(game)
        check_performance(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
