import unittest

import config
from enemy import Enemy
from enemy02 import Enemy02
from tests.helpers import advance
from tests.test_rush_flight import capture_enemy, launch
from tests.test_strong_attacks import encounter


INPUTS = (("up",), ("down",), ("up", "down"),
          ("right", "up"), ("right", "down"), ("left", "up"), ("left", "down"))


def steer(world, keys):
    for key in ("left", "right", "up", "down"):
        world.controls.release(key)
    for key in keys:
        world.controls.press(key)


class HorizontalRushTests(unittest.TestCase):
    def test_vertical_input_during_launch_and_flight_never_changes_depth(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for side in (-1, 1):
                for keys in INPUTS[:3]:
                    with self.subTest(weapon=weapon, side=side, keys=keys):
                        world, _ = encounter(side=side, weapon=weapon)
                        world.enemies.clear()
                        steer(world, keys)
                        depth = world.player.ground_y
                        launch(world)
                        for _ in range(30):
                            before = world.player.x
                            world.step(config.FIXED_DT)
                            self.assertEqual(world.player.ground_y, depth)
                            self.assertEqual(world.player.ground_vy, 0)
                            self.assertEqual(world.player.facing, side)
                            self.assertAlmostEqual(world.player.x - before,
                                                   side * config.RUSH_SPEED * config.FIXED_DT)

    def test_diagonal_input_keeps_full_horizontal_speed_instead_of_normalizing(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for keys in INPUTS[3:]:
                with self.subTest(weapon=weapon, keys=keys):
                    world, _ = encounter(weapon=weapon)
                    world.enemies.clear()
                    steer(world, keys)
                    launch(world)
                    player = world.player
                    side = world.controls.direction
                    x, depth, height = player.x, player.ground_y, player.jump_height
                    world.step(config.FIXED_DT)
                    self.assertEqual((player.vx, player.ground_vy), (side * config.RUSH_SPEED, 0))
                    self.assertAlmostEqual(player.x - x, side * config.RUSH_SPEED * config.FIXED_DT)
                    self.assertEqual((player.ground_y, player.jump_height), (depth, height))
                    self.assertEqual(player.animation.frame, config.RUSH_PLAYER_HOLD_FRAME)

    def test_neutral_vertical_and_opposing_inputs_keep_the_last_horizontal_direction(self):
        for side in (-1, 1):
            world, _ = encounter(side=side)
            world.enemies.clear()
            launch(world)
            steer(world, ("left" if side > 0 else "right", "up"))
            world.step(config.FIXED_DT)
            for keys in ((), *INPUTS[:3], ("left", "right", "up", "down")):
                with self.subTest(side=side, keys=keys):
                    steer(world, keys)
                    depth = world.player.ground_y
                    world.step(config.FIXED_DT)
                    self.assertEqual(world.player.facing, -side)
                    self.assertEqual(world.rush.direction, -side)
                    self.assertEqual(world.player.vx, -side * config.RUSH_SPEED)
                    self.assertEqual((world.player.ground_y, world.player.ground_vy), (depth, 0))

    def test_captives_stay_at_the_horizontal_front_without_taking_damage_again(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for enemy_type in (Enemy, Enemy02):
                world, enemy = encounter(enemy_type, weapon=weapon)
                capture_enemy(world, enemy)
                sequence = world.rush
                depth = world.player.ground_y
                for keys in INPUTS:
                    with self.subTest(weapon=weapon, enemy=enemy_type, keys=keys):
                        steer(world, keys)
                        world.step(config.FIXED_DT)
                        side = world.player.facing
                        self.assertIs(world.rush, sequence)
                        self.assertAlmostEqual(enemy.x - world.player.x, side * config.RUSH_CARRY_DISTANCE)
                        self.assertEqual((world.player.ground_y, enemy.ground_y), (depth, depth))
                        self.assertEqual((world.player.ground_vy, enemy.ground_vy), (0, 0))
                        self.assertEqual((enemy.facing, enemy.hp, enemy.state), (-side, 150, "RUSH_CARRIED"))
                        self.assertEqual(len(world.damage_numbers), 1)

    def test_vertical_input_does_not_change_which_horizontal_side_can_be_hit(self):
        for side in (-1, 1):
            for key in ("up", "down"):
                for front in (True, False):
                    with self.subTest(side=side, key=key, front=front):
                        world, _ = encounter(side=side)
                        world.enemies.clear()
                        steer(world, (key,))
                        launch(world)
                        player = world.player
                        enemy = Enemy(player.x + side * (10 if front else -10), -side,
                                      ground_y=player.ground_y)
                        enemy.animation.set_state("HIT")
                        enemy.cooldown = 100
                        world.enemies = [enemy]
                        world.step(config.FIXED_DT)
                        self.assertEqual(enemy.hp, 150 if front else 200)
                        self.assertEqual(enemy in world.rush.captives, front)

    def test_release_while_vertical_keys_are_held_only_slides_the_enemy_horizontally(self):
        for enemy_type in (Enemy, Enemy02):
            for side in (-1, 1):
                for key in ("up", "down"):
                    with self.subTest(enemy=enemy_type, side=side, key=key):
                        world, enemy = encounter(enemy_type, side)
                        capture_enemy(world, enemy)
                        steer(world, (key,))
                        world.step(config.FIXED_DT)
                        px, ex, depth = world.player.x, enemy.x, world.player.ground_y
                        world.controls.release("combat_w")
                        world.step(config.FIXED_DT)
                        self.assertIsNone(world.rush)
                        self.assertEqual((world.player.x, world.player.ground_y), (px, depth))
                        self.assertEqual((world.player.vx, world.player.ground_vy), (0, 0))
                        self.assertEqual((enemy.ground_y, enemy.ground_vy), (depth, 0))
                        self.assertAlmostEqual(enemy.x - ex,
                                               side * config.RUSH_RELEASE_SPEED * config.FIXED_DT)

    def test_starting_w_clears_existing_vertical_momentum(self):
        world, _ = encounter()
        world.enemies.clear()
        world.player.ground_vy = config.RUN_SPEED
        steer(world, ("up", "right_shift"))
        depth = world.player.ground_y
        launch(world)
        self.assertEqual((world.player.ground_y, world.player.ground_vy), (depth, 0))
        advance(world, 0.1)
        self.assertEqual((world.player.ground_y, world.player.ground_vy), (depth, 0))

    def test_normal_vertical_walking_resumes_after_w_recovery(self):
        for key, side in (("up", 1), ("down", -1)):
            with self.subTest(key=key):
                world, _ = encounter()
                world.enemies.clear()
                launch(world)
                steer(world, (key,))
                world.step(config.FIXED_DT)
                depth = world.player.ground_y
                self.assertEqual(world.player.ground_vy, 0)
                world.controls.release("combat_w")
                advance(world, 0.5)
                self.assertIsNone(world.player.rush_phase)
                self.assertGreater((world.player.ground_y - depth) * side, 0)

    def test_vertical_keys_at_every_stage_floor_edge_keep_the_pair_at_the_same_depth(self):
        for stage in range(len(config.STAGE_IMAGES)):
            for edge in (1, 3):
                for enemy_type in (Enemy, Enemy02):
                    for side in (-1, 1):
                        with self.subTest(stage=stage, edge=edge, enemy=enemy_type, side=side):
                            world, enemy = encounter(enemy_type, side)
                            world.select_stage(stage)
                            world.stage.traffic = None
                            depth = world.stage.walkable.bounds[edge]
                            world.player.ground_y = enemy.ground_y = depth
                            world.enemies = [enemy]
                            capture_enemy(world, enemy)
                            for key in ("up", "down"):
                                steer(world, (key,))
                                for _ in range(5):
                                    world.step(config.FIXED_DT)
                                    self.assertEqual((world.player.ground_y, enemy.ground_y),
                                                     (depth, depth))
                                    for actor in (world.player, enemy):
                                        self.assertTrue(world.stage.walkable.contains(
                                            actor.x, actor.ground_y, actor.boundary_padding))

    def test_horizontal_flight_and_release_with_vertical_input_are_render_rate_independent(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world, enemy = encounter()
            capture_enemy(world, enemy)
            depth = world.player.ground_y
            for keys in (("up",), ("left", "down"), ("down",), ()):
                steer(world, keys)
                advance(world, 0.1, fps)
            world.controls.release("combat_w")
            advance(world, 0.1, fps)
            self.assertEqual((world.player.ground_y, enemy.ground_y), (depth, depth))
            outcomes.append((world.player.x, world.player.vx, world.player.rush_phase,
                             enemy.x, enemy.vx, enemy.hp, enemy.state))
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
