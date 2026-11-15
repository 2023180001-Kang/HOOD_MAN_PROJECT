import random
import unittest

import config
from combat import MOVES
from counter import COUNTERS
from enemy import Enemy
from tests.helpers import advance
from traffic import Car, Traffic
from world import World


def city_world():
    world = World(rng=random.Random(7), traffic_rng=random.Random(11))
    world.stage_index = 2
    world.player.ground_y = config.CAR_GROUND_Y
    return world


def place_car(world, direction=1, *, x=None, speed=600):
    car = Car(world.player.x if x is None else x, direction, speed)
    world.stage.traffic.car = car
    return car


class TrafficTests(unittest.TestCase):
    def test_only_city_stage_one_has_traffic_and_it_waits_before_the_first_pass(self):
        world = World()
        self.assertEqual([index for index, stage in enumerate(world.stages)
                          if stage.traffic is not None], [2])
        traffic = world.stages[2].traffic
        traffic.update(config.CAR_INITIAL_DELAY - config.FIXED_DT)
        self.assertIsNone(traffic.car)
        traffic.update(config.FIXED_DT)
        self.assertIsNotNone(traffic.car)
        self.assertEqual(traffic.car.ground_y, config.CAR_GROUND_Y)

    def test_repeated_passes_randomize_direction_and_speed_and_leave_a_gap(self):
        traffic = Traffic(rng=random.Random(5))
        directions, speeds, delays = set(), set(), []
        for _ in range(20):
            traffic.update(traffic.spawn_remaining)
            car = traffic.car
            self.assertIsNotNone(car)
            directions.add(car.facing)
            speeds.add(car.speed)
            self.assertTrue(config.CAR_SPEED_RANGE[0] <= car.speed <= config.CAR_SPEED_RANGE[1])
            while traffic.car is not None:
                before = car.x
                traffic.update(config.FIXED_DT)
                self.assertAlmostEqual(car.x - before, car.facing * car.speed * config.FIXED_DT)
            delays.append(traffic.spawn_remaining)
            traffic.update(config.FIXED_DT)
            self.assertIsNone(traffic.car)
        self.assertEqual(directions, {-1, 1})
        self.assertGreater(len(speeds), 10)
        self.assertTrue(all(config.CAR_PASS_DELAY[0] <= delay <= config.CAR_PASS_DELAY[1]
                            for delay in delays))

    def test_both_directions_kill_a_full_health_player_even_during_an_attack_or_p_invincibility(self):
        for direction in (-1, 1):
            for mode in ("idle", "attack", "invincible", "HIT"):
                with self.subTest(direction=direction, mode=mode):
                    world = city_world()
                    if mode == "attack":
                        world.player.start_move(MOVES["combat_f"], -direction)
                    elif mode == "invincible":
                        world.player.invincible = True
                    elif mode == "HIT":
                        world.player.take_damage(20)
                    place_car(world, direction)
                    world.step(config.FIXED_DT)
                    self.assertEqual((world.player.hp, world.player.state), (0, "CAR_HIT"))
                    self.assertEqual(world.player.sprite_image, config.PLAYER_CAR_HIT_IMAGE)
                    self.assertEqual(world.player.facing, direction)
                    self.assertIsNone(world.player.active_move)
                    self.assertFalse(world.player.invincible)
                    self.assertTrue(world.death_handled)
                    self.assertGreater(world.camera.shake_remaining, 0)

    def test_a_single_pass_kills_multiple_enemies_and_the_player_in_the_same_tick(self):
        world = city_world()
        world.enemies = [Enemy(world.player.x + offset, ground_y=config.CAR_GROUND_Y)
                         for offset in (-100, 0, 100)]
        place_car(world)
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 0)
        for enemy in world.enemies:
            self.assertEqual((enemy.hp, enemy.state), (0, "CAR_HIT"))
            self.assertEqual(enemy.sprite_image, config.ENEMY_CAR_HIT_IMAGE)
            self.assertIsNone(enemy.attack_box)
            self.assertFalse(enemy.knockback_started)
        self.assertEqual([number.damage for number in world.damage_numbers], [200, 200, 200])
        self.assertEqual(len(world.effects), 4)

    def test_sidewalk_and_a_jump_above_the_roof_are_safe(self):
        for ground_y, height in ((100, 0), (148, 0), (64, config.CAR_HEIGHT + 10)):
            with self.subTest(ground_y=ground_y, height=height):
                world = city_world()
                world.player.ground_y = ground_y
                world.player.jump_height = height
                place_car(world)
                world.step(config.FIXED_DT)
                self.assertEqual(world.player.hp, config.MAX_HP)
                self.assertFalse(world.effects)

    def test_depth_boundary_hits_but_the_next_lane_does_not(self):
        for delta, dies in ((24, True), (24.01, False)):
            world = city_world()
            world.player.ground_y += delta
            place_car(world)
            world.step(config.FIXED_DT)
            self.assertEqual(not world.player.alive, dies)

    def test_swept_collision_catches_a_car_crossing_the_entire_actor_between_ticks(self):
        for direction in (-1, 1):
            with self.subTest(direction=direction):
                world = city_world()
                car = place_car(world, direction, x=world.player.x - direction * 500, speed=120000)
                world.step(config.FIXED_DT)
                self.assertGreater(abs(car.x - world.player.x), 400)
                self.assertEqual(world.player.hp, 0)

    def test_swept_axes_must_overlap_at_the_same_instant(self):
        world = city_world()
        player = world.player
        car = place_car(world, x=player.x - 100)
        car.previous_x, car.x = player.x - 100, player.x + 900
        player.previous_ground_y, player.ground_y = 148, 64
        self.assertFalse(car.hits(player))
        player.previous_ground_y = player.ground_y
        player.previous_jump_height, player.jump_height = 220, 0
        self.assertFalse(car.hits(player))
        player.previous_jump_height = 0
        self.assertTrue(car.hits(player))

    def test_car_hit_preempts_same_tick_normal_combat_and_does_not_restart_on_a_corpse(self):
        world = city_world()
        enemy = Enemy(world.player.x + 80, -1, ground_y=world.player.ground_y)
        world.enemies.append(enemy)
        world.player.start_move(MOVES["combat_f"], 1)
        world.player.animation.elapsed = 3 / MOVES["combat_f"].fps
        place_car(world, speed=1)
        world.step(config.FIXED_DT)
        self.assertEqual([number.damage for number in world.damage_numbers], [200])
        advance(world, 0.1)
        self.assertEqual(len(world.effects), 2)
        self.assertEqual(len(world.damage_numbers), 1)
        self.assertGreater(enemy.animation.frame, 0)
        self.assertFalse(enemy.hit_by_car(-1))
        self.assertFalse(world.player.hit_by_car(-1))
        self.assertEqual((world.player.facing, enemy.facing), (1, 1))

    def test_vehicle_interrupts_both_sides_of_a_counter_without_leaving_a_link(self):
        for target in ("enemy", "both"):
            with self.subTest(target=target):
                world = city_world()
                enemy = Enemy(world.player.x + 80, -1, ground_y=world.player.ground_y)
                enemy.animation.set_state("ATTACK")
                enemy.animation.elapsed = 2 / enemy.attack_fps
                world.enemies.append(enemy)
                self.assertTrue(world.try_start_counter("counter_h"))
                place_car(world, x=world.player.x + (270 if target == "enemy" else 0), speed=1)
                world.step(config.FIXED_DT)
                self.assertIsNone(world.counter)
                self.assertIsNone(world.player.counter_move)
                self.assertIsNone(enemy.counter_move)
                self.assertFalse(enemy.counter_linked)
                self.assertEqual(enemy.state, "CAR_HIT")
                self.assertEqual(world.player.hp, 500 if target == "enemy" else 0)
                self.assertEqual(world.player.boundary_padding, config.PLAYER_BOUNDARY_PADDING)
                self.assertEqual(enemy.boundary_padding, config.ENEMY_BOUNDARY_PADDING)

    def test_independent_subdued_enemy_and_knockback_enemy_can_be_run_over(self):
        for mode in ("subdued", "knockback"):
            world = city_world()
            world.player.ground_y = 148
            enemy = Enemy(world.player.x, ground_y=config.CAR_GROUND_Y)
            if mode == "subdued":
                enemy.start_counter(COUNTERS["counter_j"], -1)
                enemy.release_counter()
            else:
                enemy.knockback(enemy.x - 40)
            world.enemies.append(enemy)
            place_car(world)
            world.step(config.FIXED_DT)
            self.assertEqual((enemy.hp, enemy.state), (0, "CAR_HIT"))
            self.assertIsNone(enemy.counter_move)
            self.assertFalse(enemy.knockback_started)
            self.assertEqual(world.player.hp, 500)

    def test_all_eight_death_frames_play_once_then_the_final_pose_is_held(self):
        world = city_world()
        enemy = Enemy(world.player.x + 100, ground_y=config.CAR_GROUND_Y)
        world.enemies.append(enemy)
        place_car(world)
        world.step(config.FIXED_DT)
        player_x, enemy_x = world.player.x, enemy.x
        seen = [set(), set()]
        while world.player.state != "DEAD" or enemy.state != "DEAD":
            for actor, frames in zip((world.player, enemy), seen):
                frames.add(actor.animation.frame)
                self.assertEqual(actor.animation.row, 1)
            world.step(config.FIXED_DT)
        self.assertEqual(seen, [set(range(8)), set(range(8))])
        self.assertGreater(world.player.x, player_x + 80)
        self.assertGreater(enemy.x, enemy_x + 80)
        self.assertEqual(enemy.corpse_elapsed, 0)
        self.assertEqual((world.player.animation.frame, enemy.animation.frame), (7, 7))
        advance(world, 1)
        self.assertEqual((world.player.sprite_image, enemy.sprite_image),
                         (config.PLAYER_CAR_HIT_IMAGE, config.ENEMY_CAR_HIT_IMAGE))
        self.assertEqual((world.player.animation.frame, enemy.animation.frame), (7, 7))

    def test_vehicle_corpse_uses_the_existing_hold_fade_and_removal_lifecycle(self):
        world = city_world()
        world.player.ground_y = 148
        enemy = Enemy(world.player.x, ground_y=config.CAR_GROUND_Y)
        world.enemies.append(enemy)
        place_car(world)
        world.step(config.FIXED_DT)
        while enemy.state != "DEAD":
            self.assertEqual((enemy.opacity, enemy.corpse_elapsed), (1, 0))
            world.step(config.FIXED_DT)
        advance(world, 3)
        self.assertEqual(enemy.opacity, 1)
        advance(world, 0.5)
        self.assertAlmostEqual(enemy.opacity, 0.5)
        advance(world, 0.5)
        self.assertNotIn(enemy, world.enemies)
        self.assertEqual(world.player.hp, 500)

    def test_fatal_slide_stays_inside_both_map_edges(self):
        for direction in (-1, 1):
            world = city_world()
            world.player.x = (config.PLAYER_BOUNDARY_PADDING if direction < 0 else
                              config.WORLD_WIDTH - config.PLAYER_BOUNDARY_PADDING)
            enemy = Enemy(world.player.x, ground_y=config.CAR_GROUND_Y)
            world.enemies.append(enemy)
            place_car(world, direction)
            advance(world, 1)
            for actor in (world.player, enemy):
                self.assertTrue(world.stage.walkable.contains(
                    actor.x, actor.ground_y, actor.boundary_padding))
                self.assertEqual((actor.hp, actor.state, actor.animation.frame), (0, "DEAD", 7))

    def test_traffic_and_vehicle_deaths_pause_off_stage_and_during_loading(self):
        world = city_world()
        world.player.ground_y = 148
        enemy = Enemy(world.player.x, ground_y=config.CAR_GROUND_Y)
        world.enemies.append(enemy)
        car = place_car(world)
        world.step(config.FIXED_DT)
        traffic = world.stage.traffic
        snapshot = car.x, car.animation.elapsed, enemy.animation.elapsed
        world.stage_index = 3
        advance(world, 1)
        self.assertEqual((car.x, car.animation.elapsed, enemy.animation.elapsed), snapshot)
        world.stage_index = 2
        world.pending_stage_index = 1
        world.stage_loading_remaining = 2
        advance(world, 1)
        self.assertEqual((car.x, car.animation.elapsed, enemy.animation.elapsed), snapshot)
        world.pending_stage_index = None
        advance(world, 0.1)
        self.assertIs(world.stage.traffic, traffic)
        self.assertGreater(car.x, snapshot[0])
        self.assertGreater(enemy.animation.elapsed, snapshot[2])

    def test_restart_clears_traffic_and_death_state_and_dead_inputs_cannot_revive(self):
        world = city_world()
        traffic = world.stage.traffic
        place_car(world)
        world.step(config.FIXED_DT)
        for key in ("spawn_9", "combat_a", "jump", "counter_h", "stage_exits", "invincibility"):
            world.controls.press(key)
        world.step(config.FIXED_DT)
        self.assertFalse(world.controls.pressed)
        self.assertEqual(world.enemies, [])
        self.assertEqual(world.player.hp, 0)
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertEqual((world.stage_index, world.player.hp, world.player.state), (0, 500, "IDLE"))
        self.assertFalse(world.player.car_hit)
        self.assertEqual(world.player.sprite_image, config.PLAYER_IMAGE)
        self.assertIsNot(world.stages[2].traffic, traffic)
        self.assertIsNone(world.stages[2].traffic.car)
        self.assertEqual(world.stages[2].traffic.spawn_remaining, config.CAR_INITIAL_DELAY)

    def test_seeded_traffic_and_death_are_identical_at_different_render_frame_rates(self):
        results = []
        for fps in (30, 60, 120, 144):
            world = city_world()
            advance(world, 10, fps)
            car = world.stage.traffic.car
            results.append((world.player.hp, world.player.x, world.player.state,
                            world.player.animation.frame, world.death_handled,
                            world.stage.traffic.spawn_remaining,
                            None if car is None else (car.x, car.facing, car.speed, car.animation.frame)))
        self.assertEqual(results[0][0], 0)
        self.assertTrue(all(result == results[0] for result in results))


if __name__ == "__main__":
    unittest.main()
