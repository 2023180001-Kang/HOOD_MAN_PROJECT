import unittest

import config
from tests.helpers import advance, tap
from world import World


class JumpCameraTests(unittest.TestCase):
    def test_double_jump_needs_two_distinct_presses_and_third_is_blocked(self):
        world = World()
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
        world = World()
        world.controls.press("jump")
        advance(world, 2)
        self.assertTrue(world.player.grounded)
        self.assertEqual(world.player.jump_count, 0)
        self.assertEqual(world.player.y, config.GROUND_Y)
        tap(world.controls, "jump")
        world.update(1 / 60)
        self.assertEqual(world.player.jump_count, 1)

    def test_air_control_and_jump_animation_take_priority(self):
        world = World()
        for key in ("right", "left_shift", "jump"):
            world.controls.press(key)
        advance(world, 0.2)
        self.assertGreater(world.player.x, config.START_X)
        self.assertEqual(world.player.state, "JUMP")
        self.assertEqual(world.player.animation.row, 4)

    def test_camera_follows_and_clamps_at_both_map_edges(self):
        world = World()
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
            world = World()
            world.controls.press("jump")
            advance(world, 0.5, fps)
            results.append((world.player.y, world.player.vy))
        for height, velocity in results:
            self.assertAlmostEqual(height, results[0][0], places=6)
            self.assertAlmostEqual(velocity, results[0][1], places=6)


if __name__ == "__main__":
    unittest.main()
