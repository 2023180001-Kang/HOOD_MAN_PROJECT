import hashlib
import random
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import config
from assets import Assets
from combat import MOVES
from effects import DamageNumber, HitEffect
from enemy import Enemy
from enemy02 import Enemy02
from tests.helpers import advance, clear_encounters, spawn_encounter, tap
from traffic import Car, Traffic
from tests.helpers import ManualSpawnWorld as World


class CityStageTests(unittest.TestCase):
    def at_exit(self, index=1, side=1):
        world = clear_encounters(World())
        world.stage_index = index
        world.stage.arrows_visible = True
        world.player.x = (config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
                          if side > 0 else config.STAGE_EXIT_MARGIN)
        world.player.vx = side * config.RUN_SPEED
        world.controls.press("right" if side > 0 else "left")
        world.controls.press("left_shift")
        return world

    def test_twelve_backgrounds_form_one_bidirectional_route_with_a_final_boundary(self):
        world = World()
        self.assertEqual([stage.image_name for stage in world.stages],
                         ["changed_first_map_no_door.png", "newStage-2_floor300_1672x941.png",
                          *config.CITY_STAGE_IMAGES,
                          config.FACTORY_OUTSIDE_IMAGE, config.FACTORY_EXTERIOR_IMAGE,
                          "factoryInside-1.png", "factoryStage-2.png",
                          "labStage-1_floor300_1672x941.png", "labStage-2_floor300_1672x941.png",
                           "bossStage_floor300_1672x941.png", "bossStage-2_floor300_1672x941.png"])
        for index, stage in enumerate(world.stages):
            stage.arrows_visible = True
            self.assertEqual(stage.destination(-1), index - 1 if index else None)
            self.assertEqual(stage.destination(1), index + 1 if index < len(world.stages) - 1 else None)

    def test_replacement_cities_load_in_order_and_old_pngs_are_archived_without_changes(self):
        self.assertEqual(config.CITY_STAGE_IMAGES,
                         ("cityStage1_ground_300px_1672x941.png", "cityStage2_ground_300px_1672x941.png"))
        self.assertEqual(config.STAGE_IMAGES[2:4], config.CITY_STAGE_IMAGES)
        hashes = (
            "3e1b8ca6cf971e703eaf30ffeb060ceabaa2a1b8f77a02c9fd53413ae3b9e01c",
            "2058b68dea74ba2a84a0ac7e45da7206f983a6919fb1ca8ef6a3740d5b2356a3",
            "c784ed4c6cdd2145605f949d416ad5f4fdeda832989c47670a2b3d30da9a9d84",
            "e01bc9427117f43d68aca30c9c17d614ddb6b5e9a7d34597f118a522756a6ebd",
        )
        for name, digest in zip((*config.CITY_STAGE_IMAGES, *config.ARCHIVED_CITY_STAGE_IMAGES), hashes):
            path = config.ROOT / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with Image.open(path) as image:
                self.assertEqual(image.size, (1672, 941))
        with patch("pico2d.load_image", return_value=Mock()), patch("pico2d.load_font", return_value=None):
            assets = Assets()
        for active, archived in zip(config.CITY_STAGE_IMAGES, config.ARCHIVED_CITY_STAGE_IMAGES):
            self.assertIn(active, assets.images)
            self.assertNotIn(archived, assets.images)
            self.assertFalse((config.ROOT / archived.removeprefix("before_sheets/")).exists())

    def test_city_floors_cover_every_sidewalk_and_road_row_without_entering_buildings(self):
        world = World()
        for index, source_top, world_top in ((2, 650, 247), (3, 618, 279)):
            stage = world.stages[index]
            self.assertEqual(stage.walkable.bounds, (0, -44, 2560, world_top))
            self.assertEqual((897 - world_top, 897 - stage.walkable.bounds[1]), (source_top, 941))
            self.assertIsNone(stage.upper_walkable)
            self.assertEqual((stage.stairs, stage.doors), ([], []))
            self.assertIsNone(stage.traffic)
            for x in (68, 300, 1280, 1672, 2260, 2492):
                for y in (-44, 0, 56, 100, 200, world_top):
                    self.assertTrue(stage.walkable.contains(x, y, 68))
            self.assertFalse(stage.walkable.contains(1280, -44.01, 68))
            self.assertFalse(stage.walkable.contains(1280, world_top + 0.01, 68))

    def test_all_loadouts_walk_and_run_to_all_four_corners_of_both_city_floors(self):
        for index, top in ((2, 247), (3, 279)):
            for weapon in (None, *config.WEAPON_POSE_IMAGES):
                for running in (False, True):
                    for side in (-1, 1):
                        for depth in (-1, 1):
                            with self.subTest(stage=index, weapon=weapon, running=running, side=side, depth=depth):
                                world = World()
                                world.select_stage(index)
                                player = world.player
                                player.equip_weapon(weapon)
                                player.x = player.previous_x = 300 if side < 0 else 2260
                                world.controls.press("left" if side < 0 else "right")
                                world.controls.press("down" if depth < 0 else "up")
                                if running:
                                    world.controls.press("left_shift")
                                advance(world, 1.5)
                                self.assertEqual((player.x, player.ground_y, player.floor, player.jump_height),
                                                 (68 if side < 0 else 2492, -44 if depth < 0 else top, 0, 0))
                                self.assertTrue(player.grounded)
                                self.assertIsNone(player.staircase)
                                self.assertGreaterEqual(player.y - world.camera.render_y, 0)

    def test_expanded_city_depth_edges_keep_double_jumps_and_weapon_interaction_on_the_floor(self):
        for index, top in ((2, 247), (3, 279)):
            for depth in (-44, top):
                for weapon in config.WEAPON_POSE_IMAGES:
                    world = World()
                    world.select_stage(index)
                    player = world.player
                    player.ground_y = player.previous_ground_y = depth
                    world.controls.press("jump")
                    advance(world, 0.05)
                    tap(world.controls, "jump")
                    advance(world, 1.5)
                    self.assertTrue(player.grounded)
                    self.assertEqual((player.ground_y, player.floor, player.jump_height), (depth, 0, 0))
                    world.stage.drop_items.clear()
                    player.equip_weapon(weapon)
                    tap(world.controls, "weapon_interact")
                    world.step(config.FIXED_DT)
                    self.assertIsNone(player.weapon)
                    item = world.stage.drop_items[0]
                    advance(world, 1)
                    self.assertTrue(item.grounded)
                    self.assertTrue(world.stage.drop_spawn_area.contains(item.x, item.ground_y))
                    player.x, player.ground_y = item.x, item.ground_y
                    tap(world.controls, "weapon_interact")
                    world.step(config.FIXED_DT)
                    self.assertEqual(player.weapon, weapon)

    def test_new_city_art_preserves_enemy02_items_revisit_and_f5(self):
        world = World(rng=random.Random(32), item_rng=random.Random(23))
        for index in (2, 3):
            world.select_stage(index)
            stage = world.stage
            self.assertEqual(len(stage.drop_items), 15)
            self.assertTrue(all(item.floor == 0 and stage.walkable.contains(item.x, item.ground_y)
                                for item in stage.drop_items))
            tap(world.controls, "spawn_9")
            world.step(config.FIXED_DT)
            self.assertEqual(len(world.enemies), 9)
            self.assertTrue(all(type(enemy) is Enemy02 and enemy.hp == 200
                                and enemy.formation_ground_min == stage.spawn_area.bounds[1]
                                for enemy in world.enemies))
            enemy, items = world.enemies[0], stage.drop_items
            enemy.take_damage(40)
            world.select_stage(4)
            advance(world, 1)
            world.select_stage(index)
            self.assertIs(world.stage, stage)
            self.assertIs(world.stage.drop_items, items)
            self.assertEqual(enemy.hp, 160)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        for index, top in ((2, 247), (3, 279)):
            stage = world.stages[index]
            self.assertEqual(stage.image_name, config.CITY_STAGE_IMAGES[index - 2])
            self.assertEqual(stage.walkable.bounds, (0, -44, 2560, top))
            self.assertEqual(stage.enemies, [])
            self.assertEqual(len(stage.drop_items), 15)
            self.assertIsNone(stage.traffic)

    def test_travel_inside_each_pair_preserves_motion_without_loading(self):
        for first in (0, 2, 4, 6, 8, 10):
            for side in (-1, 1):
                with self.subTest(first=first, side=side):
                    world = self.at_exit(first if side > 0 else first + 1, side)
                    player = world.player
                    player.hp, player.invincible = 420, True
                    player.jump_height, player.vy, player.jump_count = 150, 300, 2
                    player.animation.set_state("JUMP")
                    player.animation.elapsed = 0.2
                    self.assertTrue(world.try_stage_transition())
                    self.assertFalse(world.stage_loading)
                    self.assertEqual(world.stage_index, first + 1 if side > 0 else first)
                    self.assertIs(world.player, player)
                    self.assertEqual((player.hp, player.invincible, player.jump_height,
                                      player.vy, player.jump_count, player.vx),
                                     (420, True, 150, 300, 2, side * config.RUN_SPEED))
                    self.assertEqual(player.animation.elapsed, 0.2)

    def test_city_loading_requires_an_open_exit_outward_motion_and_a_mobile_player(self):
        for blocked in ("hidden", "inward", "not_at_exit", "attack", "HIT", "DYING", "DEAD"):
            with self.subTest(blocked=blocked):
                world = self.at_exit()
                if blocked == "hidden":
                    world.stage.arrows_visible = False
                elif blocked == "inward":
                    world.player.vx = -config.RUN_SPEED
                elif blocked == "not_at_exit":
                    world.player.x = config.START_X
                elif blocked == "attack":
                    world.player.start_move(MOVES["combat_a"], 1)
                else:
                    world.player.animation.set_state(blocked)
                    if blocked in ("DYING", "DEAD"):
                        world.player.hp = 0
                self.assertFalse(world.try_stage_transition())
                self.assertFalse(world.stage_loading)
                self.assertEqual(world.stage_index, 1)

    def test_loading_freezes_all_gameplay_and_discards_one_shot_inputs(self):
        world = self.at_exit()
        player = world.player
        player.hp, player.invincible = 440, True
        player.jump_height, player.vy, player.jump_count = 120, 300, 2
        player.animation.set_state("JUMP")
        player.animation.elapsed = 0.2
        source = world.stage
        source.enemies.append(Enemy(1200))
        source.effects.append(HitEffect(1200, 180, 1))
        source.damage_numbers.append(DamageNumber(1200, 250, 10))
        destination = world.stages[2]
        destination.enemies.append(Enemy(1800))
        destination.effects.append(HitEffect(1800, 180, 1))
        world.camera.shake()
        before = (player.x, player.ground_y, player.jump_height, player.vy,
                  player.animation.elapsed, world.camera.shake_remaining)
        self.assertTrue(world.try_stage_transition())
        for key in ("jump", "combat_f", "invincibility", "stage_exits"):
            world.controls.press(key)
        advance(world, 1.9)
        self.assertTrue(world.stage_loading)
        self.assertEqual(world.stage_index, 1)
        self.assertEqual(world.elapsed, 0)
        self.assertEqual(before, (player.x, player.ground_y, player.jump_height, player.vy,
                                  player.animation.elapsed, world.camera.shake_remaining))
        for stage in (source, destination):
            self.assertEqual(stage.enemies[0].animation.elapsed, 0)
            self.assertEqual(stage.effects[0].elapsed, 0)
        self.assertEqual(source.damage_numbers[0].elapsed, 0)
        self.assertFalse(world.controls.pressed)
        world.update(0.1)
        self.assertFalse(world.stage_loading)
        self.assertEqual(world.stage_index, 2)
        self.assertIs(world.player, player)
        self.assertEqual((player.hp, player.invincible, player.jump_count, player.vy),
                         (440, True, 2, 300))
        self.assertEqual(len(destination.enemies), 1)
        self.assertFalse(destination.arrows_visible)
        world.update(1 / 60)
        self.assertIsNone(player.active_move)
        self.assertEqual(len(destination.enemies), 1)
        self.assertTrue(player.invincible)
        self.assertEqual(player.jump_count, 2)
        self.assertFalse(destination.arrows_visible)

    def test_loading_waits_two_seconds_of_real_dt_without_simulation_catchup(self):
        world = self.at_exit()
        world.update(config.MAX_FRAME_DT)
        self.assertTrue(world.stage_loading)
        self.assertEqual(world.accumulator, 0)
        self.assertEqual(world.elapsed, config.FIXED_DT)
        world.update(1.75)
        self.assertEqual(world.stage_loading_remaining, 0.25)
        world.update(0.249)
        self.assertEqual(world.stage_index, 1)
        self.assertTrue(world.stage_loading)
        world.update(0.001)
        self.assertEqual(world.stage_index, 2)
        self.assertFalse(world.stage_loading)
        self.assertEqual(world.player.x, config.STAGE_ENTRY_MARGIN)
        self.assertEqual(world.elapsed, config.FIXED_DT)
        self.assertEqual(world.accumulator, 0)
        world.update(1 / 60)
        self.assertAlmostEqual(world.player.x, config.STAGE_ENTRY_MARGIN + config.RUN_SPEED / 60)

    def test_loading_in_both_directions_preserves_jump_and_projects_destination_floor(self):
        for index, side, target in ((1, 1, 2), (2, -1, 1)):
            with self.subTest(index=index):
                world = self.at_exit(index, side)
                player = world.player
                player.ground_y = 239 if index == 1 else 247
                player.jump_height, player.vy, player.jump_count = 150, -100, 2
                player.animation.set_state("JUMP")
                player.animation.elapsed = 0.25
                self.assertTrue(world.try_stage_transition())
                self.assertEqual(world.pending_stage_index, target)
                world.update(config.STAGE_LOADING_DURATION)
                self.assertEqual(world.stage_index, target)
                self.assertEqual(player.x, config.STAGE_ENTRY_MARGIN if side > 0 else
                                 config.WORLD_WIDTH - config.STAGE_ENTRY_MARGIN)
                self.assertEqual(player.ground_y, 239)
                self.assertEqual((player.jump_height, player.vy, player.jump_count,
                                  player.animation.elapsed), (150, -100, 2, 0.25))
                self.assertEqual(player.previous_ground_y, 239)
                self.assertEqual(player.previous_x, player.x)
                self.assertFalse(world.try_stage_transition())

    def test_f5_cancels_loading_and_resets_all_stages(self):
        world = self.at_exit()
        for stage in world.stages:
            stage.arrows_visible = True
            stage.enemies.extend(stage.spawner.spawn(2, 0))
            stage.effects.append(HitEffect(500, 180, 1))
            stage.damage_numbers.append(DamageNumber(500, 250, 10))
        self.assertTrue(world.try_stage_transition())
        world.update(1)
        tap(world.controls, "restart")
        world.update(1 / 60)
        self.assertFalse(world.stage_loading)
        self.assertIsNone(world.pending_stage_index)
        self.assertEqual(world.stage_loading_remaining, 0)
        self.assertEqual(world.stage_index, 0)
        self.assertEqual(world.player.hp, 500)
        self.assertEqual(world.player.x, config.START_X)
        for stage in world.stages:
            self.assertFalse(stage.arrows_visible)
            self.assertEqual(stage.enemies, [])
            self.assertEqual((stage.effects, stage.damage_numbers), ([], []))
            self.assertEqual(stage.spawner.spawned_count, 0)
        advance(world, 2.5)
        self.assertEqual(world.stage_index, 0)

    def test_new_city_maps_keep_feet_and_spawned_enemies_inside_their_floor(self):
        world = World()
        for index in (2, 3):
            world.stage_index = index
            area = world.stage.walkable
            tap(world.controls, "spawn_4")
            for key in ("right", "up", "left_shift"):
                tap(world.controls, key)
            world.player.invincible = True
            advance(world, 1)
            for actor in (world.player, *world.enemies):
                self.assertTrue(area.contains(actor.x, actor.ground_y, actor.boundary_padding))
            self.assertEqual(len(world.enemies), 4)
        rates = [enemy.attack_speed for stage in world.stages for enemy in stage.enemies]
        self.assertEqual(len(set(rates)), len(rates))

    def test_city_one_spawns_only_on_sidewalk_at_both_edges_including_after_restart(self):
        world = World(rng=random.Random(42))
        for _ in range(2):
            stage = world.stages[2]
            enemies = stage.spawner.spawn(200, 0)
            self.assertEqual({enemy.x for enemy in enemies},
                             {config.ENEMY02_BOUNDARY_PADDING,
                              config.WORLD_WIDTH - config.ENEMY02_BOUNDARY_PADDING})
            for enemy in enemies:
                self.assertTrue(stage.spawn_area.contains(enemy.x, enemy.ground_y,
                                                          enemy.boundary_padding))
                self.assertGreaterEqual(enemy.ground_y, 200)
                self.assertGreater(enemy.ground_y - config.CAR_GROUND_Y, config.CAR_DEPTH_TOLERANCE)
                self.assertIs(enemy.walkable, stage.walkable)
                self.assertEqual(enemy.hp, config.ENEMY_MAX_HP)
            for index, other in enumerate(world.stages):
                if index not in (2, 3):
                    self.assertIs(other.spawn_area, other.walkable)
            world.reset()

    def test_both_cities_summon_on_the_pavement_only_after_numeric_input(self):
        world = World(rng=random.Random(32))
        for index, bottom, top in ((2, 200, 247), (3, 208, 279)):
            stage = world.stages[index]
            self.assertEqual(stage.enemies, [])
            world.stage_index = index
            tap(world.controls, "spawn_4")
            world.update(config.FIXED_DT)
            self.assertEqual(len(stage.enemies), 4)
            for enemy in stage.enemies:
                self.assertGreaterEqual(enemy.ground_y, bottom)
                self.assertLessEqual(enemy.ground_y, top)
                self.assertIs(enemy.walkable, stage.walkable)

    def test_city_front_rows_do_not_step_below_the_pavement_when_the_player_is_on_it(self):
        for index in (2, 3):
            for side in (-1, 1):
                bottom, top = config.STAGE_ENEMY_SPAWN_BOUNDS[config.STAGE_IMAGES[index]][1::2]
                for player_y in (bottom, top):
                    with self.subTest(stage=index, side=side, player_y=player_y):
                        world = World(rng=random.Random(32))
                        world.stage_index = index
                        world.stage.traffic = None
                        world.player.ground_y = player_y
                        world.player.invincible = True
                        spawn_encounter(world)
                        for number, enemy in enumerate(world.enemies):
                            enemy.x = enemy.previous_x = world.player.x + side * (220 + number * 5)
                            enemy.ground_y = enemy.previous_ground_y = bottom
                            enemy.facing = -side
                        for _ in range(240):
                            world.step(config.FIXED_DT)
                            for enemy in world.enemies:
                                self.assertGreaterEqual(enemy.ground_y, bottom - 1e-8)
                                if enemy.target_ground_y is not None:
                                    self.assertGreaterEqual(enemy.target_ground_y, bottom)
                        self.assertEqual(world.spawner.spawned_count, 4)

    def test_pavement_formations_can_still_follow_a_player_onto_the_road(self):
        world = World(rng=random.Random(32))
        world.stage_index = 2
        traffic = Traffic()  # Legacy hazard fixture; production city traffic is retired.
        world.stage.traffic = None
        world.player.ground_y = 56
        world.player.invincible = True
        spawn_encounter(world)
        for number, enemy in enumerate(world.enemies):
            enemy.x = enemy.previous_x = world.player.x - (220 + number * 5)
            enemy.ground_y = enemy.previous_ground_y = 100
        advance(world, 2)
        victim = min(world.enemies, key=lambda enemy: enemy.ground_y)
        self.assertLessEqual(victim.ground_y, config.CAR_GROUND_Y + config.CAR_DEPTH_TOLERANCE)
        traffic.car = Car(victim.x, 1, 1400)
        world.stage.traffic = traffic
        world.step(config.FIXED_DT)
        self.assertEqual((victim.hp, victim.state), (0, "CAR_HIT"))

    def test_cars_at_spawn_edges_do_not_run_over_newly_summoned_sidewalk_enemies(self):
        for side in (-1, 1):
            with self.subTest(side=side):
                world = World(rng=random.Random(42))
                world.stage_index = 2
                world.player.ground_y = 124
                edge = (config.ENEMY_BOUNDARY_PADDING if side < 0 else
                        config.WORLD_WIDTH - config.ENEMY_BOUNDARY_PADDING)
                car = Car(edge, -side, config.CAR_SPEED_RANGE[1])
                world.stage.traffic = Traffic()
                world.stage.traffic.car = car
                world.controls.press("spawn_4")
                world.step(config.FIXED_DT)
                self.assertEqual(len(world.enemies), 4)
                self.assertTrue(any(abs(enemy.x - car.x) < config.CAR_HALF_WIDTH
                                    for enemy in world.enemies))
                self.assertTrue(all(enemy.hp == config.ENEMY_MAX_HP and not enemy.car_hit
                                    for enemy in world.enemies))
                # Only spawning is restricted: enemies may still pursue onto the road.
                for enemy in world.enemies:
                    self.assertTrue(enemy.walkable.contains(enemy.x, config.CAR_GROUND_Y,
                                                            enemy.boundary_padding))

    def test_loading_finishes_at_the_same_time_at_different_render_rates(self):
        results = []
        for fps in (30, 60, 120, 144):
            world = self.at_exit()
            world.try_stage_transition()
            for _ in range(2 * fps - 1):
                world.update(1 / fps)
            self.assertTrue(world.stage_loading)
            self.assertEqual(world.stage_index, 1)
            world.update(1 / fps)
            self.assertFalse(world.stage_loading)
            results.append((world.stage_index, world.player.x, world.player.vx,
                            world.player.jump_height, world.elapsed, world.accumulator))
        self.assertTrue(all(result == results[0] for result in results))


if __name__ == "__main__":
    unittest.main()
