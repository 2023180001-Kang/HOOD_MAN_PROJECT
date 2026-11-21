import json
import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import config
from assets import Assets
from axe_enemy import AxeEnemy
from combat import MOVES, STRONG_MOVES
from enemy import Enemy
from enemy02 import Enemy02
from player import Player
from projectiles import ResearcherBullet
from researcher import Researcher
from tests.helpers import advance, tap
from tests.test_strong_attacks import strike
from ui import UI
from world import World


def encounter(side=1, *, index=6, gap=300, invincible=False):
    world = World(rng=random.Random(23), item_rng=random.Random(5))
    world.select_stage(index)
    world.player.invincible = invincible
    world.player.facing = side
    enemy = world.spawner.spawn(1, world.elapsed)[0]
    world.enemies.append(enemy)
    enemy.x = enemy.previous_x = world.player.x + side * gap
    enemy.ground_y = enemy.previous_ground_y = world.player.ground_y
    enemy.facing = -side
    return world, enemy


def bullet_at(player, *, x=None, facing=1, height=83.25, depth=0, floor=0):
    return ResearcherBullet(player.x - 100 if x is None else x,
                            player.ground_y + depth, height, facing, floor)


def until(world, predicate, steps=2400):
    for _ in range(steps):
        world.step(config.FIXED_DT)
        if predicate():
            return
    raise AssertionError("Expected researcher event did not occur")


