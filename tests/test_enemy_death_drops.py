import random
import unittest
from unittest.mock import Mock, patch

import config
from assets import Assets
from drop_items import DropItem
from enemy import Enemy
from tests.helpers import advance, archived_two_floor_map, tap
from tests.test_stair_combat_and_drops import on_stairs
from tests.test_strong_attacks import encounter, strike
from tests.test_two_floors import place
from tests.test_weapon_combat import target
from tests.test_weapon_leap import aim
from tests.helpers import ManualSpawnWorld as World


def drop_world():
    world = World(rng=random.Random(41), item_rng=random.Random(5))
    world.player.invincible = True
    world.stage.drop_items.clear()
    enemy = Enemy(world.player.x + 65, -1, ground_y=world.player.ground_y)
    world.enemies = [enemy]
    return world, enemy


class RemovedEnemyDeathDropTests(unittest.TestCase):
    def test_live_and_nonlethally_hit_enemies_do_not_add_items(self):
        world, enemy = drop_world()
        world.step(config.FIXED_DT)
        enemy.take_damage(40)
        advance(world, 0.5)
        self.assertTrue(enemy.alive)
        self.assertEqual(world.stage.drop_items, [])

    def test_basic_and_equipped_kills_keep_damage_and_death_without_dropping_items(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for key in ("asdf" if weapon is None else "asf"):
                for side in (-1, 1):
                    with self.subTest(weapon=weapon, key=key, side=side):
                        world, enemy = encounter(side=side, weapon=weapon)
                        move = world.player.moves[f"combat_{key}"]
                        enemy.hp = move.damage
                        strike(world, enemy, f"combat_{key}")
                        self.assertEqual((enemy.hp, enemy.state), (0, "DYING"))
                        self.assertEqual([number.damage for number in world.damage_numbers],
                                         [move.damage])
                        self.assertEqual(world.effects[-1].image_name, move.hit_image)
                        self.assertEqual(world.stage.drop_items, [])
                        advance(world, 6)
                        self.assertNotIn(enemy, world.enemies)
                        expected = [weapon] if weapon is not None and key == "s" else []
                        self.assertEqual([item.kind for item in world.stage.drop_items], expected)

    def test_lethal_weapon_dive_does_not_drop_a_club(self):
        for kind in config.WEAPON_AIRBORNE_ROWS:
            with self.subTest(kind=kind):
                world = aim(kind)
                world.controls.press("right")
                enemy = target(world)
                enemy.hp = 50
                tap(world.controls, "combat_d")
                for _ in range(90):
                    world.step(config.FIXED_DT)
                    if not enemy.alive:
                        break
                self.assertFalse(enemy.alive)
                self.assertEqual(world.stage.drop_items, [])

    def test_each_strong_attack_does_not_add_items(self):
        for key in "qwe":
            with self.subTest(key=key):
                world, enemy = encounter()
                enemy.hp = 20
                strike(world, enemy, f"combat_{key}")
                self.assertFalse(enemy.alive)
                self.assertEqual(world.stage.drop_items, [])
                world.controls.release(f"combat_{key}")
                advance(world, 1)
                self.assertEqual(world.stage.drop_items, [])

    def test_multiple_deaths_and_repeated_damage_add_nothing_through_corpse_fade(self):
        world, first = drop_world()
        second = Enemy(first.x + 100, ground_y=first.ground_y)
        world.enemies.append(second)
        for enemy in world.enemies:
            enemy.take_damage(enemy.max_hp)
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage.drop_items, [])
        self.assertFalse(first.take_damage(200))
        advance(world, 6)
        self.assertEqual(world.enemies, [])
        self.assertEqual(world.stage.drop_items, [])

    def test_spawned_enemies_on_every_stage_leave_initial_weapons_unchanged(self):
        world = World(rng=random.Random(41), item_rng=random.Random(5))
        for index in range(len(world.stages)):
            with self.subTest(stage=index):
                world.select_stage(index)
                items = list(world.stage.drop_items)
                world.enemies = world.spawner.spawn(3, world.elapsed)
                for enemy in world.enemies:
                    enemy.take_damage(enemy.max_hp)
                advance(world, 6)
                self.assertEqual(world.enemies, [])
                self.assertEqual(world.stage.drop_items, items)
                self.assertEqual(len(items), 15)
                self.assertEqual({item.kind for item in items}, set(config.DROP_ITEM_IMAGES))

    def test_legacy_car_death_does_not_add_items(self):
        world, enemy = drop_world()
        enemy.hit_by_car(1)
        advance(world, 6)
        self.assertEqual(world.enemies, [])
        self.assertEqual(world.stage.drop_items, [])
        self.assertIsNone(world.stage.traffic)

    @archived_two_floor_map()
    def test_upper_floor_death_does_not_add_items(self):
        world, enemy = drop_world()
        place(world, world.player, 1, 1200, 476)
        place(world, enemy, 1, 1300, 502)
        enemy.take_damage(200)
        advance(world, 6)
        self.assertEqual(world.enemies, [])
        self.assertEqual(world.stage.drop_items, [])

    @archived_two_floor_map()
    def test_lethal_stair_hit_still_falls_without_dropping_items(self):
        world, _ = drop_world()
        world.enemies.clear()
        enemy = on_stairs(world)
        enemy.take_damage(200)
        world.step(config.FIXED_DT)
        self.assertFalse(enemy.alive)
        self.assertTrue(enemy.falling_from_upper)
        self.assertEqual(world.stage.drop_items, [])
        advance(world, 6)
        self.assertEqual(world.enemies, [])
        self.assertEqual(world.stage.drop_items, [])

    def test_enemy_death_while_the_player_is_dead_does_not_add_items(self):
        world, enemy = drop_world()
        enemy.take_damage(200)
        world.player.invincible = False
        world.player.take_damage(config.MAX_HP)
        advance(world, 6)
        self.assertFalse(world.player.alive)
        self.assertEqual(world.enemies, [])
        self.assertEqual(world.stage.drop_items, [])

    def test_existing_weapon_pickup_swap_and_discard_still_work_after_a_kill(self):
        world, enemy = drop_world()
        enemy.take_damage(200)
        world.step(config.FIXED_DT)
        self.assertIsNone(world.pickup_item)
        self.assertFalse(world.interact_weapon())
        player = world.player
        knife = DropItem("combat_knife", player.x + 10, player.ground_y)
        pipe = DropItem("steel_pipe", player.x + 20, player.ground_y)
        world.stage.drop_items.extend((knife, pipe))
        self.assertTrue(world.interact_weapon())
        self.assertEqual(player.weapon, "combat_knife")
        self.assertTrue(world.interact_weapon())
        self.assertEqual(player.weapon, "steel_pipe")
        self.assertTrue(world.interact_weapon())
        self.assertIsNone(player.weapon)
        advance(world, 1)
        self.assertEqual({item.kind for item in world.stage.drop_items},
                         set(config.DROP_ITEM_IMAGES))
        self.assertEqual(len(world.stage.drop_items), 2)
        self.assertTrue(all(item.grounded for item in world.stage.drop_items))

    def test_revisit_and_loading_do_not_defer_or_recreate_a_death_drop(self):
        world, enemy = drop_world()
        enemy.take_damage(200)
        world.select_stage(1)
        advance(world, 1)
        world.select_stage(0)
        world.pending_stage_index, world.stage_loading_remaining = 1, 2
        world.update(0.5)
        self.assertEqual(world.stage.drop_items, [])
        world.pending_stage_index = None
        advance(world, 6)
        self.assertEqual(world.enemies, [])
        self.assertEqual(world.stage.drop_items, [])

    def test_f5_after_a_kill_restores_only_fifteen_initial_weapons(self):
        world, enemy = drop_world()
        enemy.take_damage(200)
        world.step(config.FIXED_DT)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        for stage in world.stages:
            self.assertEqual(len(stage.drop_items), 15)
            self.assertEqual({item.kind for item in stage.drop_items},
                             set(config.DROP_ITEM_IMAGES))
        self.assertEqual(world.enemies, [])

    def test_enemy_death_does_not_consume_spawn_or_initial_item_randomness(self):
        world, enemy = drop_world()
        spawn_state, item_state = world.spawn_rng.getstate(), world.item_rng.getstate()
        enemy.take_damage(200)
        world.step(config.FIXED_DT)
        self.assertEqual(world.spawn_rng.getstate(), spawn_state)
        self.assertEqual(world.item_rng.getstate(), item_state)

    def test_no_death_items_are_added_at_any_render_rate(self):
        for fps in (30, 60, 120, 144):
            with self.subTest(fps=fps):
                world, enemy = drop_world()
                enemy.take_damage(200)
                advance(world, 6, fps)
                self.assertEqual(world.enemies, [])
                self.assertEqual(world.stage.drop_items, [])

    def test_unused_club_sheet_is_preserved_but_not_loaded(self):
        name = "HoodMan_MetalClub_Item_6frames_1536x256.png"
        self.assertTrue((config.ROOT / name).is_file())
        with patch("pico2d.load_image", return_value=Mock()) as load_image:
            with patch("pico2d.load_font"):
                assets = Assets()
        self.assertNotIn(name, assets.images)
        self.assertNotIn(name, assets.frames)
        load_image.assert_any_call(str(config.ROOT / config.DROP_ITEM_IMAGES["combat_knife"]))
        load_image.assert_any_call(str(config.ROOT / config.DROP_ITEM_IMAGES["steel_pipe"]))
        self.assertFalse(any(call.args[0] == str(config.ROOT / name)
                             for call in load_image.call_args_list))


if __name__ == "__main__":
    unittest.main()
