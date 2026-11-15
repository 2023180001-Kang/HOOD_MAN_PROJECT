import random
import unittest

import config
from combat import MOVES
from effects import DamageNumber, HitEffect
from enemy import Enemy
from tests.helpers import advance, clear_encounters, tap
from traffic import Car
from world import World


class CityStageTests(unittest.TestCase):
    def at_exit(self, index=1, side=1):
        world = clear_encounters(World())
        world.stage_index = index
        world.stage.arrows_visible = True
        world.player.x = (config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
                          if side > 0 else config.STAGE_EXIT_MARGIN)
        world.player.vx = side * config.RUN_SPEED
        world.controls.press("right" if side > 0 else "left")
        world.controls.press("left_shift")
        return world

    def test_ten_backgrounds_form_one_bidirectional_route_with_a_final_boundary(self):
        world = World()
        self.assertEqual([stage.image_name for stage in world.stages],
                         ["newStage.png", "newStage-2.png", "cityStage-1.png", "cityStage-2.png",
                          config.FACTORY_OUTSIDE_IMAGE, config.FACTORY_EXTERIOR_IMAGE,
                          "factoryInside-1.png", "factoryStage-2.png",
                          "labStage-1_1672x941.png", "labStage-2_1672x941.png"])
        for index, stage in enumerate(world.stages):
            stage.arrows_visible = True
            self.assertEqual(stage.destination(-1), index - 1 if index else None)
            self.assertEqual(stage.destination(1), index + 1 if index < len(world.stages) - 1 else None)

    def test_travel_inside_each_pair_preserves_motion_without_loading(self):
        for first in (0, 2, 4, 6, 8):
            for side in (-1, 1):
                with self.subTest(first=first, side=side):
                    world = self.at_exit(first if side > 0 else first + 1, side)
                    player = world.player
                    player.hp, player.invincible = 420, True
                    player.jump_height, player.vy, player.jump_count = 150, 300, 2
                    player.animation.set_state("JUMP")
                    player.animation.elapsed = 0.2
                    self.assertTrue(world.try_stage_transition())
                    self.assertFalse(world.stage_loading)
                    self.assertEqual(world.stage_index, first + 1 if side > 0 else first)
                    self.assertIs(world.player, player)
                    self.assertEqual((player.hp, player.invincible, player.jump_height,
                                      player.vy, player.jump_count, player.vx),
                                     (420, True, 150, 300, 2, side * config.RUN_SPEED))
                    self.assertEqual(player.animation.elapsed, 0.2)

    def test_city_loading_requires_an_open_exit_outward_motion_and_a_mobile_player(self):
        for blocked in ("hidden", "inward", "not_at_exit", "attack", "HIT", "DYING", "DEAD"):
            with self.subTest(blocked=blocked):
                world = self.at_exit()
                if blocked == "hidden":
                    world.stage.arrows_visible = False
                elif blocked == "inward":
                    world.player.vx = -config.RUN_SPEED
                elif blocked == "not_at_exit":
                    world.player.x = config.START_X
                elif blocked == "attack":
                    world.player.start_move(MOVES["combat_a"], 1)
                else:
                    world.player.animation.set_state(blocked)
                    if blocked in ("DYING", "DEAD"):
                        world.player.hp = 0
                self.assertFalse(world.try_stage_transition())
                self.assertFalse(world.stage_loading)
                self.assertEqual(world.stage_index, 1)

    def test_loading_freezes_all_gameplay_and_discards_one_shot_inputs(self):
        world = self.at_exit()
        player = world.player
        player.hp, player.invincible = 440, True
        player.jump_height, player.vy, player.jump_count = 120, 300, 2
        player.animation.set_state("JUMP")
        player.animation.elapsed = 0.2
        source = world.stage
        source.enemies.append(Enemy(1200))
        source.effects.append(HitEffect(1200, 180, 1))
        source.damage_numbers.append(DamageNumber(1200, 250, 10))
        destination = world.stages[2]
        destination.enemies.append(Enemy(1800))
        destination.effects.append(HitEffect(1800, 180, 1))
        world.camera.shake()
        before = (player.x, player.ground_y, player.jump_height, player.vy,
                  player.animation.elapsed, world.camera.shake_remaining)
        self.assertTrue(world.try_stage_transition())
        for key in ("jump", "combat_f", "invincibility", "stage_exits"):
            world.controls.press(key)
        advance(world, 1.9)
        self.assertTrue(world.stage_loading)
        self.assertEqual(world.stage_index, 1)
        self.assertEqual(world.elapsed, 0)
        self.assertEqual(before, (player.x, player.ground_y, player.jump_height, player.vy,
                                  player.animation.elapsed, world.camera.shake_remaining))
        for stage in (source, destination):
            self.assertEqual(stage.enemies[0].animation.elapsed, 0)
            self.assertEqual(stage.effects[0].elapsed, 0)
        self.assertEqual(source.damage_numbers[0].elapsed, 0)
        self.assertEqual(world.controls.pressed, {})
        world.update(0.1)
        self.assertFalse(world.stage_loading)
        self.assertEqual(world.stage_index, 2)
        self.assertIs(world.player, player)
        self.assertEqual((player.hp, player.invincible, player.jump_count, player.vy),
                         (440, True, 2, 300))
        self.assertEqual(len(destination.enemies), 1)
        self.assertFalse(destination.arrows_visible)
        world.update(1 / 60)
        self.assertIsNone(player.active_move)
        self.assertEqual(len(destination.enemies), 1)
        self.assertTrue(player.invincible)
        self.assertEqual(player.jump_count, 2)
        self.assertFalse(destination.arrows_visible)

    def test_loading_waits_two_seconds_of_real_dt_without_simulation_catchup(self):
        world = self.at_exit()
        world.update(config.MAX_FRAME_DT)
        self.assertTrue(world.stage_loading)
        self.assertEqual(world.accumulator, 0)
        self.assertEqual(world.elapsed, config.FIXED_DT)
        world.update(1.75)
        self.assertEqual(world.stage_loading_remaining, 0.25)
        world.update(0.249)
        self.assertEqual(world.stage_index, 1)
        self.assertTrue(world.stage_loading)
        world.update(0.001)
        self.assertEqual(world.stage_index, 2)
        self.assertFalse(world.stage_loading)
        self.assertEqual(world.player.x, config.STAGE_ENTRY_MARGIN)
        self.assertEqual(world.elapsed, config.FIXED_DT)
        self.assertEqual(world.accumulator, 0)
        world.update(1 / 60)
        self.assertAlmostEqual(world.player.x, config.STAGE_ENTRY_MARGIN + config.RUN_SPEED / 60)

    def test_loading_in_both_directions_preserves_jump_and_projects_destination_floor(self):
        for index, side, target in ((1, 1, 2), (2, -1, 1)):
            with self.subTest(index=index):
                world = self.at_exit(index, side)
                player = world.player
                player.ground_y = 116 if index == 1 else 145
                player.jump_height, player.vy, player.jump_count = 150, -100, 2
                player.animation.set_state("JUMP")
                player.animation.elapsed = 0.25
                self.assertTrue(world.try_stage_transition())
                self.assertEqual(world.pending_stage_index, target)
                world.update(config.STAGE_LOADING_DURATION)
                self.assertEqual(world.stage_index, target)
                self.assertEqual(player.x, config.STAGE_ENTRY_MARGIN if side > 0 else
                                 config.WORLD_WIDTH - config.STAGE_ENTRY_MARGIN)
                self.assertEqual(player.ground_y, 116)
                self.assertEqual((player.jump_height, player.vy, player.jump_count,
                                  player.animation.elapsed), (150, -100, 2, 0.25))
                self.assertEqual(player.previous_ground_y, 116)
                self.assertEqual(player.previous_x, player.x)
                self.assertFalse(world.try_stage_transition())

    def test_f5_cancels_loading_and_resets_all_stages(self):
        world = self.at_exit()
        for stage in world.stages:
            stage.arrows_visible = True
            stage.enemies.extend(stage.spawner.spawn(2, 0))
            stage.effects.append(HitEffect(500, 180, 1))
            stage.damage_numbers.append(DamageNumber(500, 250, 10))
        self.assertTrue(world.try_stage_transition())
        world.update(1)
        tap(world.controls, "restart")
        world.update(1 / 60)
        self.assertFalse(world.stage_loading)
        self.assertIsNone(world.pending_stage_index)
        self.assertEqual(world.stage_loading_remaining, 0)
        self.assertEqual(world.stage_index, 0)
        self.assertEqual(world.player.hp, 500)
        self.assertEqual(world.player.x, config.START_X)
        for stage in world.stages:
            self.assertFalse(stage.arrows_visible)
            self.assertEqual(len(stage.enemies), 4)
            self.assertEqual((stage.effects, stage.damage_numbers), ([], []))
            self.assertEqual(stage.spawner.spawned_count, 4)
        advance(world, 2.5)
        self.assertEqual(world.stage_index, 0)

    def test_new_city_maps_keep_feet_and_spawned_enemies_inside_their_floor(self):
        world = World()
        for index in (2, 3):
            world.stage_index = index
            area = world.stage.walkable
            for key in ("right", "up", "left_shift"):
                tap(world.controls, key)
            world.player.invincible = True
            advance(world, 1)
            for actor in (world.player, *world.enemies):
                self.assertTrue(area.contains(actor.x, actor.ground_y, actor.boundary_padding))
            self.assertEqual(len(world.enemies), 4)
        rates = [enemy.attack_speed for stage in world.stages for enemy in stage.enemies]
        self.assertEqual(len(set(rates)), len(rates))

    def test_city_one_spawns_only_on_sidewalk_at_both_edges_including_after_restart(self):
        world = World(rng=random.Random(42))
        for _ in range(2):
            stage = world.stages[2]
            enemies = stage.spawner.spawn(200, 0)
            self.assertEqual({enemy.x for enemy in enemies},
                             {config.ENEMY02_BOUNDARY_PADDING,
                              config.WORLD_WIDTH - config.ENEMY02_BOUNDARY_PADDING})
            for enemy in enemies:
                self.assertTrue(stage.spawn_area.contains(enemy.x, enemy.ground_y,
                                                          enemy.boundary_padding))
                self.assertGreaterEqual(enemy.ground_y, config.GROUND_Y)
                self.assertGreater(enemy.ground_y - config.CAR_GROUND_Y, config.CAR_DEPTH_TOLERANCE)
                self.assertIs(enemy.walkable, stage.walkable)
                self.assertEqual(enemy.hp, config.ENEMY_MAX_HP)
            for index, other in enumerate(world.stages):
                if index not in (2, 3):
                    self.assertIs(other.spawn_area, other.walkable)
            world.reset()

    def test_both_cities_start_with_four_enemies_on_the_pavement(self):
        world = World(rng=random.Random(32))
        for index, top in ((2, 148), (3, 116)):
            stage = world.stages[index]
            self.assertEqual(len(stage.enemies), 4)
            for enemy in stage.enemies:
                self.assertGreaterEqual(enemy.ground_y, 100)
                self.assertLessEqual(enemy.ground_y, top)
                self.assertIs(enemy.walkable, stage.walkable)

    def test_city_front_rows_do_not_step_below_the_pavement_when_the_player_is_on_it(self):
        for index in (2, 3):
            for side in (-1, 1):
                for player_y in (100, config.STAGE_WALKABLE_BOUNDS[index][3]):
                    with self.subTest(stage=index, side=side, player_y=player_y):
                        world = World(rng=random.Random(32))
                        world.stage_index = index
                        world.stage.traffic = None
                        world.player.ground_y = player_y
                        world.player.invincible = True
                        for number, enemy in enumerate(world.enemies):
                            enemy.x = enemy.previous_x = world.player.x + side * (220 + number * 5)
                            enemy.ground_y = enemy.previous_ground_y = 100
                            enemy.facing = -side
                        for _ in range(240):
                            world.step(config.FIXED_DT)
                            for enemy in world.enemies:
                                self.assertGreaterEqual(enemy.ground_y, 100 - 1e-8)
                                if enemy.target_ground_y is not None:
                                    self.assertGreaterEqual(enemy.target_ground_y, 100)
                        self.assertEqual(world.spawner.spawned_count, 4)

    def test_pavement_formations_can_still_follow_a_player_onto_the_road(self):
        world = World(rng=random.Random(32))
        world.stage_index = 2
        traffic = world.stage.traffic
        world.stage.traffic = None
        world.player.ground_y = 56
        world.player.invincible = True
        for number, enemy in enumerate(world.enemies):
            enemy.x = enemy.previous_x = world.player.x - (220 + number * 5)
            enemy.ground_y = enemy.previous_ground_y = 100
        advance(world, 2)
        victim = min(world.enemies, key=lambda enemy: enemy.ground_y)
        self.assertLessEqual(victim.ground_y, config.CAR_GROUND_Y + config.CAR_DEPTH_TOLERANCE)
        traffic.car = Car(victim.x, 1, 1400)
        world.stage.traffic = traffic
        world.step(config.FIXED_DT)
        self.assertEqual((victim.hp, victim.state), (0, "CAR_HIT"))

    def test_cars_at_spawn_edges_do_not_run_over_newly_summoned_sidewalk_enemies(self):
        for side in (-1, 1):
            with self.subTest(side=side):
                world = World(rng=random.Random(42))
                world.stage_index = 2
                world.player.ground_y = 124
                edge = (config.ENEMY_BOUNDARY_PADDING if side < 0 else
                        config.WORLD_WIDTH - config.ENEMY_BOUNDARY_PADDING)
                car = Car(edge, -side, config.CAR_SPEED_RANGE[1])
                world.stage.traffic.car = car
                world.step(config.FIXED_DT)
                self.assertEqual(len(world.enemies), 4)
                self.assertTrue(any(abs(enemy.x - car.x) < config.CAR_HALF_WIDTH
                                    for enemy in world.enemies))
                self.assertTrue(all(enemy.hp == config.ENEMY_MAX_HP and not enemy.car_hit
                                    for enemy in world.enemies))
                # Only spawning is restricted: enemies may still pursue onto the road.
                for enemy in world.enemies:
                    self.assertTrue(enemy.walkable.contains(enemy.x, config.CAR_GROUND_Y,
                                                            enemy.boundary_padding))

    def test_loading_finishes_at_the_same_time_at_different_render_rates(self):
        results = []
        for fps in (30, 60, 120, 144):
            world = self.at_exit()
            world.try_stage_transition()
            for _ in range(2 * fps - 1):
                world.update(1 / fps)
            self.assertTrue(world.stage_loading)
            self.assertEqual(world.stage_index, 1)
            world.update(1 / fps)
            self.assertFalse(world.stage_loading)
            results.append((world.stage_index, world.player.x, world.player.vx,
                            world.player.jump_height, world.elapsed, world.accumulator))
        self.assertTrue(all(result == results[0] for result in results))


if __name__ == "__main__":
    unittest.main()
