from math import hypot
import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import config
from enemy import Enemy
from tests.helpers import ArchivedTwoFloorTests, advance
from tests.test_two_floors import place
from ui import UI
from world import World


def steer(world, direction):
    for key in ("up", "down"):
        world.controls.release(key)
    if direction:
        world.controls.press("up" if direction > 0 else "down")


def stair_world(floor=0, seconds=0.6):
    world = World(rng=random.Random(41), item_rng=random.Random(5))
    world.player.invincible = True
    stair = world.stage.stairs[0]
    place(world, world.player, floor, *stair.entrance(floor))
    steer(world, 1 if floor == 0 else -1)
    world.step(config.FIXED_DT)
    advance(world, seconds)
    return world, stair


class StairControlTests(ArchivedTwoFloorTests):
    def test_releasing_the_key_pauses_both_upward_and_downward_travel(self):
        for floor in (0, 1):
            world, stair = stair_world(floor)
            player = world.player
            before = player.x, player.ground_y, stair.occupants[player]
            steer(world, 0)
            advance(world, 1)
            self.assertEqual((player.x, player.ground_y, stair.occupants[player]), before)
            self.assertEqual(player.state, "IDLE")
            self.assertEqual((player.vx, player.ground_vy, player.vy, player.jump_height), (0, 0, 0, 0))
            self.assertIs(player.staircase, stair)
            self.assertEqual(player.floor, floor)

    def test_repressing_the_same_key_resumes_from_the_paused_position(self):
        for floor in (0, 1):
            world, stair = stair_world(floor)
            steer(world, 0)
            advance(world, 0.5)
            before = stair.progress
            steer(world, 1 if floor == 0 else -1)
            world.step(config.FIXED_DT)
            self.assertAlmostEqual(stair.progress - before, config.STAIR_SPEED * config.FIXED_DT)
            self.assertEqual(world.player.state, "WALK")

    def test_opposite_key_immediately_reverses_without_rebasing_or_teleporting(self):
        for floor in (0, 1):
            world, stair = stair_world(floor)
            player = world.player
            before = player.x, player.ground_y, stair.progress
            steer(world, -1 if floor == 0 else 1)
            world.step(config.FIXED_DT)
            self.assertAlmostEqual(stair.progress - before[2], -config.STAIR_SPEED * config.FIXED_DT)
            self.assertLessEqual(hypot(player.x - before[0], player.ground_y - before[1]),
                                 config.STAIR_SPEED * config.FIXED_DT + 1e-8)
            self.assertEqual(player.facing, -1 if floor == 0 else 1)
            self.assertEqual(player.state, "WALK")
            self.assertEqual(stair.destination_floor, floor)
            self.assertEqual(player.floor, floor)

    def test_repeated_reversals_do_not_drift_or_lose_the_stair_lock(self):
        for floor in (0, 1):
            world, stair = stair_world(floor)
            start = world.player.x, world.player.ground_y, stair.progress
            forward = 1 if floor == 0 else -1
            for _ in range(10):
                for direction in (-forward, forward):
                    steer(world, direction)
                    for _ in range(12):
                        before = world.player.x, world.player.ground_y
                        world.step(config.FIXED_DT)
                        self.assertIs(world.player.staircase, stair)
                        self.assertLessEqual(hypot(world.player.x - before[0],
                                                   world.player.ground_y - before[1]),
                                             config.STAIR_SPEED * config.FIXED_DT + 1e-8)
            for actual, expected in zip((world.player.x, world.player.ground_y, stair.progress), start):
                self.assertAlmostEqual(actual, expected)

    def test_turning_back_reaches_the_original_floor_from_either_half_of_the_stairs(self):
        for floor in (0, 1):
            for seconds in (0.3, 1.2):
                world, stair = stair_world(floor, seconds)
                steer(world, -1 if floor == 0 else 1)
                for _ in range(300):
                    world.step(config.FIXED_DT)
                    if world.player.staircase is None:
                        break
                self.assertEqual(world.player.floor, floor)
                self.assertEqual((world.player.x, world.player.ground_y), stair.entrance(floor))
                self.assertFalse(stair.occupants)
                self.assertIsNone(stair.destination_floor)
                self.assertTrue(world.player.stair_arrival)

    def test_holding_the_key_still_completes_each_full_trip(self):
        for floor in (0, 1):
            world, stair = stair_world(floor, 0)
            for _ in range(300):
                world.step(config.FIXED_DT)
                if world.player.staircase is None:
                    break
            self.assertEqual(world.player.floor, 1 - floor)
            self.assertEqual((world.player.x, world.player.ground_y), stair.entrance(1 - floor))
            self.assertTrue(world.player.grounded)

    def test_opposing_up_down_keys_pause_and_releasing_one_resumes_the_other(self):
        world, stair = stair_world()
        before = stair.progress
        world.controls.press("down")
        advance(world, 0.5)
        self.assertEqual(stair.progress, before)
        self.assertEqual(world.player.state, "IDLE")
        world.controls.release("up")
        world.step(config.FIXED_DT)
        self.assertAlmostEqual(stair.progress - before, -config.STAIR_SPEED * config.FIXED_DT)
        self.assertEqual(stair.destination_floor, 0)

    def test_lateral_keys_detach_instead_of_trapping_the_player_on_the_path(self):
        for key in ("left", "right"):
            world, stair = stair_world()
            steer(world, 0)
            world.controls.press(key)
            world.step(config.FIXED_DT)
            self.assertIsNone(world.player.staircase)
            self.assertFalse(stair.occupants)

    def test_shift_does_not_change_stair_speed_in_either_direction(self):
        world, stair = stair_world()
        world.controls.press("left_shift")
        for direction in (1, -1):
            steer(world, direction)
            before = stair.progress
            world.step(config.FIXED_DT)
            self.assertAlmostEqual(stair.progress - before,
                                   direction * config.STAIR_SPEED * config.FIXED_DT)

    def test_paused_and_reversing_player_remains_exclusive_and_waiters_resume_after_exit(self):
        world, stair = stair_world()
        lower = Enemy(238, ground_y=136)
        upper = Enemy(500, ground_y=476)
        upper.descent_route = "STAIRS"
        place(world, upper, 1, 500, 476)
        world.enemies = [lower, upper]
        steer(world, 0)
        advance(world, 1)
        self.assertIn(lower, stair.queue)
        self.assertEqual(list(stair.occupants), [world.player])
        steer(world, -1)
        for _ in range(300):
            world.step(config.FIXED_DT)
            if world.player.staircase is None:
                break
            self.assertEqual(list(stair.occupants), [world.player])
        self.assertEqual(world.player.floor, 0)
        for _ in range(120):
            world.step(config.FIXED_DT)
            if upper.staircase:
                break
        self.assertIs(upper.staircase, stair)

    def test_reversal_updates_enemy_route_destination_in_the_same_tick(self):
        world, stair = stair_world()
        enemies = [Enemy(1000 + 100 * index, ground_y=476) for index in range(2)]
        for enemy in enemies:
            place(world, enemy, 1, enemy.x, 476)
        world.enemies = enemies
        steer(world, -1)
        world.step(config.FIXED_DT)
        self.assertEqual(stair.destination_floor, 0)
        self.assertEqual({enemy.descent_route for enemy in enemies}, {"STAIRS", "DROP"})
        steer(world, 1)
        world.step(config.FIXED_DT)
        self.assertEqual(stair.destination_floor, 1)
        self.assertTrue(all(enemy.descent_route is None for enemy in enemies))

    def test_paused_player_does_not_run_ground_movement_or_floor_projection(self):
        world, stair = stair_world()
        steer(world, 0)
        before = world.player.x, world.player.ground_y
        with patch.object(world.player, "update", wraps=world.player.update) as update:
            world.step(config.FIXED_DT)
        update.assert_not_called()
        self.assertEqual((world.player.x, world.player.ground_y), before)
        self.assertIs(world.player.staircase, stair)
        self.assertGreater(world.player.ground_y, world.stage.walkable.bounds[3])

    def test_paused_player_still_consumes_forbidden_actions_without_buffering(self):
        world, stair = stair_world()
        steer(world, 0)
        world.player.equip_weapon("steel_pipe")
        for key in ("combat_q", "counter_h", "weapon_interact"):
            world.controls.press(key)
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.state, "IDLE")
        self.assertEqual(world.player.weapon, "steel_pipe")
        self.assertIsNone(world.player.active_move)
        self.assertIsNone(world.counter)
        self.assertEqual(world.player.jump_height, 0)
        self.assertIs(world.player.staircase, stair)
        self.assertTrue(all(key not in world.controls.pressed
                             for key in ("combat_q", "counter_h", "weapon_interact")))
        steer(world, 1)
        advance(world, 3)
        self.assertIsNone(world.player.active_move)
        self.assertEqual(world.player.floor, 1)

    def test_death_after_reversal_releases_to_the_physically_nearest_landing(self):
        for floor in (0, 1):
            for seconds in (0.3, 1.2):
                world, stair = stair_world(floor, seconds)
                expected = floor if stair.progress < stair.length / 2 else 1 - floor
                steer(world, -1 if floor == 0 else 1)
                world.step(config.FIXED_DT)
                steer(world, 0)
                world.player.invincible = False
                world.player.take_damage(config.MAX_HP)
                world.step(config.FIXED_DT)
                self.assertFalse(world.player.alive)
                self.assertIsNone(world.player.staircase)
                self.assertEqual(world.player.floor, expected)
                self.assertEqual((world.player.x, world.player.ground_y), stair.entrance(expected))
                self.assertFalse(stair.occupants)
                self.assertFalse(stair.queue)

    def test_f5_while_paused_after_a_turn_clears_occupancy_and_held_input(self):
        world, stair = stair_world()
        player = world.player
        steer(world, -1)
        world.step(config.FIXED_DT)
        steer(world, 0)
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertIsNone(player.staircase)
        self.assertFalse(stair.occupants)
        self.assertIsNone(stair.destination_floor)
        self.assertIsNone(world.player.staircase)
        self.assertEqual(world.player.floor, 0)
        self.assertEqual(world.controls.held, {"restart"})
        self.assertEqual(len(world.stage.drop_items), 15)

    def test_forced_scene_change_releases_a_paused_reversed_player(self):
        world, stair = stair_world()
        steer(world, -1)
        world.step(config.FIXED_DT)
        steer(world, 0)
        world.select_stage(1)
        self.assertIsNone(world.player.staircase)
        self.assertFalse(stair.occupants)
        self.assertIsNone(stair.destination_floor)
        world.select_stage(0)
        self.assertFalse(stair.occupants)

    def test_direction_can_change_at_zero_dt_without_moving_the_actor(self):
        world, stair = stair_world()
        before = world.player.x, world.player.ground_y, stair.progress
        steer(world, -1)
        world.stage.update_navigation(0, world.player, world.controls)
        self.assertEqual((world.player.x, world.player.ground_y, stair.progress), before)
        self.assertEqual(stair.destination_floor, 0)

    def test_turning_at_path_corners_remains_continuous(self):
        for floor in (0, 1):
            world, stair = stair_world(floor)
            joints = (stair.lengths[0], sum(stair.lengths[:2]))
            for joint in joints:
                for delta in (-0.5, 0.5):
                    stair.occupants[world.player] = joint + delta
                    stair.update(0)
                    for direction in (1, -1):
                        before = world.player.x, world.player.ground_y
                        steer(world, direction)
                        world.step(config.FIXED_DT)
                        self.assertLessEqual(hypot(world.player.x - before[0],
                                                   world.player.ground_y - before[1]),
                                             config.STAIR_SPEED * config.FIXED_DT + 1e-8)

    def test_pause_and_turn_sequences_are_render_rate_independent(self):
        for floor in (0, 1):
            snapshots = []
            for fps in (30, 60, 120, 144):
                world, stair = stair_world(floor, 0)
                forward = 1 if floor == 0 else -1
                for direction, seconds in ((forward, 0.5), (0, 0.5), (-forward, 1 / 3),
                                           (0, 0.5), (forward, 1 / 3)):
                    steer(world, direction)
                    advance(world, seconds, fps)
                snapshots.append((world.player.x, world.player.ground_y, world.player.floor,
                                  world.player.state, stair.progress, stair.destination_floor))
            self.assertTrue(all(snapshot == snapshots[0] for snapshot in snapshots))

    def test_hud_distinguishes_pausing_and_explains_stop_and_reverse(self):
        world, _ = stair_world()
        ui = UI()
        assets = SimpleNamespace(images={config.HP_IMAGE: Mock(w=700, h=80)}, font=Mock())
        for direction, label in ((0, "계단 정지 중"), (-1, "계단 이동 중")):
            steer(world, direction)
            world.step(config.FIXED_DT)
            assets.font.reset_mock()
            with patch("pico2d.draw_rectangle"):
                ui.draw(assets, world)
            text = [call.args[2] for call in assets.font.draw.call_args_list]
            self.assertTrue(any(label in line and "반전" in line and "정지" in line for line in text))


if __name__ == "__main__":
    unittest.main()
