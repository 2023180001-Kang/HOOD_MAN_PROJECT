import random
import unittest

import config
from combat import MOVES, WEAPON_MOVES
from drop_items import DropItem
from enemy import Enemy
from enemy02 import Enemy02
from tests.helpers import advance, tap
from world import World


def equipped_world(kind):
    world = World(item_rng=random.Random(5))
    world.stage.drop_items = [DropItem(kind, world.player.x + 30, world.player.ground_y)]
    world.controls.press("weapon_interact")
    world.step(config.FIXED_DT)
    world.controls.release("weapon_interact")
    world.player.invincible = True
    return world


def target(world, enemy_type=Enemy, side=1):
    enemy = enemy_type(world.player.x + side * 80, -side, ground_y=world.player.ground_y)
    enemy.animation.set_state("HIT")
    enemy.cooldown = 100
    world.enemies.append(enemy)
    return enemy


def double_jump(world):
    tap(world.controls, "jump")
    world.step(config.FIXED_DT)
    advance(world, 0.05)
    tap(world.controls, "jump")
    world.step(config.FIXED_DT)


class WeaponCombatTests(unittest.TestCase):
    def test_weapon_strikes_hit_one_pixel_inside_their_forward_reach_and_miss_outside(self):
        reaches = {
            "combat_knife": {"a": 120, "s": 130, "d": 140},
            "steel_pipe": {"a": 120, "s": 130, "d": 140},
            "steel_club": {"a": 130, "d": 140},
            "axe": {"a": 130, "d": 130},
        }
        for kind, attacks in reaches.items():
            for key, reach in attacks.items():
                for side in (-1, 1):
                    with self.subTest(kind=kind, key=key, side=side):
                        world = equipped_world(kind)
                        player = world.player
                        player.facing = side
                        if key == "d":
                            double_jump(world)
                            tap(world.controls, "combat_d")
                            world.step(config.FIXED_DT)
                        tap(world.controls, f"combat_{key}")
                        for _ in range(120):
                            world.step(config.FIXED_DT)
                            if player.attack_box is not None:
                                break
                        self.assertIsNotNone(player.attack_box)
                        if key == "d":
                            self.assertEqual(player.weapon_leap_phase, "LANDING")
                        edge = player.x + side * (reach + config.ENEMY_HALF_WIDTH)
                        enemy = Enemy(edge + side, -side, ground_y=player.ground_y)
                        self.assertFalse(player.try_hit(enemy))
                        enemy.x = edge - side
                        self.assertTrue(player.try_hit(enemy))

    def test_g_pickup_remaps_asd_to_each_weapon_and_keeps_f_as_the_kick(self):
        for kind, rows in (("combat_knife", (7, 8, 9)), ("steel_pipe", (6, 7, 8))):
            for key, row, damage in zip("asd", rows, (10, 40, 50)):
                world = equipped_world(kind)
                player = world.player
                if key == "d":
                    double_jump(world)
                world.controls.press(f"combat_{key}")
                world.step(config.FIXED_DT)
                self.assertEqual((player.sprite_image, player.sprite_row),
                                 (config.WEAPON_POSE_IMAGES[kind], row))
                self.assertEqual(player.active_move.damage, damage)
                self.assertEqual(player.animation.definitions[player.state][1],
                                 MOVES[f"combat_{key}"].fps)
                if key == "d":
                    tap(world.controls, "combat_d")
                advance(world, 0.7)
                self.assertIsNone(player.active_move)
                self.assertEqual((player.state, player.sprite_image, player.sprite_row),
                                 ("IDLE", config.WEAPON_POSE_IMAGES[kind], 1))
                tap(world.controls, "combat_f")
                world.step(config.FIXED_DT)
                self.assertIs(player.active_move, MOVES["combat_f"])
                self.assertEqual(player.sprite_image, config.COMBAT_IMAGE)

    def test_six_attacks_hit_both_enemy_types_on_both_sides_once_with_existing_effects(self):
        for kind, moves in WEAPON_MOVES.items():
            for key, move in moves.items():
                for enemy_type in (Enemy, Enemy02):
                    for side in (-1, 1):
                        with self.subTest(kind=kind, key=key, enemy=enemy_type, side=side):
                            world = equipped_world(kind)
                            world.player.facing = side
                            enemy = target(world, enemy_type, side)
                            if move.jump_attack:
                                double_jump(world)
                            world.controls.press(key)
                            if move.jump_attack:
                                world.step(config.FIXED_DT)
                                tap(world.controls, key)
                            hits = 0
                            for _ in range(90):
                                hp = enemy.hp
                                world.step(config.FIXED_DT)
                                if enemy.hp != hp:
                                    hits += 1
                                    self.assertEqual(hp - enemy.hp, move.damage)
                                    self.assertIn(world.player.animation.frame, move.active_frames)
                                    self.assertEqual(world.effects[-1].image_name,
                                                     config.WEAPON_HIT_IMAGES[kind])
                                    self.assertEqual(world.effects[-1].facing, side)
                                    self.assertEqual(world.damage_numbers[-1].damage, move.damage)
                                    self.assertGreater(world.camera.shake_remaining, 0)
                                    self.assertEqual(world.camera.shake_strength,
                                                     config.WEAPON_DIVE_SHAKE_STRENGTH
                                                     if move.jump_attack else config.SHAKE_STRENGTH)
                            self.assertEqual((hits, enemy.hp, world.player.hp),
                                             (1, 200 - move.damage, 500))

    def test_pipe_swing_and_both_jump_strikes_wait_for_the_source_impact_pose(self):
        for kind, key, before in (("steel_pipe", "s", 0.18),
                                  ("combat_knife", "d", 0.3), ("steel_pipe", "d", 0.3)):
            world = equipped_world(kind)
            enemy = target(world)
            if key == "d":
                double_jump(world)
            world.controls.press(f"combat_{key}")
            advance(world, before)
            self.assertEqual(enemy.hp, 200)
            self.assertEqual(world.effects, [])
            if key == "d":
                tap(world.controls, "combat_d")
            advance(world, 0.5 if key == "d" else 0.1)
            self.assertEqual(enemy.hp, 200 - WEAPON_MOVES[kind][f"combat_{key}"].damage)

    def test_depth_facing_height_and_dead_targets_still_filter_weapon_hits(self):
        for kind, moves in WEAPON_MOVES.items():
            for move in moves.values():
                world = equipped_world(kind)
                player = world.player
                enemy = target(world)
                if move.jump_attack:
                    double_jump(world)
                player.start_move(move, 1)
                if move.jump_attack:
                    player.weapon_leap_phase = "LANDING"
                    player.jump_height = player.vy = 0
                player.animation.elapsed = (move.active_frames[0] + 0.1) / move.fps
                self.assertIsNotNone(player.attack_box)
                enemy.ground_y = player.ground_y + 33
                self.assertFalse(player.try_hit(enemy))
                enemy.ground_y = player.ground_y
                enemy.x = player.x - 80
                self.assertFalse(player.try_hit(enemy))
                enemy.x = player.x + 80
                player.jump_height = config.ENEMY_HEIGHT + 1
                self.assertFalse(player.try_hit(enemy))
                player.jump_height = 0
                enemy.hp = 0
                self.assertFalse(player.try_hit(enemy))
                self.assertFalse(player.hit_enemies)

    def test_multiple_targets_and_lethal_hits_use_actual_damage_once(self):
        for kind in WEAPON_MOVES:
            world = equipped_world(kind)
            first, second = target(world), target(world)
            second.hp = 15
            world.controls.press("combat_s")
            for _ in range(60):
                world.step(config.FIXED_DT)
                if not second.alive:
                    break
            self.assertEqual((first.hp, second.hp), (160, 0))
            self.assertEqual(sorted(number.damage for number in world.damage_numbers), [15, 40])
            self.assertEqual(len(world.effects), 2)
            advance(world, 0.2)
            self.assertEqual((first.hp, second.hp), (160, 0))

    def test_latest_attack_input_switches_immediately_without_buffering_or_restarting_same_key(self):
        for kind in WEAPON_MOVES:
            world = equipped_world(kind)
            player = world.player
            world.controls.press("combat_a")
            advance(world, 0.05)
            elapsed = player.animation.elapsed
            tap(world.controls, "combat_a")
            world.step(config.FIXED_DT)
            self.assertAlmostEqual(player.animation.elapsed, elapsed + config.FIXED_DT)
            world.controls.press("combat_s")
            world.controls.press("combat_f")
            world.step(config.FIXED_DT)
            self.assertIs(player.active_move, MOVES["combat_f"])
            self.assertEqual(player.animation.elapsed, config.FIXED_DT)
            advance(world, 0.7)
            self.assertIsNone(player.active_move)
            self.assertFalse(world.controls.pressed)

    def test_g_dropping_or_swapping_cancels_the_old_weapon_attack_before_it_hits(self):
        for kind in WEAPON_MOVES:
            for swap in (False, True):
                world = equipped_world(kind)
                enemy = target(world)
                world.controls.press("combat_s")
                advance(world, 0.05)
                other = "steel_pipe" if kind == "combat_knife" else "combat_knife"
                if swap:
                    world.stage.drop_items.append(DropItem(other, world.player.x, world.player.ground_y))
                tap(world.controls, "weapon_interact")
                world.step(config.FIXED_DT)
                self.assertIsNone(world.player.active_move)
                self.assertEqual(world.player.weapon, other if swap else None)
                advance(world, 0.6)
                self.assertEqual(enemy.hp, 200)
                self.assertEqual(world.effects, [])
                tap(world.controls, "combat_a")
                world.step(config.FIXED_DT)
                expected = WEAPON_MOVES[other]["combat_a"] if swap else MOVES["combat_a"]
                self.assertIs(world.player.active_move, expected)

    def test_g_and_attack_in_one_update_use_the_new_weapon_and_drop_preserves_jump(self):
        world = equipped_world("combat_knife")
        player = world.player
        world.stage.drop_items = [DropItem("steel_pipe", player.x, player.ground_y)]
        tap(world.controls, "weapon_interact")
        world.controls.press("combat_a")
        world.step(config.FIXED_DT)
        self.assertIs(player.active_move, WEAPON_MOVES["steel_pipe"]["combat_a"])
        player.jump_height, player.vy, player.jump_count = 120, 200, 1
        world.stage.drop_items.clear()
        tap(world.controls, "weapon_interact")
        world.step(config.FIXED_DT)
        self.assertIsNone(player.active_move)
        self.assertEqual(player.jump_count, 1)
        self.assertGreater(player.jump_height, 120)
        self.assertEqual(player.sprite_image, config.PLAYER_IMAGE)

    def test_weapon_combo_damage_is_identical_across_render_rates_and_f5_restores_unarmed(self):
        for kind in WEAPON_MOVES:
            results = []
            for fps in (30, 60, 120, 144):
                world = equipped_world(kind)
                enemy = target(world)
                double_jump(world)
                tap(world.controls, "combat_d")
                advance(world, 0.1, fps)
                for key, seconds in (("combat_d", 0.5), ("combat_s", 0.5), ("combat_a", 0.5)):
                    tap(world.controls, key)
                    advance(world, seconds, fps)
                results.append((enemy.hp, world.player.state, world.player.animation.elapsed,
                                world.player.weapon))
                self.assertEqual(enemy.hp, 100)
                tap(world.controls, "restart")
                world.update(config.FIXED_DT)
                self.assertIsNone(world.player.weapon)
                self.assertIs(world.player.moves, MOVES)
            self.assertTrue(all(result == results[0] for result in results))


if __name__ == "__main__":
    unittest.main()
