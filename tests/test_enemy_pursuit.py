import unittest

import config
from enemy import Enemy
from tests.helpers import advance, tap
from world import World


class EnemyPursuitTests(unittest.TestCase):
    def test_thresholds_preserve_run_mode_between_entry_and_exit(self):
        world = World()
        enemy = Enemy(500, run_speed=420)
        for gap, expected_state, expected_speed in (
            (359, "WALK", 120),
            (360, "RUN", 420),
            (300, "RUN", 420),
            (221, "RUN", 420),
            (220, "WALK", 120),
            (300, "WALK", 120),
            (360, "RUN", 420),
            (88, "ATTACK", 0),
        ):
            with self.subTest(gap=gap, expected=expected_state):
                enemy.x = 500
                world.player.x = 500 + gap
                enemy.update(config.FIXED_DT, world.player)
                self.assertEqual(enemy.state, expected_state)
                self.assertEqual(enemy.vx, expected_speed)
                self.assertEqual(enemy.running, expected_state == "RUN")
                if enemy.running:
                    self.assertEqual(enemy.animation.row, 3)

    def test_individual_run_speeds_produce_different_travel_distances(self):
        world = World()
        world.enemies = [Enemy(300, run_speed=speed) for speed in config.ENEMY_RUN_SPEEDS]
        advance(world, 0.5)
        self.assertEqual(len({enemy.x for enemy in world.enemies}), 4)
        for enemy, speed in zip(world.enemies, config.ENEMY_RUN_SPEEDS):
            self.assertEqual(enemy.state, "RUN")
            self.assertAlmostEqual(enemy.x - 300, speed * 0.5, places=6)
            self.assertEqual(enemy.vx, speed)
            self.assertGreater(speed, config.ENEMY_SPEED)

    def test_both_directions_use_run_animation_and_instance_speed(self):
        for direction in (-1, 1):
            with self.subTest(direction=direction):
                world = World()
                enemy = Enemy(config.START_X, run_speed=480)
                world.player.x += direction * 500
                world.player.y += 180
                enemy.update(config.FIXED_DT, world.player)
                self.assertEqual(enemy.facing, direction)
                self.assertEqual(enemy.vx, direction * 480)
                self.assertEqual(enemy.state, "RUN")
                self.assertEqual(enemy.animation.row, 3)

    def test_player_sprinting_and_jumping_away_triggers_different_run_speeds(self):
        world = World()
        world.enemies = [Enemy(config.START_X - 280, run_speed=speed)
                         for speed in config.ENEMY_RUN_SPEEDS]
        world.step(config.FIXED_DT)
        self.assertTrue(all(enemy.state == "WALK" for enemy in world.enemies))
        for key in ("right", "left_shift", "jump"):
            world.controls.press(key)
        advance(world, 0.5)
        self.assertGreater(world.player.y, config.GROUND_Y)
        self.assertTrue(all(enemy.state == "RUN" for enemy in world.enemies))
        self.assertEqual([enemy.vx for enemy in world.enemies], list(config.ENEMY_RUN_SPEEDS))
        self.assertEqual(len({enemy.x for enemy in world.enemies}), 4)

    def test_attack_finishes_before_resuming_a_distant_run_chase(self):
        world = World()
        enemy = Enemy(config.START_X - 80, run_speed=540)
        enemy.update(config.FIXED_DT, world.player)
        self.assertEqual(enemy.state, "ATTACK")
        world.player.x += 600
        enemy.update(0.2, world.player)
        self.assertEqual(enemy.state, "ATTACK")
        self.assertEqual(enemy.vx, 0)
        enemy.update(0.5, world.player)
        enemy.update(config.FIXED_DT, world.player)
        self.assertEqual(enemy.state, "RUN")
        self.assertEqual(enemy.vx, 540)
        self.assertIsNone(enemy.attack_box)

    def test_chase_slows_to_walk_then_attacks_without_body_penetration(self):
        world = World()
        enemy = Enemy(500, run_speed=540)
        world.enemies = [enemy]
        states = []
        for _ in range(360):
            world.step(config.FIXED_DT)
            if not states or states[-1] != enemy.state:
                states.append(enemy.state)
            self.assertFalse(world.player.body.overlaps(enemy.body))
        self.assertEqual(states[:3], ["RUN", "WALK", "ATTACK"])
        self.assertEqual(world.player.hp, 480)

    def test_death_cancels_run_mode_with_only_near_enemy_knockback(self):
        world = World()
        near = Enemy(config.START_X - 600, run_speed=360)
        far = Enemy(config.START_X + 600, -1, run_speed=540)
        world.enemies = [near, far]
        world.step(config.FIXED_DT)
        self.assertTrue(near.running and far.running)
        world.player.x = near.x + 80
        far_position, far_facing = far.x, far.facing
        world.player.take_damage(500)
        world.handle_death()
        self.assertTrue(near.knockback_started)
        self.assertFalse(far.knockback_started)
        self.assertFalse(near.running or far.running)
        advance(world, 1)
        self.assertEqual(far.x, far_position)
        self.assertEqual(far.facing, far_facing)
        self.assertEqual(far.state, "IDLE")

    def test_restart_restores_spawn_order_speed_profiles(self):
        world = World()
        world.controls.press("spawn_4")
        world.update(1 / 60)
        old_enemies = list(world.enemies)
        self.assertEqual([enemy.run_speed for enemy in old_enemies], list(config.ENEMY_RUN_SPEEDS))
        world.controls.press("restart")
        world.update(1 / 60)
        self.assertEqual(world.enemies, [])
        self.assertEqual(world.spawner.spawned_count, 0)
        tap(world.controls, "spawn_4")
        world.update(1 / 60)
        self.assertEqual([enemy.run_speed for enemy in world.enemies], list(config.ENEMY_RUN_SPEEDS))
        self.assertTrue(all(enemy not in old_enemies for enemy in world.enemies))


if __name__ == "__main__":
    unittest.main()
