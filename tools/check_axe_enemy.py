"""Exercise loading-dock axe summons, combat and HP/text/effect pixels via SDL."""

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
from tools.check_counters import release, start_follow_up, wait_for_hold
from tools.check_damage_numbers import capture_number
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, tick
from world import World


DOCK = config.STAGE_IMAGES.index(config.FACTORY_OUTSIDE_IMAGE)


def encounter(game, side=1, *, hp=400, weapon=None):
    game.world = World(rng=random.Random(23), item_rng=random.Random(5))
    world = game.world
    world.select_stage(DOCK)
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


def check_summons(game):
    texture = game.assets.images[config.AXE_ENEMY_IMAGE]
    for prefix in ("", "KP_"):
        for count in config.SPAWN_COUNTS:
            game.world = World(rng=random.Random(42))
            world = game.world
            world.select_stage(DOCK)
            tick(game, 12)
            assert not world.enemies
            key = getattr(pico2d, f"SDLK_{prefix}{count}")
            push_key(key)
            tick(game)
            assert len(world.enemies) == world.spawner.spawned_count == count
            assert all(type(enemy) is AxeEnemy and enemy.hp == enemy.max_hp == 400
                       and enemy.attack_damage == 60 for enemy in world.enemies)
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
        capture(game, f"axe_spawn_{label}")
    print("PASS: all 18 SDL digit/keypad inputs summon their count of HP-400/damage-60 "
          "axe enemies only on the dock; repeat latch, fresh input, bounds and texture reuse.")


def check_source_frames(game):
    world, enemy = encounter(game)
    texture = game.assets.images[config.AXE_ENEMY_IMAGE]
    for facing in (-1, 1):
        enemy.facing = facing
        for state, row in (("IDLE", 1), ("WALK", 2), ("RUN", 3), ("ATTACK", 4),
                           ("HIT", 5), ("DYING", 6)):
            enemy.animation.set_state(state)
            fps = enemy.animation.definitions[state][1]
            for frame in range(8):
                enemy.animation.elapsed = (frame + 0.05) / fps
                tile = game.assets.frames[config.AXE_ENEMY_IMAGE][row - 1][frame]
                with patch.object(texture, "clip_composite_draw",
                                  wraps=texture.clip_composite_draw) as draw:
                    render_image(game)
                args = draw.call_args.args
                assert args[:4] == tuple(tile["clip"])
                assert args[5] == ("h" if facing < 0 else "")
                assert abs(args[7] - args[9] / 2 - (enemy.y - world.camera.render_y)) < 1e-8
                assert enemy.animation.row != 7
    print("PASS: own sheet rows 1..6, all 8 frames in both directions, exact clips/flips/feet; "
          "last-row stun has no runtime mapping.")


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
    for side in (-1, 1):
        world, enemy = encounter(game, side)
        world.player.invincible = False
        enemy.start_attack()
        for _ in range(60):
            tick(game)
            if enemy.has_hit:
                break
        assert world.player.hp == 440 and enemy.has_hit
        assert len(world.effects) == 1 and world.effects[0].image_name == config.CLUB_HIT_IMAGE
        assert world.camera.shake_remaining > 0
        capture(game, f"axe_attack_{side}")
        tick(game, 6)
        assert world.player.hp == 440
    print("PASS: both directions of axe swing deal 60 once, with existing club impact and hit shake.")


def check_strong_and_counter_reactions(game):
    for move in STRONG_MOVES.values():
        world, enemy = encounter(game)
        press_attack(game, move.key, enemy)
        assert enemy.hp == 350 and enemy.animation.row == 5
        capture(game, f"axe_strong_{move.key}")
    for key in "hjkl":
        world, enemy = encounter(game)
        enemy.start_attack()
        enemy.animation.elapsed = 1.05 / enemy.attack_fps
        keycode = getattr(pico2d, f"SDLK_{key}")
        push_key(keycode)
        tick(game)
        release(game, keycode)
        wait_for_hold(game)
        assert enemy.hp == 400 and enemy.animation.row in (5, 6)
        capture(game, f"axe_counter_{key}_hold")
        start_follow_up(game)
        hit_captured = False
        for _ in range(180):
            assert enemy.sprite_image == config.AXE_ENEMY_IMAGE and enemy.animation.row < 7
            tick(game)
            if enemy.hp == 320 and not hit_captured:
                capture(game, f"axe_counter_{key}_impact")
                hit_captured = True
            if world.counter is None and enemy.counter_move is None:
                break
        assert hit_captured and enemy.hp == 320 and enemy.state == "IDLE"
    print("PASS: real SDL QWERT and all HJKL hold/A follow-ups keep axe identity, "
          "50/80 single damage, own recovery rows and no row-7 stun.")


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


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_summons(game)
        check_source_frames(game)
        check_health_pixels(game)
        check_player_damage_pixels(game)
        check_axe_attack(game)
        check_strong_and_counter_reactions(game)
        check_combat_and_restart(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
