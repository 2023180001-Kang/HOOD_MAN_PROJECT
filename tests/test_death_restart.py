import unittest

import config
from enemy import Enemy
from tests.helpers import advance, tap
from world import World


class DeathRestartTests(unittest.TestCase):
    def test_twenty_fifth_valid_hit_kills_and_last_death_frame_is_held(self):
        world = World()
        world.enemies.clear()  # Apply exactly the scripted 25 hits.
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
        world = World()
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

    def test_same_x_knockback_uses_opposite_facing(self):
        world = World()
        world.enemies = [Enemy(config.START_X, 1)]
        world.player.take_damage(500)
        world.step(config.FIXED_DT)
        self.assertLess(world.enemies[0].vx, 0)

    def test_nearby_knockback_at_both_map_boundaries_is_clamped(self):
        for player_x, enemy_x, facing in (
            (config.ENEMY_BOUNDARY_PADDING + 80, config.ENEMY_BOUNDARY_PADDING, 1),
            (config.WORLD_WIDTH - config.ENEMY_BOUNDARY_PADDING - 80,
             config.WORLD_WIDTH - config.ENEMY_BOUNDARY_PADDING, -1),
        ):
            with self.subTest(player_x=player_x):
                world = World()
                world.player.x = player_x
                enemy = Enemy(enemy_x, facing)
                world.enemies = [enemy]
                world.player.take_damage(500)
                advance(world, 1)
                self.assertTrue(enemy.knockback_started)
                self.assertEqual(enemy.x, enemy_x)
                self.assertEqual(enemy.vx, 0)
                self.assertEqual(enemy.facing, facing)

    def test_death_only_knocks_back_nearby_enemies_and_stops_far_enemies(self):
        world = World()
        near = Enemy(config.START_X - 80, 1)
        boundary = Enemy(config.START_X + config.KNOCKBACK_RADIUS, -1)
        outside = Enemy(config.START_X - config.KNOCKBACK_RADIUS - 1, 1)
        far = Enemy(config.START_X + 600, -1)
        far.animation.set_state("ATTACK")
        far.vx = -config.ENEMY_SPEED
        far.cooldown = 1
        world.enemies = [near, boundary, outside, far]
        far_positions = (outside.x, far.x)
        world.player.take_damage(500)
        world.handle_death()
        self.assertTrue(near.knockback_started)
        self.assertTrue(boundary.knockback_started)
        self.assertFalse(outside.knockback_started)
        self.assertFalse(far.knockback_started)
        self.assertEqual((outside.vx, far.vx), (0, 0))
        self.assertEqual((outside.state, far.state), ("IDLE", "IDLE"))
        self.assertEqual(far.cooldown, 0)
        advance(world, 2)
        self.assertEqual((outside.x, far.x), far_positions)
        self.assertEqual((outside.facing, far.facing), (1, -1))
        self.assertIsNone(far.attack_box)

    def test_knockback_radius_is_circular_and_includes_the_boundary(self):
        world = World()
        world.player.y += 128
        on_boundary = Enemy(config.START_X + 96)
        outside = Enemy(config.START_X + 96.01)
        world.enemies = [on_boundary, outside]
        world.player.take_damage(500)
        world.handle_death()  # 96^2 + 128^2 = 160^2.
        self.assertTrue(on_boundary.knockback_started)
        self.assertFalse(outside.knockback_started)

    def test_airborne_death_does_not_later_knock_back_enemies_on_landing(self):
        world = World()
        world.player.y += config.KNOCKBACK_RADIUS + 20
        enemy = Enemy(world.player.x)
        world.enemies = [enemy]
        world.player.take_damage(500)
        world.handle_death()
        self.assertFalse(enemy.knockback_started)
        position = enemy.x
        advance(world, 2)
        self.assertTrue(world.player.grounded)
        self.assertFalse(enemy.knockback_started)
        self.assertEqual(enemy.x, position)

    def test_death_with_only_far_enemies_does_not_knock_back_anyone(self):
        world = World()
        world.enemies = [Enemy(config.START_X - 500), Enemy(config.START_X + 500, -1)]
        positions = [enemy.x for enemy in world.enemies]
        world.player.take_damage(500)
        advance(world, 1)
        self.assertTrue(world.death_handled)
        self.assertTrue(all(not enemy.knockback_started for enemy in world.enemies))
        self.assertEqual([enemy.x for enemy in world.enemies], positions)

    def test_early_death_stops_stage_selection_and_other_attacks(self):
        world = World()
        world.enemies.clear()
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
        world.controls.press("stage_9")
        advance(world, 10)
        self.assertEqual(world.stage_index, 0)
        self.assertEqual(world.spawner.spawned_count, 4)
        self.assertEqual(len(world.enemies), 2)
        self.assertTrue(all(enemy.attack_box is None for enemy in world.enemies))

    def test_restart_clears_all_state_from_every_player_state(self):
        for state in ("IDLE", "WALK", "RUN", "JUMP", "HIT", "DYING", "DEAD"):
            with self.subTest(state=state):
                world = World()
                old_player = world.player
                old_enemies = list(world.enemies)
                world.player.animation.set_state(state)
                world.player.x = 300
                world.player.y += 100
                world.player.vx = 120
                world.player.vy = 200
                world.player.jump_count = 2
                world.player.hp = 0 if state in ("DYING", "DEAD") else 100
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
                self.assertEqual(world.elapsed, 0)
                self.assertEqual(world.accumulator, 0)
                self.assertEqual(world.spawner.spawned_count, 4)
                self.assertEqual(len(world.enemies), 4)
                self.assertEqual(world.camera.shake_remaining, 0)
                self.assertEqual(world.camera.render_y, 0)
                self.assertEqual(world.controls.held, {"restart"})
                self.assertFalse(world.controls.pressed)
                self.assertFalse(world.death_handled)
                self.assertTrue(all(enemy not in old_enemies for enemy in world.enemies))
                self.assertTrue(all(enemy.hp == 200 for enemy in world.enemies))

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
            self.assertEqual(len(world.enemies), 4)


if __name__ == "__main__":
    unittest.main()
