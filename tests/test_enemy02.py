import random
import unittest
from unittest.mock import Mock, patch

import config
from collision import bodies_overlap
from counter import can_counter
from enemy import Enemy
from enemy02 import Enemy02
from player import Player
from tests.helpers import advance, tap
from tests.test_counters import follow_up
from traffic import Car
from world import World


def at_frame(kind, frame, *, side=1):
    player = Player()
    enemy = Enemy02(player.x + side * 80, -side)
    enemy.rng = Mock()
    enemy.rng.choice.return_value = kind
    enemy.start_attack()
    enemy.animation.elapsed = (frame + 0.05) / enemy.attack_fps
    enemy.update(0, player)
    return player, enemy


class Enemy02Tests(unittest.TestCase):
    def test_only_city_maps_use_the_new_type_and_all_maps_keep_four_enemies_after_f5(self):
        world = World(rng=random.Random(51))
        for _ in range(2):
            for stage in world.stages:
                expected = Enemy02 if stage.image_name in ("cityStage-1.png", "cityStage-2.png") else Enemy
                self.assertEqual(len(stage.enemies), 4)
                self.assertEqual(stage.spawner.spawned_count, 4)
                self.assertTrue(all(type(enemy) is expected for enemy in stage.enemies))
                for enemy in stage.enemies:
                    self.assertEqual(enemy.hp, 200)
                    self.assertTrue(stage.spawn_area.contains(enemy.x, enemy.ground_y,
                                                              enemy.boundary_padding))
                    self.assertEqual(enemy.facing, 1 if enemy.x < config.START_X else -1)
            world.controls.press("restart")
            world.update(config.FIXED_DT)
            world.controls.release("restart")

    def test_ai_randomizes_once_at_each_attack_start_and_keeps_the_choice_until_recovery(self):
        rng = Mock(wraps=random.Random(9))
        player = Player()
        enemy = Enemy02(player.x + 80, -1, rng=rng)
        choices = set()
        for attack in range(64):
            enemy.cooldown = 0
            enemy.update(config.FIXED_DT, player)
            self.assertEqual(enemy.state, "ATTACK")
            self.assertEqual(rng.choice.call_count, attack + 1)
            kind, row, damage = enemy.attack_kind, enemy.animation.row, enemy.attack_damage
            self.assertIn((kind, row, damage), (("clubs", 4, 60), ("slam", 5, 80)))
            choices.add(kind)
            for _ in range(160):
                enemy.update(config.FIXED_DT, player)
                self.assertEqual((enemy.attack_kind, enemy.attack_damage), (kind, damage))
                self.assertEqual(rng.choice.call_count, attack + 1)
                if enemy.state != "ATTACK":
                    break
                self.assertEqual(enemy.animation.row, row)
            self.assertEqual((enemy.state, enemy.jump_height), ("IDLE", 0))
        self.assertEqual(choices, {"clubs", "slam"})

    def test_dual_club_motion_deals_sixty_once_across_both_swings(self):
        for side in (-1, 1):
            player, enemy = at_frame("clubs", 2, side=side)
            self.assertIsNone(enemy.attack_box)
            self.assertFalse(enemy.try_hit(player))
            for frame in (3, 4, 5, 6, 7):
                enemy.animation.elapsed = (frame + 0.05) / enemy.attack_fps
                self.assertEqual(enemy.try_hit(player), frame == 3)
                self.assertEqual(player.hp, 440)
            enemy.start_attack()
            enemy.animation.elapsed = 4.05 / enemy.attack_fps
            self.assertTrue(enemy.try_hit(player))
            self.assertEqual(player.hp, 380)

    def test_jump_uses_real_source_lift_and_hits_only_after_landing_for_eighty(self):
        for frame, height in enumerate((0, 0, 36, 19.5, 0, 0, 0, 0)):
            with self.subTest(frame=frame):
                player, enemy = at_frame("slam", frame)
                self.assertEqual(enemy.jump_height, height)
                self.assertEqual(enemy.y, enemy.ground_y + height)
                self.assertEqual(enemy.body.bottom, config.GROUND_Y + height)
                self.assertEqual(enemy.try_hit(player), frame in (5, 6))
                self.assertEqual(player.hp, 420 if frame in (5, 6) else 500)
        player, enemy = at_frame("slam", 5)
        self.assertTrue(enemy.try_hit(player))
        enemy.animation.elapsed = 6.05 / enemy.attack_fps
        self.assertFalse(enemy.try_hit(player))
        self.assertEqual(player.hp, 420)

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
        for index, enemy in enumerate(world.enemies):
            enemy.x = world.player.x + (-80 if index < 2 else 80)
            enemy.previous_x = enemy.x
            enemy.ground_y = enemy.previous_ground_y = world.player.ground_y
            enemy.facing = 1 if index < 2 else -1
            enemy.rng = Mock()
            enemy.rng.choice.return_value = "clubs" if index % 2 == 0 else "slam"
            enemy.start_attack()
            frame = 3 if enemy.attack_kind == "clubs" else 5
            enemy.animation.elapsed = (frame + 0.05) / enemy.attack_fps
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 220)  # 500 - 60 - 80 - 60 - 80.
        self.assertTrue(all(enemy.has_hit for enemy in world.enemies))
        self.assertEqual(len(world.effects), 4)
        advance(world, 0.1)
        self.assertEqual(world.player.hp, 220)

    def test_counter_window_excludes_the_airborne_frames_of_the_slam(self):
        for frame, allowed in ((0, False), (1, True), (2, False), (3, False), (4, True), (6, False)):
            player, enemy = at_frame("slam", frame)
            self.assertEqual(can_counter(player, enemy), allowed)

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
                for _ in range(30):
                    enemy.update(config.FIXED_DT, player)
                    self.assertIsNone(enemy.attack_box)
                    self.assertEqual(enemy.sprite_image, config.ENEMY02_IMAGE)
                self.assertEqual(enemy.jump_height, 0)

    def test_counter_reactions_and_lethal_poses_keep_the_new_enemy_sheet(self):
        for key in "hjkl":
            for hp in (200, 40):
                with self.subTest(key=key, hp=hp), patch.object(config, "ENEMIES_PER_STAGE", 0):
                    world = World()
                    world.stage_index = 3
                    _, enemy = at_frame("clubs", 1)
                    enemy.hp = hp
                    world.enemies = [enemy]
                    world.controls.press(f"counter_{key}")
                    world.step(config.FIXED_DT)
                    self.assertIsNotNone(world.counter)
                    follow_up(world)
                    for _ in range(360):
                        self.assertEqual(enemy.sprite_image, config.ENEMY02_IMAGE)
                        world.step(config.FIXED_DT)
                        if world.counter is None and enemy.counter_move is None:
                            break
                    self.assertIsNone(world.counter)
                    self.assertIsNone(enemy.counter_move)
                    self.assertEqual(enemy.hp, max(0, hp - 80))
                    self.assertEqual(enemy.state, "IDLE" if enemy.alive else "DEAD")
                    if not enemy.alive:
                        self.assertEqual((enemy.animation.row, enemy.animation.frame), (7, 7))
                        advance(world, 3.5)
                        self.assertAlmostEqual(enemy.opacity, 0.5)
                        advance(world, 0.5)
                        self.assertNotIn(enemy, world.enemies)

    def test_city_car_hits_the_new_enemy_and_preserves_its_fall_pose(self):
        world = World(rng=random.Random(12))
        world.stage_index = 2
        world.player.ground_y = config.CAR_GROUND_Y
        world.player.invincible = True
        enemy = world.enemies[0]
        enemy.x = enemy.previous_x = world.player.x
        enemy.ground_y = enemy.previous_ground_y = config.CAR_GROUND_Y
        world.stage.traffic.car = Car(world.player.x, 1, 1400)
        world.step(config.FIXED_DT)
        self.assertEqual((world.player.hp, enemy.hp, enemy.state), (0, 0, "CAR_HIT"))
        self.assertEqual((enemy.sprite_image, enemy.animation.row), (config.ENEMY02_IMAGE, 7))
        advance(world, 1)
        self.assertEqual((enemy.state, enemy.animation.row, enemy.animation.frame), ("DEAD", 7, 7))

    def test_combat_randomness_is_private_and_cannot_change_later_spawn_sides(self):
        first, second = (World(rng=random.Random(91)) for _ in range(2))
        for world in (first, second):
            world.stage_index = 3
        enemy = first.enemies[0]
        other_state = first.enemies[1].rng.getstate()
        for _ in range(64):
            enemy.start_attack()
        self.assertEqual(first.enemies[1].rng.getstate(), other_state)
        batches = [world.spawner.spawn(4, 0) for world in (first, second)]
        self.assertEqual([(actor.x, actor.ground_y, actor.attack_speed) for actor in batches[0]],
                         [(actor.x, actor.ground_y, actor.attack_speed) for actor in batches[1]])

    def test_loading_and_revisits_pause_the_selected_attack_and_its_private_rng(self):
        world = World(rng=random.Random(83))
        world.stage_index = 3
        enemy = world.enemies[0]
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
        tap(world.controls, "stage_4")
        world.update(1 / 60)
        self.assertIs(world.enemies[0], enemy)
        self.assertEqual((enemy.attack_kind, enemy.animation.elapsed, enemy.jump_height,
                          enemy.rng.getstate()), snapshot)
        self.assertEqual(world.spawner.spawned_count, 4)

    def test_new_attack_ai_and_damage_results_are_identical_across_render_rates(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world = World(rng=random.Random(37))
            world.stage_index = 3
            world.player.invincible = True
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
                    advance(world, 4)
                    for enemy in world.enemies:
                        self.assertTrue(world.stage.walkable.contains(enemy.x, enemy.ground_y, 128))
                        self.assertFalse(bodies_overlap(world.player, enemy))


if __name__ == "__main__":
    unittest.main()
