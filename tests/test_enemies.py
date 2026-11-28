import random
import unittest

import config
from collision import bodies_overlap, resolve_bodies
from combat import MOVES
from enemy import Enemy
from enemy02 import Enemy02
from ar_soldier import ARSoldier
from sniper import Sniper
from projectiles import PlayerPistolBullet
from spawn_manager import SpawnManager
from sword_enemy import SwordEnemy
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

    def test_first_wave_has_four_native_enemies_at_start_entry_and_restart(self):
        world = World()
        for index in range(len(world.stages)):
            world.select_stage(index)
            if index:
                advance(world, 1 - config.FIXED_DT, fps=120)
                self.assertEqual(world.enemies, [])
                world.update(config.FIXED_DT)
            wave = list(world.enemies)
            expected = [world.spawner.enemy_type] * 4
            if index in (2, 3):
                expected = [Enemy02, Enemy02, SwordEnemy, SwordEnemy]
            elif index == 11:
                expected = [ARSoldier, ARSoldier, Sniper, Sniper]
            self.assertCountEqual([type(enemy) for enemy in wave], expected)
            advance(world, 0.2)
            world.select_stage(index)
            advance(world, 1)
            self.assertEqual(world.enemies[:4], wave)
            self.assertEqual(world.spawner.spawned_count, 8 if index < 4 else 4)
        world.controls.press("restart")
        world.update(1 / 60)
        self.assertEqual((world.stage_index, world.player.hp, len(world.enemies)), (0, 500, 4))
        self.assertTrue(all(not stage.enemies and stage.spawner.spawned_count == 0
                            for stage in world.stages[1:]))

    def test_alley_and_city_repeat_their_first_wave_after_one_second_then_half_a_second(self):
        world = World(rng=random.Random(42))
        for index in (0, 1, 2, 3):
            with self.subTest(stage=index):
                world.reset(stage_index=index)
                world.player.invincible = True
                expected = [Enemy] * 4 if index < 2 else [Enemy02, Enemy02, SwordEnemy, SwordEnemy]
                self.assertCountEqual([type(enemy) for enemy in world.enemies], expected)
                for delay, before in ((1.0, 4), (0.5, 8)):
                    advance(world, delay - config.FIXED_DT, fps=120)
                    self.assertEqual(len(world.enemies), before)
                    world.update(config.FIXED_DT)
                    self.assertEqual(len(world.enemies), before + 4)
                    self.assertCountEqual([type(enemy) for enemy in world.enemies[-4:]], expected)
                advance(world, 2)
                self.assertEqual(world.spawner.spawned_count, 12)

    def test_alley_reinforcement_timer_pauses_off_map_and_restarts_on_retry(self):
        world = World()
        advance(world, 0.75)
        world.select_stage(2)
        advance(world, 3)
        self.assertEqual((world.stages[0].spawner.spawned_count, world.spawner.spawned_count), (4, 12))
        world.select_stage(0)
        advance(world, 0.25)
        self.assertEqual(world.spawner.spawned_count, 8)
        world.retry_current_map()
        self.assertEqual(world.spawner.spawned_count, 4)
        advance(world, 0.5)
        self.assertEqual(world.spawner.spawned_count, 4)
        advance(world, 1)
        self.assertEqual(world.spawner.spawned_count, 12)

    def test_requested_encounter_tracks_the_player(self):
        world = World(rng=random.Random(42))
        world.controls.press("spawn_4")
        world.update(1 / 60)
        self.assertEqual(len(world.enemies), 8)
        enemy = world.enemies[4]
        world.enemies = [enemy]  # Isolate this actor's change of pursuit direction.
        enemy.x = 600
        world.player.x = 200
        # A committed attack finishes before the next chase direction is chosen.
        advance(world, 1)
        self.assertEqual(enemy.facing, -1)
        self.assertLess(enemy.vx, 0)

    def test_each_number_spawns_its_count_once_until_released_and_never_changes_stage(self):
        for number in range(1, 10):
            with self.subTest(number=number):
                world = World(rng=random.Random(42))
                action = f"spawn_{number}"
                world.controls.press(action)
                world.update(1 / 60)
                self.assertEqual(world.stage_index, 0)
                self.assertEqual(world.player.x, config.START_X)
                self.assertFalse(world.stage_loading)
                enemies = list(world.enemies)
                self.assertEqual(len(enemies), 4 + number)
                world.controls.press(action)
                advance(world, 0.1)
                self.assertEqual(len(world.enemies), 4 + number)
                tap(world.controls, action)
                world.update(1 / 60)
                self.assertEqual(len(world.enemies), 4 + number * 2)
                self.assertTrue(all(enemy in world.enemies for enemy in enemies))
                self.assertEqual(world.spawner.spawned_count, 4 + number * 2)
                self.assertFalse(world.controls.pressed)

    def test_simultaneous_numbers_add_their_counts_without_a_four_enemy_limit(self):
        world = World()
        world.controls.press("spawn_2")
        world.controls.press("spawn_5")
        world.update(1 / 60)
        self.assertEqual(len(world.enemies), 11)
        tap(world.controls, "spawn_9")
        world.update(1 / 60)
        self.assertEqual((world.stage_index, len(world.enemies), world.spawner.spawned_count), (0, 20, 20))
        self.assertFalse(world.controls.pressed)

    def test_numeric_spawns_work_while_attacking_or_hit_without_resetting_the_player(self):
        for action in (None, "combat_a", "hit"):
            with self.subTest(action=action):
                world = World()
                if action == "hit":
                    world.player.take_damage(20)
                elif action is not None:
                    world.player.start_move(MOVES[action], 1)
                player, hp, state = world.player, world.player.hp, world.player.state
                world.controls.press("spawn_3")
                world.update(1 / 60)
                self.assertEqual(world.stage_index, 0)
                self.assertIs(world.player, player)
                self.assertEqual((player.hp, player.state), (hp, state))
                self.assertEqual(len(world.enemies), 7)

    def test_death_discards_spawn_presses_and_restart_requires_fresh_input(self):
        world = World()
        world.controls.press("spawn_2")
        world.update(1 / 60)
        old_enemies = list(world.enemies)
        world.player.take_damage(500)
        for _ in range(2):
            tap(world.controls, "spawn_9")
            advance(world, 1)
            self.assertEqual(world.stage_index, 0)
            self.assertEqual(world.spawner.spawned_count, 6)
            self.assertNotIn("spawn_9", world.controls.pressed)
        tap(world.controls, "spawn_9")
        world.controls.press("restart")
        world.update(1 / 60)
        self.assertEqual((world.stage_index, world.player.hp), (0, 500))
        for stage in world.stages[1:]:
            self.assertEqual(stage.enemies, [])
            self.assertEqual(stage.spawner.spawned_count, 0)
        self.assertFalse(world.controls.pressed)
        advance(world, 1)
        self.assertEqual(len(world.enemies), 8)
        tap(world.controls, "spawn_1")
        world.update(1 / 60)
        self.assertEqual(len(world.enemies), 9)
        self.assertNotIn(world.enemies[0], old_enemies)
        self.assertEqual((world.enemies[0].hp, world.enemies[0].run_speed), (200, 360))

    def test_manual_spawns_on_every_stage_have_independent_profiles_and_random_boundaries(self):
        sides = set()
        for seed in range(8):
            world = World(rng=random.Random(seed))
            all_enemies = []
            for index, stage in enumerate(world.stages):
                world.select_stage(index)
                if index:
                    advance(world, 1)
                tap(world.controls, "spawn_9")
                world.update(config.FIXED_DT)
                self.assertEqual(len(stage.enemies), 13)
                self.assertEqual(stage.spawner.spawned_count, 13)
                self.assertEqual([enemy.run_speed for enemy in stage.enemies[:4]],
                                 list(config.ENEMY_RUN_SPEEDS))
                for enemy in stage.enemies[4:]:
                    sides.add(enemy.facing)
                    distance_from_edge = min(enemy.x, config.WORLD_WIDTH - enemy.x)
                    if enemy.uses_ranged_spacing or isinstance(enemy, Sniper):
                        # AR peers spread before the first visible frame; their
                        # source edge/RNG profile must still be preserved.
                        self.assertIn(enemy.spawn_source, (("edge", -1), ("edge", 1)))
                        self.assertTrue(all(not bodies_overlap(enemy, other)
                                            for other in stage.enemies if other is not enemy))
                    else:
                        self.assertLessEqual(
                            distance_from_edge,
                            enemy.boundary_padding + max(config.ENEMY_RUN_SPEEDS) * config.FIXED_DT)
                    self.assertTrue(stage.spawn_area.contains(enemy.x, enemy.ground_y,
                                                              enemy.boundary_padding))
                    self.assertEqual((enemy.hp, enemy.spawned_at), (type(enemy).max_hp, world.elapsed))
                all_enemies.extend(stage.enemies[4:])
            total = 9 * len(world.stages)
            self.assertEqual(len({id(enemy) for enemy in all_enemies}), total)
            self.assertEqual(len({enemy.attack_speed for enemy in all_enemies}), total)
        self.assertEqual(sides, {-1, 1})

    def test_defeated_encounter_does_not_respawn_when_revisiting_a_stage(self):
        world = World()
        advance(world, 1.5)
        for enemy in world.enemies:
            enemy.take_damage(200)
        advance(world, 5)
        self.assertEqual(world.enemies, [])
        for number in (2, 1, 2, 1):
            world.select_stage(number - 1)
            advance(world, 0.1)
        self.assertEqual(world.stage_index, 0)
        self.assertEqual(world.enemies, [])
        self.assertEqual(world.spawner.spawned_count, 12)

    def test_fourth_defeat_opens_the_exit_even_with_extra_enemies_alive(self):
        world = World(rng=random.Random(42))
        world.player.invincible = True
        world.controls.press("spawn_sword_1")
        world.step(config.FIXED_DT)
        for enemy in world.enemies[:3]:
            enemy.take_damage(enemy.hp)
        advance(world, 6)
        self.assertEqual((world.stage.defeated_count, world.stage.arrow_sides), (3, ()))
        self.assertEqual(len(world.enemies), 10)
        world.select_stage(1)
        self.assertEqual((world.stage.defeated_count, world.stage.arrow_sides), (0, ()))
        world.select_stage(0)
        target = world.enemies[-1]
        target.x, target.ground_y = world.player.x + 200, world.player.ground_y
        target.hp = 1
        world.projectiles.append(PlayerPistolBullet(target.x, target.ground_y, 50, 1))
        world.step(config.FIXED_DT)
        self.assertFalse(target.alive)
        self.assertEqual((world.stage.defeated_count, world.stage.arrow_sides), (4, (1,)))
        self.assertTrue(world.enemies[0].alive)
        world.player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
        world.controls.press("right")
        world.step(config.FIXED_DT)
        self.assertEqual((world.stage_index, len(world.enemies), world.stage.arrow_sides), (1, 0, ()))
        advance(world, 1 - config.FIXED_DT, fps=120)
        self.assertEqual(world.enemies, [])
        world.update(config.FIXED_DT)
        self.assertEqual(len(world.enemies), 4)

    def test_auto_exits_connect_the_full_route_and_restart_resets_progress(self):
        world = World(rng=random.Random(17))
        for index, stage in enumerate(world.stages):
            self.assertIs(world.stage, stage)
            if index:
                advance(world, 1 - config.FIXED_DT, fps=120)
                self.assertEqual(stage.spawner.spawned_count, 0)
                world.update(config.FIXED_DT)
            self.assertEqual((len(world.enemies), stage.arrow_sides), (4, ()))
            for enemy in world.enemies:
                enemy.take_damage(enemy.hp)
            world.step(config.FIXED_DT)
            if index == len(world.stages) - 1:
                self.assertEqual(stage.arrow_sides, (-1,))
                break
            if stage.factory_gate is not None:
                self.assertTrue(world.opening_factory_exit)
                advance(world, config.FACTORY_GATE_DURATION + config.FIXED_DT, fps=120)
                self.assertFalse(world.stage_loading)
                world.player.x = stage.factory_doorway(world.player.x)[0]
                world.player.ground_y = stage.walkable.bounds[3]
                self.assertTrue(world.try_stage_transition())
                world.update(config.FACTORY_FADE_DURATION)
                world.update(config.FIXED_DT)
                continue
            self.assertEqual(stage.destination(1), index + 1)
            world.player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
            world.controls.press("right")
            self.assertTrue(world.try_stage_transition())
            if world.stage_loading:
                world.update(world.stage_loading_remaining)
                if world.stage_loading:
                    world.update(0)
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertEqual((world.stage_index, len(world.enemies)), (0, 4))
        self.assertTrue(all(stage.defeated_count == 0 and not stage.arrow_sides for stage in world.stages))

    def test_loading_discards_numeric_spawns_and_preserves_the_pending_destination(self):
        world = World()
        world.select_stage(1)
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
        world.controls.press("spawn_9")
        world.update(4.4)
        self.assertIs(world.player, player)
        self.assertEqual((world.stage_index, world.pending_stage_index), (1, 2))
        self.assertTrue(world.stage_loading)
        self.assertEqual(world.stages[2].spawner.spawned_count, 0)
        world.update(0.1)
        world.update(0)
        self.assertEqual(world.stage_index, 2)
        self.assertFalse(world.stage_loading)
        self.assertEqual(player.x, config.STAGE_ENTRY_MARGIN)
        self.assertEqual((player.hp, player.invincible, player.vx, player.jump_height,
                          player.vy, player.jump_count, player.animation.elapsed),
                         (420, True, config.RUN_SPEED, 140, 300, 2, 0.2))
        world.controls.press("spawn_9")  # Still held: do not replay the discarded input.
        world.update(config.FIXED_DT)
        self.assertEqual(len(world.enemies), 0)
        tap(world.controls, "cycle_spawn_enemy")
        tap(world.controls, "spawn_9")
        world.update(config.FIXED_DT)
        self.assertEqual(len(world.enemies), 9)
        advance(world, 1 - 2 * config.FIXED_DT, fps=120)
        self.assertEqual((world.stage_index, len(world.enemies)), (2, 13))
        self.assertTrue(all(type(enemy) is Enemy for enemy in world.enemies[:9]))
        self.assertCountEqual([type(enemy) for enemy in world.enemies[9:]],
                              [Enemy02, Enemy02, SwordEnemy, SwordEnemy])

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
