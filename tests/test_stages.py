import unittest

import config
from combat import MOVES
from effects import HitEffect
from tests.helpers import advance, tap
from world import World


class StageTests(unittest.TestCase):
    def assert_same_motion(self, actual, expected):
        for attribute in ("vx", "vy", "y", "jump_count", "hp", "facing", "grounded", "state"):
            self.assertEqual(getattr(actual, attribute), getattr(expected, attribute), attribute)
        self.assertEqual(actual.animation.elapsed, expected.animation.elapsed)
        self.assertEqual(actual.animation.frame, expected.animation.frame)

    def test_n_reveals_only_the_first_stage_right_arrow_and_is_not_a_toggle(self):
        world = World()
        self.assertEqual(world.stage_index, 0)
        self.assertEqual(world.stage.image_name, "newStage.png")
        self.assertEqual(world.stage.arrow_sides, ())
        world.controls.press("stage_exits")
        advance(world, 0.1)
        self.assertEqual(world.stage.arrow_sides, (1,))
        self.assertEqual(world.stage.destination(1), 1)
        self.assertIsNone(world.stage.destination(-1))
        world.controls.press("stage_exits")
        advance(world, 0.1)
        tap(world.controls, "stage_exits")
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage.arrow_sides, (1,))

    def test_second_stage_has_both_markers_and_an_unavailable_next_destination(self):
        world = World()
        world.stage_index = 1
        self.assertEqual(world.stage.image_name, "newStage-2.png")
        self.assertEqual(world.stage.arrow_sides, ())
        world.controls.press("stage_exits")
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage.arrow_sides, (-1, 1))
        self.assertEqual(world.stage.destination(-1), 0)
        self.assertIsNone(world.stage.destination(1))

    def test_held_n_does_not_reveal_another_stage_without_a_new_press(self):
        world = World()
        world.controls.press("stage_exits")
        world.step(config.FIXED_DT)
        world.stage_index = 1
        advance(world, 0.5)
        self.assertEqual(world.stage.arrow_sides, ())
        tap(world.controls, "stage_exits")
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage.arrow_sides, (-1, 1))

    def test_scenes_keep_independent_enemies_effects_and_spawn_profiles(self):
        world = World()
        world.controls.press("spawn_3")
        world.step(config.FIXED_DT)
        enemies = world.enemies
        effect = HitEffect(500, 180, 1)
        world.effects.append(effect)
        positions = [enemy.x for enemy in enemies]
        world.stage_index = 1
        self.assertEqual(world.enemies, [])
        self.assertEqual(world.effects, [])
        self.assertEqual(world.spawner.spawned_count, 0)
        world.controls.press("spawn_1")
        advance(world, 0.2)
        self.assertEqual(len(world.enemies), 1)
        self.assertEqual(world.enemies[0].run_speed, 360)
        self.assertEqual([enemy.x for enemy in enemies], positions)
        self.assertEqual(effect.elapsed, 0)
        world.stage_index = 0
        self.assertIs(world.enemies, enemies)
        self.assertIs(world.effects[0], effect)
        self.assertEqual(world.spawner.spawned_count, 3)

    def test_dead_n_is_consumed_and_restart_resets_both_scenes(self):
        world = World()
        for index in range(2):
            world.stage_index = index
            tap(world.controls, "stage_exits")
            tap(world.controls, "spawn_2")
            world.step(config.FIXED_DT)
        world.stage.arrows_visible = False
        world.player.take_damage(500)
        tap(world.controls, "stage_exits")
        world.step(config.FIXED_DT)
        self.assertFalse(world.stage.arrows_visible)
        self.assertNotIn("stage_exits", world.controls.pressed)
        world.controls.press("restart")
        world.update(1 / 60)
        self.assertEqual(world.stage_index, 0)
        self.assertTrue(all(stage.arrow_sides == () for stage in world.stages))
        self.assertTrue(all(stage.enemies == [] and stage.effects == [] for stage in world.stages))
        self.assertTrue(all(stage.spawner.spawned_count == 0 for stage in world.stages))

    def test_both_directions_keep_walking_running_and_rising_or_falling_double_jumps(self):
        for side in (-1, 1):
            for state, speed, vertical_speed in (("WALK", 300, 0), ("RUN", 720, 0),
                                                  ("JUMP", 720, 400), ("JUMP", 300, -200)):
                with self.subTest(side=side, state=state, vertical_speed=vertical_speed):
                    world, reference = World(), World()
                    world.stage_index = 0 if side > 0 else 1
                    world.stage.arrows_visible = True
                    for scene in (world, reference):
                        scene.elapsed = 12
                        player = scene.player
                        player.vx = side * speed
                        player.vy = vertical_speed
                        player.facing = side
                        player.hp = 440
                        if state == "JUMP":
                            player.y += 140
                            player.jump_count = 2
                            scene.controls.held.add("jump")
                        scene.controls.held.add("right" if side > 0 else "left")
                        if speed == 720:
                            scene.controls.held.add("left_shift")
                        player.animation.set_state(state)
                        player.animation.elapsed = 0.23
                    world.player.x = (config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
                                      if side > 0 else config.STAGE_EXIT_MARGIN)
                    player, controls = world.player, world.controls
                    held = set(controls.held)
                    world.camera.shake()
                    world.step(config.FIXED_DT)
                    reference.step(config.FIXED_DT)
                    self.assertEqual(world.stage_index, 1 if side > 0 else 0)
                    self.assertIs(world.player, player)
                    self.assertIs(world.controls, controls)
                    self.assertEqual(controls.held, held)
                    self.assert_same_motion(player, reference.player)
                    self.assertAlmostEqual(abs(player.x - player.previous_x), speed * config.FIXED_DT)
                    self.assertEqual(world.camera.shake_remaining, 0)
                    self.assertEqual(world.camera.x, 0 if side > 0 else
                                     config.WORLD_WIDTH - config.SCREEN_WIDTH)
                    advance(world, 0.1)
                    advance(reference, 0.1)
                    self.assert_same_motion(player, reference.player)
                    self.assertEqual(world.elapsed, reference.elapsed)

    def test_travel_requires_visible_markers_and_last_right_edge_stays_in_bounds(self):
        for index, side in ((0, -1), (0, 1), (1, 1)):
            with self.subTest(index=index, side=side):
                world = World()
                world.stage_index = index
                world.stage.arrows_visible = index == 1 or side < 0
                world.player.x = (config.PLAYER_HALF_WIDTH if side < 0 else
                                  config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)
                world.controls.press("left" if side < 0 else "right")
                world.controls.press("left_shift")
                advance(world, 0.5)
                self.assertEqual(world.stage_index, index)
                self.assertGreaterEqual(world.player.x, config.PLAYER_HALF_WIDTH)
                self.assertLessEqual(world.player.x, config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)
                if index == 0 and side > 0:
                    world.controls.press("stage_exits")
                    world.step(config.FIXED_DT)
                    self.assertEqual(world.stage_index, 1)
                    self.assertGreater(world.player.vx, 0)

    def test_n_stays_local_during_travel_and_return_does_not_bounce(self):
        world = World()
        world.controls.press("stage_exits")
        world.controls.press("right")
        world.controls.press("left_shift")
        world.player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
        world.player.vx = 720
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage_index, 1)
        self.assertEqual(world.stage.arrow_sides, ())
        self.assertIn("stage_exits", world.controls.held)
        world.controls.press("stage_exits")
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage.arrow_sides, ())
        tap(world.controls, "stage_exits")
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage.arrow_sides, (-1, 1))
        world.controls.release("right")
        world.controls.press("left")
        world.player.x = config.STAGE_EXIT_MARGIN
        world.player.vx = -720
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage_index, 0)
        self.assertEqual(world.stage.arrow_sides, (1,))
        advance(world, 0.1)
        self.assertEqual(world.stage_index, 0)
        self.assertLess(world.player.x, config.WORLD_WIDTH - config.STAGE_ENTRY_MARGIN)

    def test_real_round_trip_restores_scene_objects_and_pauses_inactive_simulation(self):
        world = World()
        world.controls.press("spawn_3")
        world.step(config.FIXED_DT)
        first = world.stage
        first.enemies[0].take_damage(20)
        first.effects.append(HitEffect(600, 180, 1))
        positions = [enemy.x for enemy in first.enemies]
        world.controls.press("right")
        world.controls.press("left_shift")
        world.controls.press("stage_exits")
        world.player.vx = 720
        world.player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage_index, 1)
        world.controls.press("spawn_2")
        advance(world, 0.2)
        second = world.stage
        self.assertEqual(len(second.enemies), 2)
        self.assertEqual(first.spawner.spawned_count, 3)
        self.assertEqual(first.effects[0].elapsed, 0)
        self.assertEqual([enemy.x for enemy in first.enemies], positions)
        world.controls.release("right")
        world.controls.press("left")
        tap(world.controls, "stage_exits")
        world.player.x = config.STAGE_EXIT_MARGIN
        world.player.vx = -720
        world.step(config.FIXED_DT)
        self.assertIs(world.stage, first)
        self.assertEqual(first.enemies[0].hp, 180)
        self.assertEqual(world.spawner.spawned_count, 3)
        self.assertEqual(first.effects[0].elapsed, config.FIXED_DT)
        self.assertEqual(second.spawner.spawned_count, 2)

    def test_attacks_guard_recoil_hit_and_death_cannot_trigger_travel(self):
        for action in ("combat_q", "combat_h", "HIT", "DYING", "DEAD"):
            with self.subTest(action=action):
                world = World()
                world.stage.arrows_visible = True
                world.controls.press("right")
                world.player.x = config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH
                if action.startswith("combat_"):
                    world.controls.press(action)
                    world.player.start_move(MOVES[action], -1)
                    world.player.vx = 240
                else:
                    world.player.animation.set_state(action)
                    if action in ("DYING", "DEAD"):
                        world.player.hp = 0
                advance(world, 0.1)
                self.assertEqual(world.stage_index, 0)
                self.assertLessEqual(world.player.x, config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)

    def test_round_trip_is_identical_across_render_rates(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world = World()
            for stage in world.stages:
                stage.arrows_visible = True
            world.player.x = config.WORLD_WIDTH - 300
            world.player.vx = 720
            world.controls.press("right")
            world.controls.press("left_shift")
            advance(world, 1, fps)
            self.assertEqual(world.stage_index, 1)
            world.controls.release("right")
            world.controls.press("left")
            advance(world, 1.5, fps)
            self.assertEqual(world.stage_index, 0)
            outcomes.append((world.stage_index, world.player.x, world.player.vx,
                             world.player.y, world.player.state, world.player.animation.frame))
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
