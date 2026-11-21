import random
from math import cos, sin
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from PIL import Image

import config
from assets import Assets
from combat import MOVES
from drop_items import DropItem, MetalClubDrop
from enemy import Enemy
from enemy02 import Enemy02
from tests.helpers import advance, archived_two_floor_map, tap
from tests.test_stair_combat_and_drops import on_stairs
from tests.test_strong_attacks import encounter, strike
from tests.test_two_floors import place
from ui import UI
from world import World


def drop_world(enemy_type=Enemy):
    world = World(rng=random.Random(41), item_rng=random.Random(5))
    world.player.invincible = True
    world.stage.drop_items.clear()
    enemy = enemy_type(world.player.x + 65, -1, ground_y=world.player.ground_y)
    world.enemies = [enemy]
    return world, enemy


def clubs(world):
    return [item for item in world.stage.drop_items if isinstance(item, MetalClubDrop)]


class EnemyDeathDropTests(unittest.TestCase):
    def test_live_and_nonlethally_hit_enemies_do_not_drop_clubs(self):
        world, enemy = drop_world()
        world.step(config.FIXED_DT)
        self.assertEqual(clubs(world), [])
        enemy.take_damage(40)
        advance(world, 0.5)
        self.assertEqual(clubs(world), [])
        self.assertFalse(enemy.death_drop_spawned)

    def test_lethal_basic_hit_drops_the_requested_asset_in_the_same_tick(self):
        world, enemy = drop_world()
        enemy.hp = 40
        world.player.start_move(MOVES["combat_s"], 1)
        world.player.animation.elapsed = 3 / MOVES["combat_s"].fps
        world.step(config.FIXED_DT)
        self.assertFalse(enemy.alive)
        self.assertTrue(enemy.death_drop_spawned)
        self.assertEqual(len(clubs(world)), 1)
        item = clubs(world)[0]
        self.assertEqual(item.image_name, "HoodMan_MetalClub_Item_6frames_1536x256.png")
        self.assertEqual((item.kind, item.x, item.floor, item.frame),
                         ("metal_club", enemy.x, enemy.floor, 0))
        self.assertAlmostEqual(item.ground_y + item.jump_height,
                               enemy.y + config.METAL_CLUB_DROP_HEIGHT)
        self.assertFalse(item.collectible)

    def test_each_strong_attack_including_lethal_rush_drops_once(self):
        for key in "qwert":
            with self.subTest(key=key):
                world, enemy = encounter()
                enemy.hp = 50
                strike(world, enemy, f"combat_{key}")
                self.assertEqual(len(clubs(world)), 1)
                advance(world, 1)
                self.assertEqual(len(clubs(world)), 1)

    def test_multiple_deaths_keep_one_item_each_after_enemies_fade_out(self):
        world, first = drop_world()
        second = Enemy(first.x + 100, ground_y=first.ground_y)
        world.enemies.append(second)
        for enemy in world.enemies:
            enemy.take_damage(200)
        world.step(config.FIXED_DT)
        items = clubs(world)
        self.assertEqual(len(items), 2)
        self.assertEqual({item.x for item in items}, {first.x, second.x})
        first.take_damage(200)
        world.spawn_enemy_death_drops()
        advance(world, 6)
        self.assertEqual(world.enemies, [])
        self.assertEqual(clubs(world), items)

    def test_dual_club_enemy_does_not_gain_the_single_club_drop(self):
        world, enemy = drop_world(Enemy02)
        enemy.take_damage(200)
        advance(world, 6)
        self.assertEqual(clubs(world), [])
        self.assertEqual(world.enemies, [])

    def test_spawned_enemy_types_drop_only_on_single_club_stages(self):
        world = World(rng=random.Random(41), item_rng=random.Random(5))
        for index in range(len(world.stages)):
            world.select_stage(index)
            initial = len(world.stage.drop_items)
            world.enemies = world.spawner.spawn(3, world.elapsed)
            for enemy in world.enemies:
                enemy.take_damage(enemy.max_hp)
            world.step(config.FIXED_DT)
            excluded = (*config.ENEMY02_STAGE_IMAGES, config.FACTORY_OUTSIDE_IMAGE,
                        *config.FACTORY_INSIDE_IMAGES, *config.LAB_STAGE_IMAGES)
            expected = 0 if world.stage.image_name in excluded else 3
            self.assertEqual(len(clubs(world)), expected)
            self.assertEqual(len(world.stage.drop_items), initial + expected)

    def test_legacy_car_death_still_emits_one_club(self):
        world, enemy = drop_world()
        enemy.hit_by_car(1)
        world.step(config.FIXED_DT)
        self.assertEqual(len(clubs(world)), 1)
        advance(world, 2)
        self.assertEqual(len(clubs(world)), 1)
        self.assertIsNone(world.stage.traffic)

    @archived_two_floor_map()
    def test_upper_floor_drop_stays_on_the_victims_floor_and_fits_its_bounds(self):
        world, enemy = drop_world()
        place(world, world.player, 1, 1200, 476)
        place(world, enemy, 1, 1300, 502)
        enemy.take_damage(200)
        world.step(config.FIXED_DT)
        item = clubs(world)[0]
        self.assertEqual(item.floor, 1)
        self.assertAlmostEqual(item.ground_y + item.jump_height,
                               enemy.y + config.METAL_CLUB_DROP_HEIGHT)
        advance(world, 1)
        self.assertTrue(item.grounded)
        area = world.stage.upper_walkable
        for x in (item.x - config.METAL_CLUB_ITEM_HALF_WIDTH,
                  item.x + config.METAL_CLUB_ITEM_HALF_WIDTH):
            for y in (item.ground_y, item.ground_y + config.METAL_CLUB_ITEM_HEIGHT):
                self.assertTrue(area.contains(x, y))

    @archived_two_floor_map()
    def test_lethal_stair_hit_drops_from_visible_height_to_the_lower_floor(self):
        world, _ = drop_world()
        world.enemies.clear()
        enemy = on_stairs(world)
        feet = enemy.y
        enemy.take_damage(200)
        world.step(config.FIXED_DT)
        item = clubs(world)[0]
        self.assertEqual(item.floor, 0)
        self.assertLessEqual(abs(item.ground_y + item.jump_height
                                 - feet - config.METAL_CLUB_DROP_HEIGHT), 1)
        self.assertGreater(item.jump_height, 300)
        advance(world, 1)
        self.assertTrue(item.grounded)
        self.assertEqual(len(clubs(world)), 1)

    def test_gravity_lands_the_drop_and_keeps_it_at_its_death_location(self):
        world, enemy = drop_world()
        enemy.take_damage(200)
        world.step(config.FIXED_DT)
        item = clubs(world)[0]
        x, ground_y, height = item.x, item.ground_y, item.jump_height
        world.step(config.FIXED_DT)
        self.assertLess(item.jump_height, height)
        self.assertLess(item.vy, 0)
        advance(world, 1)
        self.assertEqual((item.x, item.ground_y, item.jump_height, item.vy),
                         (x, ground_y, 0, 0))

    def test_walking_attacking_and_g_do_not_collect_or_equip_the_club(self):
        world, enemy = drop_world()
        enemy.take_damage(200)
        advance(world, 1)
        item = clubs(world)[0]
        world.player.x, world.player.ground_y = item.x, item.ground_y
        self.assertIsNone(world.pickup_item)
        self.assertFalse(world.interact_weapon())
        world.controls.press("weapon_interact")
        world.controls.press("combat_s")
        advance(world, 0.5)
        self.assertIsNone(world.player.weapon)
        self.assertEqual(clubs(world), [item])
        assets = SimpleNamespace(font=Mock())
        UI().draw_pickup_prompt(assets, world, 0, 0)
        assets.font.draw.assert_not_called()

    def test_noncollectible_club_does_not_block_existing_weapon_pickup_or_discard(self):
        world, enemy = drop_world()
        enemy.take_damage(200)
        advance(world, 1)
        item = clubs(world)[0]
        world.player.x, world.player.ground_y = item.x, item.ground_y
        knife = DropItem("combat_knife", item.x + 10, item.ground_y)
        world.stage.drop_items.append(knife)
        self.assertIs(world.pickup_item, knife)
        self.assertTrue(world.interact_weapon())
        self.assertEqual(world.player.weapon, "combat_knife")
        self.assertIn(item, world.stage.drop_items)
        self.assertTrue(world.interact_weapon())  # Existing G-without-pickup discard.
        self.assertIsNone(world.player.weapon)
        self.assertIn(item, world.stage.drop_items)

    def test_inactive_scene_and_loading_pause_drop_motion_without_duplicating(self):
        world, enemy = drop_world()
        enemy.take_damage(200)
        world.step(config.FIXED_DT)
        item = clubs(world)[0]
        state = item.elapsed, item.jump_height, item.vy
        world.select_stage(1)
        advance(world, 1)
        self.assertEqual((item.elapsed, item.jump_height, item.vy), state)
        world.select_stage(0)
        world.pending_stage_index, world.stage_loading_remaining = 1, 2
        world.update(0.5)
        self.assertEqual((item.elapsed, item.jump_height, item.vy), state)
        world.pending_stage_index = None
        world.step(config.FIXED_DT)
        self.assertLess(item.jump_height, state[1])
        self.assertEqual(clubs(world), [item])

    def test_drops_still_spawn_when_the_player_is_dead(self):
        world, enemy = drop_world()
        enemy.take_damage(200)
        world.player.invincible = False
        world.player.take_damage(config.MAX_HP)
        self.assertFalse(world.player.alive)
        world.step(config.FIXED_DT)
        self.assertEqual(len(clubs(world)), 1)

    def test_f5_removes_death_drops_and_restores_only_fifteen_initial_items(self):
        world, enemy = drop_world()
        enemy.take_damage(200)
        world.step(config.FIXED_DT)
        old = clubs(world)[0]
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        for stage in world.stages:
            self.assertEqual(len(stage.drop_items), 15)
            self.assertFalse(any(isinstance(item, MetalClubDrop) for item in stage.drop_items))
            self.assertFalse(any(item is old for item in stage.drop_items))
        self.assertEqual(world.enemies, [])

    def test_death_drops_do_not_consume_spawn_or_initial_item_randomness(self):
        world, enemy = drop_world()
        spawn_state, item_state = world.spawn_rng.getstate(), world.item_rng.getstate()
        enemy.take_damage(200)
        world.step(config.FIXED_DT)
        self.assertEqual(world.spawn_rng.getstate(), spawn_state)
        self.assertEqual(world.item_rng.getstate(), item_state)

    def test_death_drop_motion_is_render_rate_independent(self):
        snapshots = []
        for fps in (30, 60, 120, 144):
            world, enemy = drop_world()
            enemy.take_damage(200)
            advance(world, 0.5, fps)
            item = clubs(world)[0]
            snapshots.append((item.x, item.ground_y, item.jump_height, item.vy,
                              item.frame, item.elapsed))
        self.assertTrue(all(snapshot == snapshots[0] for snapshot in snapshots))


