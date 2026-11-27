import hashlib
import json
import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import config
from assets import Assets
from combat import STRONG_MOVES
from player import Player
from shield_soldier import ShieldSoldier
from tests.helpers import advance, enter_kick_wait, tap
from tests.test_strong_attacks import strike
from ui import UI
from tests.helpers import ManualSpawnWorld as World


def encounter(side=1, *, index=8, weapon=None, guarded=False):
    world = World(rng=random.Random(23), item_rng=random.Random(5))
    world.select_stage(index)
    player = world.player
    player.invincible = True
    player.facing = side
    player.equip_weapon(weapon)
    enemy = world.spawner.spawn(1, world.elapsed)[0]
    world.enemies.append(enemy)
    enemy.x = enemy.previous_x = player.x + side * 80
    enemy.ground_y = enemy.previous_ground_y = player.ground_y
    enemy.facing = -side
    enemy.cooldown = 100
    if guarded:
        enemy.start_guard()
    return world, enemy


class ShieldSoldierTests(unittest.TestCase):
    def test_only_lab_maps_summon_full_health_shield_soldiers(self):
        world = World(rng=random.Random(42))
        for index, stage in enumerate(world.stages):
            world.select_stage(index)
            self.assertEqual(world.enemies, [])
            tap(world.controls, "spawn_4")
            world.step(config.FIXED_DT)
            if stage.image_name in config.LAB_STAGE_IMAGES:
                self.assertTrue(all(type(enemy) is ShieldSoldier and enemy.hp == enemy.max_hp == 400
                                    and enemy.attack_damage == 40 for enemy in world.enemies))
            else:
                self.assertFalse(any(isinstance(enemy, ShieldSoldier) for enemy in world.enemies))
            self.assertEqual(len(world.enemies), 4)

    def test_all_numeric_counts_latch_and_keep_unique_speed_profiles(self):
        for index in (8, 9):
            for count in config.SPAWN_COUNTS:
                world = World(rng=random.Random(41))
                world.select_stage(index)
                action = f"spawn_{count}"
                tap(world.controls, action)
                world.step(config.FIXED_DT)
                world.controls.press(action)
                advance(world, 0.1)
                self.assertEqual(len(world.enemies), count)
                tap(world.controls, action)
                world.step(config.FIXED_DT)
                self.assertEqual((len(world.enemies), world.spawner.spawned_count), (count * 2, count * 2))
                self.assertEqual(len({enemy.attack_speed for enemy in world.enemies}), count * 2)
                self.assertTrue(all(enemy.hp == 400 for enemy in world.enemies))

    def test_source_sheet_and_all_seven_rows_preserve_original_pixels_and_feet(self):
        path = config.ROOT / config.SHIELD_SOLDIER_IMAGE
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "fce4ebf0e923b32ecc54413ad5d8afa9bfaeb0e25d7cd87114afffbb284b0021")
        with Image.open(path) as image:
            self.assertEqual((image.size, image.mode), ((2048, 1792), "RGBA"))
            with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
                rows = json.load(file)[config.SHIELD_SOLDIER_IMAGE]
            self.assertEqual(len(rows), 7)
            for row_index, row in enumerate(rows):
                self.assertEqual(len(row), 8)
                for column, tile in enumerate(row):
                    left, top, right, bottom = image.crop(
                        (column * 256, row_index * 256, (column + 1) * 256, (row_index + 1) * 256)).getbbox()
                    self.assertEqual(tile["clip"], [column * 256 + left,
                                                   image.height - row_index * 256 - bottom,
                                                   right - left, bottom - top])
                    self.assertEqual(tile["offset_x"], (left + right) / 2 - 128)
        enemy = ShieldSoldier(1000)
        for state, row in (("IDLE", 1), ("WALK", 2), ("RUN", 3), ("GUARD", 4),
                           ("ATTACK", 5), ("HIT", 6), ("KNOCKBACK", 6), ("DYING", 7), ("DEAD", 7)):
            enemy.animation.set_state(state)
            self.assertEqual((enemy.sprite_image, enemy.animation.row), (config.SHIELD_SOLDIER_IMAGE, row))
        with patch("pico2d.load_image", return_value=Mock()), patch("pico2d.load_font"):
            assets = Assets()
        self.assertIn(config.SHIELD_SOLDIER_IMAGE, assets.images)

    def test_guard_or_swing_is_selected_once_with_a_half_probability_boundary(self):
        for roll, state, row in ((0, "GUARD", 4), (0.49999, "GUARD", 4),
                                 (0.5, "ATTACK", 5), (0.99999, "ATTACK", 5)):
            enemy = ShieldSoldier(1000)
            with patch.object(enemy.rng, "random", return_value=roll) as choice:
                enemy.start_attack()
                for _ in range(10):
                    enemy.update(config.FIXED_DT, Player())
            choice.assert_called_once_with()
            self.assertEqual((enemy.state, enemy.animation.row), (state, row))
            self.assertEqual((enemy.vx, enemy.ground_vy), (0, 0))

    def test_natural_ai_randomly_guards_and_attacks_but_does_not_choose_outside_reach(self):
        world, enemy = encounter()
        enemy.cooldown = 0
        with patch.object(enemy.rng, "random", side_effect=(0.1, 0.9, 0.1, 0.9)) as choice:
            observed = set()
            for _ in range(370):
                world.step(config.FIXED_DT)
                observed.add(enemy.state)
            self.assertEqual(choice.call_count, 4)
        self.assertTrue({"GUARD", "ATTACK"} <= observed)
        for situation in ("far", "deep", "floor", "cooldown"):
            world, enemy = encounter()
            enemy.cooldown = 0
            if situation == "far":
                enemy.x += 500
            elif situation == "deep":
                enemy.ground_y = world.player.ground_y - 40
            elif situation == "floor":
                enemy.floor = 1
            else:
                enemy.cooldown = 2
            with patch.object(enemy.rng, "random") as choice:
                enemy.update(config.FIXED_DT, world.player)
            choice.assert_not_called()

    def test_guard_halves_damage_without_restarting_or_replacing_the_guard_pose(self):
        for damage in (1, 7, 10, 40, 50, 60):
            for facing in (-1, 1):
                enemy = ShieldSoldier(1000, facing)
                enemy.start_guard()
                enemy.animation.elapsed = 0.2
                self.assertTrue(enemy.take_damage(damage))
                self.assertEqual(enemy.hp, 400 - damage / 2)
                self.assertEqual((enemy.state, enemy.animation.row, enemy.animation.elapsed), ("GUARD", 4, 0.2))
                self.assertIsNone(enemy.attack_box)
                self.assertIsNone(enemy.take_projectile())

    def test_unguarded_or_finished_guard_takes_full_damage_and_uses_hit_row_six(self):
        for state in ("IDLE", "WALK", "RUN", "ATTACK", "finished_guard", "falling_guard"):
            enemy = ShieldSoldier(1000)
            if "guard" in state:
                enemy.start_guard()
                if state == "finished_guard":
                    enemy.animation.elapsed = 8 / enemy.animation.definitions["GUARD"][1]
                else:
                    enemy.falling_from_upper = True
            else:
                enemy.animation.set_state(state)
            self.assertTrue(enemy.take_damage(40))
            self.assertEqual((enemy.hp, enemy.state, enemy.animation.row), (360, "HIT", 6))

    def test_guard_ends_on_its_own_clock_and_cannot_be_extended_by_repeated_damage(self):
        for speed in (0.8, 1, 1.4):
            enemy = ShieldSoldier(1000, attack_speed=speed)
            enemy.start_guard()
            duration = 8 / enemy.animation.definitions["GUARD"][1]
            enemy.update(duration - config.FIXED_DT, Player())
            self.assertTrue(enemy.guarding)
            enemy.take_damage(10)
            enemy.update(config.FIXED_DT + 1e-9, Player())
            self.assertFalse(enemy.guarding)
            self.assertEqual(enemy.state, "IDLE")
            enemy.take_damage(40)
            self.assertEqual(enemy.hp, 355)

    def test_basic_and_equipped_attacks_show_reduced_actual_damage_numbers_and_effects(self):
        for guarded in (False, True):
            for index in (8, 9):
                for weapon in (None, *config.WEAPON_POSE_IMAGES):
                    for side in (-1, 1):
                        for key in "asdf" if weapon is None else "asf":
                            world, enemy = encounter(side, index=index, weapon=weapon, guarded=guarded)
                            strike(world, enemy, f"combat_{key}")
                            move = world.player.active_move
                            damage = move.damage / 2 if guarded else move.damage
                            self.assertEqual(enemy.hp, 400 - damage)
                            self.assertEqual([number.damage for number in world.damage_numbers], [damage])
                            self.assertEqual(world.effects[-1].image_name, move.hit_image)
                            self.assertEqual((enemy.sprite_image, enemy.animation.row),
                                             (config.SHIELD_SOLDIER_IMAGE, 4 if guarded else 6))
                            advance(world, 0.03)
                            self.assertEqual(enemy.hp, 400 - damage)

    def test_all_strong_attacks_halve_guard_damage_and_keep_own_hit_row(self):
        for guarded in (False, True):
            for action in STRONG_MOVES:
                for side in (-1, 1):
                    world, enemy = encounter(side, guarded=guarded)
                    strike(world, enemy, action)
                    damage = STRONG_MOVES[action].damage * (0.5 if guarded else 1)
                    self.assertEqual(enemy.hp, 400 - damage)
                    self.assertEqual([number.damage for number in world.damage_numbers], [damage])
                    self.assertEqual((enemy.sprite_image, enemy.animation.row), (config.SHIELD_SOLDIER_IMAGE, 6))
                    self.assertFalse(enemy.guarding)
                    advance(world, 1.5)
                    self.assertEqual(enemy.sprite_image, config.SHIELD_SOLDIER_IMAGE)

    def test_both_weapon_dive_landings_respect_guard_and_use_existing_feedback(self):
        for guarded in (False, True):
            for weapon in config.WEAPON_AIRBORNE_ROWS:
                world, enemy = encounter(weapon=weapon)
                for action in ("jump", "jump", "combat_d", "combat_d"):
                    tap(world.controls, action)
                    world.step(config.FIXED_DT)
                if guarded:
                    enemy.start_guard()
                for _ in range(180):
                    world.step(config.FIXED_DT)
                    if enemy.hp < 400:
                        break
                self.assertEqual(enemy.hp, 370 if guarded else 340)
                self.assertEqual([number.damage for number in world.damage_numbers], [30 if guarded else 60])
                self.assertEqual(world.effects[-1].image_name, config.WEAPON_HIT_IMAGES[weapon])

    def test_fifth_row_swing_deals_forty_once_at_active_frames_on_both_sides(self):
        for facing in (-1, 1):
            for speed in (0.8, 1, 1.4):
                player = Player()
                enemy = ShieldSoldier(player.x - facing * 80, facing, attack_speed=speed)
                enemy.start_swing()
                for frame in range(8):
                    enemy.animation.elapsed = (frame + 0.05) / enemy.attack_fps
                    self.assertEqual(enemy.try_hit(player), frame == 3)
                    self.assertEqual(player.hp, 500 if frame < 3 else 460)
                    self.assertEqual(enemy.animation.row, 5)

    def test_guard_has_no_damage_and_swing_keeps_range_depth_height_floor_and_p_filters(self):
        for situation in ("guard", "far", "behind", "deep", "jump", "floor", "invincible", "edge"):
            player = Player()
            enemy = ShieldSoldier(player.x + 80, -1)
            enemy.start_swing()
            enemy.animation.elapsed = 3.05 / enemy.attack_fps
            if situation == "guard":
                enemy.start_guard()
            elif situation == "far":
                player.x -= 200
            elif situation == "behind":
                player.x = enemy.x + 80
            elif situation == "deep":
                player.ground_y += 32.01
            elif situation == "jump":
                player.jump_height = 200
            elif situation == "floor":
                player.floor = 1
            elif situation == "invincible":
                player.invincible = True
            else:
                player.ground_y += 32
            self.assertEqual(enemy.try_hit(player), situation == "edge")
            self.assertEqual(player.hp, 460 if situation == "edge" else 500)
            self.assertEqual(enemy.has_hit, situation in ("guard", "edge", "invincible"))

    def test_simultaneous_swings_apply_independent_forty_damage_and_effects(self):
        world, enemy = encounter()
        world.player.invincible = False
        second = ShieldSoldier(world.player.x - 80, 1, ground_y=world.player.ground_y)
        world.enemies.append(second)
        for actor in world.enemies:
            actor.start_swing()
            actor.animation.elapsed = 3.05 / actor.attack_fps
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 420)
        self.assertTrue(enemy.has_hit and second.has_hit)
        self.assertEqual([effect.image_name for effect in world.effects], [config.CLUB_HIT_IMAGE] * 2)

    def test_lethal_guard_and_strong_hits_use_own_death_fade_and_never_drop_a_club(self):
        for strong in (False, True):
            world, enemy = encounter(guarded=True)
            enemy.hp = 15
            if strong:
                enemy.take_strong_hit(STRONG_MOVES["combat_q"], 1)
            else:
                enemy.take_damage(40)
            self.assertEqual(enemy.hp, 0)
            self.assertFalse(enemy.guarding)
            self.assertFalse(enemy.take_damage(10))
            advance(world, 2)
            self.assertEqual((enemy.state, enemy.animation.row, enemy.animation.frame), ("DEAD", 7, 7))
            self.assertEqual(len(world.stage.drop_items), 15)
            enemy.corpse_elapsed = 3.5
            self.assertAlmostEqual(enemy.opacity, 0.5)
            advance(world, 0.5)
            self.assertNotIn(enemy, world.enemies)

    def test_player_death_stops_guard_or_knocks_back_with_own_hit_art(self):
        for gap in (80, 300):
            world, enemy = encounter(guarded=True)
            enemy.x = world.player.x + gap
            world.player.invincible = False
            world.player.take_damage(500)
            world.handle_death()
            self.assertFalse(enemy.guarding)
            self.assertEqual(enemy.state, "KNOCKBACK" if gap == 80 else "IDLE")
            self.assertEqual(enemy.sprite_image, config.SHIELD_SOLDIER_IMAGE)

    def test_guard_and_rng_pause_off_stage_and_during_loading_and_f5_resets_all(self):
        world, enemy = encounter(guarded=True)
        advance(world, 0.1)
        snapshot = enemy.hp, enemy.animation.elapsed, enemy.cooldown, enemy.rng.getstate()
        world.select_stage(7)
        advance(world, 1)
        world.select_stage(8)
        self.assertEqual((enemy.hp, enemy.animation.elapsed, enemy.cooldown, enemy.rng.getstate()), snapshot)
        world.pending_stage_index, world.stage_loading_remaining = 7, 2
        world.update(1)
        self.assertEqual((enemy.hp, enemy.animation.elapsed, enemy.cooldown, enemy.rng.getstate()), snapshot)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertTrue(all(not stage.enemies and stage.spawner.spawned_count == 0 for stage in world.stages))
        world.select_stage(9)
        tap(world.controls, "spawn_1")
        world.step(config.FIXED_DT)
        self.assertEqual(world.enemies[0].hp, 400)
        self.assertIn(world.enemies[0].state, ("WALK", "RUN"))

    def test_guard_and_action_clocks_use_the_common_slow_motion_scale(self):
        world, enemy = encounter(guarded=True)
        enter_kick_wait(world)
        world.step(config.FIXED_DT)
        self.assertEqual(world.time_scale, 0.2)
        self.assertAlmostEqual(enemy.animation.elapsed, config.FIXED_DT * 0.2)
        self.assertTrue(enemy.guarding)

    def test_natural_guard_and_attack_randomness_is_fps_independent_and_spawn_rng_is_unchanged(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world, enemy = encounter()
            enemy.cooldown = 0
            spawn_state = world.spawner.rng.getstate()
            advance(world, 4, fps)
            self.assertEqual(world.spawner.rng.getstate(), spawn_state)
            outcomes.append((enemy.x, enemy.ground_y, enemy.hp, enemy.state,
                             enemy.animation.elapsed, enemy.rng.getstate()))
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))

    def test_hp_bar_and_hud_report_shield_hp_attack_and_guard_reduction(self):
        world, enemy = encounter()
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            assets = SimpleNamespace(frames=json.load(file), damage_font=Mock(),
                                     font=Mock(), images={config.HP_IMAGE: Mock(w=700, h=80)})
        for details in (False, True):
            ui = UI()
            ui.details_visible = details
            for hp, width in ((400, 48), (200, 24), (100, 12), (0, 0)):
                enemy.hp = hp
                with patch("pico2d.draw_rectangle") as draw:
                    ui.draw_enemy_health(assets, world, 20, 30)
                bars = [call.args for call in draw.call_args_list if call.args[4:7] == (215, 38, 45)]
                self.assertEqual(len(bars), int(hp > 0))
                if hp:
                    self.assertEqual(bars[0][2] - bars[0][0] + 1, width)
        with patch("pico2d.draw_rectangle"):
            UI().draw(assets, world)
        labels = [call.args[2] for call in assets.font.draw.call_args_list]
        self.assertTrue(any("방패" in label and "400" in label and "40" in label and "50%" in label
                            for label in labels))


if __name__ == "__main__":
    unittest.main()
