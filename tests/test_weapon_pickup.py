import random
import unittest

import config
from combat import MOVES
from drop_items import DropItem
from tests.helpers import advance, tap
from tests.test_combat import attacking_enemy
from world import World


def encounter(kind="combat_knife"):
    world = World(item_rng=random.Random(5))
    item = DropItem(kind, world.player.x + 30, world.player.ground_y)
    world.stage.drop_items = [item]
    return world, item


class WeaponPickupTests(unittest.TestCase):
    def test_g_equips_each_kind_and_removes_only_the_nearest_floor_item(self):
        for kind in config.WEAPON_POSE_IMAGES:
            world, item = encounter(kind)
            farther = DropItem("steel_pipe", world.player.x + 65, world.player.ground_y)
            world.stage.drop_items.append(farther)
            self.assertIs(world.pickup_item, item)
            world.controls.press("weapon_interact")
            world.step(config.FIXED_DT)
            self.assertEqual(world.player.weapon, kind)
            self.assertEqual(world.stage.drop_items, [farther])
            self.assertEqual(world.player.sprite_image, config.WEAPON_POSE_IMAGES[kind])
            self.assertEqual((world.player.sprite_row, world.player.hp, world.player.state), (1, 500, "IDLE"))

    def test_proximity_includes_boundaries_but_rejects_other_depths_or_falling_items(self):
        world, item = encounter()
        item.x = world.player.x + config.WEAPON_PICKUP_RANGE
        item.ground_y = world.player.ground_y - config.WEAPON_PICKUP_DEPTH
        self.assertIs(world.pickup_item, item)
        item.x += 0.01
        self.assertIsNone(world.pickup_item)
        item.x = world.player.x
        item.ground_y -= 0.01
        self.assertIsNone(world.pickup_item)
        item.ground_y = world.player.ground_y
        item.jump_height = 1
        self.assertIsNone(world.pickup_item)

    def test_ground_weapon_takes_priority_and_swapping_preserves_both_weapons(self):
        world, item = encounter("steel_pipe")
        world.player.weapon = "combat_knife"
        world.controls.press("weapon_interact")
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.weapon, "steel_pipe")
        self.assertNotIn(item, world.stage.drop_items)
        self.assertEqual(len(world.stage.drop_items), 1)
        discarded = world.stage.drop_items[0]
        self.assertEqual(discarded.kind, "combat_knife")
        self.assertGreater(discarded.jump_height, 0)
        advance(world, 0.5)
        self.assertTrue(discarded.grounded)
        tap(world.controls, "weapon_interact")
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.weapon, "combat_knife")
        self.assertEqual([drop.kind for drop in world.stage.drop_items], ["steel_pipe"])

    def test_g_without_a_floor_item_drops_the_equipped_weapon_and_empty_hands_do_nothing(self):
        world, _ = encounter()
        world.stage.drop_items.clear()
        self.assertFalse(world.interact_weapon())
        world.player.weapon = "steel_pipe"
        self.assertTrue(world.interact_weapon())
        self.assertIsNone(world.player.weapon)
        self.assertEqual(world.player.sprite_image, config.PLAYER_IMAGE)
        self.assertEqual([drop.kind for drop in world.stage.drop_items], ["steel_pipe"])

    def test_holding_or_repeating_g_does_not_drop_or_reacquire_automatically(self):
        world, _ = encounter()
        world.controls.press("weapon_interact")
        world.step(config.FIXED_DT)
        world.controls.press("weapon_interact")
        advance(world, 0.5)
        self.assertEqual(world.player.weapon, "combat_knife")
        self.assertFalse(world.stage.drop_items)
        tap(world.controls, "weapon_interact")
        world.step(config.FIXED_DT)
        discarded = world.stage.drop_items[0]
        advance(world, 1)
        self.assertIsNone(world.player.weapon)
        self.assertTrue(discarded.grounded)
        self.assertIs(world.pickup_item, discarded)

    def test_midair_g_releases_from_the_current_height_and_falls_to_the_floor(self):
        for kind in config.WEAPON_POSE_IMAGES:
            world, _ = encounter()
            world.stage.drop_items.clear()
            player = world.player
            player.weapon = kind
            player.jump_height, player.vy, player.jump_count = 180, 200, 1
            player.animation.set_state("JUMP")
            release_y = player.y + config.WEAPON_DROP_HAND_HEIGHT
            world.controls.press("weapon_interact")
            world.step(config.FIXED_DT)
            item = world.stage.drop_items[0]
            self.assertIsNone(player.weapon)
            self.assertGreater(item.jump_height, 180)
            self.assertLess(item.ground_y + item.jump_height, release_y)
            self.assertLess(item.vy, 0)
            previous = item.jump_height
            for _ in range(120):
                world.step(config.FIXED_DT)
                self.assertLessEqual(item.jump_height, previous)
                previous = item.jump_height
            self.assertEqual((item.jump_height, item.vy), (0, 0))
            self.assertIs(world.pickup_item, item)

    def test_jumping_over_a_floor_item_does_not_pick_it_up_from_the_air(self):
        world, item = encounter()
        world.player.jump_height = 100
        world.player.jump_count = 1
        world.controls.press("weapon_interact")
        world.step(config.FIXED_DT)
        self.assertIsNone(world.player.weapon)
        self.assertEqual(world.stage.drop_items, [item])

    def test_death_and_loading_consume_g_without_queuing_an_interaction(self):
        for blocked in ("death", "loading"):
            with self.subTest(blocked=blocked):
                world, item = encounter()
                if blocked == "death":
                    world.player.take_damage(500)
                else:
                    world.pending_stage_index = 1
                    world.stage_loading_remaining = 2
                world.controls.press("weapon_interact")
                world.update(config.FIXED_DT)
                self.assertIsNone(world.player.weapon)
                self.assertEqual(world.stage.drop_items, [item])
                self.assertNotIn("weapon_interact", world.controls.pressed)

    def test_equipment_survives_travel_and_inactive_dropped_weapons_pause(self):
        world, _ = encounter()
        world.player.weapon = "steel_pipe"
        world.player.jump_height = 150
        world.stage.drop_items.clear()
        world.interact_weapon()
        item = world.stage.drop_items[0]
        state = (item.jump_height, item.vy, item.elapsed)
        world.player.weapon = "combat_knife"
        world.select_stage(1)
        advance(world, 1)
        self.assertEqual(world.player.weapon, "combat_knife")
        self.assertEqual((item.jump_height, item.vy, item.elapsed), state)
        world.select_stage(0)
        advance(world, 1)
        self.assertIn(item, world.stage.drop_items)
        self.assertTrue(item.grounded)

    def test_f5_clears_equipment_falling_weapons_and_pending_g(self):
        world, _ = encounter()
        world.player.weapon = "combat_knife"
        world.player.jump_height = 100
        world.interact_weapon()
        old = world.stage.drop_items[:]
        world.player.weapon = "steel_pipe"
        world.controls.press("weapon_interact")
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertIsNone(world.player.weapon)
        self.assertTrue(all(drop.grounded for stage in world.stages for drop in stage.drop_items))
        self.assertTrue(all(drop is not previous for stage in world.stages
                            for drop in stage.drop_items for previous in old))
        self.assertNotIn("weapon_interact", world.controls.pressed)

    def test_weapon_poses_map_hit_and_death_rows_and_keep_existing_combat_sheets(self):
        world, _ = encounter()
        player = world.player
        for kind, image in config.WEAPON_POSE_IMAGES.items():
            player.weapon = kind
            for state, row in config.WEAPON_POSE_ROWS[kind].items():
                player.animation.set_state(state)
                self.assertEqual((player.sprite_image, player.sprite_row), (image, row))
            if kind == "steel_pipe":
                player.animation.set_state("DYING")
                self.assertEqual((player.sprite_image, player.sprite_row), (config.PLAYER_IMAGE, 5))
            player.animation.set_state("IDLE")
            player.start_move(MOVES["combat_a"], 1)
            self.assertEqual(player.sprite_image, config.COMBAT_IMAGE)
            self.assertEqual(player.active_move.damage, 10)
            player.cancel_combat()
        player.hit_by_car(1)
        self.assertEqual(player.sprite_image, config.PLAYER_CAR_HIT_IMAGE)

    def test_equipped_enemy_hits_return_to_the_same_weapon_idle_within_a_quarter_second(self):
        for kind, image in config.WEAPON_POSE_IMAGES.items():
            for facing in (-1, 1):
                with self.subTest(kind=kind, facing=facing):
                    world, _ = encounter(kind)
                    world.controls.press("weapon_interact")
                    world.step(config.FIXED_DT)
                    player = world.player
                    player.facing = facing
                    world.enemies = [attacking_enemy(player.x - 80)]
                    world.step(config.FIXED_DT)
                    self.assertEqual((player.hp, player.state), (480, "HIT"))
                    self.assertEqual((player.sprite_image, player.sprite_row), (image, 5))
                    advance(world, 0.1)
                    self.assertEqual(player.state, "HIT")
                    self.assertGreater(player.animation.frame, 0)
                    advance(world, 0.15)
                    self.assertEqual((player.state, player.weapon, player.facing), ("IDLE", kind, facing))
                    self.assertEqual((player.sprite_image, player.sprite_row), (image, 1))
                    self.assertEqual(player.hp, 480)

    def test_staggered_equipped_hits_keep_damage_and_do_not_extend_hit_recovery(self):
        for kind in config.WEAPON_POSE_IMAGES:
            with self.subTest(kind=kind):
                world, _ = encounter(kind)
                world.interact_weapon()
                player = world.player
                player.take_damage(20)
                advance(world, 0.1)
                elapsed = player.animation.elapsed
                world.enemies = [attacking_enemy(player.x + 80, -1)]
                world.step(config.FIXED_DT)
                self.assertEqual((player.hp, player.state), (460, "HIT"))
                self.assertAlmostEqual(player.animation.elapsed, elapsed + config.FIXED_DT)
                advance(world, 0.15)
                self.assertEqual((player.state, player.weapon), ("IDLE", kind))

    def test_quick_equipped_hit_cancels_attacks_consumes_input_and_keeps_gravity(self):
        for kind in config.WEAPON_POSE_IMAGES:
            with self.subTest(kind=kind):
                world, _ = encounter(kind)
                world.interact_weapon()
                player = world.player
                player.jump_height, player.vy, player.jump_count = 120, -30, 1
                player.start_move(MOVES["combat_f"], 1)
                player.take_damage(20)
                world.controls.press("right")
                world.controls.press("jump")
                world.controls.press("combat_a")
                x = player.x
                for _ in range(30):
                    world.step(config.FIXED_DT)
                    self.assertEqual(player.x, x)
                    if player.state != "HIT":
                        break
                self.assertEqual(player.state, "IDLE")
                self.assertEqual(player.weapon, kind)
                self.assertIsNone(player.active_move)
                self.assertEqual(player.jump_count, 1)
                self.assertLess(player.jump_height, 120)
                self.assertNotIn("jump", world.controls.pressed)
                self.assertNotIn("combat_a", world.controls.pressed)
                tap(world.controls, "combat_a")
                world.step(config.FIXED_DT)
                self.assertEqual(player.state, "ATTACK_A")

    def test_lethal_and_car_hits_override_quick_equipped_recovery(self):
        for kind in config.WEAPON_POSE_IMAGES:
            for source in ("enemy", "car"):
                with self.subTest(kind=kind, source=source):
                    world, _ = encounter(kind)
                    world.interact_weapon()
                    player = world.player
                    player.take_damage(20)
                    advance(world, 0.1)
                    if source == "enemy":
                        player.take_damage(config.MAX_HP)
                    else:
                        player.hit_by_car(1)
                    advance(world, 0.25)
                    self.assertEqual(player.state, "DYING" if source == "enemy" else "CAR_HIT")
                    self.assertEqual((player.hp, player.weapon), (0, kind))
                    advance(world, 1)
                    self.assertEqual(player.state, "DEAD")

    def test_dropping_during_a_quick_hit_does_not_extend_it_and_future_unarmed_hits_use_normal_timing(self):
        world, _ = encounter()
        world.interact_weapon()
        player = world.player
        player.take_damage(20)
        advance(world, 0.1)
        world.interact_weapon()
        self.assertIsNone(player.weapon)
        advance(world, 0.15)
        self.assertEqual(player.state, "IDLE")
        player.take_damage(20)
        advance(world, 0.25)
        self.assertEqual(player.state, "HIT")
        advance(world, 0.5)
        self.assertEqual(player.state, "IDLE")
        self.assertEqual(player.sprite_image, config.PLAYER_IMAGE)

    def test_pickup_and_falling_results_are_identical_at_different_render_rates(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world, _ = encounter()
            world.controls.press("weapon_interact")
            advance(world, 0.5, fps)
            self.assertEqual(world.player.weapon, "combat_knife")
            tap(world.controls, "weapon_interact")
            advance(world, 1, fps)
            outcomes.append((world.player.weapon, [(item.kind, item.x, item.ground_y,
                                                    item.jump_height, item.vy, item.elapsed)
                                                   for item in world.stage.drop_items]))
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))

    def test_full_size_rifle_fits_the_city_floor_and_stays_clear_of_both_exits(self):
        world = World()
        world.select_stage(config.STAGE_IMAGES.index(config.CITY_STAGE_IMAGES[0]))
        player = world.player
        _, bottom, right, top = world.stage.drop_spawn_area.bounds
        exit_width = (config.STAGE_EXIT_MARGIN + config.STAGE_ARROW_WIDTH / 2
                      + config.STAGE_ARROW_SWAY_AMPLITUDE + config.DROP_ITEM_EXIT_GAP)
        half_width = config.RIFLE_ITEM_CLIP[2] * config.RIFLE_DROP_SCALE / 2
        for x in (player.boundary_padding, right - player.boundary_padding):
            player.x, player.ground_y = x, top
            item = world.drop_weapon("ar_rifle")
            self.assertLessEqual(bottom, item.ground_y)
            self.assertLessEqual(item.ground_y, top)
            self.assertLessEqual(item.ground_y + item.display_height, world.stage.walkable.bounds[3])
            self.assertGreaterEqual(item.x - half_width, exit_width)
            self.assertLessEqual(item.x + half_width, right - exit_width)

    def test_manual_drops_keep_floor_exit_and_city_sidewalk_limits_at_all_stage_corners(self):
        for index in range(len(config.STAGE_IMAGES)):
            for side in (-1, 1):
                world = World()
                world.stage_index = index
                world.stage.traffic = None
                player = world.player
                player.x = player.boundary_padding if side < 0 else config.WORLD_WIDTH - player.boundary_padding
                player.ground_y = world.stage.walkable.bounds[3]
                player.weapon = "steel_pipe"
                world.stage.drop_items.clear()
                world.interact_weapon()
                item = world.stage.drop_items[0]
                advance(world, 1)
                self.assertTrue(item.grounded)
                self.assertTrue(world.stage.walkable.contains(item.x, item.ground_y))
                for x in (item.x - config.DROP_ITEM_HALF_WIDTH, item.x + config.DROP_ITEM_HALF_WIDTH):
                    for y in (item.ground_y - config.DROP_ITEM_SHADOW_HALF_DEPTH,
                              item.ground_y + config.DROP_ITEM_HEIGHT):
                        self.assertTrue(world.stage.drop_spawn_area.contains(x, y))
                self.assertGreaterEqual(item.x, 206)
                self.assertLessEqual(item.x, config.WORLD_WIDTH - 206)
                if world.stage.image_name == config.CITY_STAGE_IMAGES[0]:
                    self.assertGreaterEqual(item.ground_y - config.DROP_ITEM_SHADOW_HALF_DEPTH,
                                             203)
                    self.assertLessEqual(item.ground_y + config.DROP_ITEM_HEIGHT, 241)
                player.x, player.ground_y = item.x, item.ground_y
                self.assertIs(world.pickup_item, item)


if __name__ == "__main__":
    unittest.main()
