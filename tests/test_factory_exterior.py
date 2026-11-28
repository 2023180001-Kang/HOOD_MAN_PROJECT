import hashlib
import random
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import config
from assets import Assets
from axe_enemy import AxeEnemy
from tests.helpers import advance, tap
from tests.helpers import ManualSpawnWorld as World
from world import World as CampaignWorld


class FactoryExteriorTests(unittest.TestCase):
    def test_last_enemy_opens_gate_and_walking_to_it_starts_one_second_fade_to_dock(self):
        for fps in (30, 60, 144):
            with self.subTest(fps=fps):
                world = CampaignWorld(rng=random.Random(13))
                world.reset(stage_index=4)
                exterior = world.stage
                player = world.player
                player.equip_weapon("sword")
                player.hp = 275
                for key in ("stage_exits", "toggle_doors", "spawn_1"):
                    tap(world.controls, key)
                world.step(config.FIXED_DT)
                player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
                world.controls.press("right")
                self.assertIsNone(exterior.destination(1))
                self.assertFalse(world.try_stage_transition())
                self.assertEqual(len(world.enemies), 5)
                for enemy in world.enemies[:4]:
                    enemy.take_damage(enemy.hp)
                world.step(config.FIXED_DT)
                self.assertNotIn(4, world.cleared_stages)
                self.assertFalse(world.stage_loading)
                self.assertEqual(exterior.factory_gate.frame, 0)
                world.enemies[-1].take_damage(world.enemies[-1].hp)
                world.step(config.FIXED_DT)
                self.assertTrue(world.opening_factory_exit)
                self.assertIn(4, world.cleared_stages)
                frames = set()
                while world.opening_factory_exit:
                    frames.add(exterior.factory_gate.frame)
                    self.assertIsNone(world.pending_stage_index)
                    self.assertIs(world.stage, exterior)
                    world.update(1 / fps)
                self.assertEqual(frames, set(range(8)))
                self.assertTrue(exterior.factory_gate.finished)
                advance(world, 3, fps=fps)  # Walking against the right edge cannot enter the dock.
                self.assertIs(world.stage, exterior)
                self.assertFalse(world.stage_loading)
                world.controls.release("right")
                world.controls.press("up")
                for _ in range(2 * fps):
                    world.update(1 / fps)
                    if world.entering_factory_gate:
                        break
                world.controls.release("up")
                self.assertTrue(world.entering_factory_gate)
                self.assertTrue(exterior.at_open_factory_gate(player))
                self.assertEqual(world.stage_loading_remaining, 1.0)
                while world.stage_loading_remaining > 0:
                    world.update(1 / fps)
                self.assertIs(world.stage, exterior)  # A fully black frame precedes entry.
                world.update(1 / fps)
                self.assertEqual(world.stage.image_name, config.FACTORY_OUTSIDE_IMAGE)
                self.assertEqual(len(world.enemies), 0)
                self.assertIs(world.player, player)
                self.assertEqual((player.hp, player.weapon), (275, "sword"))
                advance(world, 1, fps=fps)
                self.assertEqual(len(world.enemies), 4)
                world.select_stage(4)
                world.step(config.FIXED_DT)
                self.assertFalse(world.opening_factory_exit)
                self.assertIsNone(exterior.destination(1))
                self.assertTrue(exterior.factory_gate.finished)

    def test_held_movement_and_new_jump_work_while_gate_is_still_opening(self):
        world = CampaignWorld()
        world.reset(stage_index=4)
        player = world.player
        center, sill = world.stage.factory_doorway(player.x)
        player.x, player.ground_y = center, sill - 60
        world.controls.press("up")
        for enemy in world.enemies:
            enemy.take_damage(enemy.hp)
        world.step(config.FIXED_DT)
        self.assertTrue(world.opening_factory_exit)
        depth = player.ground_y
        advance(world, 0.5)
        self.assertGreater(player.ground_y, depth)
        self.assertLessEqual(abs(player.ground_y - sill), config.FACTORY_GATE_ENTRY_DEPTH)
        self.assertFalse(world.stage_loading)
        self.assertFalse(world.try_stage_transition())
        world.controls.release("up")
        world.controls.press("left")
        tap(world.controls, "jump")
        advance(world, 0.15)
        self.assertTrue(world.opening_factory_exit)
        self.assertLess(player.x, center)
        self.assertGreater(player.jump_height, 0)
        self.assertGreater(world.stage.factory_gate.frame, 0)

    def test_restart_during_opening_wait_or_fade_restores_closed_gate(self):
        for phase in ("opening", "waiting", "fade"):
            world = CampaignWorld()
            world.reset(stage_index=4)
            for enemy in world.enemies:
                enemy.take_damage(enemy.hp)
            world.step(config.FIXED_DT)
            advance(world, 1.0 if phase == "opening" else config.FACTORY_GATE_DURATION + config.FIXED_DT,
                    fps=120)
            if phase == "fade":
                world.player.x = world.stage.factory_doorway(world.player.x)[0]
                world.player.ground_y = world.stage.walkable.bounds[3]
                world.step(config.FIXED_DT)
                self.assertTrue(world.entering_factory_gate)
                world.update(0.5)
            tap(world.controls, "restart")
            world.update(config.FIXED_DT)
            self.assertEqual(world.stage_index, 0)
            world.select_stage(4)
            self.assertFalse(world.stage_loading)
            self.assertEqual(world.stage.factory_gate.frame, 0)
            advance(world, 1)
            self.assertEqual(len(world.enemies), 4)

    def test_doorless_background_loads_and_previous_exteriors_are_archived_unchanged(self):
        self.assertEqual(config.FACTORY_EXTERIOR_IMAGE, "factoryOutside_no_door.png")
        self.assertEqual(config.ARCHIVED_FACTORY_EXTERIOR_IMAGE,
                         "before_sheets/HOOD_MAN_Factory_Exterior_1672x941.png")
        self.assertEqual(config.STAGE_IMAGES[4], config.FACTORY_EXTERIOR_IMAGE)
        hashes = {
            config.FACTORY_EXTERIOR_IMAGE: "03d04bbfe9a72ab4cfe627edadd730959dddc5ea69c7e854d087ea745a671821",
            "before_sheets/factoryOutside_floor300.px.png": "28c6f90843cf69f88fb35139baded5dac89980a0ace28166110114b80cd5bccf",
            config.ARCHIVED_FACTORY_EXTERIOR_IMAGE: "e23679ae1e7ec071c9a16b97381e9739488df390dcda7c229974b1e5f784297e",
        }
        for name, digest in hashes.items():
            path = config.ROOT / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with Image.open(path) as image:
                self.assertEqual((image.size, image.mode), ((1672, 941), "RGB"))
        self.assertFalse((config.ROOT / "HOOD_MAN_Factory_Exterior_1672x941.png").exists())
        with patch("pico2d.load_image", return_value=Mock()), patch("pico2d.load_font"):
            assets = Assets()
        self.assertFalse((config.ROOT / "factoryOutside_floor300.px.png").exists())
        self.assertIn(config.FACTORY_GATE_IMAGE, assets.images)
        self.assertIn(config.FACTORY_EXTERIOR_IMAGE, assets.images)
        self.assertNotIn(config.ARCHIVED_FACTORY_EXTERIOR_IMAGE, assets.images)
        self.assertNotIn("HOOD_MAN_Factory_Exterior_1672x941.png", assets.images)

    def test_full_asphalt_floor_runs_from_below_wall_and_prop_bases_to_image_bottom(self):
        stage = World().stages[4]
        self.assertEqual(stage.walkable.bounds, (0, 0, 2560, 284))
        anchor = config.STAGE_GROUND_ANCHORS[stage.image_name]
        source_world_top = config.GROUND_Y - anchor + config.STAGE_IMAGE_HEIGHT
        self.assertEqual((config.STAGE_SCALE, anchor, source_world_top), (1, 100, 941))
        self.assertEqual((source_world_top - stage.walkable.bounds[3],
                          source_world_top - stage.walkable.bounds[1]), (657, 941))
        self.assertEqual(stage.floor_areas, (stage.walkable,))
        self.assertIsNone(stage.upper_walkable)
        self.assertEqual((stage.stairs, stage.doors), ([], []))
        self.assertIsNone(stage.traffic)
        self.assertIs(stage.spawn_area, stage.walkable)
        self.assertIs(stage.drop_spawn_area, stage.walkable)
        for x in (68, 300, 490, 1280, 1490, 1672, 2260, 2492):
            for source_y in range(657, 942):
                self.assertTrue(stage.walkable.contains(x, source_world_top - source_y, 68))
        self.assertFalse(stage.walkable.contains(1280, -0.01, 68))
        self.assertFalse(stage.walkable.contains(490, 284.01, 68))

    def test_all_loadouts_walk_and_run_to_all_four_expanded_exterior_corners(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for running in (False, True):
                for side in (-1, 1):
                    for depth in (-1, 1):
                        with self.subTest(weapon=weapon, running=running, side=side, depth=depth):
                            world = World()
                            world.select_stage(4)
                            player = world.player
                            player.equip_weapon(weapon)
                            player.x = player.previous_x = 300 if side < 0 else 2260
                            world.controls.press("left" if side < 0 else "right")
                            world.controls.press("down" if depth < 0 else "up")
                            if running:
                                world.controls.press("left_shift")
                            advance(world, 1.5)
                            self.assertEqual((player.x, player.ground_y, player.floor, player.jump_height),
                                             (68 if side < 0 else 2492, 0 if depth < 0 else 284, 0, 0))
                            self.assertTrue(player.grounded)
                            self.assertIsNone(player.staircase)
                            self.assertGreaterEqual(player.y - world.camera.render_y, 0)

    def test_both_depth_edges_keep_running_double_jumps_and_g_interaction_on_the_floor(self):
        for depth in (0, 284):
            for weapon in config.WEAPON_POSE_IMAGES:
                with self.subTest(depth=depth, weapon=weapon):
                    world = World()
                    world.select_stage(4)
                    player = world.player
                    player.ground_y = player.previous_ground_y = depth
                    world.controls.press("up" if depth else "down")
                    world.controls.press("left_shift")
                    world.controls.press("jump")
                    advance(world, 0.05)
                    tap(world.controls, "jump")
                    advance(world, 1.5)
                    self.assertTrue(player.grounded)
                    self.assertEqual((player.ground_y, player.floor, player.jump_height), (depth, 0, 0))
                    self.assertIsNone(player.staircase)
                    world.controls.held.clear()
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

    def test_axe_spawns_items_pursuit_revisit_and_f5_share_the_expanded_exterior_floor(self):
        world = World(rng=random.Random(41), item_rng=random.Random(23))
        world.select_stage(4)
        stage = world.stage
        self.assertEqual(world.enemies, [])
        self.assertEqual(len(stage.drop_items), 15)
        self.assertTrue(all(item.floor == 0 and stage.walkable.contains(item.x, item.ground_y)
                            for item in stage.drop_items))
        self.assertTrue(any(item.ground_y < 56 for item in stage.drop_items))
        self.assertTrue(any(item.ground_y > 100 for item in stage.drop_items))
        tap(world.controls, "spawn_9")
        world.step(config.FIXED_DT)
        self.assertEqual((len(world.enemies), stage.spawner.spawned_count), (9, 9))
        self.assertTrue(all(type(enemy) is AxeEnemy and enemy.hp == 400 and enemy.attack_damage == 40
                            and stage.walkable.contains(enemy.x, enemy.ground_y, 88)
                            for enemy in world.enemies))
        self.assertTrue(any(enemy.ground_y < 56 for enemy in world.enemies))
        self.assertTrue(any(enemy.ground_y > 100 for enemy in world.enemies))
        first, items = world.enemies[0], stage.drop_items
        first.take_damage(40)
        snapshot = first.x, first.ground_y, first.animation.elapsed
        world.select_stage(5)
        advance(world, 1)
        world.select_stage(4)
        self.assertIs(world.stage, stage)
        self.assertIs(world.enemies[0], first)
        self.assertIs(stage.drop_items, items)
        self.assertEqual((first.hp, stage.spawner.spawned_count), (360, 9))
        self.assertEqual((first.x, first.ground_y, first.animation.elapsed), snapshot)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertEqual(world.stage_index, 0)
        self.assertEqual(world.stages[4].image_name, config.FACTORY_EXTERIOR_IMAGE)
        self.assertEqual(world.stages[4].walkable.bounds, (0, 0, 2560, 284))
        self.assertEqual((world.stages[4].enemies, world.stages[4].spawner.spawned_count), ([], 0))
        self.assertEqual(len(world.stages[4].drop_items), 15)
        for depth, opposite in ((0, 284), (284, 0)):
            world = World()
            world.select_stage(4)
            world.player.invincible = True
            world.player.ground_y = depth
            enemy = AxeEnemy(world.player.x + 150, -1, ground_y=opposite)
            world.enemies.append(enemy)
            advance(world, 3)
            self.assertLessEqual(abs(enemy.ground_y - depth), config.ATTACK_DEPTH_TOLERANCE)
            self.assertTrue(world.stage.walkable.contains(enemy.x, enemy.ground_y, 88))
            self.assertEqual(enemy.floor, 0)

    def test_dock_and_interior_travel_preserve_common_depth_and_only_project_outside_values(self):
        cases = ((5, 4, 45, 45), (5, 4, 258, 258),
                 (4, 3, 0, 0), (4, 3, 284, 279),
                 (5, 6, 45, 45), (5, 6, 258, 172),
                 (6, 5, 56, 56), (6, 5, 148, 148))
        for source, destination, depth, projected in cases:
            with self.subTest(source=source, destination=destination, depth=depth):
                world = World()
                world.select_stage(source)
                stage, player = world.stage, world.player
                stage.arrows_visible = True
                side = 1 if destination > source else -1
                player.x = (config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN if side > 0
                            else config.STAGE_EXIT_MARGIN)
                player.ground_y = depth
                player.hp, player.invincible = 420, True
                player.jump_height, player.vy, player.jump_count = 150, -100, 2
                player.vx = side * config.RUN_SPEED
                player.animation.set_state("JUMP")
                player.animation.elapsed = 0.25
                world.controls.press("right" if side > 0 else "left")
                world.controls.press("left_shift")
                held = set(world.controls.held)
                self.assertTrue(world.try_stage_transition())
                loading = (source, destination) in config.STAGE_LOADING_TRANSITIONS
                self.assertEqual(world.stage_loading, loading)
                if loading:
                    world.update(world.stage_loading_remaining - 0.001)
                    self.assertTrue(world.stage_loading)
                    self.assertEqual(world.stage_index, source)
                    self.assertEqual(player.ground_y, depth)
                    world.update(0.001)
                    if destination == 3:
                        world.update(0)
                self.assertFalse(world.stage_loading)
                self.assertEqual(world.stage_index, destination)
                self.assertIs(world.player, player)
                self.assertEqual((player.ground_y, player.previous_ground_y), (projected, projected))
                self.assertEqual((player.hp, player.invincible, player.jump_height, player.vy,
                                  player.jump_count, player.vx, player.animation.elapsed),
                                 (420, True, 150, -100, 2, side * config.RUN_SPEED, 0.25))
                self.assertEqual(world.controls.held, held)
                self.assertFalse(world.try_stage_transition())


if __name__ == "__main__":
    unittest.main()