class ResearcherTests(unittest.TestCase):
    def test_only_both_factory_interiors_summon_researchers_and_other_types_stay_unchanged(self):
        world = World(rng=random.Random(42))
        for index, stage in enumerate(world.stages):
            world.select_stage(index)
            self.assertEqual(world.enemies, [])
            tap(world.controls, "spawn_4")
            world.update(config.FIXED_DT)
            expected, hp = Enemy, 200
            if stage.image_name in config.FACTORY_INSIDE_IMAGES:
                expected = Researcher
            elif stage.image_name == config.FACTORY_OUTSIDE_IMAGE:
                expected, hp = AxeEnemy, 400
            elif stage.image_name in config.ENEMY02_STAGE_IMAGES:
                expected = Enemy02
            self.assertEqual(len(world.enemies), 4)
            self.assertTrue(all(type(enemy) is expected and enemy.hp == enemy.max_hp == hp
                                for enemy in world.enemies))
            if expected is Researcher:
                self.assertTrue(all(enemy.ammo == 7 and enemy.attack_damage == 30
                                    for enemy in world.enemies))
            self.assertTrue(all(stage.walkable.contains(enemy.x, enemy.ground_y,
                                                        enemy.boundary_padding)
                                for enemy in world.enemies))

    def test_shoot_range_depth_and_floor_gate_attacks_in_both_directions(self):
        for side in (-1, 1):
            for gap, depth, floor, allowed in ((480, 0, 0, True), (480.01, 0, 0, False),
                                              (300, 32, 0, True), (300, 32.01, 0, False),
                                              (80, 0, 0, True), (300, 0, 1, False)):
                player = Player()
                enemy = Researcher(player.x + side * gap, -side,
                                   ground_y=player.ground_y + depth)
                enemy.floor = floor
                enemy.update(config.FIXED_DT, player)
                self.assertEqual(enemy.state == "ATTACK", allowed)
                self.assertIsNone(enemy.attack_box)  # Gunshots never deal melee damage.
                self.assertFalse(enemy.try_hit(player))
                self.assertEqual(player.hp, 500)

    def test_attack_frame_three_emits_one_round_and_does_not_repeat_across_frames(self):
        for speed in (0.8, 1, 1.4):
            enemy = Researcher(1000, attack_speed=speed)
            enemy.start_attack()
            enemy.animation.elapsed = 2.9 / enemy.attack_fps
            self.assertIsNone(enemy.take_projectile())
            self.assertEqual(enemy.ammo, 7)
            enemy.update(config.RESEARCHER_AIM_DURATION, Player())
            enemy.animation.elapsed = 3.05 / enemy.attack_fps
            bullet = enemy.take_projectile()
            self.assertIsInstance(bullet, ResearcherBullet)
            self.assertEqual((enemy.ammo, bullet.damage, bullet.facing), (6, 30, 1))
            self.assertIsNone(enemy.take_projectile())
            enemy.animation.elapsed = 6.05 / enemy.attack_fps
            self.assertIsNone(enemy.take_projectile())
            self.assertEqual(enemy.ammo, 6)

    def test_bullets_spawn_just_outside_the_actual_pistol_muzzle(self):
        for facing in (-1, 1):
            enemy = Researcher(1000, facing, ground_y=140)
            enemy.jump_height = 20
            enemy.start_attack()
            enemy.update(config.RESEARCHER_AIM_DURATION, Player())
            enemy.animation.elapsed = 3.05 / enemy.attack_fps
            bullet = enemy.take_projectile()
            self.assertAlmostEqual(bullet.x - facing * config.RESEARCHER_BULLET_HALF_WIDTH,
                                   enemy.x + facing * config.RESEARCHER_MUZZLE_X)
            self.assertEqual(bullet.ground_y, 140)
            self.assertAlmostEqual(bullet.y, enemy.y + config.RESEARCHER_MUZZLE_HEIGHT)

    def test_seven_shots_then_row_five_reload_refills_only_after_all_eight_frames(self):
        player = Player()
        enemy = Researcher(player.x + 300, -1)
        for remaining in range(6, -1, -1):
            enemy.start_attack()
            enemy.update(config.RESEARCHER_AIM_DURATION, player)
            enemy.animation.elapsed = 3.05 / enemy.attack_fps
            self.assertIsNotNone(enemy.take_projectile())
            self.assertEqual(enemy.ammo, remaining)
            enemy.animation.elapsed = 8 / enemy.attack_fps
            enemy.update(0, player)
        self.assertEqual((enemy.ammo, enemy.state, enemy.animation.row), (0, "RELOAD", 5))
        self.assertIsNone(enemy.take_projectile())
        duration = 8 / config.RESEARCHER_RELOAD_FPS
        enemy.update(duration - config.FIXED_DT, player)
        self.assertEqual((enemy.ammo, enemy.state), (0, "RELOAD"))
        self.assertEqual(enemy.animation.frame, 7)
        enemy.update(config.FIXED_DT, player)
        self.assertEqual((enemy.ammo, enemy.state), (7, "IDLE"))
        enemy.cooldown = 0
        enemy.update(config.FIXED_DT, player)
        self.assertEqual(enemy.state, "ATTACK")

    def test_reload_interruption_never_refills_early_and_survivor_restarts_reload(self):
        player = Player()
        enemy = Researcher(player.x + 300, -1)
        enemy.ammo = 0
        enemy.update(config.FIXED_DT, player)
        enemy.update(0.5, player)
        enemy.take_damage(10)
        self.assertEqual((enemy.hp, enemy.ammo, enemy.state, enemy.animation.row), (190, 0, "HIT", 6))
        enemy.update(1, player)
        enemy.update(config.FIXED_DT, player)
        self.assertEqual((enemy.ammo, enemy.state, enemy.animation.elapsed),
                         (0, "RELOAD", config.FIXED_DT))
        enemy.update(1, player)
        self.assertEqual(enemy.ammo, 7)

    def test_a_bullet_hit_deals_thirty_enters_player_hit_and_spawns_existing_impact(self):
        for side in (-1, 1):
            for index in (6, 7):
                for weapon in (None, *config.WEAPON_POSE_IMAGES):
                    world, enemy = encounter(side, index=index)
                    world.player.equip_weapon(weapon)
                    until(world, lambda: world.player.hp < 500)
                    self.assertEqual((world.player.hp, world.player.state), (470, "HIT"))
                    self.assertEqual(enemy.ammo, 6)
                    self.assertEqual(len(world.effects), 1)
                    self.assertEqual(world.effects[0].image_name, config.CLUB_HIT_IMAGE)
                    self.assertFalse(world.damage_numbers)
                    self.assertGreater(world.camera.shake_remaining, 0)
                    advance(world, 0.1)
                    self.assertEqual(world.player.hp, 470)

    def test_researchers_take_player_damage_with_their_own_hit_art_numbers_and_effects(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for side in (-1, 1):
                for key in "asdf" if weapon is None else "asf":
                    world, enemy = encounter(side, gap=80, invincible=True)
                    world.player.equip_weapon(weapon)
                    enemy.cooldown = 100
                    strike(world, enemy, f"combat_{key}")
                    move = world.player.active_move
                    self.assertEqual((enemy.hp, enemy.state, enemy.animation.row),
                                     (200 - move.damage, "HIT", 6))
                    self.assertEqual(enemy.sprite_image, config.RESEARCHER_IMAGE)
                    self.assertEqual([number.damage for number in world.damage_numbers], [move.damage])
                    self.assertEqual(world.effects[-1].image_name, move.hit_image)
                if weapon is not None:
                    world, enemy = encounter(side, gap=80, invincible=True)
                    world.player.equip_weapon(weapon)
                    enemy.cooldown = 100
                    for action in ("jump", "jump", "combat_d", "combat_d"):
                        tap(world.controls, action)
                        world.step(config.FIXED_DT)
                    until(world, lambda: enemy.hp < 200)
                    self.assertEqual(enemy.hp, 150)
                    self.assertEqual([number.damage for number in world.damage_numbers], [50])
                    self.assertEqual(world.effects[-1].image_name, config.WEAPON_HIT_IMAGES[weapon])

    def test_lethal_bullet_uses_normal_player_death_instead_of_hit(self):
        world, _ = encounter()
        world.player.hp = 20
        until(world, lambda: not world.player.alive)
        self.assertEqual((world.player.hp, world.player.state), (0, "DYING"))
        advance(world, 1)
        self.assertEqual(world.player.state, "DEAD")

    def test_swept_bullet_hit_catches_fast_crossing_and_consumes_exactly_once(self):
        for facing in (-1, 1):
            player = Player()
            bullet = bullet_at(player, x=player.x - facing * 300, facing=facing)
            self.assertTrue(bullet.update(0.7, player))
            self.assertEqual(player.hp, 470)
            self.assertTrue(bullet.finished)
            self.assertFalse(bullet.update(0.01, player))
            self.assertEqual(player.hp, 470)

    def test_bullets_check_depth_height_floor_and_do_not_damage_a_dead_player(self):
        for situation in ("depth_edge", "deep", "high_jump", "other_floor", "dead", "stair"):
            player = Player()
            if situation == "high_jump":
                player.jump_height = player.previous_jump_height = 200
            elif situation == "dead":
                player.take_damage(500)
            elif situation == "stair":
                player.staircase = object()
            bullet = bullet_at(player, depth=32 if situation == "depth_edge" else
                               32.01 if situation == "deep" else 0,
                               floor=1 if situation == "other_floor" else 0)
            self.assertEqual(bullet.update(0.2, player), situation == "depth_edge")
            self.assertEqual(player.hp, 470 if situation == "depth_edge" else
                             0 if situation == "dead" else 500)

    def test_swept_axes_must_intersect_at_one_common_instant(self):
        player = Player()
        player.previous_ground_y = 100
        player.ground_y = 200
        bullet = ResearcherBullet(player.x - 200, 100, 83.25, 1)
        self.assertFalse(bullet.update(0.5, player))
        self.assertEqual(player.hp, 500)
        player.ground_y = 150
        bullet = ResearcherBullet(player.x - 70, 100, 83.25, 1)
        self.assertTrue(bullet.update(0.5, player))
        self.assertEqual(player.hp, 470)

    def test_new_bullet_does_not_collide_with_the_players_pre_birth_position(self):
        player = Player()
        player.previous_x = player.x - 200
        bullet = bullet_at(player, x=player.previous_x)
        self.assertFalse(bullet.update(0, player))
        self.assertFalse(bullet.spent)
        self.assertEqual(player.hp, 500)

    def test_p_immunity_consumes_the_bullet_without_hit_effect_or_shake(self):
        world, _ = encounter(invincible=True)
        world.enemies.clear()
        world.projectiles.append(bullet_at(world.player))
        advance(world, 0.2)
        self.assertEqual((world.player.hp, world.player.state), (500, "IDLE"))
        self.assertFalse(world.projectiles)
        self.assertFalse(world.effects)
        self.assertEqual(world.camera.shake_remaining, 0)

    def test_multiple_bullets_apply_damage_during_hit_without_restarting_its_clock(self):
        world, _ = encounter()
        world.enemies.clear()
        for _ in range(2):
            world.projectiles.append(bullet_at(world.player, x=world.player.x - 40))
        world.step(config.FIXED_DT)
        self.assertEqual((world.player.hp, world.player.state), (440, "HIT"))
        advance(world, 0.1)
        elapsed = world.player.animation.elapsed
        world.projectiles.append(bullet_at(world.player, x=world.player.x - 35))
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 410)
        self.assertGreater(world.player.animation.elapsed, elapsed)
        self.assertEqual(len(world.effects), 3)

    def test_player_strike_cancels_same_tick_shot_before_ammo_or_projectile_is_emitted(self):
        world, enemy = encounter(gap=80)
        enemy.start_attack()
        enemy.update(config.RESEARCHER_AIM_DURATION - config.FIXED_DT, world.player)
        move = MOVES["combat_s"]
        world.player.start_move(move, 1)
        world.player.animation.elapsed = 3 / move.fps
        world.step(config.FIXED_DT)
        self.assertEqual((world.player.hp, enemy.hp, enemy.state, enemy.ammo), (500, 160, "HIT", 7))
        self.assertFalse(world.projectiles)

    def test_an_already_fired_bullet_survives_its_shooters_death(self):
        world, enemy = encounter()
        until(world, lambda: bool(world.projectiles))
        enemy.take_damage(200)
        until(world, lambda: world.player.hp < 500)
        self.assertEqual((enemy.hp, world.player.hp), (0, 470))
        self.assertEqual((enemy.sprite_image, enemy.animation.row), (config.RESEARCHER_IMAGE, 7))
        self.assertFalse(any(item.kind == "metal_club" for item in world.stage.drop_items))

    def test_magazines_and_reload_clocks_are_private_to_each_researcher(self):
        player = Player()
        first = Researcher(player.x - 300)
        second = Researcher(player.x + 300, -1)
        first.ammo = 0
        first.update(0.5, player)
        second.start_attack()
        second.update(config.RESEARCHER_AIM_DURATION, player)
        second.animation.elapsed = 3.05 / second.attack_fps
        self.assertIsNotNone(second.take_projectile())
        self.assertEqual((first.ammo, first.state, second.ammo), (0, "RELOAD", 6))
        first.update(0.5, player)
        self.assertEqual((first.ammo, second.ammo), (7, 6))

    def test_strong_attacks_and_rush_keep_researcher_identity_and_ammo(self):
        for action in STRONG_MOVES:
            world, enemy = encounter(gap=80, invincible=True)
            enemy.cooldown = 100
            strike(world, enemy, action)
            self.assertEqual((enemy.hp, enemy.animation.row, enemy.ammo), (150, 6, 7))
            self.assertEqual(enemy.sprite_image, config.RESEARCHER_IMAGE)
            if action == "combat_w":
                world.controls.release(action)
                world.step(config.FIXED_DT)
            until(world, lambda: enemy.state == "IDLE")
            self.assertEqual(enemy.sprite_image, config.RESEARCHER_IMAGE)

    def test_ranged_enemies_ignore_melee_slots_and_hold_their_firing_distance(self):
        world, enemy = encounter(invincible=True)
        second = Researcher(enemy.x + 5, ground_y=enemy.ground_y)
        second.walkable = world.stage.walkable
        world.enemies.append(second)
        positions = [actor.x for actor in world.enemies]
        advance(world, 3)
        self.assertEqual([actor.x for actor in world.enemies], positions)
        self.assertTrue(all(actor.target_x is None and actor.formation_slot is None
                            for actor in world.enemies))
        self.assertTrue(all(actor.ammo < 7 for actor in world.enemies))

    def test_stage_revisit_pauses_bullets_ammo_and_reload_and_f5_clears_every_stage(self):
        world, enemy = encounter(invincible=True)
        until(world, lambda: bool(world.projectiles))
        bullet = world.projectiles[0]
        enemy.ammo = 0
        enemy.animation.set_state("RELOAD")
        snapshot = (bullet.x, bullet.elapsed, enemy.ammo, enemy.animation.elapsed)
        world.select_stage(5)
        advance(world, 0.3)
        world.select_stage(6)
        self.assertIs(world.projectiles[0], bullet)
        self.assertEqual((bullet.x, bullet.elapsed, enemy.ammo, enemy.animation.elapsed), snapshot)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertTrue(all(not stage.enemies and not stage.projectiles for stage in world.stages))
        world.select_stage(7)
        tap(world.controls, "spawn_1")
        world.update(config.FIXED_DT)
        self.assertEqual((world.enemies[0].hp, world.enemies[0].ammo), (200, 7))

    def test_health_bar_and_factory_gun_hud_use_researcher_values(self):
        world, enemy = encounter()
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            assets = SimpleNamespace(frames=json.load(file), damage_font=Mock(),
                                     font=Mock(), images={config.HP_IMAGE: Mock(w=700, h=80)})
        ui = UI()
        for details in (True, False):
            ui.details_visible = details
            for hp, width in ((200, 48), (100, 24), (0, 0)):
                enemy.hp = hp
                with patch("pico2d.draw_rectangle") as draw:
                    ui.draw_enemy_health(assets, world, 0, 0)
                bars = [call.args for call in draw.call_args_list if call.args[4:7] == (215, 38, 45)]
                self.assertEqual(len(bars), int(hp > 0))
                if bars:
                    self.assertEqual(bars[0][2] - bars[0][0] + 1, width)
        ui.details_visible = True
        with patch("pico2d.draw_rectangle"):
            ui.draw(assets, world)
        self.assertTrue(any("권총" in call.args[2] and "30" in call.args[2] and "7" in call.args[2]
                            for call in assets.font.draw.call_args_list))

    def test_slow_motion_and_loading_pause_or_scale_bullets_and_reload_together(self):
        world, enemy = encounter(invincible=True)
        enemy.ammo = 0
        enemy.start_reload()
        bullet = bullet_at(world.player, x=world.player.x - 400, height=500)
        world.projectiles.append(bullet)
        start = bullet.x
        tap(world.controls, "combat_r")
        world.step(config.FIXED_DT)
        dt = config.FIXED_DT * config.R_RAISE_TIME_SCALE
        self.assertAlmostEqual(bullet.x - start, config.RESEARCHER_BULLET_SPEED * dt)
        self.assertAlmostEqual(bullet.elapsed, dt)
        self.assertAlmostEqual(enemy.animation.elapsed, dt)
        world.pending_stage_index = 7
        world.stage_loading_remaining = 2
        snapshot = bullet.x, bullet.elapsed, enemy.ammo, enemy.animation.elapsed
        world.update(0.1)
        self.assertEqual((bullet.x, bullet.elapsed, enemy.ammo, enemy.animation.elapsed), snapshot)

    def test_source_grids_and_bullet_clips_remain_small_and_nose_anchored_in_both_facings(self):
        from PIL import Image

        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            metadata = json.load(file)
        for name, rows in ((config.RESEARCHER_IMAGE, 7), (config.RESEARCHER_BULLET_IMAGE, 1)):
            with Image.open(config.ROOT / name) as image:
                self.assertEqual((image.size, image.mode), ((2048, rows * 256), "RGBA"))
            self.assertEqual(len(metadata[name]), rows)
        image = Mock(w=2048, h=256)
        assets = SimpleNamespace(images={config.RESEARCHER_BULLET_IMAGE: image}, frames=metadata)
        for facing in (-1, 1):
            bullet = ResearcherBullet(1000, 100, 83.25, facing)
            for frame in range(8):
                bullet.elapsed = (frame + 0.05) / config.RESEARCHER_BULLET_FPS
                Assets.draw_projectile(assets, bullet, 20, 30)
                args = image.clip_composite_draw.call_args.args
                self.assertEqual(args[:4], tuple(metadata[bullet.image_name][0][frame]["clip"]))
                self.assertEqual(args[5], "h" if facing < 0 else "")
                self.assertLessEqual(args[8], 26)
                self.assertLessEqual(args[9], 7)
                self.assertAlmostEqual(args[6] + facing * args[8] / 2,
                                       bullet.impact_x - 20)
        self.assertIsNone(Researcher(1000).death_drop_kind)

    def test_bullet_lifetime_and_world_bounds_remove_misses(self):
        player = Player()
        for x, facing in ((0, -1), (config.WORLD_WIDTH, 1)):
            bullet = bullet_at(player, x=x, facing=facing)
            bullet.update(0.1, player)
            self.assertTrue(bullet.finished)
        bullet = bullet_at(player, height=400)
        bullet.update(config.RESEARCHER_BULLET_LIFETIME, player)
        self.assertTrue(bullet.finished)

    def test_firing_reloading_and_projectiles_are_render_rate_independent(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world, enemy = encounter(invincible=True)
            advance(world, 10, fps)
            outcomes.append((enemy.hp, enemy.ammo, enemy.state, enemy.animation.elapsed,
                             world.player.hp, [(bullet.x, bullet.elapsed) for bullet in world.projectiles]))
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
