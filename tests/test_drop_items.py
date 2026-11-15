import random
import unittest

from PIL import Image

import config
from drop_items import DropItem
from tests.helpers import advance, tap
from world import World


def layout(stage):
    return [(item.kind, item.x, item.ground_y, item.facing) for item in stage.drop_items]


class DropItemTests(unittest.TestCase):
    def test_every_stage_has_five_to_eight_total_items_including_both_kinds(self):
        counts, layouts = set(), set()
        for seed in range(32):
            world = World(item_rng=random.Random(seed))
            for stage in world.stages:
                self.assertIn(len(stage.drop_items), range(5, 9))
                self.assertEqual({item.kind for item in stage.drop_items},
                                 {"combat_knife", "steel_pipe"})
                counts.add(len(stage.drop_items))
                layouts.add(tuple(layout(stage)))
        self.assertEqual(counts, {5, 6, 7, 8})
        self.assertEqual(len(layouts), 320)

    def test_all_visible_frames_and_shadows_fit_the_floor_and_avoid_swaying_arrows(self):
        bounds = {}
        for kind, name in config.DROP_ITEM_IMAGES.items():
            with Image.open(config.ROOT / name) as image:
                self.assertEqual((image.size, image.mode), ((2048, 256), "RGBA"))
                alpha = image.getchannel("A")
                self.assertEqual(alpha.getextrema(), (0, 255))
                bounds[kind] = [alpha.crop((frame * 256, 0, (frame + 1) * 256, 256)).getbbox()
                                for frame in range(8)]
        arrow_edge = (config.STAGE_EXIT_MARGIN + config.STAGE_ARROW_WIDTH / 2
                      + config.STAGE_ARROW_SWAY_AMPLITUDE)
        for seed in range(16):
            world = World(item_rng=random.Random(seed))
            for stage in world.stages:
                self.assertFalse(stage.arrows_visible)
                previous_right = None
                for item in stage.drop_items:
                    for left, top, right, bottom in bounds[item.kind]:
                        xs = [(left - 128) * config.DROP_ITEM_SCALE * item.facing,
                              (right - 128) * config.DROP_ITEM_SCALE * item.facing]
                        visible_left, visible_right = item.x + min(xs), item.x + max(xs)
                        visible_bottom = item.ground_y + (128 - bottom) * config.DROP_ITEM_SCALE
                        visible_top = item.ground_y + (128 - top) * config.DROP_ITEM_SCALE
                        for x in (visible_left, visible_right):
                            for y in (visible_bottom, visible_top):
                                self.assertTrue(stage.walkable.contains(x, y))
                        self.assertGreaterEqual(visible_left, arrow_edge + config.DROP_ITEM_EXIT_GAP)
                        self.assertLessEqual(visible_right,
                                             config.WORLD_WIDTH - arrow_edge - config.DROP_ITEM_EXIT_GAP)
                    if previous_right is not None:
                        self.assertGreater(item.x - config.DROP_ITEM_HALF_WIDTH, previous_right)
                    previous_right = item.x + config.DROP_ITEM_HALF_WIDTH
                original = layout(stage)
                stage.arrows_visible = True
                self.assertEqual(layout(stage), original)

    def test_item_randomness_is_reproducible_and_independent_from_enemies_and_traffic(self):
        spawn_rng, traffic_rng = random.Random(42), random.Random(99)
        spawn_state, traffic_state = spawn_rng.getstate(), traffic_rng.getstate()
        world = World(rng=spawn_rng, traffic_rng=traffic_rng, item_rng=random.Random(7))
        self.assertEqual(spawn_rng.getstate(), spawn_state)
        self.assertEqual(traffic_rng.getstate(), traffic_state)
        reference = World(rng=random.Random(42), traffic_rng=random.Random(99),
                          item_rng=random.Random(7))
        self.assertEqual([layout(stage) for stage in world.stages],
                         [layout(stage) for stage in reference.stages])
        different_items = World(rng=random.Random(42), traffic_rng=random.Random(99),
                                item_rng=random.Random(8))
        for scene in (world, different_items):
            scene.select_stage(2)
            scene.controls.press("spawn_4")
            advance(scene, 0.5)
        self.assertEqual([(enemy.x, enemy.ground_y, enemy.attack_speed) for enemy in world.enemies],
                         [(enemy.x, enemy.ground_y, enemy.attack_speed)
                          for enemy in different_items.enemies])
        for attribute in ("x", "previous_x", "facing", "speed", "ground_y"):
            self.assertEqual(getattr(world.stage.traffic.car, attribute),
                             getattr(different_items.stage.traffic.car, attribute))

    def test_scene_return_keeps_items_and_loading_pauses_their_clocks(self):
        world = World(item_rng=random.Random(1))
        first = world.stage
        items, original = first.drop_items, layout(first)
        advance(world, 0.2)
        clocks = [item.elapsed for item in items]
        world.select_stage(1)
        advance(world, 0.3)
        self.assertEqual([item.elapsed for item in items], clocks)
        world.select_stage(0)
        self.assertIs(world.stage.drop_items, items)
        self.assertEqual(layout(world.stage), original)
        advance(world, 0.1)
        self.assertTrue(all(item.elapsed > clock for item, clock in zip(items, clocks)))
        world.select_stage(1)
        world.stage.arrows_visible = True
        world.player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
        world.controls.press("right")
        self.assertTrue(world.try_stage_transition())
        current_clocks = [item.elapsed for item in world.stage.drop_items]
        world.update(1.0)
        self.assertTrue(world.stage_loading)
        self.assertEqual([item.elapsed for item in world.stage.drop_items], current_clocks)

    def test_restart_regenerates_every_stage_without_retaining_old_items(self):
        world = World(item_rng=random.Random(123))
        stages = world.stages[:]
        originals = [layout(stage) for stage in stages]
        advance(world, 0.5)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertEqual(world.stage_index, 0)
        self.assertNotEqual([layout(stage) for stage in world.stages], originals)
        for old, new in zip(stages, world.stages):
            self.assertIsNot(old.drop_items, new.drop_items)
            self.assertFalse(any(item is previous for item in new.drop_items
                                 for previous in old.drop_items))
            self.assertIn(len(new.drop_items), range(5, 9))

    def test_walking_over_and_attacking_items_does_not_collect_move_or_destroy_them(self):
        world = World(item_rng=random.Random(1))
        stage, player = world.stage, world.player
        items, original = stage.drop_items, layout(stage)
        item = items[len(items) // 2]
        player.x, player.ground_y = item.x - 80, item.ground_y
        world.controls.press("right")
        advance(world, 0.6)
        self.assertGreater(player.x, item.x + 50)
        world.controls.release("right")
        world.controls.press("combat_a")
        advance(world, 0.5)
        self.assertIs(stage.drop_items, items)
        self.assertEqual(layout(stage), original)
        self.assertEqual(player.hp, config.MAX_HP)
        self.assertEqual(world.effects, [])

    def test_eight_frame_loop_and_clocks_are_independent_of_render_rate(self):
        item = DropItem("combat_knife", 500, 100)
        frames = []
        for _ in range(9):
            frames.append(item.frame)
            item.update(1 / config.DROP_ITEM_FPS)
        self.assertEqual(frames, [0, 1, 2, 3, 4, 5, 6, 7, 0])
        outcomes = []
        for fps in (30, 60, 120, 144):
            world = World(item_rng=random.Random(5))
            advance(world, 1.5, fps)
            outcomes.append([(item.x, item.ground_y, item.frame, item.elapsed)
                             for item in world.stage.drop_items])
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