class MetalClubDropRenderingTests(unittest.TestCase):
    def test_club_long_axis_is_horizontal_in_both_facings_on_the_floor_and_in_the_air(self):
        image = SimpleNamespace(h=256, clip_composite_draw=Mock())
        assets = Assets.__new__(Assets)
        assets.images = {config.METAL_CLUB_ITEM_IMAGE: image}
        with Image.open(config.ROOT / config.METAL_CLUB_ITEM_IMAGE) as source:
            alpha = source.getchannel("A")
            for facing in (-1, 1):
                for height, frame in [(0, 0), *[(60, f) for f in range(6)]]:
                    with self.subTest(facing=facing, height=height, frame=frame):
                        item = MetalClubDrop(500, 90, facing, jump_height=height)
                        item.elapsed = frame / config.DROP_ITEM_FPS
                        assets.draw_drop_item(item, 120, -3)
                        angle = image.clip_composite_draw.call_args.args[4]
                        top, bottom = config.METAL_CLUB_ITEM_BODY_BOUNDS[frame]
                        tile = alpha.crop((frame * 256, top, (frame + 1) * 256, bottom))
                        points = []
                        for y in range(bottom - top):
                            for x in range(256):
                                if tile.getpixel((x, y)) < 64:
                                    continue
                                px = (x + 0.5 - 128) * facing
                                py = (bottom - top) / 2 - y - 0.5
                                points.append((px * cos(angle) - py * sin(angle),
                                               px * sin(angle) + py * cos(angle)))
                        mean_x = sum(x for x, _ in points) / len(points)
                        mean_y = sum(y for _, y in points) / len(points)
                        spread_x = sum((x - mean_x) ** 2 for x, _ in points)
                        spread_y = sum((y - mean_y) ** 2 for _, y in points)
                        covariance = sum((x - mean_x) * (y - mean_y) for x, y in points)
                        self.assertGreater(spread_x, spread_y * 10)
                        self.assertLess(abs(covariance), spread_x * 0.001)

    def test_grounded_club_keeps_one_pose_as_its_clock_advances(self):
        for facing in (-1, 1):
            item = MetalClubDrop(500, 90, facing)
            for _ in range(24):
                item.update(1 / config.DROP_ITEM_FPS)
                self.assertEqual(item.frame, 0)
                self.assertEqual((item.x, item.ground_y, item.jump_height, item.vy),
                                 (500, 90, 0, 0))

    def test_horizontal_silhouettes_stay_centered_and_inside_the_landing_envelope(self):
        image = SimpleNamespace(h=256, clip_composite_draw=Mock())
        assets = Assets.__new__(Assets)
        assets.images = {config.METAL_CLUB_ITEM_IMAGE: image}
        with Image.open(config.ROOT / config.METAL_CLUB_ITEM_IMAGE) as source:
            alpha = source.getchannel("A")
            for facing in (-1, 1):
                for frame, (top, bottom) in enumerate(config.METAL_CLUB_ITEM_BODY_BOUNDS):
                    item = MetalClubDrop(500, 90, facing, jump_height=60)
                    item.elapsed = frame / config.DROP_ITEM_FPS
                    assets.draw_drop_item(item, 120, -3)
                    args = image.clip_composite_draw.call_args.args
                    angle, center_x, center_y = args[4], args[6], args[7]
                    scale = config.METAL_CLUB_ITEM_SCALE
                    tile = alpha.crop((frame * 256, top, (frame + 1) * 256, bottom))
                    points = []
                    for y in range(bottom - top):
                        for x in range(256):
                            if tile.getpixel((x, y)) == 0:
                                continue
                            for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                                px = (x + dx - 128) * facing * scale
                                py = ((bottom - top) / 2 - y - dy) * scale
                                points.append((center_x + px * cos(angle) - py * sin(angle),
                                               center_y + px * sin(angle) + py * cos(angle)))
                    left, right = min(x for x, _ in points), max(x for x, _ in points)
                    base, high = min(y for _, y in points), max(y for _, y in points)
                    self.assertAlmostEqual((left + right) / 2, 380, delta=0.01)
                    self.assertAlmostEqual(base, 153, delta=0.01)
                    self.assertGreaterEqual(left, 380 - config.METAL_CLUB_ITEM_HALF_WIDTH)
                    self.assertLessEqual(right, 380 + config.METAL_CLUB_ITEM_HALF_WIDTH)
                    self.assertLessEqual(high, 153 + config.METAL_CLUB_ITEM_HEIGHT)

    def test_landing_stops_animation_from_every_airborne_frame(self):
        for frame in range(config.METAL_CLUB_ITEM_FRAMES):
            with self.subTest(frame=frame):
                item = MetalClubDrop(500, 90, jump_height=1)
                item.elapsed = frame / config.DROP_ITEM_FPS
                item.vy = -100
                self.assertEqual(item.frame, frame)
                item.update(1 / 60)
                self.assertTrue(item.grounded)
                self.assertEqual(item.frame, 0)
                item.update(2)
                self.assertEqual(item.frame, 0)

    def test_grounded_draw_calls_remain_identical_between_animation_ticks(self):
        image = SimpleNamespace(h=256, clip_composite_draw=Mock())
        assets = Assets.__new__(Assets)
        assets.images = {config.METAL_CLUB_ITEM_IMAGE: image}
        for facing in (-1, 1):
            item = MetalClubDrop(500, 90, facing)
            assets.draw_drop_item(item, 120, -3)
            original = image.clip_composite_draw.call_args
            for _ in range(12):
                item.update(1 / config.DROP_ITEM_FPS)
                assets.draw_drop_item(item, 120, -3)
                self.assertEqual(image.clip_composite_draw.call_args, original)

    def test_original_six_frame_sheet_bounds_and_airborne_loop(self):
        with Image.open(config.ROOT / config.METAL_CLUB_ITEM_IMAGE) as image:
            self.assertEqual((image.size, image.mode), ((1536, 256), "RGBA"))
            alpha = image.getchannel("A")
            for frame, (top, bottom) in enumerate(config.METAL_CLUB_ITEM_BODY_BOUNDS):
                bounds = alpha.crop((frame * 256, 0, (frame + 1) * 256, 256)).getbbox()
                self.assertEqual((bounds[1], bounds[3]), (top, bottom))
        item = MetalClubDrop(500, 90, jump_height=2000)
        frames = []
        for _ in range(8):
            frames.append(item.frame)
            item.update(1 / config.DROP_ITEM_FPS)
        self.assertEqual(frames, [0, 1, 2, 3, 4, 5, 0, 1])

    def test_all_source_clips_facings_and_camera_offsets_pin_the_club_to_its_feet(self):
        image = SimpleNamespace(h=256, clip_composite_draw=Mock())
        assets = Assets.__new__(Assets)
        assets.images = {config.METAL_CLUB_ITEM_IMAGE: image}
        for facing in (-1, 1):
            for frame, (top, bottom) in enumerate(config.METAL_CLUB_ITEM_BODY_BOUNDS):
                item = MetalClubDrop(500, 90, facing, jump_height=60)
                item.elapsed = frame / config.DROP_ITEM_FPS
                assets.draw_drop_item(item, 120, -3)
                height = bottom - top
                scale = config.METAL_CLUB_ITEM_SCALE
                angle, left, base, right, _ = config.METAL_CLUB_ITEM_HORIZONTAL_POSES[frame]
                image.clip_composite_draw.assert_called_with(
                    frame * 256, 256 - bottom, 256, height,
                    angle * facing, "h" if facing < 0 else "",
                    380 - (left + right) * scale / 2 * facing,
                    153 - base * scale, 256 * scale, height * scale,
                )


if __name__ == "__main__":
    unittest.main()
