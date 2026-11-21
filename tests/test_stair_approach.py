from math import hypot
import unittest

import config
from enemy import Enemy
from tests.helpers import ArchivedTwoFloorTests, advance
from tests.test_two_floors import place
from world import World


def encounter(floor=1, x=1000, y=476, speed=360):
    world = World()
    place(world, world.player, 1 - floor, 1400, 100 if floor else 476)
    world.player.invincible = True
    enemy = Enemy(x, ground_y=y, run_speed=speed)
    enemy.descent_route = "STAIRS"  # Isolate stair timing from the randomized drop route.
    place(world, enemy, floor, x, y)
    world.enemies = [enemy]
    return world, enemy


class StairApproachTests(ArchivedTwoFloorTests):
    def assert_runs_to_entry(self, world, enemy):
        for _ in range(360):
            before = enemy.x, enemy.ground_y
            world.step(config.FIXED_DT)
            if enemy.staircase is not None:
                self.assertIs(enemy.staircase.occupant, enemy)
                return
            self.assertTrue(enemy.running)
            self.assertEqual(enemy.state, "RUN")
            self.assertAlmostEqual(hypot(enemy.vx, enemy.ground_vy), enemy.run_speed)
            self.assertAlmostEqual(hypot(enemy.x - before[0], enemy.ground_y - before[1]),
                                   enemy.run_speed * config.FIXED_DT)
        self.fail("Enemy did not enter the empty staircase")

    def test_descending_enemy_does_not_slow_to_walking_within_360_pixels_of_the_stair(self):
        world, enemy = encounter()
        self.assert_runs_to_entry(world, enemy)
        self.assertLess(world.elapsed, 1.4)

    def test_both_floors_and_both_approach_sides_keep_each_enemys_run_speed(self):
        for floor in (0, 1):
            for side in (-1, 1):
                for speed in config.ENEMY_RUN_SPEEDS:
                    with self.subTest(floor=floor, side=side, speed=speed):
                        x = 88 if side < 0 else 1000
                        world, enemy = encounter(floor, x, 100 if floor == 0 else 495, speed)
                        self.assert_runs_to_entry(world, enemy)

    def test_waiters_stop_at_their_slots_until_the_following_gap_is_available(self):
        world, occupant = encounter(x=500)
        waiters = [Enemy(600, ground_y=476), Enemy(690, ground_y=476)]
        for enemy in waiters:
            enemy.descent_route = "STAIRS"
            place(world, enemy, 1, enemy.x, enemy.ground_y)
        world.enemies.extend(waiters)
        advance(world, 1 / 3)
        stair = world.stage.stairs[0]
        self.assertIs(stair.occupant, occupant)
        positions = [(enemy.x, enemy.ground_y) for enemy in waiters]
        for _ in range(6):
            world.step(config.FIXED_DT)
            self.assertIs(stair.occupant, occupant)
            self.assertEqual(sum(enemy.staircase is not None for enemy in world.enemies), 1)
            for enemy, point in zip(waiters, positions):
                self.assertEqual((enemy.x, enemy.ground_y), point)
                self.assertEqual((enemy.vx, enemy.ground_vy), (0, 0))
                self.assertFalse(enemy.running)
                self.assertEqual(enemy.state, "IDLE")

    def test_next_waiter_runs_forward_when_space_is_available_without_reordering(self):
        world, first = encounter(x=500)
        others = [Enemy(600, ground_y=476), Enemy(690, ground_y=476)]
        for enemy in others:
            enemy.descent_route = "STAIRS"
            place(world, enemy, 1, enemy.x, enemy.ground_y)
        world.enemies.extend(others)
        entered = []
        for _ in range(1000):
            world.step(config.FIXED_DT)
            stair = world.stage.stairs[0]
            for actor in stair.occupants:
                if actor not in entered:
                    entered.append(actor)
            progress = list(stair.occupants.values())
            self.assertTrue(all(a - b >= config.STAIR_FOLLOW_DISTANCE - 1e-8
                                for a, b in zip(progress, progress[1:])))
            for enemy in others:
                if (enemy.floor == 1 and enemy.staircase is None
                        and hypot(enemy.vx, enemy.ground_vy) > 0):
                    self.assertAlmostEqual(hypot(enemy.vx, enemy.ground_vy), enemy.run_speed)
            if len(entered) == 3:
                break
        self.assertEqual(entered, [first, *others])

    def test_navigation_at_a_reached_waypoint_is_idle_not_running_or_creeping(self):
        world, enemy = encounter()
        enemy.navigation_target = enemy.x + 0.5, enemy.ground_y
        enemy.running = True
        before = enemy.x, enemy.ground_y
        enemy.update(config.FIXED_DT, world.player, world.stage.upper_walkable)
        self.assertEqual((enemy.x, enemy.ground_y), before)
        self.assertEqual((enemy.vx, enemy.ground_vy), (0, 0))
        self.assertFalse(enemy.running)
        self.assertEqual(enemy.state, "IDLE")

    def test_stair_traversal_speed_itself_remains_unchanged(self):
        world, enemy = encounter(x=500)
        world.step(config.FIXED_DT)
        stair = world.stage.stairs[0]
        previous = stair.progress
        world.step(config.FIXED_DT)
        self.assertIs(stair.occupant, enemy)
        self.assertAlmostEqual(stair.progress - previous, config.STAIR_SPEED * config.FIXED_DT)

    def test_same_floor_melee_approach_still_walks_and_hit_reactions_still_stop(self):
        world = World()
        enemy = Enemy(world.player.x - 280)
        world.enemies = [enemy]
        world.step(config.FIXED_DT)
        self.assertIsNone(enemy.navigation_target)
        self.assertFalse(enemy.running)
        self.assertAlmostEqual(hypot(enemy.vx, enemy.ground_vy), config.ENEMY_SPEED)
        enemy.take_damage(10)
        before = enemy.x, enemy.ground_y
        world.step(config.FIXED_DT)
        self.assertEqual(enemy.state, "HIT")
        self.assertEqual((enemy.x, enemy.ground_y), before)

    def test_stair_approach_is_render_rate_independent(self):
        results = []
        for fps in (30, 60, 120, 144):
            world, enemy = encounter()
            advance(world, 1, fps)
            results.append((enemy.x, enemy.ground_y, enemy.vx, enemy.ground_vy, enemy.state))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(results[0], (640, 476, -360, 0, "RUN"))


if __name__ == "__main__":
    unittest.main()
