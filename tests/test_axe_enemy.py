import json
import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import config
from axe_enemy import AxeEnemy
from combat import STRONG_MOVES
from enemy import Enemy
from enemy02 import Enemy02
from player import Player
from researcher import Researcher
from shield_soldier import ShieldSoldier
from tests.helpers import advance, spawn_encounter, tap
from tests.test_strong_attacks import strike
from ui import UI
from world import World


def encounter(side=1, *, hp=400, weapon=None):
    world = World(rng=random.Random(23), item_rng=random.Random(5))
    world.select_stage(config.STAGE_IMAGES.index(config.FACTORY_OUTSIDE_IMAGE))
    world.player.invincible = True
    world.player.facing = side
    world.player.equip_weapon(weapon)
    enemy = spawn_encounter(world, 1)[0]
    enemy.x = enemy.previous_x = world.player.x + side * 80
    enemy.ground_y = enemy.previous_ground_y = world.player.ground_y
    enemy.facing = -side
    enemy.hp = hp
    enemy.cooldown = 100
    return world, enemy


class AxeEnemyTests(unittest.TestCase):
    def test_only_the_loading_dock_summons_axe_enemies_with_their_own_max_hp(self):
        world = World(rng=random.Random(42))
        for index, stage in enumerate(world.stages):
            world.select_stage(index)
            tap(world.controls, "spawn_4")
            world.update(config.FIXED_DT)
            expected, hp = Enemy, 200
            if stage.image_name == config.FACTORY_OUTSIDE_IMAGE:
                expected, hp = AxeEnemy, 400
            elif stage.image_name in config.ENEMY02_STAGE_IMAGES:
                expected = Enemy02
            elif stage.image_name in config.FACTORY_INSIDE_IMAGES:
                expected = Researcher
            elif stage.image_name in config.LAB_STAGE_IMAGES:
                expected, hp = ShieldSoldier, 400
            self.assertEqual(len(world.enemies), 4)
            for enemy in world.enemies:
                self.assertIs(type(enemy), expected)
                self.assertEqual((enemy.hp, enemy.max_hp), (hp, hp))
                self.assertTrue(stage.walkable.contains(enemy.x, enemy.ground_y,
                                                        enemy.boundary_padding))

    def test_each_numeric_input_keeps_count_latching_and_independent_speed_profiles(self):
        for count in config.SPAWN_COUNTS:
            world, _ = encounter()
            world.enemies.clear()
            before = world.spawner.spawned_count
            action = f"spawn_{count}"
            tap(world.controls, action)
            world.update(config.FIXED_DT)
            advance(world, 0.1)
            world.controls.press(action)  # Holding/repeat is not another summon.
            world.update(config.FIXED_DT)
            self.assertEqual(len(world.enemies), count)
            tap(world.controls, action)
            world.update(config.FIXED_DT)
            self.assertEqual(len(world.enemies), count * 2)
            self.assertEqual(world.spawner.spawned_count, before + count * 2)
            self.assertEqual(len({enemy.attack_speed for enemy in world.enemies}), count * 2)
            self.assertEqual([enemy.run_speed for enemy in world.enemies],
                             [config.ENEMY_RUN_SPEEDS[(before + i) % 4]
                              for i in range(count * 2)])
            self.assertTrue(all(enemy.hp == 400 for enemy in world.enemies))

    def test_axe_swing_deals_sixty_once_only_on_active_frames_in_both_directions(self):
        for side in (-1, 1):
            player = Player()
            enemy = AxeEnemy(player.x + side * 80, -side, attack_speed=1.3)
            enemy.start_attack()
            for frame in range(8):
                enemy.animation.elapsed = (frame + 0.05) / enemy.attack_fps
                self.assertEqual(enemy.try_hit(player), frame == 4)
                self.assertEqual(player.hp, 500 if frame < 4 else 440)
            enemy.start_attack()
            enemy.animation.elapsed = 4.05 / enemy.attack_fps
            self.assertTrue(enemy.try_hit(player))
            self.assertEqual(player.hp, 380)

    def test_axe_swing_preserves_range_direction_depth_height_and_invincibility(self):
        for situation in ("far", "behind", "deep", "above", "invincible", "depth_edge"):
            player = Player()
            enemy = AxeEnemy(player.x + 80, -1)
            enemy.start_attack()
            enemy.animation.elapsed = 4.05 / enemy.attack_fps
            if situation == "far":
                player.x -= 200
            elif situation == "behind":
                player.x = enemy.x + 80
            elif situation == "deep":
                player.ground_y += 32.01
            elif situation == "above":
                player.jump_height = 200
            elif situation == "invincible":
                player.invincible = True
            else:
                player.ground_y += 32
            self.assertEqual(enemy.try_hit(player), situation == "depth_edge")
            self.assertEqual(player.hp, 440 if situation == "depth_edge" else 500)
            self.assertEqual(enemy.has_hit, situation in ("invincible", "depth_edge"))

    def test_simultaneous_axe_attacks_apply_independent_damage_and_existing_effects(self):
        world, first = encounter(-1)
        second = AxeEnemy(world.player.x + 80, -1)
        second.walkable = world.stage.walkable
        world.enemies.append(second)
        world.player.invincible = False
        for enemy in world.enemies:
            enemy.start_attack()
            enemy.animation.elapsed = 4.05 / enemy.attack_fps
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 380)
        self.assertTrue(first.has_hit and second.has_hit)
        self.assertEqual([effect.image_name for effect in world.effects],
                         [config.CLUB_HIT_IMAGE] * 2)
        self.assertGreater(world.camera.shake_remaining, 0)
        advance(world, 0.1)
        self.assertEqual(world.player.hp, 380)

    def test_basic_and_weapon_hits_show_actual_damage_numbers_and_matching_effects(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            keys = "asdf" if weapon is None else "asf"
            for key in keys:
                for side in (-1, 1):
                    with self.subTest(weapon=weapon, key=key, side=side):
                        world, enemy = encounter(side, weapon=weapon)
                        strike(world, enemy, f"combat_{key}")
                        move = world.player.active_move
                        self.assertEqual(enemy.hp, 400 - move.damage)
                        self.assertEqual((enemy.state, enemy.animation.row), ("HIT", 5))
                        self.assertEqual(enemy.sprite_image, config.AXE_ENEMY_IMAGE)
                        self.assertEqual([number.damage for number in world.damage_numbers],
                                         [move.damage])
                        self.assertEqual([effect.image_name for effect in world.effects],
                                         [move.hit_image])
                        self.assertGreater(world.camera.shake_remaining, 0)
                        advance(world, 0.04)
                        self.assertEqual(enemy.hp, 400 - move.damage)

    def test_normal_hit_recovers_without_entering_the_last_stun_row(self):
        world, enemy = encounter()
        self.assertTrue(enemy.take_damage(10))
        for _ in range(90):
            self.assertNotEqual(enemy.animation.row, 7)
            enemy.update(config.FIXED_DT, world.player)
        self.assertEqual((enemy.hp, enemy.state, enemy.sprite_image),
                         (390, "IDLE", config.AXE_ENEMY_IMAGE))
        self.assertTrue(all(row < 7 for row, _, _ in enemy.animation.definitions.values()))
        self.assertFalse(any("STUN" in state for state in enemy.animation.definitions))

    def test_both_weapon_dive_landings_deal_fifty_with_existing_feedback(self):
        for weapon in config.WEAPON_POSE_IMAGES:
            for side in (-1, 1):
                world, enemy = encounter(side, weapon=weapon)
                for action in ("jump", "jump", "combat_d", "combat_d"):
                    tap(world.controls, action)
                    world.step(config.FIXED_DT)
                for _ in range(90):
                    world.step(config.FIXED_DT)
                    if enemy.hp < 400:
                        break
                self.assertEqual(enemy.hp, 350)
                self.assertEqual([number.damage for number in world.damage_numbers], [50])
                self.assertEqual(world.effects[-1].image_name, config.WEAPON_HIT_IMAGES[weapon])
                self.assertEqual((enemy.sprite_image, enemy.animation.row),
                                 (config.AXE_ENEMY_IMAGE, 5))

    def test_all_strong_hits_and_w_carry_keep_axe_art_and_never_use_stun(self):
        for action, move in STRONG_MOVES.items():
            for side in (-1, 1):
                with self.subTest(action=action, side=side):
                    world, enemy = encounter(side)
                    strike(world, enemy, action)
                    self.assertEqual(enemy.hp, 350)
                    self.assertEqual((enemy.sprite_image, enemy.animation.row),
                                     (config.AXE_ENEMY_IMAGE, 5))
                    self.assertEqual([number.damage for number in world.damage_numbers], [50])
                    if move.key == "w":
                        world.controls.release(action)
                        world.step(config.FIXED_DT)
                        self.assertEqual(enemy.state, "RUSH_RELEASED")
                    for _ in range(360):
                        self.assertNotEqual(enemy.animation.row, 7)
                        self.assertEqual(enemy.sprite_image, config.AXE_ENEMY_IMAGE)
                        if enemy.state == "IDLE":
                            break
                        world.step(config.FIXED_DT)
                    self.assertEqual((enemy.hp, enemy.state), (350, "IDLE"))

    def test_lethal_strong_reactions_finish_with_the_axe_death_row_not_stun(self):
        for action in STRONG_MOVES:
            world, enemy = encounter(hp=30)
            strike(world, enemy, action)
            self.assertEqual(enemy.hp, 0)
            self.assertEqual([number.damage for number in world.damage_numbers], [30])
            if action == "combat_w":
                world.controls.release(action)
            for _ in range(900):
                self.assertEqual(enemy.sprite_image, config.AXE_ENEMY_IMAGE)
                self.assertLess(enemy.animation.row, 7)
                if enemy.state == "DEAD":
                    break
                world.step(config.FIXED_DT)
            self.assertEqual((enemy.state, enemy.animation.row, enemy.animation.frame), ("DEAD", 6, 7))

    def test_player_death_knockback_uses_hit_art_without_activating_stun(self):
        world, enemy = encounter()
        facing = enemy.facing
        world.player.invincible = False
        world.player.take_damage(500)
        world.handle_death()
        self.assertEqual((enemy.state, enemy.animation.row), ("KNOCKBACK", 5))
        for _ in range(180):
            world.step(config.FIXED_DT)
            self.assertEqual(enemy.sprite_image, config.AXE_ENEMY_IMAGE)
            self.assertLess(enemy.animation.row, 7)
            self.assertEqual(enemy.facing, facing)
        self.assertEqual((enemy.hp, enemy.state), (400, "IDLE"))

    def test_lethal_hit_uses_actual_remaining_hp_death_fade_and_no_metal_club_drop(self):
        world, enemy = encounter(hp=25)
        items = list(world.stage.drop_items)
        strike(world, enemy, "combat_f")
        self.assertEqual((enemy.hp, enemy.state, enemy.animation.row), (0, "DYING", 6))
        self.assertEqual([number.damage for number in world.damage_numbers], [25])
        self.assertIsNone(enemy.death_drop_kind)
        advance(world, 1)
        self.assertEqual((enemy.state, enemy.animation.row, enemy.animation.frame), ("DEAD", 6, 7))
        self.assertFalse(enemy.blocks_movement)
        self.assertFalse(enemy.take_damage(10))
        self.assertEqual(world.stage.drop_items, items)
        enemy.corpse_elapsed = 3.5
        self.assertAlmostEqual(enemy.opacity, 0.5)
        advance(world, 0.5)
        self.assertNotIn(enemy, world.enemies)

    def test_health_bar_uses_each_enemys_max_hp_and_remains_visible_with_help_hidden(self):
        world, enemy = encounter()
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            assets = SimpleNamespace(frames=json.load(file), damage_font=Mock())
        ui = UI()
        for enemy_type, hp_values in ((AxeEnemy, (400, 200, 100, 0)), (Enemy, (200, 100, 50, 0))):
            world.enemies = [enemy_type(enemy.x, ground_y=180)]
            for details in (True, False):
                ui.details_visible = details
                for hp in hp_values:
                    world.enemies[0].hp = hp
                    with patch("pico2d.draw_rectangle") as draw:
                        ui.draw_enemy_health(assets, world, 17, 29)
                    bars = [call.args for call in draw.call_args_list if call.args[4:7] == (215, 38, 45)]
                    if hp == 0:
                        self.assertEqual(draw.call_count, 0)
                    else:
                        self.assertEqual(len(bars), 1)
                        self.assertEqual(bars[0][2] - bars[0][0] + 1,
                                         config.ENEMY_HP_BAR_WIDTH * hp / world.enemies[0].max_hp)
                        self.assertEqual(bars[0][3] - bars[0][1] + 1, config.ENEMY_HP_BAR_HEIGHT)

    def test_dock_hud_reports_axe_damage_instead_of_the_old_club_damage(self):
        world, _ = encounter()
        assets = SimpleNamespace(images={config.HP_IMAGE: Mock(w=700, h=80)}, font=Mock())
        with patch("pico2d.draw_rectangle"):
            UI().draw(assets, world)
        labels = [call.args[2] for call in assets.font.draw.call_args_list]
        self.assertTrue(any("도끼" in text and "60" in text for text in labels))

    def test_sheet_metadata_has_seven_rows_but_no_runtime_stun_mapping(self):
        from PIL import Image

        with Image.open(config.ROOT / config.AXE_ENEMY_IMAGE) as image:
            self.assertEqual((image.size, image.mode), ((2048, 1792), "RGBA"))
            with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
                rows = json.load(file)[config.AXE_ENEMY_IMAGE]
            self.assertEqual(len(rows), 7)
            for row_index, row in enumerate(rows):
                self.assertEqual(len(row), 8)
                for column, tile in enumerate(row):
                    bounds = image.crop((column * 256, row_index * 256,
                                         (column + 1) * 256, (row_index + 1) * 256)).getbbox()
                    left, top, right, bottom = bounds
                    self.assertEqual(tile["clip"], [column * 256 + left,
                                                    image.height - row_index * 256 - bottom,
                                                    right - left, bottom - top])
        enemy = AxeEnemy(1000)
        self.assertTrue(all(1 <= row <= 6 for row, _, _ in enemy.animation.definitions.values()))

    def test_revisiting_pauses_axe_hp_animation_and_effects_and_f5_restores_fresh_summons(self):
        world, enemy = encounter()
        strike(world, enemy, "combat_s")
        dock = world.stage_index
        snapshot = (enemy.hp, enemy.animation.elapsed, world.effects[0].elapsed,
                    world.damage_numbers[0].elapsed)
        world.select_stage(dock + 1)
        advance(world, 0.3)
        world.select_stage(dock)
        self.assertIs(world.enemies[0], enemy)
        self.assertEqual((enemy.hp, enemy.animation.elapsed, world.effects[0].elapsed,
                          world.damage_numbers[0].elapsed), snapshot)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertTrue(all(not stage.enemies and not stage.effects and not stage.damage_numbers
                            and stage.spawner.spawned_count == 0 for stage in world.stages))
        world.select_stage(dock)
        tap(world.controls, "spawn_1")
        world.update(config.FIXED_DT)
        fresh = world.enemies[0]
        self.assertIsNot(fresh, enemy)
        self.assertEqual((fresh.hp, fresh.max_hp, fresh.attack_damage), (400, 400, 60))

    def test_natural_axe_pursuit_and_attacks_are_identical_across_render_rates(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world = World(rng=random.Random(37))
            world.select_stage(config.STAGE_IMAGES.index(config.FACTORY_OUTSIDE_IMAGE))
            world.player.invincible = True
            tap(world.controls, "spawn_4")
            world.update(config.FIXED_DT)
            advance(world, 4, fps)
            outcomes.append([(enemy.x, enemy.ground_y, enemy.state, enemy.hp,
                              enemy.animation.elapsed, enemy.has_hit) for enemy in world.enemies])
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
