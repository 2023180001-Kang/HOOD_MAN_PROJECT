"""Verify lab shield summons, random guard/swing, combat and pixels through SDL."""

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
from combat import STRONG_MOVES
from tests.helpers import ManualSpawnWorld as World, enter_kick_wait, expected_numeric_summons
from game import Game
from shield_soldier import ShieldSoldier
from tools.check_damage_numbers import capture_number
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, release, tick


def encounter(game, side=1, *, index=8, hp=400, weapon=None, guarded=False):
    game.world = World(rng=random.Random(23), item_rng=random.Random(5))
    world = game.world
    world.select_stage(index)
    player = world.player
    player.facing, player.invincible = side, True
    player.equip_weapon(weapon)
    enemy = world.spawner.spawn(1, world.elapsed)[0]
    world.enemies = [enemy]
    enemy.x = enemy.previous_x = player.x + side * 80
    enemy.ground_y = enemy.previous_ground_y = player.ground_y
    enemy.facing = -side
    enemy.hp, enemy.cooldown = hp, 100
    if guarded:
        enemy.start_guard()
    return world, enemy


def tap(game, key):
    push_key(key)
    tick(game)
    release(game, key)


def check_summons(game):
    texture = game.assets.images[config.SHIELD_SOLDIER_IMAGE]
    assert (texture.w, texture.h) == (2048, 1792)
    for index in (8, 9):
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
                assert [type(enemy) for enemy in world.enemies] == expected_numeric_summons(index, count)
                assert all(enemy.hp == enemy.max_hp == type(enemy).max_hp and enemy.attack_damage == 40
                           for enemy in world.enemies)
                assert all(world.stage.walkable.contains(enemy.x, enemy.ground_y, enemy.boundary_padding)
                           for enemy in world.enemies)
                push_key(key, repeat=True)
                tick(game, 6)
                assert len(world.enemies) == count
                release(game, key)
                tap(game, key)
                assert len(world.enemies) == count * 2
                assert [type(enemy) for enemy in world.enemies] == expected_numeric_summons(index, count * 2)
                assert len({enemy.attack_speed for enemy in world.enemies}) == count * 2
                assert game.assets.images[config.SHIELD_SOLDIER_IMAGE] is texture
        for label, camera_x in (("left", 0), ("right", 1280)):
            world.camera.x = camera_x
            capture(game, f"shield_lab_{index - 7}_spawn_{label}")
    for index in range(len(config.STAGE_IMAGES)):
        if index in (8, 9):
            continue
        game.world = World(rng=random.Random(42))
        game.world.select_stage(index)
        tap(game, pico2d.SDLK_1)
        assert len(game.world.enemies) == 1
        assert type(game.world.enemies[0]) is not ShieldSoldier
    print("PASS: both labs, all 36 digit/keypad cases alternate shield soldiers and researchers; "
          "no automatic/repeated summons, fresh input adds, unique speeds/bounds/texture reuse; "
          "all ten other maps keep their enemy types.")


def check_source_frames(game):
    world, enemy = encounter(game)
    texture = game.assets.images[config.SHIELD_SOLDIER_IMAGE]
    for facing in (-1, 1):
        enemy.facing = facing
        for state, row in (("IDLE", 1), ("WALK", 2), ("RUN", 3), ("GUARD", 4),
                           ("ATTACK", 5), ("HIT", 6), ("DYING", 7)):
            enemy.animation.set_state(state)
            fps = enemy.animation.definitions[state][1]
            for frame in range(8):
                enemy.animation.elapsed = (frame + 0.05) / fps
                tile = game.assets.frames[config.SHIELD_SOLDIER_IMAGE][row - 1][frame]
                with patch.object(texture, "clip_composite_draw",
                                  wraps=texture.clip_composite_draw) as draw:
                    if state in ("GUARD", "ATTACK") and frame == 3:
                        capture(game, f"shield_{state.lower()}_{facing}")
                    else:
                        render_image(game)
                args = draw.call_args.args
                assert args[:4] == tuple(tile["clip"])
                assert args[5] == ("h" if facing < 0 else "")
                assert abs(args[7] - args[9] / 2 - (enemy.y - world.camera.render_y)) < 1e-8
    print("PASS: all 56 original clips in both facings, exact rows/flips/foot alignment; "
          "row 4 guards, row 5 swings, row 6 reacts, row 7 dies.")


