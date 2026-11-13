"""Exercise H/J/K/L through real SDL input and capture both matching sheets."""

from pathlib import Path
import sys
from unittest.mock import patch

from PIL import ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from counter import COUNTERS
from enemy import Enemy
from game import Game
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, tick
from world import World


def attacker(game, side=1, *, hp=200, gap=80, depth=0, frame=2):
    player = game.world.player
    enemy = Enemy(player.x + side * gap, -side, ground_y=player.ground_y + depth)
    enemy.hp = hp
    enemy.animation.set_state("ATTACK")
    enemy.animation.elapsed = (frame + 0.05) / enemy.attack_fps
    enemy.cooldown = enemy.attack_interval
    game.world.enemies.append(enemy)
    return enemy


def release(game, key):
    push_key(key, down=False)
    game.handle_events()


def assert_pair(game, enemy, move):
    player = game.world.player
    assert game.world.counter is not None
    assert (player.sprite_image, enemy.sprite_image) == (
        config.COUNTER_PLAYER_IMAGE, config.COUNTER_ENEMY_IMAGE)
    assert player.animation.row == enemy.animation.row == move.row
    assert enemy.animation.frame <= player.animation.frame
    assert player.animation.elapsed == enemy.animation.elapsed
    assert player.hp == 500 and enemy.has_hit


def check_rows_damage_and_recovery(game):
    textures = dict(game.assets.images)
    for side in (-1, 1):
        for move in COUNTERS.values():
            game.world = World()
            enemy = attacker(game, side)
            key = getattr(pico2d, f"SDLK_{move.key}")
            push_key(key)
            tick(game)
            assert_pair(game, enemy, move)
            airborne = False
            while enemy.hp == 200:
                assert_pair(game, enemy, move)
                if move.key == "l" and enemy.animation.frame == 3 and not airborne:
                    capture(game, f"counter_l_{side}_airborne")
                    airborne = True
                tick(game)
            assert enemy.hp == 120
            assert [number.damage for number in game.world.damage_numbers] == [80]
            with patch.object(game.assets, "draw_sprite", wraps=game.assets.draw_sprite) as draw:
                image = capture(game, f"counter_{move.key}_{side}_impact")
            sheets = [call.args[0] for call in draw.call_args_list]
            assert sheets.count(config.COUNTER_PLAYER_IMAGE) == 1
            assert sheets.count(config.COUNTER_ENEMY_IMAGE) == 1
            for index in range(4):
                x = 22 + index * 310
                gold = sum(r > 180 and g > 130 and b < 120
                           for r, g, b, _ in image.crop((x, 636, x + 300, 655)).get_flattened_data())
                assert gold > 40, (move.key, index, gold)
            push_key(key, repeat=True)
            while game.world.counter is not None:
                assert_pair(game, enemy, move)
                tick(game)
            assert game.world.player.state == "IDLE"
            assert enemy.counter_move is move and not enemy.counter_linked
            assert move.duration - 1e-9 <= game.world.elapsed < move.enemy_duration
            capture(game, f"counter_{move.key}_{side}_enemy_reaction")
            while enemy.counter_move is not None:
                tick(game)
            assert enemy.hp == 120 and enemy.state == "IDLE"
            assert enemy.sprite_image == config.ENEMY_IMAGE
            assert game.world.player.state == "IDLE"
            tick(game)
            assert game.world.counter is None and enemy.hp == 120
            if side > 0:
                capture(game, f"counter_{move.key}_recovered")
            game.world.player.x += side * 500
            tick(game)
            assert enemy.state == "RUN" and enemy.vx * side > 0
            release(game, key)
    assert all(game.assets.images[name] is image for name, image in textures.items())
    print("PASS: SDL H/J/K/L match rows 1-4 on both sides, deal 80 once, show four HUD hints, "
          "release the player at 1s, finish slower enemy reactions, and restore IDLE/chase.")


def check_lethal_counters(game):
    for move in COUNTERS.values():
        game.world = World()
        enemy = attacker(game, hp=40)
        key = getattr(pico2d, f"SDLK_{move.key}")
        push_key(key)
        tick(game)
        while enemy.hp:
            tick(game)
        assert game.world.counter is not None and enemy.counter_move is move
        assert [number.damage for number in game.world.damage_numbers] == [40]
        while game.world.counter is not None or enemy.counter_move is not None:
            tick(game)
        assert enemy.state == "DEAD" and enemy.sprite_image == config.COUNTER_ENEMY_IMAGE
        assert (enemy.animation.row, enemy.animation.frame) == (move.row, 7)
        capture(game, f"counter_{move.key}_defeated")
        tick(game, 30)
        assert enemy.hp == 0 and enemy.animation.frame == 7
        assert enemy.attack_box is None
        release(game, key)
    print("PASS: lethal counters finish the supplied reaction and keep the matching final pose; "
          "HP clamps at zero, no resurrection or extra attacks.")


