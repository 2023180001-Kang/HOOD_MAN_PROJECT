import unittest

import config
from enemy import Enemy
from tests.helpers import advance, tap
from world import World


class DeathRestartTests(unittest.TestCase):
    def test_twenty_fifth_valid_hit_kills_and_last_death_frame_is_held(self):
        world = World(spawn_schedule=())
        for _ in range(24):
            self.assertTrue(world.player.take_damage(20))
            advance(world, 0.8)
        self.assertEqual(world.player.hp, 20)
        self.assertTrue(world.player.take_damage(20))
        self.assertEqual(world.player.hp, 0)
        self.assertEqual(world.player.state, "DYING")
        self.assertEqual(world.player.animation.row, 5)
        self.assertFalse(world.player.take_damage(20))
        advance(world, 2)
        self.assertEqual(world.player.state, "DEAD")
        self.assertEqual(world.player.animation.frame, 7)
        world.controls.press("right")
        world.controls.press("jump")
        x = world.player.x
        advance(world, 1)
        self.assertEqual(world.player.x, x)
        self.assertEqual(world.player.animation.frame, 7)
        self.assertEqual(world.player.hp, 0)

    def test_knockback_is_outward_once_and_facing_does_not_change(self):
        world = World(spawn_schedule=())
        left = Enemy(config.START_X - 80, facing=1)
        right = Enemy(config.START_X + 80, facing=-1)
        world.enemies = [left, right]
        world.player.take_damage(500)
        world.update(1 / 60)
        self.assertLess(left.x, config.START_X - 80)
        self.assertGreater(right.x, config.START_X + 80)
        self.assertEqual((left.facing, right.facing), (1, -1))
        advance(world, 2)
        positions = (left.x, right.x)
        self.assertEqual((left.vx, right.vx), (0, 0))
        self.assertEqual((left.state, right.state), ("IDLE", "IDLE"))
        advance(world, 2)
        self.assertEqual((left.x, right.x), positions)
        self.assertEqual((left.facing, right.facing), (1, -1))

    def test_boundary_knockback_is_clamped_and_same_x_uses_opposite_facing(self):
        world = World(spawn_schedule=())
        world.enemies = [Enemy(config.ENEMY_HALF_WIDTH, 1),
                         Enemy(config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH, -1),
                         Enemy(config.START_X, 1)]
        world.player.take_damage(500)
        world.step(config.FIXED_DT)
        self.assertLess(world.enemies[2].vx, 0)
        advance(world, 1)
        self.assertEqual(world.enemies[0].x, config.ENEMY_HALF_WIDTH)
        self.assertEqual(world.enemies[1].x, config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH)

    def test_early_death_stops_pending_spawns_and_other_attacks(self):
        world = World()
        world.player.hp = 20
        for x, facing in ((config.START_X - 80, 1), (config.START_X + 80, -1)):
            enemy = Enemy(x, facing)
            enemy.animation.set_state("ATTACK")
            enemy.animation.elapsed = 4 / config.ENEMY_ANIMATIONS["ATTACK"][1]
            world.enemies.append(enemy)
        world.update(1 / 60)
        self.assertEqual(world.player.hp, 0)
        self.assertTrue(world.death_handled)
        self.assertTrue(all(enemy.knockback_started for enemy in world.enemies))
        advance(world, 10)
        self.assertEqual(world.spawner.spawned_count, 0)
        self.assertEqual(len(world.enemies), 2)
        self.assertTrue(all(enemy.attack_box is None for enemy in world.enemies))

    def test_restart_clears_all_state_from_every_player_state(self):
        for state in ("IDLE", "WALK", "RUN", "JUMP", "HIT", "DYING", "DEAD"):
            with self.subTest(state=state):
                world = World()
                advance(world, 8)
                old_player = world.player
                old_enemies = list(world.enemies)
                world.player.animation.set_state(state)
                world.player.x = 300
                world.player.y += 100
                world.player.vx = 120
                world.player.vy = 200
                world.player.jump_count = 2
                world.player.hp = 0 if state in ("DYING", "DEAD") else 100
                world.player.invulnerability = 1
                world.camera.shake()
                world.controls.press("right")
                world.controls.press("jump")
                world.controls.press("restart")
                world.update(1 / 60)
                self.assertIsNot(world.player, old_player)
                self.assertEqual(world.player.state, "IDLE")
                self.assertEqual(world.player.hp, 500)
                self.assertEqual(world.player.x, config.START_X)
                self.assertEqual(world.player.y, config.GROUND_Y)
                self.assertEqual((world.player.vx, world.player.vy), (0, 0))
                self.assertEqual(world.player.jump_count, 0)
                self.assertEqual(world.player.invulnerability, 0)
                self.assertEqual(world.elapsed, 0)
                self.assertEqual(world.accumulator, 0)
                self.assertEqual(world.spawner.spawned_count, 0)
                self.assertEqual(world.enemies, [])
                self.assertEqual(world.camera.shake_remaining, 0)
                self.assertEqual(world.camera.render_y, 0)
                self.assertEqual(world.controls.held, {"restart"})
                self.assertEqual(world.controls.pressed, set())
                self.assertFalse(world.death_handled)
                advance(world, 1.1)
                self.assertEqual(len(world.enemies), 1)
                self.assertNotIn(world.enemies[0], old_enemies)

    def test_restart_is_edge_triggered_over_ten_repetitions(self):
        world = World()
        for _ in range(12):
            tap(world.controls, "restart")
            world.update(1 / 60)
            player = world.player
            world.controls.press("restart")  # OS repeat / held R.
            advance(world, 0.1)
            self.assertIs(world.player, player)
            self.assertGreater(world.elapsed, 0)
            self.assertEqual(world.player.hp, 500)
            self.assertEqual(world.enemies, [])


if __name__ == "__main__":
    unittest.main()
