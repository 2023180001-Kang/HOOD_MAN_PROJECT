import random
import unittest

import config
from combat import MOVES
from enemy import Enemy
from tests.helpers import ArchivedTwoFloorTests, advance, tap
from tests.test_stair_controls import stair_world, steer
from tests.test_two_floors import place
from world import World


class StairJumpExitTests(ArchivedTwoFloorTests):
    def test_single_jump_toward_the_steps_catches_without_up_or_a_second_jump(self):
        world = World(item_rng=random.Random(5))
        player = world.player
        place(world, player, 0, 180, 136)
        world.controls.press("right")
        world.controls.press("jump")
        for _ in range(120):
            world.step(config.FIXED_DT)
            if player.staircase is not None:
                break
        self.assertIs(player.staircase, world.stage.stairs[0])
        self.assertGreater(player.ground_y, 136)
        self.assertEqual((player.jump_height, player.vy, player.jump_count), (0, 0, 0))
        advance(world, 0.2)
        self.assertIsNotNone(player.staircase)  # Holding the approach key is not a new exit press.
        world.controls.release("right")
        before = player.ground_y
        steer(world, 1)
        advance(world, 0.2)
        self.assertGreater(player.ground_y, before)
        before = player.ground_y
        steer(world, -1)
        advance(world, 0.1)
        self.assertLess(player.ground_y, before)

    def test_upper_floor_single_jump_can_catch_the_top_of_the_steps_on_descent(self):
        world = World()
        player = world.player
        place(world, player, 1, 500, 476)
        world.controls.press("jump")
        for _ in range(180):
            world.step(config.FIXED_DT)
            if player.staircase is not None:
                break
        self.assertIs(player.staircase, world.stage.stairs[0])
        steer(world, -1)
        advance(world, 0.25)
        self.assertLess(player.ground_y, 476)

    def test_air_catch_does_not_steal_an_enemy_column_or_an_older_waiter(self):
        for occupied in (False, True):
            world = World()
            stair = world.stage.stairs[0]
            enemy = Enemy(stair.entrance(0)[0], ground_y=136)
            stair.request(enemy)
            if occupied:
                stair.start_next()
            place(world, world.player, 0, 252, 136)
            world.player.jump_height, world.player.vy, world.player.jump_count = 35, -100, 1
            world.player.animation.set_state("JUMP")
            self.assertFalse(world.stage.try_player_stair_catch(world.player))
            self.assertIsNone(world.player.staircase)
            self.assertTrue(enemy in stair.occupants or enemy in stair.queue)

    def test_air_catch_rejects_double_jumps_attacks_falling_and_distant_feet(self):
        for blocked in ("double_jump", "attack", "falling", "distant", "dead"):
            world = World()
            player = world.player
            place(world, player, 0, 252, 136)
            player.jump_height, player.vy, player.jump_count = 35, -100, 1
            player.animation.set_state("JUMP")
            if blocked == "double_jump":
                player.jump_count = 2
            elif blocked == "attack":
                player.start_move(MOVES["combat_a"], 1)
            elif blocked == "falling":
                player.falling_from_upper = True
            elif blocked == "distant":
                player.x += 200
            else:
                player.take_damage(config.MAX_HP)
            self.assertFalse(world.stage.try_player_stair_catch(player))
            self.assertIsNone(player.staircase)

    def test_jump_exits_both_travel_directions_at_the_current_visible_feet(self):
        for floor in (0, 1):
            for seconds in (0.2, 1.3):
                world, stair = stair_world(floor, seconds)
                player = world.player
                feet, x = player.y, player.x
                world.controls.press("jump")
                self.assertTrue(world.stage.exit_player_stairs(player, world.controls))
                self.assertIsNone(player.staircase)
                self.assertNotIn(player, stair.occupants)
                self.assertEqual((player.x, player.y), (x, feet))
                self.assertEqual((player.vy, player.jump_count, player.state),
                                 (config.JUMP_SPEED, 1, "JUMP"))
                world.step(config.FIXED_DT)
                self.assertGreater(player.y, feet)
                self.assertIsNone(player.staircase)

    def test_lateral_press_exits_without_teleporting_and_gravity_lands_on_a_real_floor(self):
        for floor in (0, 1):
            for key, sign in (("left", -1), ("right", 1)):
                world, stair = stair_world(floor)
                player = world.player
                feet, x = player.y, player.x
                world.controls.press(key)
                self.assertTrue(world.stage.exit_player_stairs(player, world.controls))
                self.assertEqual((player.x, player.y), (x, feet))
                self.assertIsNone(player.staircase)
                self.assertFalse(stair.occupants)
                advance(world, 0.15)
                self.assertGreater((player.x - x) * sign, 0)
                self.assertLess(player.y, feet)
                world.controls.release(key)
                steer(world, 0)
                advance(world, 2)
                self.assertTrue(player.grounded)
                self.assertTrue(world.stage.area_for(player).contains(player.x, player.ground_y))

    def test_new_horizontal_press_exits_even_while_up_or_down_is_held(self):
        for floor in (0, 1):
            world, stair = stair_world(floor)
            world.controls.press("right")
            world.step(config.FIXED_DT)
            self.assertIsNone(world.player.staircase)
            self.assertNotIn(world.player, stair.occupants)
            self.assertGreater(world.player.vx, 0)

    def test_opposite_horizontal_keys_neutralize_each_other_without_an_exit(self):
        world, stair = stair_world()
        world.controls.press("left")
        world.controls.press("right")
        world.step(config.FIXED_DT)
        self.assertIs(world.player.staircase, stair)

    def test_exit_cooldown_prevents_instant_recatch_and_does_not_repeat_held_space(self):
        world, stair = stair_world()
        world.controls.press("jump")
        world.step(config.FIXED_DT)
        self.assertIsNone(world.player.staircase)
        self.assertGreater(world.player.stair_regrab_remaining, 0)
        self.assertFalse(world.stage.try_player_stair_catch(world.player))
        advance(world, 0.1)
        self.assertIsNone(world.player.staircase)
        self.assertEqual(world.player.jump_count, 1)
        tap(world.controls, "jump")
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.jump_count, 2)
        self.assertNotIn(world.player, stair.occupants)

    def test_exit_releases_the_exclusive_lock_for_waiting_enemies(self):
        world, stair = stair_world()
        enemy = Enemy(500, ground_y=476)
        place(world, enemy, 1, 500, 476)
        world.enemies = [enemy]
        steer(world, -1)
        advance(world, 0.1)
        self.assertIn(enemy, stair.queue)
        world.controls.press("jump")
        world.step(config.FIXED_DT)
        self.assertIsNone(world.player.staircase)
        self.assertIs(enemy.staircase, stair)

    def test_f5_and_scene_travel_clear_the_regrab_delay(self):
        for reset in ("restart", "travel"):
            world, _ = stair_world()
            world.controls.press("jump")
            world.step(config.FIXED_DT)
            self.assertGreater(world.player.stair_regrab_remaining, 0)
            if reset == "restart":
                world.controls.press("restart")
                world.update(config.FIXED_DT)
            else:
                world.select_stage(1)
            self.assertEqual(world.player.stair_regrab_remaining, 0)
            self.assertIsNone(world.player.staircase)

    def test_exit_and_falling_are_render_rate_independent(self):
        snapshots = []
        for fps in (30, 60, 120, 144):
            world, _ = stair_world()
            world.controls.press("right")
            advance(world, 0.5, fps)
            player = world.player
            snapshots.append((player.x, player.y, player.vy, player.floor, player.jump_count))
        self.assertTrue(all(snapshot == snapshots[0] for snapshot in snapshots))


if __name__ == "__main__":
    unittest.main()
