import unittest

import config
from world import World
from tests.helpers import advance


class MovementTests(unittest.TestCase):
    def test_run_accelerates_and_release_stops_without_reversing(self):
        world = World(spawn_schedule=())
        world.controls.press("right")
        world.controls.press("left_shift")
        world.update(1 / 60)
        self.assertGreater(world.player.vx, 0)
        self.assertLess(world.player.vx, config.RUN_SPEED)
        advance(world, 0.5)
        self.assertEqual(world.player.vx, config.RUN_SPEED)
        world.controls.release("right")
        advance(world, 1)
        self.assertEqual(world.player.vx, 0)
        self.assertEqual(world.player.state, "IDLE")

    def test_shift_release_slows_to_walk_and_reversal_is_gradual(self):
        world = World(spawn_schedule=())
        world.controls.press("right")
        world.controls.press("right_shift")
        advance(world, 0.5)
        world.controls.release("right_shift")
        world.update(1 / 60)
        self.assertGreater(world.player.vx, config.WALK_SPEED)
        advance(world, 0.5)
        self.assertEqual(world.player.vx, config.WALK_SPEED)
        world.controls.release("right")
        world.controls.press("left")
        world.update(1 / 60)
        self.assertGreater(world.player.vx, 0)
        advance(world, 0.5)
        self.assertEqual(world.player.vx, -config.WALK_SPEED)
        self.assertEqual(world.player.facing, -1)

    def test_opposite_keys_cancel_and_shift_alone_does_not_move(self):
        world = World(spawn_schedule=())
        for key in ("left", "right", "left_shift"):
            world.controls.press(key)
        advance(world, 0.5)
        self.assertEqual(world.player.x, config.START_X)
        world.controls.release("left")
        world.controls.release("right")
        advance(world, 0.5)
        self.assertEqual(world.player.x, config.START_X)

    def test_frame_rates_produce_the_same_simulation(self):
        positions = []
        for fps in (30, 60, 120, 144):
            world = World(spawn_schedule=())
            world.controls.press("right")
            world.controls.press("left_shift")
            advance(world, 1, fps)
            positions.append(world.player.x)
        for position in positions:
            self.assertAlmostEqual(position, positions[0], places=6)
            self.assertLess(position, config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)

    def test_requested_walk_and_double_run_speeds_are_reached(self):
        for running, expected in ((False, 300.0), (True, 720.0)):
            with self.subTest(running=running):
                world = World(spawn_schedule=())
                world.controls.press("right")
                if running:
                    world.controls.press("left_shift")
                advance(world, 0.5)
                self.assertEqual(world.player.vx, expected)
        self.assertGreater(config.WALK_SPEED, 180)
        self.assertLess(config.WALK_SPEED, config.RUN_SPEED)

    def test_full_speed_turn_stops_forward_slide_within_tenth_second(self):
        for direction, key, opposite in ((1, "right", "left"), (-1, "left", "right")):
            with self.subTest(direction=direction):
                world = World(spawn_schedule=())
                world.controls.press(key)
                world.controls.press("left_shift")
                advance(world, 0.5)
                self.assertEqual(world.player.vx, direction * 720)
                start = world.player.x
                world.controls.release(key)
                world.controls.press(opposite)
                advance(world, 0.1)
                self.assertLessEqual(world.player.vx * direction, 0)
                self.assertLess((world.player.x - start) * direction, 35)
                advance(world, 0.3)
                self.assertEqual(world.player.vx, -direction * 720)

    def test_full_speed_release_stops_quickly_without_drifting(self):
        world = World(spawn_schedule=())
        world.controls.press("right")
        world.controls.press("left_shift")
        advance(world, 0.5)
        start = world.player.x
        world.controls.release("right")
        advance(world, 0.1)
        self.assertEqual(world.player.vx, 0)
        self.assertLess(world.player.x - start, 35)
        stopped = world.player.x
        advance(world, 0.5)
        self.assertEqual(world.player.x, stopped)

    def test_world_boundaries_stop_the_player(self):
        for key, expected in (("left", config.PLAYER_HALF_WIDTH),
                              ("right", config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)):
            world = World(spawn_schedule=())
            world.controls.press(key)
            world.controls.press("left_shift")
            advance(world, 10)
            self.assertEqual(world.player.x, expected)
            self.assertEqual(world.player.vx, 0)


if __name__ == "__main__":
    unittest.main()