def check_windows_held_input_and_restart(game):
    for gap, depth, frame in ((200, 0, 2), (80, 44, 2), (80, 0, 0), (80, 0, 7)):
        game.world = World()
        attacker(game, gap=gap, depth=depth, frame=frame)
        push_key(pico2d.SDLK_h)
        tick(game)
        assert game.world.counter is None
        release(game, pico2d.SDLK_h)
    game.world = World()
    push_key(pico2d.SDLK_h)
    tick(game)
    enemy = attacker(game)
    tick(game)
    assert game.world.counter is None
    release(game, pico2d.SDLK_h)
    push_key(pico2d.SDLK_h)
    tick(game)
    assert game.world.counter.enemy is enemy
    textures = dict(game.assets.images)
    push_key(pico2d.SDLK_F5)
    tick(game)
    assert game.world.counter is None and enemy.counter_move is None
    assert game.world.player.hp == 500 and game.world.player.state == "IDLE"
    assert all(not stage.enemies for stage in game.world.stages)
    assert all(game.assets.images[name] is image for name, image in textures.items())
    release(game, pico2d.SDLK_h)
    release(game, pico2d.SDLK_F5)
    print("PASS: SDL range/depth/timing gates, no held-key or late automatic counter, "
          "fresh re-press and F5 release/reset/resource reuse.")


def check_corpse_fade(game):
    for style in ("normal", "counter"):
        game.world = World()
        if style == "counter":
            corpse = attacker(game, hp=40)
            push_key(pico2d.SDLK_h)
            tick(game)
            while game.world.counter is not None or corpse.counter_move is not None:
                tick(game)
            release(game, pico2d.SDLK_h)
        else:
            corpse = Enemy(game.world.player.x + 180, -1)
            game.world.enemies.append(corpse)
            corpse.take_damage(200)
            while corpse.state != "DEAD":
                tick(game)
        corpse.x = game.world.player.x + 180
        corpse.ground_y = 120
        live = Enemy(game.world.player.x - 220)
        if style == "counter":
            # Keep a live pose on the same shared texture to catch alpha leakage.
            live.start_counter(COUNTERS["counter_h"], 1)
            live.animation.elapsed = 4 / COUNTERS["counter_h"].enemy_fps
        game.world.enemies.append(live)
        game.world.camera.update(config.SHAKE_DURATION, game.world.player.x)
        game.world.enemies.remove(corpse)
        background = render_image(game)
        game.world.enemies.insert(0, corpse)
        corpse_region = (700, 400, 940, 625)
        live_region = (300, 360, 540, 625)
        energy = []
        live_pixels = None
        for elapsed, label in ((0, "settled"), (3, "hold_3s"),
                               (3.5, "fade_half"), (4, "fade_end")):
            corpse.corpse_elapsed = elapsed
            image = capture(game, f"{style}_corpse_{label}")
            difference = ImageChops.difference(image.crop(corpse_region).convert("RGB"),
                                              background.crop(corpse_region).convert("RGB"))
            energy.append(sum(sum(pixel) for pixel in difference.get_flattened_data()))
            pixels = image.crop(live_region).tobytes()
            if live_pixels is None:
                live_pixels = pixels
            assert pixels == live_pixels, "Fading changed another actor sharing the texture"
        assert energy[0] > 0 and energy[1] == energy[0]
        assert 0.35 < energy[2] / energy[0] < 0.65
        assert energy[3] == 0
        if live.counter_move is not None:
            live.finish_counter()
        game.update(1 / 60)
        assert corpse not in game.world.enemies and live in game.world.enemies
        assert live.alive and live.opacity == 1
        print(f"PASS: {style} corpse stays opaque through 3s, half-fade pixel ratio "
              f"{energy[2] / energy[0]:.3f}, disappears at 4s; shared live texture stays opaque.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_rows_damage_and_recovery(game)
        check_lethal_counters(game)
        check_windows_held_input_and_restart(game)
        check_corpse_fade(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
