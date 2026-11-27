import random
import unittest
from unittest.mock import Mock

import config
from ar_soldier import ARSoldier
from axe_enemy import AxeEnemy
from collision import bodies_overlap
from combat import STRONG_MOVES
from enemy import Enemy
from enemy02 import Enemy02
from player import Player
from researcher import Researcher
from shield_soldier import ShieldSoldier
from tests.helpers import advance, spawn_encounter
from tests.test_strong_attacks import strike
from traffic import Car, Traffic
from tests.helpers import ManualSpawnWorld as World


def at_frame(kind, frame, *, side=1):
    player = Player()
    enemy = Enemy02(player.x + side * (400 if kind == "slam" else 80), -side)
    if kind == "slam":
        assert enemy.start_leap(player)
        if frame >= 2:
            while enemy.leap_phase == "WINDUP":
                enemy.update(config.FIXED_DT, player)
            if frame in (2, 3):
                target_time = enemy.leap_duration * (0.25 if frame == 2 else 0.75)
                enemy.update(target_time - enemy.leap_elapsed, player)
            else:
                while enemy.leap_phase != "LANDING":
                    enemy.update(config.FIXED_DT, player)
    else:
        enemy.start_attack()
    enemy.animation.elapsed = (frame + 0.05) / enemy.attack_fps
    enemy.update(0, player)
    return player, enemy


