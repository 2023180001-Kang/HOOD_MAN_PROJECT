import unittest
from unittest.mock import patch

import config
from tests.helpers import advance, tap
from world import World


class JumpCameraTests(unittest.TestCase):
    def running_double_jump_distance(self, direction=1):
        world = World(spawn_schedule=())
        world.player.x = 350 if direction > 0 else config.WORLD_WIDTH - 350
        world.controls.press("right" if direction > 0 else "left")
        world.controls.press("left_shift")
        advance(world, 0.5)
        start = world.player.x
        world.controls.press("jump")
        advance(world, 0.5)
        tap(world.controls, "jump")
        world.update(1 / 60)
        self.assertEqual(world.player.jump_count, 2)
        for _ in range(180):
            world.update(1 / 60)
            if world.player.grounded:
                break
        self.assertTrue(world.player.grounded)
        self.assertGreater(world.player.x, config.PLAYER_HALF_WIDTH)
        self.assertLess(world.player.x, config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)
        return (world.player.x - start) * direction

    def test_running_double_jump_adds_range_beyond_the_speed_increase(self):
        for direction in (-1, 1):
            with self.subTest(direction=direction):
                with patch.object(config, "RUN_DOUBLE_JUMP_SPEED", config.DOUBLE_JUMP_SPEED):
                    normal = self.running_double_jump_distance(direction)
                extended = self.running_double_jump_distance(direction)
                self.assertGreater(extended - normal, 100)

    def test_running_double_jump_travels_more_than_twice_the_original_range(self):
        with patch.multiple(config, RUN_SPEED=360.0, WALK_SPEED=180.0,
                            ACCELERATION=1000.0, FRICTION=1200.0,
                            RUN_DOUBLE_JUMP_SPEED=600.0):
            original = self.running_double_jump_distance()
        improved = self.running_double_jump_distance()
        self.assertGreater(improved, original * 2)

    def test_shift_alone_does_not_boost_a_stationary_double_jump(self):
        world = World(spawn_schedule=())
        world.controls.press("left_shift")
        world.controls.press("jump")
        advance(world, 0.2)
        tap(world.controls, "jump")
        world.step(config.FIXED_DT)
        self.assertAlmostEqual(world.player.vy,
                               config.DOUBLE_JUMP_SPEED - config.GRAVITY * config.FIXED_DT)
        self.assertEqual(world.player.x, config.START_X)

    def test_double_jump_needs_two_distinct_presses_and_third_is_blocked(self):
        world = World(spawn_schedule=())
        world.controls.press("jump")
        world.update(1 / 60)
        self.assertEqual(world.player.jump_count, 1)
        self.assertGreater(world.player.y, config.GROUND_Y)
        world.controls.press("jump")  # Key repeat must not count.
        advance(world, 0.1)
        self.assertEqual(world.player.jump_count, 1)
        tap(world.controls, "jump")
        world.update(1 / 60)
        self.assertEqual(world.player.jump_count, 2)
        self.assertGreater(world.player.vy, 0)
        before = world.player.vy
        tap(world.controls, "jump")
        world.update(1 / 60)
        self.assertEqual(world.player.jump_count, 2)
        self.assertLess(world.player.vy, before)

    def test_landing_resets_jumps_but_held_space_does_not_auto_jump(self):
        world = World(spawn_schedule=())
        world.controls.press("jump")
        advance(world, 2)
        self.assertTrue(world.player.grounded)
        self.assertEqual(world.player.jump_count, 0)
        self.assertEqual(world.player.y, config.GROUND_Y)
        tap(world.controls, "jump")
        world.update(1 / 60)
        self.assertEqual(world.player.jump_count, 1)

    def test_air_control_and_jump_animation_take_priority(self):
        world = World(spawn_schedule=())
        for key in ("right", "left_shift", "jump"):
            world.controls.press(key)
        advance(world, 0.2)
        self.assertGreater(world.player.x, config.START_X)
        self.assertEqual(world.player.state, "JUMP")
        self.assertEqual(world.player.animation.row, 4)

    def test_camera_follows_and_clamps_at_both_map_edges(self):
        world = World(spawn_schedule=())
        self.assertEqual(world.camera.x, config.START_X - config.SCREEN_WIDTH / 2)
        for key, expected in (("left", 0),
                              ("right", config.WORLD_WIDTH - config.SCREEN_WIDTH)):
            world.controls.held.clear()
            world.controls.press(key)
            world.controls.press("left_shift")
            advance(world, 10)
            self.assertEqual(world.camera.x, expected)

    def test_jump_height_is_independent_of_render_frame_rate(self):
        results = []
        for fps in (30, 60, 120, 144):
            world = World(spawn_schedule=())
            world.controls.press("jump")
            advance(world, 0.5, fps)
            results.append((world.player.y, world.player.vy))
        for height, velocity in results:
            self.assertAlmostEqual(height, results[0][0], places=6)
            self.assertAlmostEqual(velocity, results[0][1], places=6)


if __name__ == "__main__":
    unittest.main()
