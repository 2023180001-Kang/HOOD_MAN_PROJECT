import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pico2d

import config
from ar_soldier import ARSoldier
from axe_enemy import AxeEnemy
from enemy import Enemy
from enemy02 import Enemy02
from game import KEYS
from researcher import Researcher
from shield_soldier import ShieldSoldier
from stage import enemy_type_for_stage
from tests.helpers import advance, tap
from ui import ENEMY_BOUNDS_COLOR, UI
from world import World


NATIVE_TYPES = (Enemy, Enemy, Enemy02, Enemy02, AxeEnemy, Enemy,
                Researcher, Researcher, ShieldSoldier, ShieldSoldier, ARSoldier, ARSoldier)


def press(world, action):
    tap(world.controls, action)
    world.update(config.FIXED_DT)


class SpawnEnemyCycleTests(unittest.TestCase):
    def test_m_binding_and_default_native_types_are_unchanged(self):
        self.assertEqual(KEYS[pico2d.SDLK_m], "cycle_spawn_enemy")
        world = World()
        for index, expected in enumerate(NATIVE_TYPES):
            stage = world.stages[index]
            self.assertIsNone(stage.spawn_cycle_index)
            self.assertEqual(stage.spawn_enemy_stage_index, index)
            self.assertIs(enemy_type_for_stage(index), expected)
            self.assertIs(stage.spawner.enemy_type, expected)
            self.assertEqual((stage.enemies, stage.spawner.spawned_count), ([], 0))

    def test_every_nonfirst_map_starts_at_first_then_cycles_all_stage_entries_and_wraps(self):
        for index in range(1, len(config.STAGE_IMAGES)):
            world = World()
            world.select_stage(index)
            stage, player = world.stage, world.player
            image, area, items = stage.image_name, stage.walkable, stage.drop_items
            for ordinal in range(len(NATIVE_TYPES) * 2 + 1):
                press(world, "cycle_spawn_enemy")
                source = ordinal % len(NATIVE_TYPES)
                self.assertEqual((world.stage_index, stage.spawn_enemy_stage_index), (index, source))
                self.assertIs(stage.spawner.enemy_type, NATIVE_TYPES[source])
                self.assertIs(world.stage, stage)
                self.assertIs(world.player, player)
                self.assertEqual(stage.image_name, image)
                self.assertIs(stage.walkable, area)
                self.assertIs(stage.drop_items, items)
                self.assertEqual((stage.enemies, stage.spawner.spawned_count), ([], 0))

    def test_first_map_m_is_a_noop_even_with_existing_enemies(self):
        world = World(rng=random.Random(31))
        press(world, "spawn_2")
        enemies = tuple(world.enemies)
        rng = world.spawner.rng.getstate()
        for _ in range(24):
            press(world, "cycle_spawn_enemy")
        self.assertEqual(world.stage_index, 0)
        self.assertIsNone(world.stage.spawn_cycle_index)
        self.assertEqual(world.stage.spawn_enemy_stage_index, 0)
        self.assertIs(world.spawner.enemy_type, Enemy)
        self.assertEqual(tuple(world.enemies), enemies)
        self.assertEqual(world.spawner.spawned_count, 2)
        self.assertEqual(world.spawner.rng.getstate(), rng)
        self.assertTrue(all(type(enemy) is Enemy and enemy.hp == 200 for enemy in enemies))

    def test_m_hold_and_duplicate_presses_do_not_skip_entries(self):
        world = World()
        world.select_stage(8)
        world.controls.press("cycle_spawn_enemy")
        advance(world, 0.5)
        self.assertEqual(world.stage.spawn_enemy_stage_index, 0)
        for _ in range(10):
            world.controls.press("cycle_spawn_enemy")
            world.update(config.FIXED_DT)
        self.assertEqual(world.stage.spawn_enemy_stage_index, 0)
        press(world, "cycle_spawn_enemy")
        self.assertEqual(world.stage.spawn_enemy_stage_index, 1)
        self.assertIs(world.spawner.enemy_type, Enemy)  # Two consecutive stages share this art.
        press(world, "cycle_spawn_enemy")
        self.assertEqual(world.stage.spawn_enemy_stage_index, 2)
        self.assertIs(world.spawner.enemy_type, Enemy02)

    def test_all_numeric_counts_use_selected_type_without_changing_the_map(self):
        for count in config.SPAWN_COUNTS:
            world = World(rng=random.Random(41))
            world.select_stage(8)
            press(world, "cycle_spawn_enemy")
            self.assertEqual(world.enemies, [])
            press(world, f"spawn_{count}")
            self.assertEqual((world.stage_index, len(world.enemies), world.spawner.spawned_count),
                             (8, count, count))
            self.assertTrue(all(type(enemy) is Enemy and enemy.hp == 200 for enemy in world.enemies))
            world.controls.press(f"spawn_{count}")
            advance(world, 0.1)
            self.assertEqual(len(world.enemies), count)
            press(world, f"spawn_{count}")
            self.assertEqual(len(world.enemies), count * 2)

    def test_same_tick_m_is_applied_before_numeric_requests_in_either_input_order(self):
        for actions in (("cycle_spawn_enemy", "spawn_2", "spawn_5"),
                        ("spawn_5", "spawn_2", "cycle_spawn_enemy")):
            world = World()
            world.select_stage(6)
            for action in actions:
                world.controls.press(action)
            world.update(config.FIXED_DT)
            self.assertEqual((world.stage_index, world.stage.spawn_enemy_stage_index), (6, 0))
            self.assertEqual((len(world.enemies), world.spawner.spawned_count), (7, 7))
            self.assertTrue(all(type(enemy) is Enemy for enemy in world.enemies))

    def test_all_selected_types_spawn_on_each_current_maps_own_floor_with_unique_profiles(self):
        for index in range(1, len(config.STAGE_IMAGES)):
            world = World(rng=random.Random(41))
            world.select_stage(index)
            stage = world.stage
            enemies = []
            for source, expected in enumerate(NATIVE_TYPES):
                stage.cycle_spawn_enemy_type()
                self.assertEqual(stage.spawn_enemy_stage_index, source)
                spawned = world.spawner.spawn(3, world.elapsed)
                enemies.extend(spawned)
                self.assertTrue(all(type(enemy) is expected and enemy.hp == expected.max_hp
                                    and enemy.walkable is stage.walkable and enemy.floor == 0
                                    and stage.spawn_area.contains(enemy.x, enemy.ground_y,
                                                                  enemy.boundary_padding)
                                    for enemy in spawned))
                if expected is Researcher:
                    self.assertTrue(all(enemy.ammo == 7 and enemy.attack_damage == 30 for enemy in spawned))
                if expected is ShieldSoldier:
                    self.assertTrue(all(enemy.attack_damage == 40 for enemy in spawned))
                if expected is ARSoldier:
                    self.assertTrue(all(enemy.hp == 300 and enemy.attack_damage == 10 for enemy in spawned))
            self.assertEqual(stage.spawner.spawned_count, 36)
            self.assertEqual(len({enemy.attack_speed for enemy in enemies}), 36)
            self.assertEqual([enemy.run_speed for enemy in enemies[:4]], list(config.ENEMY_RUN_SPEEDS))

    def test_changing_selection_does_not_replace_or_reset_existing_actors_or_feedback(self):
        world = World(rng=random.Random(23))
        world.select_stage(8)
        enemies = world.spawner.spawn(2, 0)
        world.enemies.extend(enemies)
        enemies[0].start_guard()
        enemies[0].take_damage(40)
        snapshots = [vars(enemy).copy() for enemy in enemies]
        items, effects, numbers, projectiles = (world.stage.drop_items, world.effects,
                                                world.damage_numbers, world.projectiles)
        rng, count = world.spawner.rng.getstate(), world.spawner.spawned_count
        world.stage.cycle_spawn_enemy_type()
        self.assertEqual(world.enemies, enemies)
        self.assertEqual([vars(enemy) for enemy in enemies], snapshots)
        self.assertIs(world.stage.drop_items, items)
        self.assertIs(world.effects, effects)
        self.assertIs(world.damage_numbers, numbers)
        self.assertIs(world.projectiles, projectiles)
        self.assertEqual((world.spawner.rng.getstate(), world.spawner.spawned_count), (rng, count))
        press(world, "spawn_1")
        self.assertTrue(all(type(enemy) is ShieldSoldier for enemy in world.enemies[:2]))
        self.assertIs(type(world.enemies[-1]), Enemy)
        self.assertEqual([enemy.hp for enemy in world.enemies], [380, 400, 200])

    def test_cycle_never_consumes_spawn_randomness_or_speed_allocations(self):
        world = World(rng=random.Random(29), item_rng=random.Random(17))
        reference = World(rng=random.Random(29), item_rng=random.Random(17))
        world.select_stage(6)
        reference.select_stage(6)
        clocks = [item.elapsed for item in world.stage.drop_items]
        for _ in range(25):
            world.stage.cycle_spawn_enemy_type()
        self.assertEqual(world.spawner.rng.getstate(), reference.spawner.rng.getstate())
        self.assertEqual([item.elapsed for item in world.stage.drop_items], clocks)
        actual = world.spawner.spawn(9, 1)
        expected = reference.spawner.spawn(9, 1)
        self.assertEqual([(enemy.facing, enemy.ground_y, enemy.run_speed, enemy.attack_speed)
                          for enemy in actual],
                         [(enemy.facing, enemy.ground_y, enemy.run_speed, enemy.attack_speed)
                          for enemy in expected])

    def test_selections_are_per_map_and_continue_after_revisiting(self):
        world = World()
        world.select_stage(8)
        for _ in range(7):
            press(world, "cycle_spawn_enemy")
        self.assertIs(world.spawner.enemy_type, Researcher)
        world.select_stage(3)
        self.assertEqual(world.stage.spawn_enemy_stage_index, 3)
        self.assertIsNone(world.stage.spawn_cycle_index)
        press(world, "cycle_spawn_enemy")
        self.assertEqual(world.stage.spawn_enemy_stage_index, 0)
        world.select_stage(0)
        press(world, "cycle_spawn_enemy")
        self.assertIsNone(world.stage.spawn_cycle_index)
        world.select_stage(8)
        self.assertEqual(world.stage.spawn_enemy_stage_index, 6)
        press(world, "cycle_spawn_enemy")
        self.assertEqual(world.stage.spawn_enemy_stage_index, 7)
        world.select_stage(3)
        self.assertEqual(world.stage.spawn_enemy_stage_index, 0)

    def test_loading_discards_m_and_does_not_cycle_either_scene_or_buffer_held_input(self):
        world = World()
        world.select_stage(8)
        press(world, "cycle_spawn_enemy")
        world.pending_stage_index, world.stage_loading_remaining = 9, 2
        tap(world.controls, "cycle_spawn_enemy")
        world.controls.press("spawn_9")
        world.update(1)
        self.assertEqual(world.stages[8].spawn_enemy_stage_index, 0)
        self.assertIsNone(world.stages[9].spawn_cycle_index)
        world.update(1)
        world.controls.press("cycle_spawn_enemy")  # Still held after loading.
        world.update(config.FIXED_DT)
        self.assertEqual(world.stage_index, 9)
        self.assertIsNone(world.stage.spawn_cycle_index)
        self.assertEqual(world.enemies, [])
        press(world, "cycle_spawn_enemy")
        self.assertEqual(world.stage.spawn_enemy_stage_index, 0)

    def test_dead_input_is_consumed_and_f5_restores_every_maps_native_selection(self):
        world = World()
        for index in range(1, len(NATIVE_TYPES)):
            world.select_stage(index)
            world.stage.cycle_spawn_enemy_type()
        world.player.take_damage(500)
        press(world, "cycle_spawn_enemy")
        self.assertEqual(world.stage.spawn_enemy_stage_index, 0)
        self.assertNotIn("cycle_spawn_enemy", world.controls.pressed)
        tap(world.controls, "cycle_spawn_enemy")
        tap(world.controls, "spawn_9")
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        for index, stage in enumerate(world.stages):
            self.assertIsNone(stage.spawn_cycle_index)
            self.assertEqual(stage.spawn_enemy_stage_index, index)
            self.assertIs(stage.spawner.enemy_type, NATIVE_TYPES[index])
            self.assertEqual((stage.enemies, stage.spawner.spawned_count), ([], 0))
        self.assertFalse(world.controls.pressed)

    def test_m_does_not_cancel_player_attacks_and_still_selects_during_slow_motion(self):
        world = World()
        world.select_stage(6)
        press(world, "combat_r")
        move = world.player.active_move
        self.assertEqual(world.time_scale, 0.2)
        press(world, "cycle_spawn_enemy")
        self.assertIs(world.player.active_move, move)
        self.assertEqual((world.time_scale, world.stage.spawn_enemy_stage_index), (0.2, 0))
        press(world, "spawn_1")
        self.assertIs(type(world.enemies[0]), Enemy)
        self.assertIs(world.player.active_move, move)

    def test_cycle_order_is_identical_at_all_render_rates(self):
        results = []
        for fps in (30, 60, 120, 144):
            world = World()
            world.select_stage(6)
            sequence = []
            for _ in range(26):
                tap(world.controls, "cycle_spawn_enemy")
                advance(world, 0.5, fps)
                sequence.append((world.stage.spawn_enemy_stage_index, world.spawner.enemy_type))
            results.append(sequence)
        self.assertTrue(all(result == results[0] for result in results))

    def test_selected_enemy02_f4_padding_does_not_change_existing_shield_padding(self):
        world = World()
        world.select_stage(8)
        enemy = world.spawner.spawn(1, 0)[0]
        world.enemies.append(enemy)
        for _ in range(3):
            world.stage.cycle_spawn_enemy_type()
        ui = UI()
        ui.floor_bounds_visible = True
        with patch("pico2d.draw_line") as draw:
            ui.draw_floor_bounds(world, 0, 0)
        xs = [x for call in draw.call_args_list if call.args[4:] == ENEMY_BOUNDS_COLOR
              for x in (call.args[0], call.args[2])]
        self.assertEqual((min(xs), max(xs)), (128, 2432))
        self.assertEqual(enemy.boundary_padding, 88)
        self.assertIs(type(enemy), ShieldSoldier)

    def test_mixed_enemy_deaths_do_not_add_items_regardless_of_map_or_selection(self):
        world = World()
        world.select_stage(8)
        items = list(world.stage.drop_items)
        shield = world.spawner.spawn(1, 0)[0]
        world.enemies.append(shield)
        world.stage.cycle_spawn_enemy_type()
        thug = world.spawner.spawn(1, 0)[0]
        world.enemies.append(thug)
        shield.take_damage(400)
        thug.take_damage(200)
        world.step(config.FIXED_DT)
        self.assertFalse(shield.alive or thug.alive)
        self.assertEqual(world.stage.drop_items, items)
        self.assertFalse(any(item.kind == "metal_club" for item in world.stage.drop_items))
        self.assertEqual(len(world.stage.drop_items), 15)

    def test_hud_tracks_selected_source_damage_and_m_help_and_respects_u_hiding(self):
        world = World()
        world.select_stage(6)
        assets = SimpleNamespace(font=Mock(), images={config.HP_IMAGE: Mock(w=700, h=80)})
        ui = UI()
        expected_help = ("20", "20", "몽둥이", "몽둥이", "도끼", "20",
                         "권총", "권총", "방패", "방패", "소총", "소총")
        for source, keyword in enumerate(expected_help):
            world.stage.cycle_spawn_enemy_type()
            assets.font.reset_mock()
            with patch("pico2d.draw_rectangle"):
                ui.draw(assets, world)
            labels = [call.args[2] for call in assets.font.draw.call_args_list]
            self.assertTrue(any("M 소환 적 순환" in label and f"{source + 1}번 맵" in label
                                for label in labels))
            self.assertTrue(any(keyword in label and ("적 공격" in label or "적 권총" in label)
                                for label in labels))
            self.assertTrue(any("1~9" in label for label in labels))
        ui.details_visible = False
        assets.font.reset_mock()
        with patch("pico2d.draw_rectangle"):
            ui.draw(assets, world)
        self.assertEqual([call.args[2] for call in assets.font.draw.call_args_list], ["500 / 500"])


if __name__ == "__main__":
    unittest.main()