class Enemy02Tests(unittest.TestCase):
    def test_only_city_maps_summon_the_new_type_and_f5_clears_every_stage(self):
        world = World(rng=random.Random(51))
        for _ in range(2):
            for index, stage in enumerate(world.stages):
                self.assertEqual(stage.enemies, [])
                world.stage_index = index
                world.player.ground_y = sum(stage.spawn_area.bounds[1::2]) / 2
                world.controls.press("spawn_4")
                world.update(config.FIXED_DT)
                world.controls.release("spawn_4")
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
                self.assertEqual(len(stage.enemies), 4)
                self.assertEqual(stage.spawner.spawned_count, 4)
                self.assertTrue(all(type(enemy) is expected for enemy in stage.enemies))
                for enemy in stage.enemies:
                    self.assertEqual(enemy.hp, hp)
                    self.assertTrue(stage.spawn_area.contains(enemy.x, enemy.ground_y,
                                                              enemy.boundary_padding))
                    self.assertEqual(enemy.facing, 1 if enemy.x < config.START_X else -1)
            world.controls.press("restart")
            world.update(config.FIXED_DT)
            world.controls.release("restart")
            self.assertTrue(all(not stage.enemies and stage.spawner.spawned_count == 0
                                for stage in world.stages))

    def test_ai_selects_close_clubs_or_medium_range_leap_and_commits_until_recovery(self):
        for kind, gap, row, damage in (("clubs", 80, 4, 30), ("slam", 400, 5, 50)):
            player = Player()
            rng = Mock(wraps=random.Random(9))
            enemy = Enemy02(player.x + gap, -1, rng=rng)
            enemy.update(config.FIXED_DT, player)
            self.assertEqual(enemy.state, "ATTACK")
            self.assertEqual((enemy.attack_kind, enemy.animation.row, enemy.attack_damage),
                             (kind, row, damage))
            for _ in range(320):
                enemy.update(config.FIXED_DT, player)
                self.assertEqual((enemy.attack_kind, enemy.attack_damage), (kind, damage))
                if enemy.state != "ATTACK":
                    break
                self.assertEqual(enemy.animation.row, row)
            self.assertEqual((enemy.state, enemy.jump_height), ("IDLE", 0))
            self.assertEqual(rng.choice.call_count, 0)

    def test_dual_club_motion_deals_thirty_once_across_both_swings(self):
        for side in (-1, 1):
            player, enemy = at_frame("clubs", 2, side=side)
            self.assertIsNone(enemy.attack_box)
            self.assertFalse(enemy.try_hit(player))
            for frame in (3, 4, 5, 6, 7):
                enemy.animation.elapsed = (frame + 0.05) / enemy.attack_fps
                self.assertEqual(enemy.try_hit(player), frame == 3)
                self.assertEqual(player.hp, 470)
            enemy.start_attack()
            enemy.animation.elapsed = 4.05 / enemy.attack_fps
            self.assertTrue(enemy.try_hit(player))
            self.assertEqual(player.hp, 440)

    def test_flight_height_and_landing_frames_gate_fifty_damage(self):
        for frame in range(8):
            with self.subTest(frame=frame):
                player, enemy = at_frame("slam", frame)
                if frame in (2, 3):
                    self.assertGreater(enemy.jump_height, 200)
                else:
                    self.assertEqual(enemy.jump_height, 0)
                self.assertEqual(enemy.y, enemy.ground_y + enemy.jump_height)
                self.assertEqual(enemy.body.bottom, config.GROUND_Y + enemy.jump_height)
                self.assertEqual(enemy.try_hit(player), frame in (5, 6))
                self.assertEqual(player.hp, 450 if frame in (5, 6) else 500)
        player, enemy = at_frame("slam", 5)
        self.assertTrue(enemy.try_hit(player))
        enemy.animation.elapsed = 6.05 / enemy.attack_fps
        self.assertFalse(enemy.try_hit(player))
        self.assertEqual(player.hp, 450)

    def test_both_attacks_keep_direction_depth_and_airborne_dodge_checks(self):
        for kind, frame in (("clubs", 3), ("slam", 5)):
            for side in (-1, 1):
                for situation in ("behind", "too_deep", "above", "depth_boundary"):
                    with self.subTest(kind=kind, side=side, situation=situation):
                        player, enemy = at_frame(kind, frame, side=side)
                        if situation == "behind":
                            player.x = enemy.x + side * 80
                        elif situation == "too_deep":
                            player.ground_y += 32.01
                        elif situation == "above":
                            player.jump_height = 200
                        else:
                            player.ground_y += 32
                        self.assertEqual(enemy.try_hit(player), situation == "depth_boundary")
                        self.assertEqual(enemy.has_hit, situation == "depth_boundary")

    def test_four_mixed_attacks_apply_each_enemys_damage_once_in_the_same_update(self):
        world = World(rng=random.Random(38))
        world.stage_index = 3
        world.enemies = [at_frame("clubs" if index % 2 == 0 else "slam",
                                  3 if index % 2 == 0 else 5,
                                  side=-1 if index < 2 else 1)[1] for index in range(4)]
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 340)  # 500 - 30 - 50 - 30 - 50.
        self.assertTrue(all(enemy.has_hit for enemy in world.enemies))
        self.assertEqual(len(world.effects), 4)
        advance(world, 0.1)
        self.assertEqual(world.player.hp, 340)

    def test_interruptions_end_damage_and_fall_instead_of_leaving_a_floating_enemy(self):
        for interruption in ("hit", "death", "knockback", "player_death", "car"):
            with self.subTest(interruption=interruption):
                player, enemy = at_frame("slam", 2)
                if interruption == "hit":
                    enemy.take_damage(10)
                elif interruption == "death":
                    enemy.take_damage(200)
                elif interruption == "knockback":
                    enemy.knockback(player.x, player.ground_y)
                elif interruption == "player_death":
                    player.take_damage(500)
                else:
                    enemy.hit_by_car(1)
                enemy.cooldown = 10  # Inspect the cancellation without another attack.
                for _ in range(180):
                    enemy.update(config.FIXED_DT, player)
                    self.assertIsNone(enemy.attack_box)
                    self.assertEqual(enemy.sprite_image, config.ENEMY02_IMAGE)
                self.assertEqual(enemy.jump_height, 0)

    def test_city_strong_hits_use_enemy02_hit_art_until_recovery(self):
        for index in (2, 3):
            for action, move in STRONG_MOVES.items():
                for side in (-1, 1):
                    with self.subTest(stage=index, action=action, side=side):
                        world = World(rng=random.Random(23))
                        world.select_stage(index)
                        world.stage.traffic = None
                        world.player.invincible = True
                        world.player.facing = side
                        enemy = spawn_encounter(world, 1)[0]
                        enemy.x = enemy.previous_x = world.player.x + side * 80
                        enemy.ground_y = enemy.previous_ground_y = world.player.ground_y
                        enemy.animation.set_state("HIT")
                        enemy.cooldown = 100
                        strike(world, enemy, action)
                        remaining = enemy.max_hp - move.damage
                        self.assertEqual((enemy.hp, enemy.state), (remaining, "STRONG_HIT"))
                        self.assertEqual((enemy.sprite_image, enemy.animation.row),
                                         (config.ENEMY02_IMAGE, 6))
                        frames = set()
                        for _ in range(360):  # W's wait slows the reaction clock to 0.2x.
                            if enemy.state != "STRONG_HIT":
                                break
                            self.assertEqual((enemy.sprite_image, enemy.animation.row),
                                             (config.ENEMY02_IMAGE, 6))
                            frames.add(enemy.animation.frame)
                            world.step(config.FIXED_DT)
                        expected_frames = set(range(8))
                        self.assertEqual(frames, expected_frames)
                        self.assertEqual((enemy.hp, enemy.state, enemy.sprite_image),
                                         (remaining, "IDLE", config.ENEMY02_IMAGE))

    def test_city_car_hits_the_new_enemy_and_preserves_its_fall_pose(self):
        world = World(rng=random.Random(12))
        world.stage_index = 2
        world.player.ground_y = config.CAR_GROUND_Y
        world.player.invincible = True
        enemy = spawn_encounter(world, 1)[0]
        enemy.x = enemy.previous_x = world.player.x
        enemy.ground_y = enemy.previous_ground_y = config.CAR_GROUND_Y
        world.stage.traffic = Traffic()  # Explicit legacy reaction fixture.
        world.stage.traffic.car = Car(world.player.x, 1, 1400)
        world.step(config.FIXED_DT)
        self.assertEqual((world.player.hp, enemy.hp, enemy.state), (0, 0, "CAR_HIT"))
        self.assertEqual((enemy.sprite_image, enemy.animation.row), (config.ENEMY02_IMAGE, 7))
        advance(world, 1)
        self.assertEqual((enemy.state, enemy.animation.row, enemy.animation.frame), ("DEAD", 7, 7))

    def test_leap_planning_cannot_change_other_enemies_or_later_spawn_sides(self):
        first, second = (World(rng=random.Random(91)) for _ in range(2))
        for world in (first, second):
            world.stage_index = 3
            spawn_encounter(world)
        enemy = first.enemies[0]
        other_state = first.enemies[1].rng.getstate()
        for _ in range(8):
            enemy.x = enemy.previous_x = first.player.x + 400
            enemy.cooldown = enemy.leap_cooldown = 0
            self.assertTrue(enemy.start_leap(first.player))
            while enemy.leap_phase is not None:
                enemy.update(config.FIXED_DT, first.player)
        self.assertEqual(first.enemies[1].rng.getstate(), other_state)
        batches = [world.spawner.spawn(4, 0) for world in (first, second)]
        self.assertEqual([(actor.x, actor.ground_y, actor.attack_speed) for actor in batches[0]],
                         [(actor.x, actor.ground_y, actor.attack_speed) for actor in batches[1]])

    def test_loading_and_revisits_pause_the_selected_attack_and_its_private_rng(self):
        world = World(rng=random.Random(83))
        world.stage_index = 3
        enemy = spawn_encounter(world, 1)[0]
        enemy.start_attack()
        enemy.animation.elapsed = 2.05 / enemy.attack_fps
        enemy.update(0, world.player)
        snapshot = enemy.attack_kind, enemy.animation.elapsed, enemy.jump_height, enemy.rng.getstate()
        world.stage.arrows_visible = True
        world.player.x, world.player.vx = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN, config.RUN_SPEED
        self.assertTrue(world.try_stage_transition())
        advance(world, 2)
        self.assertEqual(world.stage_index, 4)
        advance(world, 0.2)
        world.select_stage(3)
        self.assertIs(world.enemies[0], enemy)
        self.assertEqual((enemy.attack_kind, enemy.animation.elapsed, enemy.jump_height,
                          enemy.rng.getstate()), snapshot)
        self.assertEqual(world.spawner.spawned_count, 1)

    def test_new_attack_ai_and_damage_results_are_identical_across_render_rates(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world = World(rng=random.Random(37))
            world.stage_index = 3
            world.player.invincible = True
            spawn_encounter(world)
            advance(world, 6, fps)
            outcomes.append([(enemy.x, enemy.ground_y, enemy.jump_height, enemy.state,
                              enemy.attack_kind, enemy.animation.elapsed, enemy.has_hit,
                              enemy.rng.getstate()) for enemy in world.enemies])
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))

    def test_four_new_enemies_keep_their_large_sprite_padding_at_city_corners(self):
        for index in (2, 3):
            for x in (config.PLAYER_BOUNDARY_PADDING, config.WORLD_WIDTH - config.PLAYER_BOUNDARY_PADDING):
                with self.subTest(stage=index, x=x):
                    world = World(rng=random.Random(14))
                    world.stage_index = index
                    world.stage.traffic = None
                    world.player.x = x
                    world.player.invincible = True
                    spawn_encounter(world)
                    advance(world, 4)
                    for enemy in world.enemies:
                        self.assertTrue(world.stage.walkable.contains(enemy.x, enemy.ground_y, 128))
                        self.assertFalse(bodies_overlap(world.player, enemy))


if __name__ == "__main__":
    unittest.main()