def check_random_actions(game):
    for roll, state, row in ((0.49999, "GUARD", 4), (0.5, "ATTACK", 5)):
        world, enemy = encounter(game)
        enemy.cooldown = 0
        with patch.object(enemy.rng, "random", return_value=roll) as choice:
            tick(game, 10)
        choice.assert_called_once_with()
        assert (enemy.state, enemy.animation.row) == (state, row)
        assert enemy.vx == enemy.ground_vy == 0
        if state == "GUARD":
            assert enemy.guarding and enemy.attack_box is None
            elapsed = enemy.animation.elapsed
            for _ in range(3):
                render_image(game)
            assert enemy.animation.elapsed == elapsed
            enemy.take_damage(40)
            assert enemy.hp == 380 and enemy.animation.elapsed == elapsed
            enemy.cooldown = 100  # Inspect this guard's end, not a later random action.
            tick(game, 60)
            assert not enemy.guarding
    print("PASS: melee AI commits to one 50/50 random choice per due action, not per frame/hit; "
          "normal blocks and render-only calls cannot restart or extend guard.")


def check_health_pixels(game):
    for hp, expected in ((400, 48), (200, 24), (100, 12), (0, 0)):
        world, enemy = encounter(game, hp=hp, guarded=hp > 0)
        for details in (True, False):
            game.ui.details_visible = details
            image = render_image(game).convert("RGB")
            tile = game.assets.frames[enemy.sprite_image][enemy.animation.row - 1][enemy.animation.frame]
            left = round(enemy.x - world.camera.render_x - config.ENEMY_HP_BAR_WIDTH / 2)
            bottom = (enemy.y - world.camera.render_y
                      + tile["clip"][3] * config.SPRITE_SCALE + config.ENEMY_HP_BAR_GAP)
            row = config.SCREEN_HEIGHT - round(bottom) - 2
            widths = [sum(1 for x in range(left, left + 48)
                          if (lambda rgb: rgb[0] > 180 and rgb[1] < 75 and rgb[2] < 90)(
                              image.getpixel((x, y))))
                      for y in range(row - 2, row + 3)]
            assert max(widths) == expected, (hp, details, widths)
        capture(game, f"shield_hp_{hp}")
    game.ui.details_visible = True
    encounter(game)
    with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as text:
        capture(game, "shield_lab_hud")
    assert any(all(word in call.args[2] for word in ("방패", "400", "40", "50%"))
               for call in text.call_args_list)
    print("PASS: real red HP fills are 48/24/12/hidden pixels at 400/200/100/0, also with U hidden; "
          "lab HUD reports 400 HP, 40 damage and 50% guarded damage.")


def press_attack(game, key, enemy):
    keycode = getattr(pico2d, f"SDLK_{key}")
    before = enemy.hp
    push_key(keycode)
    for _ in range(180):
        tick(game)
        assert enemy.sprite_image == config.SHIELD_SOLDIER_IMAGE
        if enemy.hp != before:
            release(game, keycode)
            return
    raise AssertionError(f"SDL {key} did not hit the shield soldier")


def check_player_damage(game):
    cases = [(None, key) for key in "asdf"]
    cases += [(weapon, key) for weapon in config.WEAPON_POSE_IMAGES for key in "asf"]
    for index in (8, 9):
        for guarded in (False, True):
            for number, (weapon, key) in enumerate(cases):
                world, enemy = encounter(game, -1 if number % 2 else 1, index=index,
                                         weapon=weapon, guarded=guarded)
                damage = world.player.moves[f"combat_{key}"].damage
                damage = damage / 2 if guarded else damage
                press_attack(game, key, enemy)
                assert enemy.hp == 400 - damage
                assert [value.damage for value in world.damage_numbers] == [damage]
                assert [effect.image_name for effect in world.effects] == [world.player.active_move.hit_image]
                assert enemy.animation.row == (4 if guarded else 6)
                assert world.camera.shake_remaining > 0
                world.update_camera(config.SHAKE_DURATION)
                image = render_image(game)
                with patch.object(world.stage, "effects", []):
                    clean = render_image(game)
                assert ImageChops.difference(image.convert("RGB"), clean.convert("RGB")).getbbox()
                if index == 8:
                    capture_number(game, f"shield_damage_{'guard' if guarded else 'full'}_{weapon or 'unarmed'}_{key}")
                tick(game, 2)
                assert enemy.hp == 400 - damage
                tick(game, 60)
                assert not world.damage_numbers and not world.effects
    print("PASS: both lab maps, SDL ASDF/weapon AS/F deal full or exactly half damage; "
          "actual damage text/effect pixels, guard preservation, one hit and feedback expiry.")


