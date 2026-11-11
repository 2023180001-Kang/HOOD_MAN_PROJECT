import unittest

import config
from effects import HitEffect
from tests.helpers import advance, tap
from world import World


class StageTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
