import unittest

import config
from camera import Camera
from enemy import Enemy
from tests.helpers import advance
from world import World


def attacking_enemy(x, facing=1):
    enemy = Enemy(x, facing)
    enemy.animation.set_state("ATTACK")
    enemy.animation.elapsed = 4 / config.ENEMY_ANIMATIONS["ATTACK"][1]
    return enemy


class CombatTests(unittest.TestCase):
    def test_windup_does_not_damage_and_active_frames_deal_twenty(self):
        world = World(spawn_schedule=())
        world.enemies = [Enemy(config.START_X - 80)]
        advance(world, 0.3)
        self.assertEqual(world.player.hp, 500)
        advance(world, 0.15)
        self.assertEqual(world.player.hp, 480)
        self.assertEqual(world.player.state, "HIT")
        self.assertEqual(world.player.animation.row, 6)

    def test_each_swing_hits_only_once_even_if_invulnerability_is_removed(self):
        world = World(spawn_schedule=())
        enemy = attacking_enemy(config.START_X - 80)
        self.assertTrue(enemy.try_hit(world.player))
        world.player.invulnerability = 0
        world.player.animation.set_state("IDLE")
        self.assertFalse(enemy.try_hit(world.player))
        self.assertEqual(world.player.hp, 480)

    def test_simultaneous_attacks_apply_only_one_damage_and_shake_event(self):
        world = World(spawn_schedule=())
        world.enemies = [attacking_enemy(config.START_X - 80),
                         attacking_enemy(config.START_X + 80, -1)]
        world.update(1 / 60)
        self.assertEqual(world.player.hp, 480)
        self.assertGreater(world.camera.shake_remaining, 0)
        self.assertTrue(all(enemy.has_hit for enemy in world.enemies))
        initial_shake = world.camera.shake_remaining
        world.update(1 / 60)
        self.assertEqual(world.player.hp, 480)
        self.assertLess(world.camera.shake_remaining, initial_shake)

    def test_attack_misses_outside_reach_behind_or_above(self):
        world = World(spawn_schedule=())
        for x, facing in ((config.START_X - 200, 1), (config.START_X - 80, -1)):
            self.assertFalse(attacking_enemy(x, facing).try_hit(world.player))
        world.player.y = config.GROUND_Y + config.ENEMY_HEIGHT + 1
        self.assertFalse(attacking_enemy(config.START_X - 80).try_hit(world.player))
        self.assertEqual(world.player.hp, 500)

    def test_hit_blocks_input_keeps_gravity_and_finishes_in_idle(self):
        world = World(spawn_schedule=())
        player = world.player
        player.y += 100
        player.vy = -100
        player.take_damage(20)
        world.controls.press("right")
        world.controls.press("jump")
        start_x, start_y = player.x, player.y
        player.update(config.FIXED_DT, world.controls)
        self.assertEqual(player.x, start_x)
        self.assertLess(player.y, start_y)
        self.assertEqual(player.jump_count, 0)
        for _ in range(120):
            player.update(config.FIXED_DT, world.controls)
            if player.state != "HIT":
                break
        self.assertEqual(player.state, "IDLE")
        self.assertFalse(world.controls.take_press("jump"))

    def test_attack_timers_are_independent_and_interval_is_respected(self):
        world = World(spawn_schedule=())
        first = Enemy(config.START_X - 80)
        first.update(config.FIXED_DT, world.player)
        second = Enemy(config.START_X + 80, -1)
        self.assertEqual(second.cooldown, 0)
        self.assertGreater(first.cooldown, 0)
        self.assertEqual(second.state, "IDLE")
        for _ in range(90):
            first.update(config.FIXED_DT, world.player)
        self.assertNotEqual(first.state, "ATTACK")

    def test_shake_is_render_only_and_expires_at_map_edges(self):
        for x in (0, config.START_X, config.WORLD_WIDTH):
            camera = Camera(x)
            original = camera.x
            camera.shake()
            for _ in range(30):
                camera.update(config.FIXED_DT, x)
                self.assertEqual(camera.x, original)
                self.assertGreaterEqual(camera.render_x, 0)
                self.assertLessEqual(camera.render_x,
                                     config.WORLD_WIDTH - config.SCREEN_WIDTH)
            self.assertEqual(camera.render_y, 0)
            self.assertEqual(camera.render_x, original)


if __name__ == "__main__":
    unittest.main()
