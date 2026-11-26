"""Exercise replacement axe art, both factory summons and combat through SDL."""

from math import isclose, tau
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
from axe_enemy import AxeEnemy
from combat import STRONG_MOVES
from game import Game
from tools.check_damage_numbers import capture_number
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, release, tick
from ui import PLAYER_BOUNDS_COLOR
from world import World


DOCK = config.STAGE_IMAGES.index(config.FACTORY_OUTSIDE_IMAGE)
EXTERIORS = tuple(config.STAGE_IMAGES.index(name) for name in config.AXE_ENEMY_STAGE_IMAGES)


def encounter(game, side=1, *, hp=400, weapon=None, index=DOCK):
    game.world = World(rng=random.Random(23), item_rng=random.Random(5))
    world = game.world
    world.select_stage(index)
    world.player.facing = side
    world.player.invincible = True
    world.player.equip_weapon(weapon)
    enemy = world.spawner.spawn(1, world.elapsed)[0]
    world.enemies = [enemy]
    enemy.x = enemy.previous_x = world.player.x + side * 80
    enemy.ground_y = enemy.previous_ground_y = world.player.ground_y
    enemy.facing = -side
    enemy.hp, enemy.cooldown = hp, 100
    return world, enemy


def check_stair_free_dock_floor(game):
    assert config.FACTORY_OUTSIDE_IMAGE == "factory_loading_dock_no_stairs_1672x941.png"
    assert config.FACTORY_OUTSIDE_IMAGE in game.assets.images
    assert config.ARCHIVED_FACTORY_OUTSIDE_IMAGE not in game.assets.images
    assert Path(config.ARCHIVED_FACTORY_OUTSIDE_IMAGE).name not in game.assets.images
    visible, details = game.ui.floor_bounds_visible, game.ui.details_visible
    game.ui.floor_bounds_visible, game.ui.details_visible = False, False
    try:
        push_key(pico2d.SDLK_F4)
        tick(game)
        release(game, pico2d.SDLK_F4)
        assert game.ui.floor_bounds_visible
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for running in (False, True):
                for side in (-1, 1):
                    for depth in (-1, 1):
                        game.world = World(item_rng=random.Random(23))
                        world = game.world
                        world.select_stage(DOCK)
                        player = world.player
                        assert world.stage.walkable.bounds == (0, 45, 2560, 258)
                        assert not world.stage.stairs and world.stage.upper_walkable is None
                        player.equip_weapon(weapon)
                        player.x = player.previous_x = 300 if side < 0 else 2260
                        keys = (pico2d.SDLK_LEFT if side < 0 else pico2d.SDLK_RIGHT,
                                pico2d.SDLK_DOWN if depth < 0 else pico2d.SDLK_UP)
                        if running:
                            keys += (pico2d.SDLK_LSHIFT,)
                        for key in keys:
                            push_key(key)
                        tick(game, 90)
                        for key in keys:
                            release(game, key)
                        assert (player.x, player.ground_y, player.jump_height, player.floor) == (
                            68 if side < 0 else 2492, 45 if depth < 0 else 258, 0, 0)
                        with patch.object(pico2d, "draw_line", wraps=pico2d.draw_line) as draw:
                            if weapon is None:
                                capture(game, f"dock_no_stairs_{'run' if running else 'walk'}_{side}_{depth}")
                            else:
                                render_image(game)
                        endpoints = {point for call in draw.call_args_list
                                     if call.args[4:] == PLAYER_BOUNDS_COLOR
                                     for point in (call.args[:2], call.args[2:4])}
                        assert (player.x - world.camera.render_x,
                                player.ground_y - world.camera.render_y) in endpoints
                        assert 941 - player.ground_y == (896 if depth < 0 else 683)
        for depth in (45, 258):
            game.world = World(item_rng=random.Random(23))
            world = game.world
            world.select_stage(DOCK)
            player = world.player
            player.ground_y = player.previous_ground_y = depth
            for _ in range(2):
                push_key(pico2d.SDLK_SPACE)
                tick(game, 3)
                release(game, pico2d.SDLK_SPACE)
            assert player.jump_count == 2
            tick(game, 120)
            assert player.grounded and player.ground_y == depth and player.floor == 0
            capture(game, f"dock_no_stairs_jump_landed_{depth}")
        push_key(pico2d.SDLK_F5)
        tick(game)
        release(game, pico2d.SDLK_F5)
        assert world.stage_index == 0 and game.ui.floor_bounds_visible
        world.select_stage(DOCK)
        assert world.stage.image_name == config.FACTORY_OUTSIDE_IMAGE
        assert world.stage.walkable.bounds == (0, 45, 2560, 258)
        assert len(world.stage.drop_items) == 15 and not world.enemies
        capture(game, "dock_no_stairs_restarted")
    finally:
        game.ui.floor_bounds_visible, game.ui.details_visible = visible, details
    print("PASS: new stair-free dock is loaded, archived art is not; all 3 loadouts walk/run "
          "to all 4 concrete-floor corners, F4 matches source rows 683/896, double jumps "
          "land on both depth edges without ghost stairs/platforms, and F5 preserves the new map.")


