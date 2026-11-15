import random
import unittest

import config
from collision import bodies_overlap, resolve_bodies
from combat import MOVES
from enemy import Enemy
from spawn_manager import SpawnManager
from tests.helpers import advance, tap
from world import World


class EnemyTests(unittest.TestCase):
    def test_requested_batches_spawn_randomly_at_both_map_boundaries(self):
        spawner = SpawnManager(rng=random.Random(42))
        spawned = spawner.spawn(9, 3)
        boundaries = {config.ENEMY_BOUNDARY_PADDING, config.WORLD_WIDTH - config.ENEMY_BOUNDARY_PADDING}
        self.assertEqual({enemy.x for enemy in spawned}, boundaries)
        self.assertEqual(len({id(enemy) for enemy in spawned}), 9)
        self.assertEqual(spawner.spawned_count, 9)
        for index, enemy in enumerate(spawned):
            self.assertEqual(enemy.spawned_at, 3)
            self.assertEqual(enemy.facing, 1 if enemy.x < config.START_X else -1)
            self.assertEqual(enemy.hp, 200)
            self.assertEqual(enemy.run_speed, config.ENEMY_RUN_SPEEDS[index % 4])
        next_batch = spawner.spawn(2, 5)
        self.assertEqual([enemy.run_speed for enemy in next_batch], [420, 480])
        self.assertEqual(spawner.spawned_count, 11)

    def test_automatic_encounter_tracks_the_player(self):
        world = World(rng=random.Random(42))
        self.assertEqual(len(world.enemies), 4)
        enemy = world.enemies[0]
        world.enemies = [enemy]  # Isolate this actor's change of pursuit direction.
        enemy.x = 600
        world.player.x = 200
        # A committed attack finishes before the next chase direction is chosen.
        advance(world, 1)
        self.assertEqual(enemy.facing, -1)
        self.assertLess(enemy.vx, 0)

    def test_each_number_selects_its_stage_without_spawning_more_enemies(self):
        world = World(rng=random.Random(42))
        for number in range(1, 11):
            with self.subTest(number=number):
                action = f"stage_{number}"
                world.controls.press(action)
                world.update(1 / 60)
                self.assertEqual(world.stage_index, number - 1)
                self.assertEqual(world.player.x, config.START_X)
                self.assertFalse(world.stage_loading)
                enemies = list(world.enemies)
                self.assertEqual(len(enemies), 4)
                world.player.x = 500
                world.controls.press(action)
                world.update(0)
                self.assertEqual(world.player.x, 500)
                tap(world.controls, action)
                world.update(1 / 60)
                self.assertEqual(world.enemies, enemies)
                self.assertEqual(world.spawner.spawned_count, 4)
                self.assertFalse(world.controls.pressed)

    def test_simultaneous_numbers_select_only_the_latest_pressed_stage(self):
        world = World()
        world.controls.press("stage_2")
        world.controls.press("stage_5")
        world.update(1 / 60)
        self.assertEqual(world.stage_index, 4)
        tap(world.controls, "stage_5")
        tap(world.controls, "stage_2")
        world.update(1 / 60)
        self.assertEqual(world.stage_index, 1)
        self.assertTrue(all(stage.spawner.spawned_count == 4 for stage in world.stages))
        self.assertFalse(world.controls.pressed)

    def test_stage_selection_works_while_attacking_or_hit_without_healing(self):
        for action in (None, "combat_a", "hit"):
            with self.subTest(action=action):
                world = World()
                if action == "hit":
                    world.player.take_damage(20)
                elif action is not None:
                    world.player.start_move(MOVES[action], 1)
                player, hp, state = world.player, world.player.hp, world.player.state
                world.controls.press("stage_3")
                world.update(1 / 60)
                self.assertEqual(world.stage_index, 2)
                self.assertIs(world.player, player)
                self.assertEqual((player.hp, player.state), (hp, state))
                self.assertEqual(len(world.enemies), 4)

    def test_death_discards_stage_presses_and_restart_creates_fresh_encounters(self):
        world = World()
        old_enemies = [enemy for stage in world.stages for enemy in stage.enemies]
        world.player.take_damage(500)
        for _ in range(2):
            tap(world.controls, "stage_9")
            advance(world, 1)
            self.assertEqual(world.stage_index, 0)
            self.assertNotIn("stage_9", world.controls.pressed)
        tap(world.controls, "stage_9")
        world.controls.press("restart")
        world.update(1 / 60)
        self.assertEqual((world.stage_index, world.player.hp), (0, 500))
        for stage in world.stages:
            self.assertEqual(len(stage.enemies), 4)
            self.assertEqual(stage.spawner.spawned_count, 4)
            self.assertTrue(all(enemy not in old_enemies and enemy.hp == 200
                                for enemy in stage.enemies))
        self.assertFalse(world.controls.pressed)

    def test_every_stage_has_four_independent_random_boundary_enemies(self):
        sides = set()
        for seed in range(8):
            world = World(rng=random.Random(seed))
            all_enemies = []
            for stage in world.stages:
                self.assertEqual(len(stage.enemies), 4)
                self.assertEqual(stage.spawner.spawned_count, 4)
                self.assertEqual([enemy.run_speed for enemy in stage.enemies],
                                 list(config.ENEMY_RUN_SPEEDS))
                for enemy in stage.enemies:
                    sides.add(enemy.facing)
                    self.assertEqual(enemy.x, enemy.boundary_padding if enemy.facing > 0
                                     else config.WORLD_WIDTH - enemy.boundary_padding)
                    self.assertTrue(stage.spawn_area.contains(enemy.x, enemy.ground_y,
                                                              enemy.boundary_padding))
                    self.assertEqual((enemy.hp, enemy.spawned_at), (200, 0))
                all_enemies.extend(stage.enemies)
            self.assertEqual(len({id(enemy) for enemy in all_enemies}), 40)
            self.assertEqual(len({enemy.attack_speed for enemy in all_enemies}), 40)
        self.assertEqual(sides, {-1, 1})

    def test_defeated_encounter_does_not_respawn_when_revisiting_a_stage(self):
        world = World()
        for enemy in world.enemies:
            enemy.take_damage(200)
        advance(world, 5)
        self.assertEqual(world.enemies, [])
        for number in (2, 1, 2, 1):
            tap(world.controls, f"stage_{number}")
            world.update(1 / 60)
        self.assertEqual(world.stage_index, 0)
        self.assertEqual(world.enemies, [])
        self.assertEqual(world.spawner.spawned_count, 4)

    def test_shortcut_cancels_loading_and_preserves_airborne_player_state(self):
        world = World()
        world.stage_index = 1
        world.stage.arrows_visible = True
        player = world.player
        player.x, player.vx = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN, config.RUN_SPEED
        player.hp, player.invincible = 420, True
        player.ground_y, player.ground_vy = 145, 80
        player.jump_height, player.vy, player.jump_count = 140, 300, 2
        player.animation.set_state("JUMP")
        player.animation.elapsed = 0.2
        self.assertTrue(world.try_stage_transition())
        self.assertTrue(world.stage_loading)
        world.controls.press("stage_10")
        world.update(0)
        self.assertIs(world.player, player)
        self.assertEqual(world.stage_index, 9)
        self.assertFalse(world.stage_loading)
        self.assertEqual((world.stage_loading_remaining, world.accumulator), (0, 0))
        self.assertEqual((player.x, player.ground_y, player.ground_vy), (config.START_X, 116, 0))
        self.assertEqual((player.hp, player.invincible, player.vx, player.jump_height,
                          player.vy, player.jump_count, player.animation.elapsed),
                         (420, True, config.RUN_SPEED, 140, 300, 2, 0.2))
        advance(world, 2.1)
        self.assertEqual(world.stage_index, 9)

    def test_shortcut_releases_a_carried_enemy_before_changing_scenes(self):
        world = World()
        enemy = world.enemies[0]
        enemy.x, enemy.ground_y, enemy.facing = world.player.x + 80, 100, -1
        enemy.animation.set_state("ATTACK")
        enemy.animation.elapsed = 2 / enemy.attack_fps
        world.controls.press("counter_j")
        world.step(config.FIXED_DT)
        advance(world, 0.4)
        self.assertIsNotNone(world.counter)
        self.assertTrue(world.counter.holding)
        world.controls.press("stage_6")
        world.update(1 / 60)
        self.assertEqual(world.stage_index, 5)
        self.assertIsNone(world.counter)
        self.assertIsNone(world.player.counter_move)
        self.assertIsNone(enemy.counter_move)
        self.assertEqual(enemy.jump_height, 0)
        self.assertEqual(world.player.boundary_padding, config.PLAYER_BOUNDARY_PADDING)
        self.assertIn(enemy, world.stages[0].enemies)
        self.assertNotIn(enemy, world.enemies)

    def test_shortcut_resolves_a_returning_scene_enemy_at_the_arrival_position(self):
        world = World()
        enemy = world.stages[1].enemies[0]
        enemy.x = enemy.previous_x = config.START_X
        enemy.ground_y = enemy.previous_ground_y = config.GROUND_Y
        world.controls.press("stage_2")
        world.update(1 / 60)
        self.assertEqual(world.stage_index, 1)
        self.assertTrue(all(not bodies_overlap(world.player, actor) for actor in world.enemies))
        self.assertEqual(world.player.previous_x, world.player.x)
        self.assertTrue(world.stage.walkable.contains(world.player.x, world.player.ground_y,
                                                      world.player.boundary_padding))

    def test_distant_enemies_keep_independent_ai_before_melee_spacing(self):
        world = World()
        world.enemies = [Enemy(500), Enemy(500)]
        advance(world, 0.5)
        self.assertEqual(world.enemies[0].x, world.enemies[1].x)
        self.assertTrue(world.enemies[0].body.overlaps(world.enemies[1].body))
        world.enemies[0].animation.elapsed = 99
        self.assertNotEqual(world.enemies[0].animation.elapsed,
                            world.enemies[1].animation.elapsed)

    def test_body_blocks_player_but_can_be_jumped_over(self):
        world = World()
        world.enemies = [Enemy(config.START_X + 100, facing=-1)]
        world.controls.press("right")
        world.controls.press("left_shift")
        advance(world, 0.2)
        self.assertFalse(bodies_overlap(world.player, world.enemies[0]))
        self.assertLess(world.player.x, world.enemies[0].x)
        world.player.y = config.GROUND_Y + config.ENEMY_HEIGHT + 40
        world.player.vy = 300
        advance(world, 0.5)
        self.assertGreater(world.player.x, world.enemies[0].x)

    def test_crowd_and_boundary_collisions_do_not_leave_penetration(self):
        for x in (config.PLAYER_HALF_WIDTH, config.START_X,
                  config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH):
            world = World()
            world.player.x = world.player.previous_x = x
            world.enemies = [Enemy(x, 1), Enemy(x, -1), Enemy(x, 1), Enemy(x, -1)]
            resolve_bodies(world.player, world.enemies)
            self.assertGreaterEqual(world.player.x, config.PLAYER_HALF_WIDTH)
            self.assertLessEqual(world.player.x, config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)
            for enemy in world.enemies:
                self.assertFalse(bodies_overlap(world.player, enemy))
                self.assertGreaterEqual(enemy.x, config.ENEMY_HALF_WIDTH)
                self.assertLessEqual(enemy.x, config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH)


if __name__ == "__main__":
    unittest.main()
