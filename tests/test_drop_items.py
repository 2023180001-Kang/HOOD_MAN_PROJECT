import random
import unittest
from math import degrees
from unittest.mock import Mock

from PIL import Image

import config
from assets import Assets
from drop_items import DropItem
from tests.helpers import advance, archived_two_floor_map, tap
from tests.helpers import ManualSpawnWorld as World


def layout(stage):
    return [(item.kind, item.x, item.ground_y, item.facing, item.floor)
            for item in stage.drop_items]


class DropItemTests(unittest.TestCase):
    def test_sword_lies_flat_on_landing_in_both_directions(self):
        assets = Assets.__new__(Assets)
        texture = Mock()
        assets.images = {config.SWORD_ITEM_IMAGE: texture}
        for facing in (-1, 1):
            with self.subTest(facing=facing):
                item = DropItem("sword", 500, 100, facing, jump_height=40)
                assets.draw_drop_item(item, 0, 0)
                self.assertEqual(texture.clip_composite_draw.call_args.args[4], 0)
                item.update(1)
                assets.draw_drop_item(item, 0, 0)
                angle, flip, _, center_y = texture.clip_composite_draw.call_args.args[4:8]
                self.assertAlmostEqual(degrees(angle), -69 * facing)
                self.assertEqual(flip, "h" if facing < 0 else "")
                self.assertAlmostEqual(center_y - 10 * config.SPRITE_SCALE, item.surface_y)

    def test_dropped_weapon_lengths_match_the_equipped_sprites(self):
        assets = Assets.__new__(Assets)
        for kind, held_length in (("steel_club", 108), ("pistol", 57), ("ar_rifle", 136)):
            with self.subTest(kind=kind):
                item = DropItem(kind, 500, 100)
                with Image.open(config.ROOT / item.image_name) as image:
                    texture = Mock(w=image.width, h=image.height)
                    assets.images = {item.image_name: texture}
                    assets.draw_drop_item(item, 0, 0)
                    args = texture.clip_composite_draw.call_args.args
                    length = args[-2]
                    if kind == "steel_club":
                        # Its draw rectangle also contains the transparent rotation margins.
                        alpha = image.getchannel("A").rotate(degrees(args[4]), expand=True)
                        left, _, right, _ = alpha.getbbox()
                        length *= (right - left) / image.width
                self.assertAlmostEqual(length, held_length * config.SPRITE_SCALE, delta=1)

    def test_every_stage_has_fifteen_randomly_placed_items_including_both_kinds(self):
        counts, layouts = set(), set()
        for seed in range(32):
            world = World(item_rng=random.Random(seed))
            for stage in world.stages:
                self.assertEqual(len(stage.drop_items), 15)
                self.assertEqual({item.kind for item in stage.drop_items},
                                 {"combat_knife", "steel_pipe"})
                counts.add(len(stage.drop_items))
                layouts.add(tuple(layout(stage)))
        self.assertEqual(counts, {15})
        self.assertEqual(len(layouts), 32 * len(config.STAGE_IMAGES))

    def test_flat_first_stage_places_all_fifteen_items_on_its_only_floor(self):
        for seed in range(32):
            world = World(item_rng=random.Random(seed))
            self.assertEqual(len(world.stage.drop_items), 15)
            self.assertEqual({item.floor for item in world.stage.drop_items}, {0})
            self.assertEqual({item.kind for item in world.stage.drop_items}, set(config.DROP_ITEM_IMAGES))
            self.assertTrue(all(item.grounded and world.stage.walkable.contains(item.x, item.ground_y)
                                for item in world.stage.drop_items))

    @archived_two_floor_map()
    def test_archived_first_stage_splits_items_between_both_floors_and_keeps_both_kinds_on_each(self):
        for seed in range(32):
            world = World(item_rng=random.Random(seed))
            for floor, count in ((0, 8), (1, 7)):
                items = [item for item in world.stage.drop_items if item.floor == floor]
                self.assertEqual(len(items), count)
                self.assertEqual({item.kind for item in items}, set(config.DROP_ITEM_IMAGES))
                self.assertTrue(all(item.grounded for item in items))
            self.assertTrue(all(item.floor == 0 for stage in world.stages[1:]
                                for item in stage.drop_items))

    @archived_two_floor_map()
    def test_generated_upper_floor_weapons_can_be_picked_up_with_g(self):
        for kind in config.DROP_ITEM_IMAGES:
            with self.subTest(kind=kind):
                world = World(item_rng=random.Random(5))
                upstairs = [item for item in world.stage.drop_items if item.floor == 1]
                self.assertTrue(upstairs)
                item = next(item for item in upstairs if item.kind == kind)
                player = world.player
                player.floor = 1
                player.x, player.ground_y = item.x, item.ground_y
                world.stage.constrain_actor(player)
                self.assertIs(world.pickup_item, item)
                world.controls.press("weapon_interact")
                world.step(config.FIXED_DT)
                self.assertEqual((player.floor, player.weapon), (1, kind))
                self.assertNotIn(item, world.stage.drop_items)
                self.assertEqual(len(world.stage.drop_items), 14)

    @archived_two_floor_map()
    def test_generated_weapons_cannot_be_picked_up_from_a_different_floor(self):
        for floor in (0, 1):
            world = World(item_rng=random.Random(5))
            candidates = [item for item in world.stage.drop_items if item.floor != floor]
            self.assertTrue(candidates)
            item = candidates[0]
            world.player.floor = floor
            # Equal coordinates deliberately isolate the floor-ID check.
            world.player.x, world.player.ground_y = item.x, item.ground_y
            self.assertIsNone(world.pickup_item)
            self.assertFalse(world.interact_weapon())
            self.assertIn(item, world.stage.drop_items)

    @archived_two_floor_map()
    def test_upper_floor_pickup_is_preserved_on_return_and_reset_by_f5(self):
        world = World(item_rng=random.Random(5))
        upstairs = [item for item in world.stage.drop_items if item.floor == 1]
        self.assertTrue(upstairs)
        item = upstairs[0]
        world.player.floor = 1
        world.player.x, world.player.ground_y = item.x, item.ground_y
        world.controls.press("weapon_interact")
        world.step(config.FIXED_DT)
        items = world.stage.drop_items
        original = layout(world.stage)
        clocks = [item.elapsed for item in items]
        world.select_stage(1)
        advance(world, 0.5)
        world.select_stage(0)
        self.assertIs(world.stage.drop_items, items)
        self.assertEqual(layout(world.stage), original)
        self.assertEqual([item.elapsed for item in items], clocks)
        self.assertNotIn(item, items)
        self.assertEqual(len(items), 14)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertEqual([sum(item.floor == floor for item in world.stage.drop_items)
                          for floor in (0, 1)], [8, 7])
        self.assertIsNone(world.player.weapon)
        self.assertFalse(any(new is old for new in world.stage.drop_items for old in items))

    @archived_two_floor_map()
    def test_items_on_both_floors_stay_grounded_without_falling_or_moving_between_floors(self):
        world = World(item_rng=random.Random(5))
        self.assertEqual({item.floor for item in world.stage.drop_items}, {0, 1})
        original = layout(world.stage)
        advance(world, 2)
        self.assertEqual(layout(world.stage), original)
        self.assertTrue(all(item.grounded for item in world.stage.drop_items))

    def test_all_visible_frames_and_shadows_fit_the_floor_and_avoid_swaying_arrows(self):
        bounds = {}
        for kind, name in config.DROP_ITEM_IMAGES.items():
            with Image.open(config.ROOT / name) as image:
                self.assertEqual((image.size, image.mode), ((2048, 256), "RGBA"))
                alpha = image.getchannel("A")
                self.assertEqual(alpha.getextrema(), (0, 255))
                bounds[kind] = []
                for frame in range(8):
                    tile = alpha.crop((frame * 256, 0, (frame + 1) * 256, 256))
                    top = config.DROP_ITEM_BODY_TOPS[kind][frame]
                    height = config.DROP_ITEM_BODY_HEIGHTS[kind]
                    # The opaque weapon must fit exactly; the faint shadow is
                    # a separate source region below the original hovering gap.
                    solid = tile.point(lambda value: 255 if value >= 64 else 0).getbbox()
                    self.assertEqual((solid[1], solid[3]), (top, top + height))
                    body = tile.crop((0, top, 256, top + height)).getbbox()
                    shadow = tile.crop((0, config.DROP_ITEM_SHADOW_TOP, 256,
                                        config.DROP_ITEM_SHADOW_TOP
                                        + config.DROP_ITEM_SHADOW_HEIGHT)).getbbox()
                    self.assertEqual((body[1], body[3]), (0, height))
                    bounds[kind].append(((body, height),
                                         (shadow, config.DROP_ITEM_SHADOW_HEIGHT / 2)))
        arrow_edge = (config.STAGE_EXIT_MARGIN + config.STAGE_ARROW_WIDTH / 2
                      + config.STAGE_ARROW_SWAY_AMPLITUDE)
        for seed in range(16):
            world = World(item_rng=random.Random(seed))
            for stage in world.stages:
                self.assertFalse(stage.arrows_visible)
                previous_right = {}
                for item in stage.drop_items:
                    area = stage.floor_areas[item.floor]
                    self.assertTrue(area.contains(item.x, item.ground_y))
                    for parts in bounds[item.kind]:
                        for (left, top, right, bottom), anchor in parts:
                            xs = [(left - 128) * config.DROP_ITEM_SCALE * item.facing,
                                  (right - 128) * config.DROP_ITEM_SCALE * item.facing]
                            visible_left, visible_right = item.x + min(xs), item.x + max(xs)
                            visible_bottom = item.ground_y + (anchor - bottom) * config.DROP_ITEM_SCALE
                            visible_top = item.ground_y + (anchor - top) * config.DROP_ITEM_SCALE
                            for x in (visible_left, visible_right):
                                for y in (visible_bottom, visible_top):
                                    self.assertTrue(area.contains(x, y))
                            self.assertGreaterEqual(visible_left, arrow_edge + config.DROP_ITEM_EXIT_GAP)
                            self.assertLessEqual(visible_right,
                                                 config.WORLD_WIDTH - arrow_edge - config.DROP_ITEM_EXIT_GAP)
                    if item.floor in previous_right:
                        self.assertGreater(item.x - config.DROP_ITEM_HALF_WIDTH,
                                           previous_right[item.floor])
                    previous_right[item.floor] = item.x + config.DROP_ITEM_HALF_WIDTH
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
        for scene in (world, different_items):
            self.assertIsNone(scene.stage.traffic)
            self.assertEqual(scene.traffic_rng.getstate(), traffic_state)

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
            self.assertEqual(len(new.drop_items), 15)

    def test_first_city_can_generate_both_weapons_on_the_road_and_sidewalk(self):
        city_index = config.STAGE_IMAGES.index(config.CITY_STAGE_IMAGES[0])
        for restart in (False, True):
            road, sidewalk = set(), set()
            for seed in range(16):
                world = World(item_rng=random.Random(seed))
                if restart:
                    tap(world.controls, "restart")
                    world.update(config.FIXED_DT)
                for item in world.stages[city_index].drop_items:
                    # The sidewalk ends at source row 694 (world y=203).
                    if item.ground_y + item.display_height < 180:
                        road.add(item.kind)
                    if item.ground_y - config.DROP_ITEM_SHADOW_HALF_DEPTH >= 203:
                        sidewalk.add(item.kind)
            with self.subTest(restart=restart):
                self.assertEqual(road, set(config.DROP_ITEM_IMAGES))
                self.assertEqual(sidewalk, set(config.DROP_ITEM_IMAGES))

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
