import hashlib
import json
import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import config
from ar_soldier import ARSoldier
from assets import Assets
from axe_enemy import AxeEnemy
from combat import STRONG_MOVES
from enemy import Enemy
from enemy02 import Enemy02
from player import Player
from projectiles import EnemyAxeProjectile
from researcher import Researcher
from shield_soldier import ShieldSoldier
from tests.helpers import advance, spawn_encounter, tap
from tests.test_strong_attacks import strike
from ui import UI
from tests.helpers import ManualSpawnWorld as World


def encounter(side=1, *, hp=400, weapon=None, index=4):
    world = World(rng=random.Random(23), item_rng=random.Random(5))
    world.select_stage(index)
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
    def advance_until(self, world, condition, seconds=6):
        for _ in range(round(seconds / config.FIXED_DT)):
            world.step(config.FIXED_DT)
            if condition():
                return
        self.fail("Combat condition was not reached before the timeout")

    def swing_then_throw(self, world, enemy):
        player = world.player
        player.invincible = False
        enemy.cooldown = 0
        hp = player.hp
        self.advance_until(world, lambda: player.hp < hp)
        self.assertEqual((enemy.attack_kind, player.hp), ("swing", hp - 40))
        player.x = enemy.x + enemy.facing * 440
        with patch.object(enemy.rng, "random", return_value=0):
            self.advance_until(world, lambda: bool(world.projectiles))
        shot, = world.projectiles
        self.assertIsInstance(shot, EnemyAxeProjectile)
        self.assertIs(shot.shooter, enemy)
        self.assertEqual((enemy.animation.row, enemy.animation.frame, enemy.armed), (7, 4, False))
        self.assertFalse(enemy.attack_box)
        self.assertIsNone(enemy.take_projectile())
        return shot

    def test_throw_requires_prior_swing_range_and_a_successful_random_roll(self):
        world, enemy = encounter()
        player = world.player
        enemy.cooldown = 0
        player.x = enemy.x - 400
        with patch.object(enemy.rng, "random", side_effect=[0.9, 0.1]) as roll:
            self.assertFalse(enemy.try_start_throw(0, player))
            enemy.start_attack()
            enemy.update(4.1 / enemy.attack_fps, player)
            enemy.update(4.1 / enemy.attack_fps, player)
            enemy.cooldown = 0
            for dx, depth in ((100, 0), (800, 0), (400, 50)):
                player.x, player.ground_y = enemy.x - dx, enemy.ground_y + depth
                self.assertFalse(enemy.try_start_throw(0, player))
            roll.assert_not_called()
            player.ground_y = enemy.ground_y
            self.assertFalse(enemy.try_start_throw(0, player))
            self.assertFalse(enemy.try_start_throw(0.1, player))
            self.assertTrue(enemy.try_start_throw(config.AXE_ENEMY_THROW_RETRY, player))
            self.assertEqual(roll.call_count, 2)
            self.assertEqual((enemy.animation.row, enemy.facing), (7, -1))
            enemy.animation.elapsed = 3.99 / enemy.attack_fps
            self.assertIsNone(enemy.take_projectile())
            enemy.take_damage(10)
            self.assertIsNone(enemy.take_projectile())
            self.assertTrue(enemy.armed)

    def test_throw_flies_level_then_falls_hits_once_and_owner_recovers_and_reuses_it(self):
        for side in (-1, 1):
            with self.subTest(side=side):
                world, enemy = encounter(side)
                world.stage.drop_items.clear()
                shot = self.swing_then_throw(world, enemy)
                start_x, start_height = shot.x, shot.height
                self.assertEqual(shot.facing, -side)
                self.advance_until(world, lambda: shot.elapsed >= 0.75)
                self.assertEqual(shot.height, start_height)
                self.assertAlmostEqual(shot.x, start_x + shot.facing * shot.speed * shot.elapsed)
                self.assertEqual(world.player.hp, 410)
                self.assertEqual(enemy.sprite_image, config.AXE_ENEMY_UNARMED_IMAGE)
                self.advance_until(world, lambda: shot.elapsed > shot.straight_duration + 0.05)
                self.assertLess(shot.height, start_height)
                self.advance_until(world, lambda: bool(world.stage.drop_items))
                item, = world.stage.drop_items
                self.assertEqual((item.kind, item.grounded, item.floor), ("axe", True, enemy.floor))
                self.assertIs(item.axe_owner, enemy)
                self.assertFalse(world.projectiles)
                self.assertEqual(world.player.hp, 410)
                self.advance_until(world, lambda: enemy.armed)
                self.assertFalse(world.stage.drop_items)
                self.assertFalse(enemy.has_swung)
                self.assertEqual(enemy.sprite_image, config.AXE_ENEMY_IMAGE)
                # Give the recovered weapon room to travel on its next throw.
                world.player.x = enemy.x + side * 80
                self.swing_then_throw(world, enemy)

    def test_sword_parries_thrown_axe_and_either_fighter_can_recover_it(self):
        for side in (-1, 1):
            with self.subTest(side=side):
                world, enemy = encounter(side, weapon="sword")
                player = world.player
                world.stage.drop_items.clear()
                axe = self.swing_then_throw(world, enemy)
                hp = player.hp
                world.controls.press("combat_s")
                with patch("projectiles.uniform", return_value=side * 0.6):
                    self.advance_until(world, lambda: axe.deflected)
                self.assertEqual((player.hp, player.state, axe.facing), (hp, "SWORD_PARRY", side))
                contact_x = axe.x
                world.controls.release("combat_s")
                self.advance_until(world, lambda: bool(world.stage.drop_items))
                item, = world.stage.drop_items
                self.assertGreater((item.x - contact_x) * side, 0)
                self.assertEqual((item.kind, item.grounded, player.hp), ("axe", True, hp))
                self.assertIs(item.axe_owner, enemy)
                self.assertFalse(world.projectiles)
                if side == 1:
                    player.x, player.ground_y = item.x, item.ground_y
                    tap(world.controls, "weapon_interact")
                    world.step(config.FIXED_DT)
                    self.assertEqual(player.weapon, "axe")
                else:
                    self.advance_until(world, lambda: enemy.armed)
                self.assertNotIn(item, world.stage.drop_items)

    def test_player_can_claim_the_same_drop_first_and_enemy_fights_unarmed(self):
        world, enemy = encounter()
        world.stage.drop_items.clear()
        self.swing_then_throw(world, enemy)
        self.advance_until(world, lambda: bool(world.stage.drop_items))
        item, = world.stage.drop_items
        world.player.x, world.player.ground_y = item.x, item.ground_y
        enemy.x, enemy.ground_y = item.x + 65, item.ground_y
        tap(world.controls, "weapon_interact")
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.weapon, "axe")
        self.assertFalse(world.stage.drop_items or enemy.armed)
        for kind, row, damage in (("punch", 4, 15), ("kick", 5, 20)):
            with patch.object(enemy.rng, "choice", return_value=kind):
                hp = world.player.hp
                self.advance_until(world, lambda: world.player.hp < hp)
                self.assertEqual((enemy.sprite_image, enemy.animation.row, hp - world.player.hp),
                                 (config.AXE_ENEMY_UNARMED_IMAGE, row, damage))
        enemy.take_damage(1)
        self.assertEqual((enemy.sprite_image, enemy.animation.row), (config.AXE_ENEMY_UNARMED_IMAGE, 6))
        enemy.take_damage(enemy.hp)
        self.assertEqual((enemy.sprite_image, enemy.animation.row), (config.AXE_ENEMY_UNARMED_IMAGE, 7))

    def test_wall_drop_stays_collectible_after_owner_dies_and_cannot_arm_another_enemy(self):
        world, enemy = encounter(-1)
        world.stage.drop_items.clear()
        world.player.x, enemy.x = 2350, 2270
        shot = self.swing_then_throw(world, enemy)
        enemy.take_damage(enemy.hp)
        other = AxeEnemy(2400, ground_y=enemy.ground_y)
        other._set_armed(False)
        world.enemies.append(other)
        self.advance_until(world, lambda: bool(world.stage.drop_items))
        item, = world.stage.drop_items
        self.assertFalse(item.grounded)
        self.assertGreater(shot.height, shot.half_height)
        self.advance_until(world, lambda: item.grounded)
        other.x, other.ground_y = item.x, item.ground_y
        world.step(config.FIXED_DT)
        self.assertFalse(other.armed)
        self.assertEqual(world.stage.drop_items, [item])
        world.player.x, world.player.ground_y = item.x, item.ground_y
        tap(world.controls, "weapon_interact")
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.weapon, "axe")

    def test_owner_can_retrieve_at_wall_with_player_standing_on_the_landing_spot(self):
        world, enemy = encounter(-1)
        world.stage.drop_items.clear()
        world.player.x, enemy.x = 2350, 2270
        shot = self.swing_then_throw(world, enemy)
        self.advance_until(world, lambda: bool(world.stage.drop_items))
        item, = world.stage.drop_items
        self.assertGreater(shot.height, shot.half_height)
        self.assertFalse(item.grounded)
        self.advance_until(world, lambda: enemy.armed)
        self.assertFalse(world.stage.drop_items)
        self.assertEqual(world.player.hp, 410)

    def test_both_factory_exteriors_summon_axe_enemies_with_their_own_max_hp(self):
        world = World(rng=random.Random(42))
        for index, stage in enumerate(world.stages):
            world.select_stage(index)
            tap(world.controls, "spawn_4")
            world.update(config.FIXED_DT)
            expected, hp = Enemy, 200
            if stage.image_name in config.AXE_ENEMY_STAGE_IMAGES:
                expected, hp = AxeEnemy, 400
            elif stage.image_name in config.ENEMY02_STAGE_IMAGES:
                expected = Enemy02
            elif stage.image_name in config.FACTORY_INSIDE_IMAGES:
                expected = Researcher
            elif stage.image_name in config.LAB_STAGE_IMAGES:
                expected, hp = ShieldSoldier, 400
            elif stage.image_name in config.BOSS_STAGE_IMAGES:
                expected, hp = ARSoldier, 300
            self.assertEqual(len(world.enemies), 4)
            for enemy in world.enemies:
                self.assertIs(type(enemy), expected)
                self.assertEqual((enemy.hp, enemy.max_hp), (hp, hp))
                self.assertTrue(stage.walkable.contains(enemy.x, enemy.ground_y,
                                                        enemy.boundary_padding))

    def test_each_numeric_input_keeps_count_latching_and_independent_speed_profiles(self):
        for index in (4, 5):
            for count in config.SPAWN_COUNTS:
                with self.subTest(index=index, count=count):
                    world, _ = encounter(index=index)
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
                    self.assertTrue(all(type(enemy) is AxeEnemy and enemy.hp == 400
                                        and enemy.sprite_image == config.AXE_ENEMY_IMAGE
                                        for enemy in world.enemies))

    def test_both_factory_m_entries_use_new_axe_art_without_replacing_existing_enemies(self):
        world = World(rng=random.Random(23))
        world.select_stage(8)
        original = world.spawner.spawn(1, 0)[0]
        original.take_damage(40)
        world.enemies = [original]
        for _ in range(5):
            world.stage.cycle_spawn_enemy_type()
        for source in (4, 5):
            self.assertEqual(world.stage.spawn_enemy_stage_index, source)
            self.assertIs(world.spawner.enemy_type, AxeEnemy)
            tap(world.controls, "spawn_1")
            world.step(config.FIXED_DT)
            fresh = world.enemies[-1]
            self.assertIs(type(fresh), AxeEnemy)
            self.assertEqual((fresh.hp, fresh.attack_damage, fresh.sprite_image),
                             (400, 40, config.AXE_ENEMY_IMAGE))
            self.assertIs(fresh.walkable, world.stage.walkable)
            self.assertIs(world.enemies[0], original)
            self.assertEqual(original.hp, 360)
            world.stage.cycle_spawn_enemy_type()

    def test_axe_swing_deals_forty_once_only_on_active_frames_in_both_directions(self):
        for side in (-1, 1):
            player = Player()
            enemy = AxeEnemy(player.x + side * 80, -side, attack_speed=1.3)
            enemy.start_attack()
            for frame in range(8):
                enemy.animation.elapsed = (frame + 0.05) / enemy.attack_fps
                self.assertEqual(enemy.try_hit(player), frame == 4)
                self.assertEqual(player.hp, 500 if frame < 4 else 460)
            enemy.start_attack()
            enemy.animation.elapsed = 4.05 / enemy.attack_fps
            self.assertTrue(enemy.try_hit(player))
            self.assertEqual(player.hp, 420)

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
            self.assertEqual(player.hp, 460 if situation == "depth_edge" else 500)
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
        self.assertEqual(world.player.hp, 420)
        self.assertTrue(first.has_hit and second.has_hit)
        self.assertEqual([effect.image_name for effect in world.effects],
                         [config.CLUB_HIT_IMAGE] * 2)
        self.assertGreater(world.camera.shake_remaining, 0)
        advance(world, 0.1)
        self.assertEqual(world.player.hp, 420)

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

    def test_pipe_dive_landings_deal_sixty_with_existing_feedback(self):
        for weapon in config.WEAPON_AIRBORNE_ROWS:
            for side in (-1, 1):
                world, enemy = encounter(side, weapon=weapon)
                for action in ("jump", "jump", "combat_d", "combat_d"):
                    tap(world.controls, action)
                    world.step(config.FIXED_DT)
                for _ in range(90):
                    world.step(config.FIXED_DT)
                    if enemy.hp < 400:
                        break
                self.assertEqual(enemy.hp, 340)
                self.assertEqual([number.damage for number in world.damage_numbers], [60])
                self.assertEqual(world.effects[-1].image_name, config.WEAPON_HIT_IMAGES[weapon])
                self.assertEqual((enemy.sprite_image, enemy.animation.row),
                                 (config.AXE_ENEMY_IMAGE, 5))

    def test_all_strong_hits_keep_axe_art_and_never_use_stun(self):
        for action, move in STRONG_MOVES.items():
            for side in (-1, 1):
                with self.subTest(action=action, side=side):
                    world, enemy = encounter(side)
                    strike(world, enemy, action)
                    self.assertEqual(enemy.hp, 400 - move.damage)
                    self.assertEqual((enemy.sprite_image, enemy.animation.row),
                                     (config.AXE_ENEMY_IMAGE, 5))
                    self.assertEqual([number.damage for number in world.damage_numbers], [move.damage])
                    for _ in range(360):
                        self.assertNotEqual(enemy.animation.row, 7)
                        self.assertEqual(enemy.sprite_image, config.AXE_ENEMY_IMAGE)
                        if enemy.state == "IDLE":
                            break
                        world.step(config.FIXED_DT)
                    self.assertEqual((enemy.hp, enemy.state), (400 - move.damage, "IDLE"))

    def test_lethal_strong_reactions_finish_with_the_axe_death_row_not_stun(self):
        for action in STRONG_MOVES:
            world, enemy = encounter(hp=20)
            strike(world, enemy, action)
            self.assertEqual(enemy.hp, 0)
            self.assertEqual([number.damage for number in world.damage_numbers], [20])
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

    def test_both_exterior_huds_report_axe_damage_instead_of_the_old_club_damage(self):
        for index in (4, 5):
            world, _ = encounter(index=index)
            assets = SimpleNamespace(images={config.HP_IMAGE: Mock(w=700, h=80)}, font=Mock())
            with patch("pico2d.draw_rectangle"):
                UI().draw(assets, world)
            labels = [call.args[2] for call in assets.font.draw.call_args_list]
            self.assertIn("적 공격: 도끼 40 / 투척 50 / 주먹 15 / 발차기 20", labels)
            self.assertTrue(any(f"{index + 1}번 맵" in text and "도끼 적" in text for text in labels))

    def test_both_sheets_have_seven_rows_with_exact_clips_flips_and_grounding(self):
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            metadata = json.load(file)
        for name in (config.AXE_ENEMY_IMAGE, config.AXE_ENEMY_UNARMED_IMAGE):
            with self.subTest(name=name), Image.open(config.ROOT / name) as image:
                self.assertEqual((image.size, image.mode), ((2048, 1792), "RGBA"))
                rows = metadata[name]
                texture = Mock()
                assets = SimpleNamespace(frames=metadata, images={name: texture})
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
                        for facing in (-1, 1):
                            Assets.draw_sprite(assets, name, row_index + 1, column,
                                               500, 100, facing)
                            args = texture.clip_composite_draw.call_args.args
                            self.assertEqual(args[:4], tuple(tile["clip"]))
                            self.assertEqual(args[5], "h" if facing < 0 else "")
                            self.assertEqual(args[7] - args[9] / 2, 100)
        enemy = AxeEnemy(1000)
        self.assertTrue(all(1 <= row <= 6 for row, _, _ in enemy.animation.definitions.values()))

    def test_new_sheet_and_archived_original_keep_supplied_bytes_and_only_new_art_is_loaded(self):
        self.assertEqual(config.AXE_ENEMY_IMAGE, "HoodMan_AxeEnemy_8x7.png")
        self.assertEqual(config.ARCHIVED_AXE_ENEMY_IMAGE, "before_sheets/axe_enemy_pico2d_256x256.png")
        for name, digest, height in (
            (config.AXE_ENEMY_IMAGE, "bb68733078fc39248cb976b9e38da9410bdb0f1b88e1fca9752d2e818f0e2c74", 1792),
            (config.AXE_ENEMY_UNARMED_IMAGE, "a92d2099c995cb889dde2da68a971f732fa36bc6134730fef2bd05811fdb4a4a", 1792),
            (config.ARCHIVED_AXE_ENEMY_IMAGE, "866eb4fda2e77de47d4ca49fe79ce98103076db5378182f926bfeb00a42deea4", 1536),
            ("before_sheets/axe_enemy_pico2d_2048x1792.png", "d677ad34fa101aecd32e111dcdd9c75b5738ee075b3a2a76491093cf8d3fd8a7", 1792),
        ):
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((config.ROOT / name).read_bytes()).hexdigest(), digest)
                with Image.open(config.ROOT / name) as image:
                    self.assertEqual((image.size, image.mode), ((2048, height), "RGBA"))
        self.assertFalse((config.ROOT / "axe_enemy_pico2d_2048x1792.png").exists())
        with patch("pico2d.load_image", return_value=Mock()), patch("pico2d.load_font"):
            assets = Assets()
        from tools.prepare_assets import SHEETS
        for name in (config.ARCHIVED_AXE_ENEMY_IMAGE, "axe_enemy_pico2d_256x256.png",
                     "before_sheets/axe_enemy_pico2d_2048x1792.png", "axe_enemy_pico2d_2048x1792.png"):
            self.assertNotIn(name, assets.images)
            self.assertNotIn(name, assets.frames)
            self.assertNotIn(name, SHEETS)
        for name in (config.AXE_ENEMY_IMAGE, config.AXE_ENEMY_UNARMED_IMAGE):
            self.assertIn(name, assets.images)
            self.assertEqual(SHEETS[name], 7)
        self.assertEqual(len(assets.frames), 26)
        self.assertEqual(sum(len(row) for rows in assets.frames.values() for row in rows), 1328)

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
        self.assertEqual((fresh.hp, fresh.max_hp, fresh.attack_damage), (400, 400, 40))

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
