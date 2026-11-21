import unittest
from unittest.mock import patch

import config
from enemy import Enemy
from player import Player
from stairs import Staircase
from tests.helpers import ArchivedTwoFloorTests, advance
from tests.test_two_floors import place
from world import World


def traveller(stair, floor=0, *, player=False, speed=360):
    actor = Player() if player else Enemy(0, run_speed=speed)
    actor.floor = floor
    actor.x, actor.ground_y = stair.entrance(floor)
    return actor


def column_world():
    world = World()
    world.player.invincible = True
    place(world, world.player, 1, 1400, 476)
    world.enemies = [Enemy(238 + 30 * index, ground_y=136) for index in range(4)]
    for _ in range(180):
        world.step(config.FIXED_DT)
        if len(world.stage.stairs[0].occupants) >= 2:
            return world
    raise AssertionError("No following enemy entered the staircase")


class StairColumnTests(ArchivedTwoFloorTests):
    def setUp(self):
        super().setUp()
        self.stair = Staircase(config.STAGE_STAIR_PATHS[config.STAGE_IMAGE][0])

    def assert_column(self, stair):
        progress = list(stair.occupants.values())
        self.assertTrue(all(a - b >= config.STAIR_FOLLOW_DISTANCE - 1e-8
                            for a, b in zip(progress, progress[1:])))
        for actor in stair.occupants:
            self.assertIs(actor.staircase, stair)
            self.assertEqual(actor.floor, 1 - stair.destination_floor)
        if len(stair.occupants) > 1:
            self.assertTrue(all(actor.stair_following for actor in stair.occupants))

    def drive(self, frames):
        for _ in range(frames):
            self.stair.start_next()
            self.stair.update(config.FIXED_DT)
            self.assert_column(self.stair)

    def test_following_enemy_enters_before_the_leader_leaves_after_the_required_gap(self):
        first, second = [traveller(self.stair) for _ in range(2)]
        for actor in (first, second):
            self.stair.request(actor)
        self.stair.start_next()
        self.stair.update((config.STAIR_FOLLOW_DISTANCE - 1) / config.STAIR_SPEED)
        self.stair.start_next()
        self.assertEqual(list(self.stair.occupants), [first])
        self.stair.update(1 / config.STAIR_SPEED)
        self.stair.start_next()
        self.assertEqual(list(self.stair.occupants), [first, second])
        self.assertIs(first.staircase, self.stair)
        self.assertEqual(self.stair.occupants[second], 0)
        self.assert_column(self.stair)

    def test_multiple_enemies_move_together_in_order_on_both_up_and_down_trips(self):
        for floor in (0, 1):
            with self.subTest(floor=floor):
                self.stair = Staircase(self.stair.path)
                actors = [traveller(self.stair, floor, speed=speed)
                          for speed in config.ENEMY_RUN_SPEEDS]
                for actor in actors:
                    self.stair.request(actor)
                entered, landed, peak = [], [], 0
                for _ in range(600):
                    self.stair.start_next()
                    for actor in self.stair.occupants:
                        if actor not in entered:
                            entered.append(actor)
                    self.stair.update(config.FIXED_DT)
                    self.assert_column(self.stair)
                    peak = max(peak, len(self.stair.occupants))
                    for actor in actors:
                        if actor.floor == 1 - floor and actor not in landed:
                            landed.append(actor)
                    if len(landed) == len(actors):
                        break
                self.assertGreaterEqual(peak, 3)
                self.assertEqual(entered, actors)
                self.assertEqual(landed, actors)
                self.assertFalse(self.stair.occupants)
                self.assertIsNone(self.stair.destination_floor)

    def test_each_active_enemy_advances_by_the_same_stair_speed_without_overtaking(self):
        actors = [traveller(self.stair, speed=speed) for speed in config.ENEMY_RUN_SPEEDS]
        for actor in actors:
            self.stair.request(actor)
        self.drive(110)
        self.assertGreater(len(self.stair.occupants), 1)
        before = dict(self.stair.occupants)
        self.stair.update(config.FIXED_DT)
        for actor, previous in before.items():
            self.assertAlmostEqual(self.stair.occupants[actor] - previous,
                                   config.STAIR_SPEED * config.FIXED_DT)
        self.assert_column(self.stair)

    def test_opposite_direction_waits_until_the_whole_column_has_cleared(self):
        up = [traveller(self.stair) for _ in range(2)]
        down = traveller(self.stair, 1)
        later_up = traveller(self.stair)
        for actor in [*up, down, later_up]:
            self.stair.request(actor)
        self.drive(110)
        self.assertEqual(list(self.stair.occupants), up)
        self.assertIn(down, self.stair.queue)
        for _ in range(500):
            self.stair.start_next()
            self.stair.update(config.FIXED_DT)
            self.assert_column(self.stair)
            if down.staircase is not None:
                break
        self.assertTrue(all(actor.floor == 1 for actor in up))
        self.assertEqual(list(self.stair.occupants), [down])
        self.assertIn(later_up, self.stair.queue)

    def test_queued_player_remains_exclusive_and_is_not_starved_by_followers(self):
        first = traveller(self.stair)
        player = traveller(self.stair, player=True)
        later = traveller(self.stair)
        for actor in (first, player, later):
            self.stair.request(actor)
        self.drive(100)
        self.assertEqual(list(self.stair.occupants), [first])
        for _ in range(300):
            self.stair.start_next()
            self.stair.update(config.FIXED_DT)
            if player.staircase is not None:
                break
        self.assertEqual(first.floor, 1)
        self.assertEqual(list(self.stair.occupants), [player])
        self.drive(80)
        self.assertEqual(list(self.stair.occupants), [player])
        self.assertIn(later, self.stair.queue)
        self.drive(500)
        self.assertEqual(later.floor, 1)
        self.assertIsNone(player.staircase)

    def test_enemy_cannot_share_steps_with_a_player_already_travelling(self):
        player = traveller(self.stair, 1, player=True)
        enemy = traveller(self.stair, 1)
        self.stair.request(player)
        self.stair.request(enemy)
        self.drive(110)
        self.assertEqual(list(self.stair.occupants), [player])
        self.assertIsNone(enemy.staircase)

    def test_removing_a_head_or_middle_actor_preserves_every_other_actors_progress(self):
        actors = [traveller(self.stair) for _ in range(3)]
        for actor in actors:
            self.stair.request(actor)
        self.drive(110)
        self.assertEqual(len(self.stair.occupants), 3)
        before = dict(self.stair.occupants)
        self.stair.release(actors[1])
        self.assertIsNone(actors[1].staircase)
        self.assertEqual(self.stair.occupants[actors[0]], before[actors[0]])
        self.assertEqual(self.stair.occupants[actors[2]], before[actors[2]])
        self.stair.release(actors[0])
        self.assertEqual(self.stair.occupants[actors[2]], before[actors[2]])
        self.assertEqual(self.stair.destination_floor, 1)
        self.assert_column(self.stair)

    def test_releasing_the_last_actor_unlocks_direction_for_the_opposite_queue(self):
        first, second = [traveller(self.stair) for _ in range(2)]
        down = traveller(self.stair, 1)
        for actor in (first, second, down):
            self.stair.request(actor)
        self.drive(60)
        self.stair.release(first)
        self.stair.release(second)
        self.assertIsNone(self.stair.destination_floor)
        self.stair.start_next()
        self.assertEqual(list(self.stair.occupants), [down])
        self.assertEqual(self.stair.destination_floor, 0)

    def test_update_returns_all_travellers_including_simultaneous_landings(self):
        actors = [traveller(self.stair) for _ in range(3)]
        for actor in actors:
            self.stair.request(actor)
        self.drive(110)
        self.assertEqual(self.stair.update(10), set(actors))
        self.assertFalse(self.stair.occupants)
        self.assertTrue(all(actor.floor == 1 and actor.staircase is None for actor in actors))

    def test_world_does_not_run_normal_ai_or_floor_projection_on_any_traveller(self):
        world = column_world()
        stair = world.stage.stairs[0]
        first, second = list(stair.occupants)
        with (patch.object(first, "update", wraps=first.update) as a,
              patch.object(second, "update", wraps=second.update) as b):
            world.step(config.FIXED_DT)
        a.assert_not_called()
        b.assert_not_called()
        self.assert_column(stair)
        self.assertGreater(second.ground_y, world.stage.walkable.bounds[3])

    def test_world_removes_a_dead_follower_without_cancelling_the_leader(self):
        world = column_world()
        stair = world.stage.stairs[0]
        first, second = list(stair.occupants)
        before = stair.occupants[first]
        second.take_damage(config.ENEMY_MAX_HP)
        world.step(config.FIXED_DT)
        self.assertNotIn(second, stair.occupants)
        self.assertIsNone(second.staircase)
        self.assertGreater(stair.occupants[first], before)
        self.assertIs(first.staircase, stair)

    def test_f5_clears_every_traveller_not_only_the_leader(self):
        world = column_world()
        stair = world.stage.stairs[0]
        actors = list(stair.occupants)
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertFalse(stair.occupants)
        self.assertFalse(stair.queue)
        self.assertTrue(all(actor.staircase is None for actor in actors))
        self.assertFalse(world.stage.stairs[0].occupants)

    def test_player_death_releases_the_entire_enemy_column_and_queue(self):
        world = column_world()
        stair = world.stage.stairs[0]
        actors = list(stair.occupants)
        world.player.invincible = False
        world.player.take_damage(config.MAX_HP)
        world.step(config.FIXED_DT)
        self.assertFalse(stair.occupants)
        self.assertFalse(stair.queue)
        self.assertTrue(all(actor.staircase is None for actor in actors))

    def test_inactive_stage_pauses_and_resumes_each_individual_progress(self):
        world = column_world()
        stair = world.stage.stairs[0]
        before = dict(stair.occupants)
        world.select_stage(1)
        advance(world, 1)
        self.assertEqual(stair.occupants, before)
        world.select_stage(0)
        world.step(config.FIXED_DT)
        for actor, progress in before.items():
            self.assertAlmostEqual(stair.occupants[actor] - progress,
                                   config.STAIR_SPEED * config.FIXED_DT)
        self.assert_column(stair)

    def test_enemy_columns_are_render_rate_independent(self):
        snapshots = []
        for fps in (30, 60, 120, 144):
            world = column_world()
            advance(world, 0.5, fps)
            snapshots.append([(enemy.floor, enemy.x, enemy.ground_y)
                              for enemy in world.enemies])
        self.assertTrue(all(snapshot == snapshots[0] for snapshot in snapshots))


if __name__ == "__main__":
    unittest.main()
