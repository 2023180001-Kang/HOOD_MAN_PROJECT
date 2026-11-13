import unittest

import config
from tests.helpers import advance
from tests.test_counters import attacker
from world import World


def fallen_enemy(world):
    enemy = world.spawner.spawn(1, world.elapsed)[0]
    world.enemies.append(enemy)
    enemy.take_damage(config.ENEMY_MAX_HP)
    while enemy.state != "DEAD":
        world.step(config.FIXED_DT)
    return enemy


class EnemyDespawnTests(unittest.TestCase):
    def test_normal_death_waits_for_the_fall_then_holds_three_seconds_and_fades(self):
        world = World()
        enemy = world.spawner.spawn(1, 0)[0]
        world.enemies.append(enemy)
        pool = world.enemies
        enemy.take_damage(200)
        advance(world, 0.5)
        self.assertEqual(enemy.state, "DYING")
        self.assertEqual((enemy.corpse_elapsed, enemy.opacity), (0, 1))
        while enemy.state != "DEAD":
            world.step(config.FIXED_DT)
        self.assertEqual(enemy.corpse_elapsed, 0)
        advance(world, 2.5)
        self.assertEqual(enemy.opacity, 1)
        advance(world, 0.5)
        self.assertEqual(enemy.opacity, 1)
        self.assertIn(enemy, world.enemies)
        advance(world, 0.5)
        self.assertAlmostEqual(enemy.opacity, 0.5)
        self.assertIn(enemy, world.enemies)
        advance(world, 0.5)
        self.assertEqual(enemy.opacity, 0)
        self.assertTrue(enemy.faded_out)
        self.assertNotIn(enemy, world.enemies)
        self.assertIs(world.enemies, pool)
        self.assertEqual(world.spawner.spawned_count, 1)
        advance(world, 2)
        self.assertEqual(world.enemies, [])

    def test_lethal_counters_finish_the_whole_pair_before_starting_the_corpse_timer(self):
        for key in "hjkl":
            with self.subTest(key=key):
                world = World()
                enemy = attacker(world)
                enemy.hp = 40
                world.controls.press(f"counter_{key}")
                world.step(config.FIXED_DT)
                while enemy.hp:
                    world.step(config.FIXED_DT)
                self.assertIsNotNone(world.counter)
                self.assertEqual((enemy.corpse_elapsed, enemy.opacity), (0, 1))
                while world.counter is not None:
                    world.step(config.FIXED_DT)
                    self.assertEqual((enemy.corpse_elapsed, enemy.opacity), (0, 1))
                self.assertEqual((enemy.state, enemy.animation.frame), ("DEAD", 7))
                self.assertEqual(enemy.sprite_image, config.COUNTER_ENEMY_IMAGE)
                advance(world, 3)
                self.assertEqual(enemy.opacity, 1)
                advance(world, 0.5)
                self.assertAlmostEqual(enemy.opacity, 0.5)
                advance(world, 0.5)
                self.assertNotIn(enemy, world.enemies)

    def test_surviving_subdued_enemies_never_fade_and_resume_pursuit(self):
        world = World()
        enemy = attacker(world)
        world.controls.press("counter_j")
        world.step(config.FIXED_DT)
        while world.counter is not None:
            world.step(config.FIXED_DT)
        self.assertEqual((enemy.hp, enemy.state), (120, "IDLE"))
        world.player.x += 500
        world.player.invincible = True
        advance(world, 5)
        self.assertIn(enemy, world.enemies)
        self.assertEqual((enemy.opacity, enemy.corpse_elapsed), (1, 0))
        self.assertFalse(enemy.faded_out)

    def test_inactive_maps_preserve_the_remaining_fade_time(self):
        world = World()
        enemy = fallen_enemy(world)
        advance(world, 3.25)
        self.assertAlmostEqual(enemy.opacity, 0.75)
        elapsed = enemy.corpse_elapsed
        world.stage_index = 1
        advance(world, 5)
        self.assertEqual(enemy.corpse_elapsed, elapsed)
        world.stage_index = 0
        advance(world, 0.25)
        self.assertAlmostEqual(enemy.opacity, 0.5)
        advance(world, 0.5)
        self.assertNotIn(enemy, world.enemies)

    def test_region_loading_freezes_the_corpse_timer(self):
        world = World()
        world.stage_index = 1
        enemy = fallen_enemy(world)
        advance(world, 3.25)
        elapsed = enemy.corpse_elapsed
        world.stage.arrows_visible = True
        world.player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
        world.player.vx = config.RUN_SPEED
        self.assertTrue(world.try_stage_transition())
        world.update(1.5)
        self.assertEqual(enemy.corpse_elapsed, elapsed)
        self.assertAlmostEqual(enemy.opacity, 0.75)
        world.update(0.5)
        self.assertEqual(world.stage_index, 2)
        self.assertEqual(enemy.corpse_elapsed, elapsed)

    def test_corpses_continue_to_fade_after_the_player_dies(self):
        world = World()
        enemy = fallen_enemy(world)
        world.player.take_damage(500)
        advance(world, 4)
        self.assertEqual(world.player.state, "DEAD")
        self.assertTrue(enemy.faded_out)
        self.assertNotIn(enemy, world.enemies)

    def test_restart_clears_fading_corpses_and_new_enemies_start_opaque(self):
        world = World()
        enemy = fallen_enemy(world)
        advance(world, 3.5)
        self.assertAlmostEqual(enemy.opacity, 0.5)
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertTrue(all(not stage.enemies for stage in world.stages))
        world.controls.press("spawn_1")
        world.update(config.FIXED_DT)
        fresh = world.enemies[0]
        self.assertEqual((fresh.corpse_elapsed, fresh.opacity), (0, 1))
        self.assertFalse(fresh.faded_out)
        self.assertIsNot(fresh, enemy)

    def test_fading_and_removal_are_identical_at_different_render_rates(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world = World()
            enemy = fallen_enemy(world)
            advance(world, 3, fps)
            self.assertEqual(enemy.opacity, 1)
            advance(world, 0.5, fps)
            self.assertAlmostEqual(enemy.opacity, 0.5)
            advance(world, 0.5, fps)
            outcomes.append((len(world.enemies), world.spawner.spawned_count,
                             enemy.opacity, enemy.faded_out))
        self.assertTrue(all(outcome == (0, 1, 0, True) for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
