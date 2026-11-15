"""Check attack-specific impact sheets, clips and actual SDL combat feedback."""

from math import ceil
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from combat import MOVES
from effects import HitEffect
from enemy import Enemy
from enemy02 import Enemy02
from game import Game
from tools.check_counters import release
from tools.check_enemy02 import encounter, set_frame
from tools.check_render import capture
from tools.check_runtime import push_key, tick, verify_hit_effect_pixels
from world import World


def check_sheets_and_frames(game):
    assert not any("blood" in name.lower() for name in game.assets.images)
    for name, label in ((config.CLUB_HIT_IMAGE, "club_hit"),
                        (config.PUNCH_KICK_HIT_IMAGE, "punch_kick_hit")):
        texture = game.assets.images[name]
        assert (texture.w, texture.h) == (2048, 1024)
        for facing in (-1, 1):
            game.world = World()
            game.world.enemies.clear()
            world = game.world
            effect = HitEffect(world.player.x + facing * 60, 190, facing, image_name=name)
            world.effects = [effect]
            for frame in range(8):
                game.handle_events()
                effect.elapsed = (frame + 0.1) / config.HIT_EFFECT_FPS
                with patch.object(texture, "clip_composite_draw", wraps=texture.clip_composite_draw) as draw:
                    capture(game, f"{label}_{facing}_{frame}")
                assert draw.call_count == 1
                args = draw.call_args.args
                assert args[:4] == (frame % 4 * 512, 512 - frame // 4 * 512, 512, 512)
                assert args[5] == ("h" if facing < 0 else "")
                assert args[6:8] == (effect.x - world.camera.render_x, effect.y - world.camera.render_y)
                assert args[8:10] == (128, 128)
                if frame == 3:
                    verify_hit_effect_pixels(game, f"{label}_{facing}_visible", name)
    print("PASS: two transparent 4x2 sheets, 8 frames x 2 directions each, 128px centered "
          "contact placement/exact clips and real visible pixels; old blood texture is absent.")


def check_player_attacks(game):
    for enemy_type in (Enemy, Enemy02):
        for facing in (-1, 1):
            for key, move in MOVES.items():
                game.world = World()
                world = game.world
                world.stage_index = 3 if enemy_type is Enemy02 else 0
                enemy = enemy_type(world.player.x + facing * 80, -facing)
                enemy.cooldown = 100
                world.enemies = [enemy]
                direction = pico2d.SDLK_LEFT if facing < 0 else pico2d.SDLK_RIGHT
                attack = getattr(pico2d, f"SDLK_{move.key}")
                push_key(direction)
                push_key(attack)
                tick(game, ceil(4 / move.fps * 60))
                tick(game, 3)
                assert enemy.hp == 200 - move.damage
                assert len(world.effects) == 1
                assert world.effects[0].facing == facing
                verify_hit_effect_pixels(game, f"punch_kick_hit_{enemy_type.__name__}_{move.key}_{facing}",
                                         config.PUNCH_KICK_HIT_IMAGE)
                release(game, direction)
                release(game, attack)
    print("PASS: actual SDL A/S/D/F attacks on both enemy types/directions use punch_kick_hit "
          "once per victim with the original damage values.")


def check_club_attacks(game):
    for side in (-1, 1):
        for kind, hp in (("old_club", 480), ("clubs", 440), ("slam", 420)):
            if kind == "old_club":
                game.world = World()
                world = game.world
                enemy = Enemy(world.player.x + side * 80, -side)
                world.enemies = [enemy]
                enemy.start_attack()
                enemy.animation.elapsed = 4.05 / enemy.attack_fps
            else:
                world, enemy = encounter(game, kind, side)
                set_frame(world, enemy, 4 if kind == "slam" else 2)
            for _ in range(20):
                tick(game)
                if world.effects:
                    break
            tick(game, 3)
            assert world.player.hp == hp and len(world.effects) == 1
            assert world.effects[0].facing == -side
            verify_hit_effect_pixels(game, f"club_hit_{kind}_{side}", config.CLUB_HIT_IMAGE)
            enemy.cooldown = 100
            tick(game, 30)
            assert not world.effects
    print("PASS: normal club=20, dual club=60 and landed leap=80 use club_hit in both "
          "directions, retain single-hit behavior and expire after playback.")


def check_scene_lifetime_and_restart(game):
    game.world = World()
    world = game.world
    textures = dict(game.assets.images)
    effects = [HitEffect(world.player.x + offset, 180, facing, elapsed=0.05, image_name=name)
               for offset, facing, name in ((-30, -1, config.CLUB_HIT_IMAGE),
                                            (30, 1, config.PUNCH_KICK_HIT_IMAGE))]
    world.effects = effects
    push_key(pico2d.SDLK_2)
    tick(game)
    release(game, pico2d.SDLK_2)
    tick(game, 6)
    assert all(effect.elapsed == 0.05 for effect in effects)
    push_key(pico2d.SDLK_1)
    tick(game)
    release(game, pico2d.SDLK_1)
    assert world.effects == effects
    capture(game, "mixed_hit_effects_returned")
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert all(not stage.effects for stage in game.world.stages)
    assert all(game.assets.images[name] is texture for name, texture in textures.items())
    print("PASS: mixed effect resources keep per-scene clocks, return correctly, and SDL F5 "
          "clears all effects while reusing both textures.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_sheets_and_frames(game)
        check_player_attacks(game)
        check_club_attacks(game)
        check_scene_lifetime_and_restart(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
