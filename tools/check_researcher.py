"""Actual SDL verification of researchers, warnings, ballistic bullets and reloads."""

from math import sqrt
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
from projectiles import ResearcherBullet
from researcher import Researcher
from tests.helpers import enter_kick_wait
from tools.check_damage_numbers import capture_number
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, release, tick
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


def check_warning_pixels(game):
    image = render_image(game).convert("RGB")
    with patch.object(game.assets, "draw_researcher_aim"):
        clean = render_image(game).convert("RGB")
    delta = ImageChops.difference(image, clean)
    box = delta.getbbox()
    assert box is not None and box[3] - box[1] <= 2 * config.RESEARCHER_AIM_DOT_RADIUS + 1, box
    changed = [(x, y) for y in range(box[1], box[3]) for x in range(box[0], box[2])
               if delta.getpixel((x, y)) != (0, 0, 0)]
    # Actors cover the warning; their translucent edge pixels can tint a dot.
    red = [point for point in changed if image.getpixel(point) == config.RESEARCHER_AIM_COLOR]
    assert len(red) > 80 and len(red) >= len(changed) * 0.75
    xs = sorted({x for x, y in red if y == (box[1] + box[3]) // 2})
    runs = []
    for x in xs:
        if not runs or x > runs[-1][-1] + 1:
            runs.append([])
        runs[-1].append(x)
    assert len(runs) >= 8 and all(len(run) <= 2 * config.RESEARCHER_AIM_DOT_RADIUS + 1 for run in runs)
    assert all(second[0] - first[-1] > 1 for first, second in zip(runs, runs[1:]))


def check_aim_warning(game):
    details = game.ui.details_visible
    game.ui.details_visible = False
    try:
        for index in (6, 7):
            for side in (-1, 1):
                for speed in (0.8, 1.4):
                    world, original = encounter(game, index=index, side=side, invincible=True)
                    enemy = Researcher(original.x, -side, ground_y=original.ground_y, attack_speed=speed)
                    enemy.walkable = world.stage.walkable
                    world.enemies[:] = [enemy]
                    tick(game)
                    assert enemy.aiming and enemy.animation.frame == 2 and enemy.ammo == 7
                    warning = enemy.aim_line
                    assert warning[1] == warning[3] == enemy.y + config.RESEARCHER_MUZZLE_HEIGHT
                    assert warning[0] == enemy.x + enemy.facing * config.RESEARCHER_MUZZLE_X
                    elapsed, remaining = world.elapsed, enemy.aim_remaining
                    check_warning_pixels(game)
                    capture(game, f"researcher_aim_{index}_{side}_{speed}_warning")
                    if speed == 0.8:
                        for camera_x, shake_y in ((0, -4), (640, 0), (1280, 4)):
                            world.camera.x, world.camera.offset_y = camera_x, shake_y
                            check_warning_pixels(game)
                            capture(game, f"researcher_aim_{index}_{side}_camera_{camera_x}")
                        world.camera.offset_y = 0
                        world.update_camera(0)
                    assert (world.elapsed, enemy.aim_remaining) == (elapsed, remaining)
                    if index == 6 and side == -1 and speed == 0.8:
                        for _ in range(2):
                            push_key(pico2d.SDLK_u)
                            game.handle_events()
                            game.update(0)
                            release(game, pico2d.SDLK_u)
                            check_warning_pixels(game)
                        game.ui.details_visible = False
                    tick(game, 29)
                    assert enemy.aiming and enemy.ammo == 7 and not world.projectiles
                    check_warning_pixels(game)
                    tick(game)
                    assert not enemy.aiming and enemy.aim_line is None and enemy.ammo == 6
                    assert len(world.projectiles) == 1 and world.projectiles[0].y == warning[1]
                    with patch.object(pico2d, "draw_circle", wraps=pico2d.draw_circle) as dots:
                        capture(game, f"researcher_aim_{index}_{side}_{speed}_fired")
                    dots.assert_not_called()
    finally:
        game.ui.details_visible = details
    print("PASS: both interiors/facings and 0.8/1.4 attack speeds show real separated red dot "
          "pixels for 30 rendered frames before firing; raised-pistol pose, muzzle/bullet "
          "lane, scrolled/shaken views, U-hide and render-only timer stability verified.")


def check_aim_interruptions_and_pause(game):
    for index in (6, 7):
        world, enemy = encounter(game, index=index, gap=80, invincible=True)
        tick(game)
        assert enemy.aiming
        push_key(pico2d.SDLK_s)
        wait(game, lambda: enemy.hp < 200)
        release(game, pico2d.SDLK_s)
        assert enemy.state == "HIT" and enemy.ammo == 7 and enemy.aim_line is None
        assert enemy.aim_remaining == 0 and not world.projectiles
        capture(game, f"researcher_aim_{index}_interrupted")

        world, enemy = encounter(game, index=index, invincible=True)
        tick(game)
        snapshot = enemy.aim_remaining, enemy.animation.elapsed, enemy.ammo
        world.select_stage(5)
        tick(game, 30)
        world.select_stage(index)
        assert (enemy.aim_remaining, enemy.animation.elapsed, enemy.ammo) == snapshot
        check_warning_pixels(game)
        world.pending_stage_index = 5 if index == 6 else 8
        world.stage_loading_remaining = config.STAGE_LOADING_DURATION
        game.update(0.5)
        assert (enemy.aim_remaining, enemy.animation.elapsed, enemy.ammo) == snapshot
        with patch.object(pico2d, "draw_circle", wraps=pico2d.draw_circle) as dots:
            capture(game, f"researcher_aim_{index}_loading")
        dots.assert_not_called()
        push_key(pico2d.SDLK_F5)
        tick(game)
        release(game, pico2d.SDLK_F5)
        assert world.stage_index == 0 and all(not stage.enemies and not stage.projectiles
                                            for stage in world.stages)

        world, enemy = encounter(game, index=index, invincible=True)
        enter_kick_wait(world)
        tick(game, 120)
        assert world.time_scale == 0.2 and enemy.aiming and enemy.ammo == 7
        check_warning_pixels(game)
        capture(game, f"researcher_aim_{index}_slow_warning")
        wait(game, lambda: enemy.ammo == 6)
        assert enemy.aim_line is None
    print("PASS: real SDL S cancels the warning/shot without spending ammo; stage inactivity "
          "and loading freeze it, loading hides it, F5 clears it, and W slow motion scales "
          "the half-second warning in both interiors.")


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
        enemy.update(config.RESEARCHER_AIM_DURATION, world.player)
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
            world.stage.encounter_started = True  # Only the selected shooter fires in this check.
            world.player.max_hp = world.player.hp = 600  # Survive two full magazines.
            shots, reloads, impacts = 0, 0, 0
            previous_ammo, previous_hp = 7, world.player.hp
            reload_frames = set()
            reload_captured = False
            warning_started = None
            warning_count = 0
            for _ in range(1200):
                was_aiming = enemy.aiming
                tick(game)
                if enemy.aiming and not was_aiming:
                    warning_started = world.elapsed
                    warning_count += 1
                if enemy.ammo < previous_ammo:
                    assert enemy.ammo == previous_ammo - 1 and enemy.animation.row == 4
                    assert warning_started is not None
                    assert abs(world.elapsed - warning_started - config.RESEARCHER_AIM_DURATION) <= 1 / 60 + 1e-8
                    assert enemy.aim_line is None
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
                    assert previous_hp - world.player.hp == 40 and world.player.state == "IDLE"
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
            assert (shots, reloads, impacts, enemy.ammo, world.player.hp) == (14, 2, 14, 7, 40)
            assert warning_count == 14
    print("PASS: both maps x both directions naturally fire exactly 7, play every row-5 reload "
          "frame with zero ammo, refill 7, and repeat; every shot has a half-second warning, "
          "and 14 real hits deal 560 total with impact effects while the player stays idle.")


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


def capture_ballistic_pixels(game, bullet, name):
    image = capture(game, name).convert("RGB")
    with patch.object(game.assets, "draw_projectile"):
        clean = render_image(game).convert("RGB")
    box = ImageChops.difference(image, clean).getbbox()
    assert box is not None and box[2] - box[0] <= 27 and box[3] - box[1] <= 8, box
    screen_y = bullet.y - game.world.camera.render_y
    assert abs((box[1] + box[3]) / 2 - (config.SCREEN_HEIGHT - screen_y)) <= 4, box


def check_ballistic_flight(game):
    details = game.ui.details_visible
    game.ui.details_visible = False
    try:
        for index in (6, 7):
            for facing in (-1, 1):
                world, enemy = encounter(game, index=index, side=-facing)
                enemy.x = enemy.previous_x = 300 if facing > 0 else config.WORLD_WIDTH - 300
                player = world.player
                player.x = player.previous_x = enemy.x + facing * 300
                world.update_camera(0)
                wait(game, lambda: bool(world.projectiles))
                bullet = world.projectiles[0]
                origin = bullet.x - facing * config.RESEARCHER_BULLET_SPEED * bullet.elapsed
                height, depth = bullet.height, bullet.ground_y
                enemy.take_damage(enemy.hp)
                push_key(pico2d.SDLK_DOWN)
                tick(game, 12)
                release(game, pico2d.SDLK_DOWN)
                while not bullet.falling:
                    assert bullet in world.projectiles and bullet.height == height
                    tick(game)
                # A shot may be born halfway through a two-step rendered frame.
                # Inspect the first rendered frame past the exact range boundary.
                fall_time = bullet.elapsed - bullet.straight_duration
                assert bullet in world.projectiles and 0 <= fall_time <= 1 / 60 + 1e-8
                assert abs(bullet.height - (height - config.RESEARCHER_BULLET_GRAVITY
                                            * fall_time ** 2 / 2)) < 1e-8
                assert abs(abs(bullet.x - origin)
                           - config.RESEARCHER_BULLET_SPEED * bullet.elapsed) < 1e-8
                view_x = max(0, min(config.WORLD_WIDTH - config.SCREEN_WIDTH,
                                    bullet.x + facing * 200 - config.SCREEN_WIDTH / 2))
                world.camera.x = view_x
                capture_ballistic_pixels(game, bullet, f"researcher_fall_{index}_{facing}_range")
                for frame in range(1, 31):
                    tick(game)
                    if bullet not in world.projectiles:
                        break
                    fall_time = bullet.elapsed - bullet.straight_duration
                    assert abs(bullet.height - (height - config.RESEARCHER_BULLET_GRAVITY
                                                * fall_time ** 2 / 2)) < 1e-8
                    assert abs(bullet.x - (origin + facing
                                          * config.RESEARCHER_BULLET_SPEED * bullet.elapsed)) < 1e-8
                    assert (bullet.floor, bullet.ground_y) == (0, depth) and bullet.vy < 0
                    if frame in (6, 12, 18, 24):
                        world.camera.x = view_x
                        snapshot = bullet.x, bullet.height, bullet.elapsed, bullet.vy
                        capture_ballistic_pixels(game, bullet, f"researcher_fall_{index}_{facing}_{frame}")
                        if frame == 12:
                            world.camera.offset_y = 4
                            capture_ballistic_pixels(game, bullet,
                                                     f"researcher_fall_{index}_{facing}_shake")
                            world.camera.offset_y = 0
                        assert (bullet.x, bullet.height, bullet.elapsed, bullet.vy) == snapshot
                assert bullet not in world.projectiles and bullet.finished
                expected_time = bullet.straight_duration + sqrt(
                    2 * (height - config.RESEARCHER_BULLET_HALF_HEIGHT)
                    / config.RESEARCHER_BULLET_GRAVITY)
                assert abs(bullet.elapsed - expected_time) < 1e-8
                assert bullet.height == config.RESEARCHER_BULLET_HALF_HEIGHT
                assert player.hp == 500 and not world.effects and world.camera.shake_remaining == 0
                assert len(world.stage.drop_items) == 15
                world.camera.x = view_x
                with patch.object(game.assets, "draw_projectile", wraps=game.assets.draw_projectile) as draw:
                    capture(game, f"researcher_fall_{index}_{facing}_ground_removed")
                draw.assert_not_called()
    finally:
        game.ui.details_visible = details
    print("PASS: actual shots in both interiors/directions keep all 1125px of straight flight, "
          "survive the shooter, then show real curved descending bullet pixels at 6/12/18/24 "
          "frames, with camera/shake alignment; ground contact removes the bullet immediately "
          "without a corpse, drop, impact, damage or shake.")


def check_ballistic_hits_and_pause(game):
    for index in (6, 7):
        for facing in (-1, 1):
            for invincible in (False, True):
                game.world = World()
                world = game.world
                world.select_stage(index)
                bullet = ResearcherBullet(300 if facing > 0 else config.WORLD_WIDTH - 300,
                                          100, 300, facing)
                player = world.player
                player.x = player.previous_x = (bullet.x + facing
                                                * (config.RESEARCHER_BULLET_STRAIGHT_RANGE
                                                   + config.RESEARCHER_BULLET_SPEED * 0.6))
                world.projectiles.append(bullet)
                if invincible:
                    push_key(pico2d.SDLK_p)
                    tick(game)
                    release(game, pico2d.SDLK_p)
                wait(game, lambda: not world.projectiles)
                assert bullet.falling and bullet.spent
                assert player.hp == (500 if invincible else 460)
                assert len(world.effects) == (0 if invincible else 1)
                if not invincible:
                    assert player.state == "IDLE" and world.effects[0].image_name == config.CLUB_HIT_IMAGE
                    assert abs(world.effects[0].y - bullet.y) < 1e-8
                    assert world.camera.shake_remaining > 0
                capture(game, f"researcher_fall_hit_{index}_{facing}_{invincible}")
        game.world = World()
        world = game.world
        world.select_stage(index)
        straight = config.RESEARCHER_BULLET_STRAIGHT_RANGE / config.RESEARCHER_BULLET_SPEED
        bullet = ResearcherBullet(900, world.stage.walkable.bounds[3], 78.75, 1, elapsed=straight + 0.1)
        world.projectiles.append(bullet)
        enter_kick_wait(world)
        tick(game, 6)
        assert world.time_scale == 0.2
        assert abs(bullet.elapsed - straight - 0.12) < 1e-8
        assert abs(bullet.height - (83.25 - config.RESEARCHER_BULLET_GRAVITY * 0.12 ** 2 / 2)) < 1e-8
        capture_ballistic_pixels(game, bullet, f"researcher_fall_{index}_slow")
        snapshot = bullet.x, bullet.height, bullet.elapsed, bullet.vy
        world.select_stage(5)
        tick(game, 30)
        world.select_stage(index)
        assert (bullet.x, bullet.height, bullet.elapsed, bullet.vy) == snapshot
        world.pending_stage_index = 5 if index == 6 else 8
        world.stage_loading_remaining = config.STAGE_LOADING_DURATION
        game.update(0.5)
        assert (bullet.x, bullet.height, bullet.elapsed, bullet.vy) == snapshot
        with patch.object(game.assets, "draw_projectile", wraps=game.assets.draw_projectile) as draw:
            capture(game, f"researcher_fall_{index}_loading")
        draw.assert_not_called()
        push_key(pico2d.SDLK_F5)
        tick(game)
        release(game, pico2d.SDLK_F5)
        assert world.stage_index == 0 and all(not stage.projectiles for stage in world.stages)
    print("PASS: curved rounds in both interiors/directions deal 40 with one impact effect "
          "at the real height; SDL P consumes them harmlessly. Actual SDL R scales the fall, "
          "inactive/loading frames freeze height/velocity/time, loading hides it, and F5 clears it.")


def check_restart(game):
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
    print("PASS: inactive bullets pause, and SDL F5 "
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
        check_aim_warning(game)
        check_aim_interruptions_and_pause(game)
        check_source_and_bullet_pixels(game)
        check_health_and_damage(game)
        check_magazines_and_hits(game)
        check_dodges_and_invincibility(game)
        check_ballistic_flight(game)
        check_ballistic_hits_and_pause(game)
        check_restart(game)
        check_performance(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