def check_summons(game):
    texture = game.assets.images[config.AXE_ENEMY_IMAGE]
    for index in EXTERIORS:
        for prefix in ("", "KP_"):
            for count in config.SPAWN_COUNTS:
                game.world = World(rng=random.Random(42))
                world = game.world
                world.select_stage(index)
                tick(game, 12)
                assert not world.enemies
                key = getattr(pico2d, f"SDLK_{prefix}{count}")
                push_key(key)
                tick(game)
                assert len(world.enemies) == world.spawner.spawned_count == count
                assert all(type(enemy) is AxeEnemy and enemy.hp == enemy.max_hp == 400
                           and enemy.attack_damage == 40 and enemy.sprite_image == config.AXE_ENEMY_IMAGE
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
                assert game.assets.images[config.AXE_ENEMY_IMAGE] is texture
        for label, camera_x in (("left", 0), ("right", config.WORLD_WIDTH - config.SCREEN_WIDTH)):
            game.world.camera.x = camera_x
            capture(game, f"axe_spawn_{index}_{label}")
    print("PASS: both factory exteriors/all 36 SDL digit/keypad cases summon the new HP-400/damage-40 "
          "axe enemy; repeat latch, fresh input, bounds and texture reuse.")


def check_source_frames(game):
    world, enemy = encounter(game)
    for name in (config.ARCHIVED_AXE_ENEMY_IMAGE, Path(config.ARCHIVED_AXE_ENEMY_IMAGE).name):
        assert name not in game.assets.images and name not in game.assets.frames
    for armed in (True, False):
        enemy._set_armed(armed)
        name = config.AXE_ENEMY_IMAGE if armed else config.AXE_ENEMY_UNARMED_IMAGE
        texture = game.assets.images[name]
        assert (texture.w, texture.h) == (2048, 1792)
        assert len(game.assets.frames[name]) == 7
        poses = ("IDLE", "WALK", "RUN", "swing", "HIT", "DYING", "throw") if armed else (
            "IDLE", "WALK", "RUN", "punch", "kick", "HIT", "DYING")
        for row, state in enumerate(poses, 1):
            if state in enemy.attacks:
                enemy._start_move(state)
            else:
                enemy.animation.set_state(state)
            assert enemy.sprite_image == name and enemy.animation.row == row
            for facing in (-1, 1):
                enemy.facing = facing
                check_pose_frames(game, world, enemy, texture, state)
    print("PASS: both 7x8 sheets rendered with the expected clips, flips and feet in both directions.")


def check_pose_frames(game, world, enemy, texture, state):
    fps = enemy.animation.definitions[enemy.state][1]
    for frame, tile in enumerate(game.assets.frames[enemy.sprite_image][enemy.animation.row - 1]):
        enemy.animation.elapsed = (frame + 0.05) / fps
        with patch.object(texture, "clip_composite_draw", wraps=texture.clip_composite_draw) as draw:
            render_image(game)
        args = draw.call_args.args
        assert args[:4] == tuple(tile["clip"])
        assert args[5] == ("h" if enemy.facing < 0 else "")
        assert abs(args[7] - args[9] / 2 - (enemy.y - world.camera.render_y)) < 1e-8
        if frame == 4 and state in ("swing", "throw", "punch", "kick"):
            capture(game, f"axe_replacement_{state}_{enemy.facing}_{frame}")


def check_throw_and_pickup(game):
    world, enemy = encounter(game, side=-1)
    player = world.player
    world.stage.drop_items.clear()
    enemy.cooldown = 0
    player.invincible = False
    tick(game, 30)
    assert player.hp == 460
    with patch.object(enemy.rng, "random", return_value=0):
        push_key(pico2d.SDLK_LSHIFT)
        push_key(pico2d.SDLK_RIGHT)
        for _ in range(150):
            tick(game)
            if enemy.attack_kind == "throw":
                break
        assert enemy.attack_kind == "throw", (player.state, player.x, enemy.x)
        release(game, pico2d.SDLK_RIGHT)
        release(game, pico2d.SDLK_LSHIFT)
        for _ in range(60):
            tick(game)
            if world.projectiles:
                break
    shot, = world.projectiles
    assert enemy.animation.row == 7 and enemy.animation.frame == 4 and not enemy.armed
    capture(game, "axe_enemy_release")
    texture = game.assets.images[config.AXE_PROJECTILE_IMAGE]
    for _ in range(2):
        tick(game)
        with patch.object(texture, "clip_composite_draw", wraps=texture.clip_composite_draw) as draw:
            render_image(game)
        assert isclose(draw.call_args.args[4], -shot.facing * tau * 8 * shot.elapsed)
    for _ in range(100):
        tick(game)
        if world.stage.drop_items:
            break
    item, = world.stage.drop_items
    assert item.grounded and player.hp == 410 and item.axe_owner is enemy
    player.x, player.ground_y = item.x, item.ground_y
    push_key(pico2d.SDLK_g)
    tick(game)
    release(game, pico2d.SDLK_g)
    assert player.weapon == "axe" and not enemy.armed and not world.stage.drop_items
    print("PASS: retreat triggered one spinning axe in cell five, 50 damage, landing and SDL G pickup.")


def check_health_pixels(game):
    for hp, expected in ((400, 48), (200, 24), (100, 12), (0, 0)):
        world, enemy = encounter(game, hp=hp)
        for details in (True, False):
            game.ui.details_visible = details
            image = render_image(game).convert("RGB")
            tile = game.assets.frames[enemy.sprite_image][enemy.animation.row - 1][enemy.animation.frame]
            scale = config.SPRITE_SCALE
            left = round(enemy.x - world.camera.render_x - config.ENEMY_HP_BAR_WIDTH / 2)
            bottom = (enemy.y - world.camera.render_y
                      + tile["clip"][3] * scale + config.ENEMY_HP_BAR_GAP)
            row = config.SCREEN_HEIGHT - round(bottom) - 2
            widths = [sum(1 for x in range(left, left + 48)
                          if (lambda rgb: rgb[0] > 180 and rgb[1] < 75 and rgb[2] < 90)(
                              image.getpixel((x, y))))
                      for y in range(row - 2, row + 3)]
            assert max(widths) == expected, (hp, details, widths)
        capture(game, f"axe_hp_{hp}")
    game.ui.details_visible = True
    print("PASS: real red HP fill at 400/200/100/0 is 48/24/12/hidden pixels, including U-hide mode.")


def press_attack(game, key, enemy):
    keycode = getattr(pico2d, f"SDLK_{key}")
    before = enemy.hp
    push_key(keycode)
    for frame in range(180):
        if key == "r" and frame == 12:
            release(game, keycode)
            push_key(keycode)
        tick(game)
        assert enemy.sprite_image == config.AXE_ENEMY_IMAGE and enemy.animation.row < 7
        if enemy.hp != before:
            release(game, keycode)
            return
    raise AssertionError(f"SDL {key} did not hit the axe enemy")


def check_player_damage_pixels(game):
    cases = [(None, key) for key in "asdf"]
    cases += [(weapon, key) for weapon in config.WEAPON_POSE_IMAGES for key in "as"]
    for index, (weapon, key) in enumerate(cases):
        world, enemy = encounter(game, side=-1 if index % 2 else 1, weapon=weapon)
        expected = world.player.moves[f"combat_{key}"].damage
        press_attack(game, key, enemy)
        assert enemy.hp == 400 - expected
        assert [number.damage for number in world.damage_numbers] == [expected]
        assert [effect.image_name for effect in world.effects] == [world.player.active_move.hit_image]
        assert world.camera.shake_remaining > 0
        world.update_camera(config.SHAKE_DURATION)
        image = render_image(game)
        with patch.object(world.stage, "effects", []):
            clean = render_image(game)
        assert ImageChops.difference(image.convert("RGB"), clean.convert("RGB")).getbbox() is not None
        capture_number(game, f"axe_damage_{weapon or 'unarmed'}_{key}")
        tick(game, 2)
        assert enemy.hp == 400 - expected
        tick(game, 40)
        assert not world.damage_numbers and not world.effects
    world, enemy = encounter(game, hp=25)
    press_attack(game, "f", enemy)
    assert enemy.hp == 0 and [number.damage for number in world.damage_numbers] == [25]
    capture_number(game, "axe_damage_lethal")
    tick(game, 60)
    assert (enemy.state, enemy.animation.row, enemy.animation.frame) == ("DEAD", 6, 7)
    assert not any(item.kind == "metal_club" for item in world.stage.drop_items)
    capture(game, "axe_defeated")
    enemy.corpse_elapsed = 3.5
    with patch.object(game.assets.images[config.AXE_ENEMY_IMAGE], "opacify",
                      wraps=game.assets.images[config.AXE_ENEMY_IMAGE].opacify) as opacity:
        capture(game, "axe_corpse_half")
    assert [call.args[0] for call in opacity.call_args_list] == [0.5, 1.0]
    print("PASS: SDL ASDF/weapon A/S show exact damage text and matching effect pixels once, "
          "then expire; lethal hit shows remaining HP, own row-6 death/fade, no club drop.")


def check_axe_attack(game):
    for index in EXTERIORS:
        for side in (-1, 1):
            world, enemy = encounter(game, side, index=index)
            world.player.invincible = False
            enemy.start_attack()
            for _ in range(60):
                tick(game)
                if enemy.has_hit:
                    break
            assert world.player.hp == 460 and enemy.has_hit
            assert len(world.effects) == 1 and world.effects[0].image_name == config.CLUB_HIT_IMAGE
            assert world.camera.shake_remaining > 0
            capture(game, f"axe_attack_{index}_{side}")
            tick(game, 6)
            assert world.player.hp == 460
    print("PASS: both maps/facings deal axe damage 40 once, with existing club impact and hit shake.")


def check_strong_reactions(game):
    for move in STRONG_MOVES.values():
        world, enemy = encounter(game)
        press_attack(game, move.key, enemy)
        assert enemy.hp == 350 and enemy.animation.row == 5
        capture(game, f"axe_strong_{move.key}")
    print("PASS: real SDL QWERT keep axe identity, 50 single damage, own recovery rows and no row-7 stun.")


def check_combat_and_restart(game):
    game.world = World(rng=random.Random(19))
    world = game.world
    world.select_stage(DOCK)
    world.player.invincible = True
    push_key(pico2d.SDLK_4)
    tick(game)
    release(game, pico2d.SDLK_4)
    participants = set()
    for _ in range(480):
        tick(game)
        participants.update(enemy for enemy in world.enemies if enemy.has_hit)
        assert all(enemy.sprite_image == config.AXE_ENEMY_IMAGE and enemy.animation.row < 7
                   for enemy in world.enemies)
    assert participants == set(world.enemies) and all(enemy.hp == 400 for enemy in world.enemies)
    capture(game, "axe_dock_combat")
    start = perf_counter()
    frames = game.run(max_frames=180)
    seconds = perf_counter() - start
    print(f"BENCHMARK: four axe enemies + pursuit/attacks/HP/UI: "
          f"{frames} frames / {seconds:.3f}s = {frames / seconds:.2f} FPS.")
    texture = game.assets.images[config.AXE_ENEMY_IMAGE]
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert world.stage_index == 0 and world.player.hp == 500
    assert all(not stage.enemies and not stage.effects and not stage.damage_numbers
               and stage.spawner.spawned_count == 0 for stage in world.stages)
    world.select_stage(DOCK)
    tick(game, 30)
    assert not world.enemies
    push_key(pico2d.SDLK_1)
    tick(game)
    release(game, pico2d.SDLK_1)
    assert len(world.enemies) == 1 and world.enemies[0].hp == 400
    assert game.assets.images[config.AXE_ENEMY_IMAGE] is texture
    print("PASS: natural dock combat, no stun, and SDL F5/new input restore HP-400 summons "
          "while reusing the texture and clearing all stage feedback.")


def check_two_exterior_lifecycle(game):
    world, enemy = encounter(game, index=EXTERIORS[1])
    enemy.take_damage(40)
    snapshot = enemy.hp, enemy.x, enemy.ground_y, enemy.animation.elapsed
    world.select_stage(DOCK)
    tick(game, 30)
    world.select_stage(EXTERIORS[1])
    assert world.enemies == [enemy]
    assert (enemy.hp, enemy.x, enemy.ground_y, enemy.animation.elapsed) == snapshot
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    for index in EXTERIORS:
        world.select_stage(index)
        tick(game, 12)
        assert not world.enemies and world.stage.spawn_cycle_index is None
        push_key(pico2d.SDLK_1)
        tick(game)
        release(game, pico2d.SDLK_1)
        assert len(world.enemies) == 1 and type(world.enemies[0]) is AxeEnemy
        assert (world.enemies[0].hp, world.enemies[0].attack_damage) == (400, 40)
        world.camera.x = 0 if world.enemies[0].x < config.START_X else config.WORLD_WIDTH - config.SCREEN_WIDTH
        capture(game, f"axe_replacement_native_map_{index}")
    print("PASS: second exterior preserves its axe actor/HP across visits; SDL F5 restores "
          "both factory defaults to replacement axe enemies with fresh-input-only summons.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_stair_free_dock_floor(game)
        check_summons(game)
        check_source_frames(game)
        check_throw_and_pickup(game)
        check_health_pixels(game)
        check_player_damage_pixels(game)
        check_axe_attack(game)
        check_strong_reactions(game)
        check_combat_and_restart(game)
        check_two_exterior_lifecycle(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
