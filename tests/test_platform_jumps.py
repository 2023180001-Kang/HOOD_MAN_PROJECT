import unittest

import config
from enemy import Enemy
from tests.helpers import advance, tap
from tests.test_two_floors import begin_player_stairs, place
from world import World


def double_jump(world, delay=0.05):
    world.controls.press("jump")
    advance(world, delay, 120)
    tap(world.controls, "jump")
    world.step(config.FIXED_DT)


def until(world, condition, frames=600):
    for _ in range(frames):
        world.step(config.FIXED_DT)
        if condition():
            return
    raise AssertionError("Expected movement did not complete")


class PlatformJumpTests(unittest.TestCase):
    def test_double_jump_then_reverse_and_steer_up_lands_on_the_upper_floor(self):
        for running in (False, True):
            for direction in (-1, 1):
                with self.subTest(running=running, direction=direction):
                    world = World()
                    place(world, world.player, 0, 1280, 100)
                    first = "right" if direction > 0 else "left"
                    reverse = "left" if direction > 0 else "right"
                    world.controls.press(first)
                    if running:
                        world.controls.press("left_shift")
                    double_jump(world)
                    world.controls.release(first)
                    world.controls.press(reverse)
                    world.controls.press("up")
                    until(world, lambda: world.player.floor == 1)
                    self.assertTrue(world.player.grounded)
                    self.assertEqual(world.player.ground_y, 452)
                    self.assertEqual(world.player.jump_count, 0)
                    self.assertEqual(world.player.facing, -direction)
                    self.assertLess((world.player.x - 1280) * direction, 0)
                    self.assertIsNone(world.player.staircase)
                    self.assertIsNone(world.stage.stairs[0].occupant)

    def test_early_and_late_second_jump_can_reach_the_ledge_from_every_lower_depth(self):
        for depth in (56, 100, 136):
            for delay in (config.FIXED_DT, 0.05, 0.35, 0.6):
                with self.subTest(depth=depth, delay=delay):
                    world = World()
                    place(world, world.player, 0, 1280, depth)
                    double_jump(world, delay)
                    world.controls.press("up")
                    until(world, lambda: world.player.floor == 1)
                    self.assertEqual(world.player.jump_height, 0)
                    self.assertEqual(world.player.hp, config.MAX_HP)

    def test_upper_landing_requires_up_not_merely_a_high_jump(self):
        world = World()
        double_jump(world)
        maximum = 0
        for _ in range(300):
            world.step(config.FIXED_DT)
            maximum = max(maximum, world.player.y)
            self.assertEqual(world.player.floor, 0)
        self.assertGreater(maximum, world.stage.upper_walkable.bounds[1])
        self.assertTrue(world.player.grounded)
        self.assertFalse(world.player.upper_landing_requested)

    def test_single_jump_with_up_does_not_change_floors(self):
        world = World()
        world.controls.press("jump")
        world.controls.press("up")
        advance(world, 2)
        self.assertEqual(world.player.floor, 0)
        self.assertTrue(world.player.grounded)
        self.assertFalse(world.player.upper_landing_requested)

    def test_platform_is_one_way_and_landing_occurs_only_on_the_descending_crossing(self):
        world = World()
        double_jump(world)
        world.controls.press("up")
        until(world, lambda: world.player.y > 452)
        self.assertGreater(world.player.vy, 0)
        self.assertEqual(world.player.floor, 0)
        until(world, lambda: world.player.floor == 1)
        self.assertEqual((world.player.y, world.player.vy), (452, 0))

    def test_up_intent_survives_turning_left_or_right_before_landing(self):
        world = World()
        double_jump(world)
        world.controls.press("up")
        advance(world, 0.1)
        self.assertTrue(world.player.upper_landing_requested)
        world.controls.release("up")
        world.controls.press("right")
        until(world, lambda: world.player.floor == 1)
        self.assertGreater(world.player.x, config.START_X)
        self.assertFalse(world.player.upper_landing_requested)

    def test_down_cancels_an_armed_upper_landing(self):
        world = World()
        double_jump(world)
        world.controls.press("up")
        advance(world, 0.2)
        world.controls.release("up")
        world.controls.press("down")
        advance(world, 2)
        self.assertEqual(world.player.floor, 0)
        self.assertTrue(world.player.grounded)
        self.assertFalse(world.player.upper_landing_requested)

    def test_third_space_does_not_refresh_the_boost(self):
        world = World()
        double_jump(world)
        before = world.player.vy
        tap(world.controls, "jump")
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.jump_count, 2)
        self.assertAlmostEqual(world.player.vy, before - config.GRAVITY * config.FIXED_DT)

    def test_first_map_jump_height_fits_the_screen_and_keeps_depth_independent_physics(self):
        results = []
        for depth in (56, 136):
            world = World()
            place(world, world.player, 0, 1280, depth)
            double_jump(world)
            maximum = 0
            heights = []
            for _ in range(200):
                world.step(config.FIXED_DT)
                maximum = max(maximum, world.player.y)
                heights.append((world.player.jump_height, world.player.vy))
            self.assertLessEqual(maximum + config.PLAYER_HEIGHT, config.SCREEN_HEIGHT)
            results.append(heights)
        self.assertEqual(results[0], results[1])

    def test_landing_does_not_teleport_the_feet_through_the_floor_gap(self):
        world = World()
        double_jump(world)
        world.controls.press("up")
        until(world, lambda: world.player.vy < 0)
        while world.player.floor == 0:
            before = world.player.y
            world.step(config.FIXED_DT)
            self.assertLess(abs(world.player.y - before), 12)
        self.assertEqual(world.player.y, 452)
        self.assertEqual(world.player.floor, 1)

    def test_upstairs_controls_work_after_a_jump_landing(self):
        world = World()
        double_jump(world)
        world.controls.press("up")
        until(world, lambda: world.player.floor == 1)
        advance(world, 0.1)
        self.assertGreater(world.player.ground_y, 452)
        self.assertLessEqual(world.player.ground_y, 502)
        world.controls.release("up")
        advance(world, 0.1)
        original = world.player.ground_y
        world.controls.press("down")
        advance(world, 0.025, 120)
        self.assertGreater(world.player.ground_y, 452)
        self.assertLess(world.player.ground_y, original)
        self.assertEqual(world.player.floor, 1)

    def test_other_maps_keep_the_original_normal_and_running_second_jump_speeds(self):
        for stage in range(1, len(config.STAGE_IMAGES)):
            for running in (False, True):
                world = World()
                world.select_stage(stage)
                world.controls.press("right")
                if running:
                    world.controls.press("left_shift")
                double_jump(world)
                expected = config.RUN_DOUBLE_JUMP_SPEED if running else config.DOUBLE_JUMP_SPEED
                self.assertAlmostEqual(world.player.vy, expected - config.GRAVITY * config.FIXED_DT)
                self.assertEqual(world.player.floor, 0)

    def test_upstairs_second_jump_is_not_boosted_again(self):
        world = World()
        place(world, world.player, 1, 1280, 476)
        double_jump(world)
        self.assertAlmostEqual(world.player.vy,
                               config.DOUBLE_JUMP_SPEED - config.GRAVITY * config.FIXED_DT)
        advance(world, 2)
        self.assertEqual(world.player.floor, 1)

    def test_walking_down_inside_the_upper_floor_drops_only_at_the_front_edge(self):
        world = World()
        place(world, world.player, 1, 1280, 502)
        world.controls.press("down")
        advance(world, 0.1)
        self.assertEqual(world.player.floor, 1)
        self.assertGreater(world.player.ground_y, 452)
        until(world, lambda: world.player.falling_from_upper)
        self.assertEqual(world.player.floor, 0)
        self.assertEqual(world.player.y, 452)
        self.assertEqual(world.player.ground_y, 136)
        self.assertEqual(world.player.jump_height, 316)
        self.assertFalse(world.player.grounded)

    def test_standing_at_the_upper_edge_without_down_does_not_drop(self):
        world = World()
        place(world, world.player, 1, 1280, 452)
        advance(world, 1)
        self.assertEqual((world.player.floor, world.player.ground_y), (1, 452))
        self.assertFalse(world.player.falling_from_upper)

    def test_fall_keeps_feet_continuous_uses_gravity_and_deals_no_damage(self):
        world = World()
        place(world, world.player, 1, 1280, 452)
        world.controls.press("down")
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.y, 452)
        world.controls.release("down")
        for _ in range(30):
            before_y, before_vy = world.player.y, world.player.vy
            world.step(config.FIXED_DT)
            self.assertAlmostEqual(world.player.vy, before_vy - config.GRAVITY * config.FIXED_DT)
            self.assertAlmostEqual(world.player.y, before_y + world.player.vy * config.FIXED_DT)
        until(world, lambda: world.player.grounded)
        self.assertEqual(world.player.floor, 0)
        self.assertEqual(world.player.ground_y, 136)
        self.assertFalse(world.player.falling_from_upper)
        self.assertEqual(world.player.jump_count, 0)
        self.assertEqual(world.player.hp, config.MAX_HP)

    def test_falling_allows_horizontal_steering_but_not_an_extra_jump_or_upper_recatch(self):
        world = World()
        place(world, world.player, 1, 1280, 452)
        world.controls.press("down")
        world.step(config.FIXED_DT)
        world.controls.release("down")
        world.controls.press("right")
        world.controls.press("up")
        world.controls.press("jump")
        world.step(config.FIXED_DT)
        self.assertLess(world.player.vy, 0)
        self.assertTrue(world.player.falling_from_upper)
        self.assertEqual(world.player.jump_count, 2)
        self.assertEqual(world.player.floor, 0)
        advance(world, 0.2)
        self.assertGreater(world.player.x, 1280)
        self.assertEqual(world.player.floor, 0)

    def test_jump_off_the_upper_edge_preserves_existing_vertical_momentum(self):
        world = World()
        place(world, world.player, 1, 1280, 452)
        world.controls.press("jump")
        world.step(config.FIXED_DT)
        before_y, before_vy = world.player.y, world.player.vy
        world.controls.press("down")
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.floor, 0)
        self.assertTrue(world.player.falling_from_upper)
        self.assertAlmostEqual(world.player.vy, before_vy - config.GRAVITY * config.FIXED_DT)
        self.assertGreater(world.player.y, before_y)

    def test_stairs_still_own_the_player_and_keep_single_occupancy(self):
        world = World()
        stair = begin_player_stairs(world, 1)
        world.controls.press("down")
        advance(world, 0.4)
        self.assertIs(world.player.staircase, stair)
        self.assertIs(stair.occupant, world.player)
        self.assertFalse(world.player.falling_from_upper)
        self.assertEqual(world.player.jump_height, 0)

    def test_jump_and_drop_do_not_take_an_enemys_staircase_lock(self):
        world = World()
        place(world, world.player, 0, 1280, 100)
        enemy = Enemy(500, ground_y=476)
        place(world, enemy, 1, 500, 476)
        world.enemies = [enemy]
        world.step(config.FIXED_DT)
        stair = world.stage.stairs[0]
        self.assertIs(stair.occupant, enemy)
        double_jump(world)
        world.controls.press("up")
        until(world, lambda: world.player.floor == 1)
        self.assertIs(stair.occupant, enemy)
        world.controls.release("up")
        world.controls.press("down")
        world.step(config.FIXED_DT)
        self.assertTrue(world.player.falling_from_upper)
        self.assertIs(stair.occupant, enemy)
        self.assertIsNone(world.player.staircase)

    def test_f5_clears_jump_landing_and_falling_state(self):
        for dropping in (False, True):
            world = World()
            if dropping:
                place(world, world.player, 1, 1280, 452)
                world.controls.press("down")
                world.step(config.FIXED_DT)
                self.assertTrue(world.player.falling_from_upper)
            else:
                double_jump(world)
                world.controls.press("up")
                world.step(config.FIXED_DT)
                self.assertTrue(world.player.upper_landing_requested)
            world.controls.press("restart")
            world.update(config.FIXED_DT)
            self.assertEqual(world.player.floor, 0)
            self.assertFalse(world.player.falling_from_upper)
            self.assertFalse(world.player.upper_landing_requested)
            self.assertTrue(world.player.grounded)
            self.assertEqual(len(world.stage.drop_items), 15)

    def test_selecting_another_stage_clears_platform_requests_and_fall_flags(self):
        world = World()
        double_jump(world)
        world.controls.press("up")
        world.step(config.FIXED_DT)
        self.assertTrue(world.player.upper_landing_requested)
        world.select_stage(1)
        self.assertFalse(world.player.upper_landing_requested)
        self.assertFalse(world.player.falling_from_upper)
        self.assertEqual(world.player.floor, 0)

    def test_jump_land_and_drop_are_identical_at_different_render_rates(self):
        results = []
        for fps in (30, 60, 120, 144):
            world = World()
            double_jump(world)
            world.controls.press("up")
            advance(world, 1.5, fps)
            self.assertEqual(world.player.floor, 1)
            world.controls.release("up")
            world.controls.press("down")
            advance(world, 0.5, fps)
            results.append((world.player.floor, world.player.x, world.player.ground_y,
                            world.player.jump_height, world.player.vy))
        self.assertTrue(all(result == results[0] for result in results))


if __name__ == "__main__":
    unittest.main()