def check_strong_and_dives(game):
    for guarded in (False, True):
        for move in STRONG_MOVES.values():
            world, enemy = encounter(game, guarded=guarded)
            press_attack(game, move.key, enemy)
            damage = move.damage * 0.5 if guarded else move.damage
            assert enemy.hp == 400 - damage and enemy.animation.row == 6
            assert [value.damage for value in world.damage_numbers] == [damage]
            assert not enemy.guarding
            capture(game, f"shield_strong_{move.key}_{'guard' if guarded else 'full'}")
            tick(game, 120)
            assert enemy.sprite_image == config.SHIELD_SOLDIER_IMAGE
        for weapon in config.WEAPON_AIRBORNE_ROWS:
            world, enemy = encounter(game, weapon=weapon)
            for key in (pico2d.SDLK_SPACE, pico2d.SDLK_SPACE, pico2d.SDLK_d, pico2d.SDLK_d):
                tap(game, key)
            if guarded:
                enemy.start_guard()
            for _ in range(180):
                tick(game)
                if enemy.hp < 400:
                    break
            assert enemy.hp == (370 if guarded else 340)
            assert [effect.image_name for effect in world.effects] == [config.WEAPON_HIT_IMAGES[weapon]]
            assert world.camera.shake_strength == 16
            capture_number(game, f"shield_dive_{weapon}_{'guard' if guarded else 'full'}")
    print("PASS: SDL Q/W/E deal half/full damage once then own row-6 reactions; "
          "both weapon D landings respect guard and preserve the 16px impact shake.")


def check_shield_attack(game):
    for index in (8, 9):
        for side in (-1, 1):
            for protected in (False, True):
                world, enemy = encounter(game, side, index=index)
                world.player.invincible = False
                if protected:
                    tap(game, pico2d.SDLK_p)
                enemy.start_swing()
                for _ in range(60):
                    tick(game)
                    if enemy.has_hit:
                        break
                assert enemy.has_hit and enemy.animation.row == 5
                assert world.player.hp == (500 if protected else 460)
                assert len(world.effects) == (0 if protected else 1)
                if not protected:
                    assert world.effects[0].image_name == config.CLUB_HIT_IMAGE
                    assert world.player.state == "HIT" and world.camera.shake_remaining > 0
                    capture(game, f"shield_swing_lab_{index - 7}_{side}")
                tick(game, 6)
                assert world.player.hp == (500 if protected else 460)
            world, enemy = encounter(game, side, index=index, guarded=True)
            world.player.invincible = False
            tick(game, 30)
            assert enemy.guarding and world.player.hp == 500 and not world.effects
    print("PASS: both labs/facings, row-5 shield swings hit for 40 exactly once with HIT/effect/shake; "
          "SDL P blocks without feedback, row-4 defense never deals attack damage.")


