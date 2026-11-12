import random
import unittest

import config
from enemy import Enemy
from tests.helpers import advance, tap
from world import World


class CombatIntegrationTests(unittest.TestCase):
    def test_scripted_two_sided_combat_is_independent_of_render_frame_rate(self):
        outcomes = []
        script = (
            ("combat_d", "right"), (), ("combat_s", "left"), (),
            ("combat_a", "left"), (), ("combat_f", "right"), (),
        )
        for fps in (30, 60, 120, 144):
            world = World()
            world.enemies = [Enemy(config.START_X + offset, -1 if offset > 0 else 1)
                             for offset in (-80, -100, 80, 100)]
            for keys in script:
                for key in tuple(world.controls.held):
                    world.controls.release(key)
                for key in keys:
                    world.controls.press(key)
                advance(world, 0.5, fps)
            self.assertLess(world.player.hp, 500)
            self.assertTrue(any(enemy.hp < 200 for enemy in world.enemies))
            outcomes.append((world.player.hp, world.player.state,
                             [(enemy.hp, enemy.state, enemy.x) for enemy in world.enemies],
                             [(effect.x, effect.y, effect.frame) for effect in world.effects]))
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))

    def test_mixed_combat_movement_and_restarts_preserve_health_and_effect_bounds(self):
        rng = random.Random(20482304)
        world = World(rng=random.Random(20482304))
        keys = ("left", "right", "left_shift", "jump",
                *(f"combat_{key}" for key in "asdf"))
        for frame in range(2400):
            if frame % 17 == 0:
                key = rng.choice(keys)
                if key in world.controls.held:
                    world.controls.release(key)
                else:
                    world.controls.press(key)
            if frame % 600 == 599:
                tap(world.controls, "restart")
            elif frame % 120 == 0:
                tap(world.controls, "spawn_3")
            world.update(1 / 60)
            self.assertGreaterEqual(world.player.hp, 0)
            self.assertLessEqual(world.player.hp, 500)
            self.assertGreaterEqual(world.player.x, config.PLAYER_HALF_WIDTH)
            self.assertLessEqual(world.player.x, config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)
            self.assertGreaterEqual(world.player.y, config.GROUND_Y)
            self.assertEqual(len(world.enemies), world.spawner.spawned_count)
            self.assertLessEqual(len(world.effects), len(world.enemies) * 2)
            for effect in world.effects:
                self.assertIn(effect.frame, range(8))
                self.assertFalse(effect.finished)
            for enemy in world.enemies:
                self.assertGreaterEqual(enemy.hp, 0)
                self.assertLessEqual(enemy.hp, 200)
                if enemy.alive and world.player.alive:
                    self.assertFalse(world.player.body.overlaps(enemy.body))
                if not enemy.alive:
                    self.assertIn(enemy.state, ("DYING", "DEAD"))
                    self.assertIsNone(enemy.attack_box)


if __name__ == "__main__":
    unittest.main()
