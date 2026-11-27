import hashlib
import random
import unittest

from PIL import Image

import config
from combat import MOVES
from effects import HitEffect
from tests.helpers import advance, clear_encounters, spawn_encounter, tap
from tests.helpers import ManualSpawnWorld as World


class StageTests(unittest.TestCase):
    def assert_same_motion(self, actual, expected):
        for attribute in ("vx", "vy", "y", "jump_count", "hp", "facing", "grounded", "state"):
            self.assertEqual(getattr(actual, attribute), getattr(expected, attribute), attribute)
        self.assertEqual(actual.animation.elapsed, expected.animation.elapsed)
        self.assertEqual(actual.animation.frame, expected.animation.frame)

    def test_first_stage_uses_flat_background_on_start_and_restart_and_archives_old_art(self):
        world = World()
        self.assertEqual(world.stage.image_name, "changed_first_map.png")
        self.assertEqual(world.stage.walkable.bounds, (0, -3, config.WORLD_WIDTH, 277))
        with Image.open(config.ROOT / world.stage.image_name) as image:
            self.assertEqual(image.size, (1672, 941))
        self.assertNotIn(config.ARCHIVED_TWO_FLOOR_IMAGE, config.STAGE_IMAGES)
        self.assertFalse((config.ROOT / "HoodMan_2F_Map_1672x941.png").exists())
        self.assertEqual(hashlib.sha256((config.ROOT / config.ARCHIVED_TWO_FLOOR_IMAGE).read_bytes()).hexdigest(),
                         "85a213244657f914cda2c5c46f82f7fb4e41cce9b9f62c4e9876c66e7a5de049")
        self.assertTrue((config.ROOT / "before_sheets/newStage.png").is_file())
        self.assertTrue((config.ROOT / "changed_first_map.png").is_file())
        world.select_stage(1)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertEqual((world.stage_index, world.stage.image_name), (0, "changed_first_map.png"))
        self.assertEqual(len(world.stage.drop_items), 15)

    def test_first_floor_keeps_walking_spawns_and_items_below_the_new_storefronts(self):
        world = World(rng=random.Random(29), item_rng=random.Random(13))
        world.controls.press("up")
        world.controls.press("left_shift")
        advance(world, 0.7)
        self.assertEqual(world.player.ground_y, 277)
        self.assertEqual(world.player.jump_height, 0)
        self.assertEqual(world.player.ground_vy, 0)
        self.assertTrue(all(world.stage.drop_spawn_area.contains(item.x, item.ground_y)
                            for item in world.stage.drop_items if item.floor == 0))
        enemies = world.spawner.spawn(40, world.elapsed)
        self.assertTrue(any(enemy.ground_y > 120 for enemy in enemies))
        for enemy in enemies:
            self.assertTrue(world.stage.walkable.contains(enemy.x, enemy.ground_y,
                                                          enemy.boundary_padding))
        world.controls.release("up")
        world.controls.press("down")
        advance(world, 1.2)
        self.assertEqual(world.player.ground_y, -3)
        self.assertEqual(world.player.jump_height, 0)

    def test_first_floor_covers_the_full_source_pavement_without_entering_wall_or_curb(self):
        world = World()
        left, bottom, right, top = world.stage.walkable.bounds
        source_world_top = config.GROUND_Y - config.STAGE_GROUND_Y + config.STAGE_IMAGE_HEIGHT
        self.assertEqual((source_world_top - top, source_world_top - bottom), (620, 900))
        self.assertEqual((left, right), (0, config.WORLD_WIDTH))
        for x in (68, 300, 1280, 1672, 2260, 2492):
            for y in (-3, 0, 28, 56, 100, 268, 277):
                self.assertTrue(world.stage.walkable.contains(x, y, world.player.boundary_padding))
        self.assertFalse(world.stage.walkable.contains(1280, -3.01, 68))
        self.assertFalse(world.stage.walkable.contains(1280, 277.01, 68))
        self.assertEqual(config.STAGE_WALKABLE_BOUNDS[1:],
                          ((0, -44, 2560, 239), (0, -44, 2560, 247), (0, -44, 2560, 279),
                          (0, 0, 2560, 284), (0, 45, 2560, 258), (0, -3, 2560, 172),
                          (0, 16, 2560, 200), (0, -109, 2560, 178), (0, -48, 2560, 239),
                          (0, -28, 2560, 247), (0, -20, 2560, 242)))

    def test_each_loadout_can_walk_and_run_to_all_four_expanded_floor_corners(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for running in (False, True):
                for side in (-1, 1):
                    for depth in (-1, 1):
                        with self.subTest(weapon=weapon, running=running, side=side, depth=depth):
                            world = World()
                            player = world.player
                            player.equip_weapon(weapon)
                            player.x = player.previous_x = 300 if side < 0 else 2260
                            for key in ("left" if side < 0 else "right",
                                        "down" if depth < 0 else "up"):
                                world.controls.press(key)
                            if running:
                                world.controls.press("left_shift")
                            advance(world, 1.5)
                            self.assertEqual((player.x, player.ground_y),
                                             (68 if side < 0 else 2492, -3 if depth < 0 else 277))
                            self.assertEqual((player.floor, player.jump_height), (0, 0))
                            self.assertTrue(player.grounded)
                            self.assertTrue(world.stage.walkable.contains(
                                player.x, player.ground_y, player.boundary_padding))
                            self.assertGreaterEqual(player.y - world.camera.render_y, 0)

    def test_expanded_front_floor_keeps_jump_depth_and_weapon_discard_pickup_on_the_floor(self):
        for kind in config.WEAPON_POSE_IMAGES:
            world = World()
            player = world.player
            player.ground_y = player.previous_ground_y = -3
            world.controls.press("jump")
            advance(world, 0.05)
            tap(world.controls, "jump")
            advance(world, 1.5)
            self.assertTrue(player.grounded)
            self.assertEqual((player.ground_y, player.jump_height, player.floor), (-3, 0, 0))
            player.equip_weapon(kind)
            world.stage.drop_items.clear()
            tap(world.controls, "weapon_interact")
            world.step(config.FIXED_DT)
            self.assertIsNone(player.weapon)
            item = world.stage.drop_items[0]
            advance(world, 0.5)
            self.assertTrue(item.grounded)
            self.assertTrue(world.stage.walkable.contains(item.x, item.ground_y))
            tap(world.controls, "weapon_interact")
            world.step(config.FIXED_DT)
            self.assertEqual(player.weapon, kind)
            self.assertEqual(player.ground_y, -3)
            tap(world.controls, "restart")
            world.update(config.FIXED_DT)
            self.assertEqual(world.stage.walkable.bounds, (0, -3, config.WORLD_WIDTH, 277))
            self.assertEqual(world.player.walkable, world.stage.walkable)

    def test_n_reveals_only_the_first_stage_right_arrow_and_is_not_a_toggle(self):
        world = World()
        self.assertEqual(world.stage_index, 0)
        self.assertEqual(world.stage.image_name, "changed_first_map.png")
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

    def test_second_stage_has_both_markers_and_connects_to_the_city(self):
        world = World()
        world.stage_index = 1
        self.assertEqual(world.stage.image_name, "newStage-2_floor300_1672x941.png")
        self.assertEqual(world.stage.arrow_sides, ())
        world.controls.press("stage_exits")
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage.arrow_sides, (-1, 1))
        self.assertEqual(world.stage.destination(-1), 0)
        self.assertEqual(world.stage.destination(1), 2)

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

    def test_dead_n_is_consumed_and_restart_resets_all_scenes(self):
        world = World()
        for index in range(len(config.STAGE_IMAGES)):
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

    def test_both_directions_keep_walking_running_and_rising_or_falling_double_jumps(self):
        for side in (-1, 1):
            for state, speed, vertical_speed in (("WALK", 300, 0), ("RUN", 720, 0),
                                                  ("JUMP", 720, 400), ("JUMP", 300, -200)):
                with self.subTest(side=side, state=state, vertical_speed=vertical_speed):
                    world, reference = World(), World()
                    world.stage_index = 0 if side > 0 else 1
                    world.stage.arrows_visible = True
                    for scene in (world, reference):
                        clear_encounters(scene)
                        scene.elapsed = 12
                        player = scene.player
                        player.vx = side * speed
                        player.vy = vertical_speed
                        player.facing = side
                        player.hp = 440
                        if state == "JUMP":
                            player.y += 140
                            player.jump_count = 2
                            scene.controls.held.add("jump")
                        scene.controls.held.add("right" if side > 0 else "left")
                        if speed == 720:
                            scene.controls.held.add("left_shift")
                        player.animation.set_state(state)
                        player.animation.elapsed = 0.23
                    world.player.x = (config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
                                      if side > 0 else config.STAGE_EXIT_MARGIN)
                    player, controls = world.player, world.controls
                    held = set(controls.held)
                    world.camera.shake()
                    world.step(config.FIXED_DT)
                    reference.step(config.FIXED_DT)
                    self.assertEqual(world.stage_index, 1 if side > 0 else 0)
                    self.assertIs(world.player, player)
                    self.assertIs(world.controls, controls)
                    self.assertEqual(controls.held, held)
                    self.assert_same_motion(player, reference.player)
                    self.assertAlmostEqual(abs(player.x - player.previous_x), speed * config.FIXED_DT)
                    self.assertEqual(world.camera.shake_remaining, 0)
                    self.assertEqual(world.camera.x, 0 if side > 0 else
                                     config.WORLD_WIDTH - config.SCREEN_WIDTH)
                    advance(world, 0.1)
                    advance(reference, 0.1)
                    self.assert_same_motion(player, reference.player)
                    self.assertEqual(world.elapsed, reference.elapsed)

    def test_travel_requires_visible_markers_and_last_right_edge_stays_in_bounds(self):
        last = len(config.STAGE_IMAGES) - 1
        for index, side in ((0, -1), (0, 1), (last, 1)):
            with self.subTest(index=index, side=side):
                world = World()
                clear_encounters(world)
                world.stage_index = index
                world.stage.arrows_visible = index == last or side < 0
                world.player.x = (config.PLAYER_HALF_WIDTH if side < 0 else
                                  config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)
                world.controls.press("left" if side < 0 else "right")
                world.controls.press("left_shift")
                advance(world, 0.5)
                self.assertEqual(world.stage_index, index)
                self.assertGreaterEqual(world.player.x, config.PLAYER_HALF_WIDTH)
                self.assertLessEqual(world.player.x, config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)
                if index == 0 and side > 0:
                    world.controls.press("stage_exits")
                    world.step(config.FIXED_DT)
                    self.assertEqual(world.stage_index, 1)
                    self.assertGreater(world.player.vx, 0)

    def test_n_stays_local_during_travel_and_return_does_not_bounce(self):
        world = clear_encounters(World())
        world.controls.press("stage_exits")
        world.controls.press("right")
        world.controls.press("left_shift")
        world.player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
        world.player.vx = 720
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage_index, 1)
        self.assertEqual(world.stage.arrow_sides, ())
        self.assertIn("stage_exits", world.controls.held)
        world.controls.press("stage_exits")
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage.arrow_sides, ())
        tap(world.controls, "stage_exits")
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage.arrow_sides, (-1, 1))
        world.controls.release("right")
        world.controls.press("left")
        world.player.x = config.STAGE_EXIT_MARGIN
        world.player.vx = -720
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage_index, 0)
        self.assertEqual(world.stage.arrow_sides, (1,))
        advance(world, 0.1)
        self.assertEqual(world.stage_index, 0)
        self.assertLess(world.player.x, config.WORLD_WIDTH - config.STAGE_ENTRY_MARGIN)

    def test_real_round_trip_restores_scene_objects_and_pauses_inactive_simulation(self):
        world = World()
        for index, count in ((0, 3), (1, 2)):
            world.stage_index = index
            spawn_encounter(world, count)
            stage = world.stage
            for index, enemy in enumerate(stage.enemies):
                enemy.x = 800 + index * 120
        world.stage_index = 0
        first = world.stage
        first.enemies[0].take_damage(20)
        first.effects.append(HitEffect(600, 180, 1))
        positions = [enemy.x for enemy in first.enemies]
        world.controls.press("right")
        world.controls.press("left_shift")
        world.controls.press("stage_exits")
        world.player.vx = 720
        world.player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage_index, 1)
        advance(world, 0.2)
        second = world.stage
        self.assertEqual(len(second.enemies), 2)
        self.assertEqual(first.spawner.spawned_count, 3)
        self.assertEqual(first.effects[0].elapsed, 0)
        self.assertEqual([enemy.x for enemy in first.enemies], positions)
        world.controls.release("right")
        world.controls.press("left")
        tap(world.controls, "stage_exits")
        world.player.x = config.STAGE_EXIT_MARGIN
        world.player.vx = -720
        world.step(config.FIXED_DT)
        self.assertIs(world.stage, first)
        self.assertEqual(first.enemies[0].hp, 180)
        self.assertEqual(world.spawner.spawned_count, 3)
        self.assertEqual(first.effects[0].elapsed, config.FIXED_DT)
        self.assertEqual(second.spawner.spawned_count, 2)

    def test_attacks_hit_and_death_cannot_trigger_travel(self):
        for action in ("combat_a", "HIT", "DYING", "DEAD"):
            with self.subTest(action=action):
                world = World()
                world.stage.arrows_visible = True
                world.controls.press("right")
                world.player.x = config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH
                if action.startswith("combat_"):
                    world.controls.press(action)
                    world.player.start_move(MOVES[action], -1)
                    world.player.vx = 240
                else:
                    world.player.animation.set_state(action)
                    if action in ("DYING", "DEAD"):
                        world.player.hp = 0
                advance(world, 0.1)
                self.assertEqual(world.stage_index, 0)
                self.assertLessEqual(world.player.x, config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)

    def test_round_trip_is_identical_across_render_rates(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world = clear_encounters(World())
            for stage in world.stages:
                stage.arrows_visible = True
            world.player.x = config.WORLD_WIDTH - 300
            world.player.vx = 720
            world.controls.press("right")
            world.controls.press("left_shift")
            advance(world, 1, fps)
            self.assertEqual(world.stage_index, 1)
            world.controls.release("right")
            world.controls.press("left")
            advance(world, 1.5, fps)
            self.assertEqual(world.stage_index, 0)
            outcomes.append((world.stage_index, world.player.x, world.player.vx,
                             world.player.y, world.player.state, world.player.animation.frame))
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