def check_death_and_pause(game):
    world, enemy = encounter(game, hp=10, guarded=True)
    press_attack(game, "f", enemy)
    assert enemy.hp == 0 and [value.damage for value in world.damage_numbers] == [10]
    capture_number(game, "shield_guard_lethal")
    tick(game, 60)
    assert (enemy.state, enemy.animation.row, enemy.animation.frame) == ("DEAD", 7, 7)
    assert len(world.stage.drop_items) == 16
    assert world.stage.drop_items[-1].kind == "shield_item"
    enemy.corpse_elapsed = 3.5
    texture = game.assets.images[config.SHIELD_SOLDIER_IMAGE]
    with patch.object(texture, "opacify", wraps=texture.opacify) as opacity:
        capture(game, "shield_corpse_half")
    assert [call.args[0] for call in opacity.call_args_list] == [0.5, 1.0]
    tick(game, 31)
    assert not world.enemies

    world, enemy = encounter(game, guarded=True)
    enter_kick_wait(world)
    tick(game)
    assert world.time_scale == 0.2
    assert abs(enemy.animation.elapsed - 1 / 60 * 0.2) < 1e-9
    capture(game, "shield_guard_slow")

    world, enemy = encounter(game, guarded=True)
    source, items = world.stage, world.stage.drop_items
    snapshot = enemy.hp, enemy.animation.elapsed, enemy.cooldown, enemy.rng.getstate()
    world.select_stage(9)
    tick(game, 60)
    world.select_stage(8)
    assert source.drop_items is items
    assert (enemy.hp, enemy.animation.elapsed, enemy.cooldown, enemy.rng.getstate()) == snapshot
    world.player.x, world.player.vx = config.STAGE_EXIT_MARGIN, -config.RUN_SPEED
    push_key(pico2d.SDLK_LEFT)
    tap(game, pico2d.SDLK_n)
    assert world.stage_loading and world.pending_stage_index == 7
    with patch.object(texture, "clip_composite_draw", wraps=texture.clip_composite_draw) as draw:
        capture(game, "shield_loading_paused")
    draw.assert_not_called()
    tap(game, pico2d.SDLK_9)
    tick(game, 30)
    assert len(source.enemies) == 1
    assert (enemy.hp, enemy.animation.elapsed, enemy.cooldown, enemy.rng.getstate()) == snapshot
    tap(game, pico2d.SDLK_F5)
    release(game, pico2d.SDLK_LEFT)
    assert world.stage_index == 0 and not world.stage_loading
    assert all(not stage.enemies and not stage.effects and not stage.damage_numbers
               and stage.spawner.spawned_count == 0 for stage in world.stages)
    world.select_stage(9)
    tick(game, 30)
    assert not world.enemies
    tap(game, pico2d.SDLK_1)
    assert len(world.enemies) == 1 and world.enemies[0].hp == 400
    assert game.assets.images[config.SHIELD_SOLDIER_IMAGE] is texture
    print("PASS: lethal guard uses actual remaining HP text, row-7 death/fade and drops one shield; "
          "SDL R slows guard, inactive/loading pause action/RNG, loading hides soldiers/consumes "
          "numeric input, SDL F5 clears everything and new input restores HP-400 summons.")


def check_natural_combat(game):
    for index in (8, 9):
        game.world = World(rng=random.Random(19))
        world = game.world
        world.select_stage(index)
        tap(game, pico2d.SDLK_p)
        world.spawn_enemies(4, ShieldSoldier)
        spawn_state = world.spawner.rng.getstate()
        actions = {enemy: set() for enemy in world.enemies}
        for _ in range(960):
            tick(game)
            for enemy in world.enemies:
                actions[enemy].add(enemy.state)
                assert world.stage.walkable.contains(enemy.x, enemy.ground_y, 88)
        assert all({"GUARD", "ATTACK"} <= states for states in actions.values()), actions
        assert all(enemy.hp == 400 for enemy in world.enemies) and world.player.hp == 500
        assert world.spawner.rng.getstate() == spawn_state
        capture(game, f"shield_lab_{index - 7}_natural_combat")
    start = perf_counter()
    frames = game.run(max_frames=180)
    seconds = perf_counter() - start
    assert frames == 180
    print(f"BENCHMARK: four shield soldiers + random defense/swing/pursuit/HP/UI: "
          f"{frames} frames / {seconds:.3f}s = {frames / seconds:.2f} FPS.")
    print("PASS: four natural soldiers on each lab all guard and attack independently, "
          "stay in floor bounds, never alter spawn RNG and preserve own HP/art.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_summons(game)
        check_source_frames(game)
        check_random_actions(game)
        check_health_pixels(game)
        check_player_damage(game)
        check_strong_and_dives(game)
        check_shield_attack(game)
        check_death_and_pause(game)
        check_natural_combat(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
