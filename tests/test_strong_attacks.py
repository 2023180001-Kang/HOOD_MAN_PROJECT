import random
import unittest

import config
from combat import MOVES, STRONG_MOVES
from counter import COUNTERS
from enemy import Enemy
from enemy02 import Enemy02
from tests.helpers import advance, tap
from tests.test_counters import attacker, follow_up
from tests.test_weapon_leap import aim
from world import World


def encounter(enemy_type=Enemy, side=1, weapon=None):
    world = World(item_rng=random.Random(5))
    world.player.invincible = True
    world.player.facing = side
    world.player.equip_weapon(weapon)
    enemy = enemy_type(world.player.x + side * 80, -side, ground_y=world.player.ground_y)
    enemy.animation.set_state("HIT")
    enemy.cooldown = 100
    world.enemies.append(enemy)
    return world, enemy


def strike(world, enemy, action):
    hp = enemy.hp
    tap(world.controls, action)
    for _ in range(90):
        world.step(config.FIXED_DT)
        if enemy.hp != hp:
            return
    raise AssertionError(f"{action} did not hit")


class StrongAttackTests(unittest.TestCase):
    def test_qwert_use_rows_one_to_five_with_fifty_damage_and_restore_each_loadout(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for key, row, hit_row in zip("qwert", range(1, 6), (1, 5, 4, 2, 3)):
                world, _ = encounter(weapon=weapon)
                action = f"combat_{key}"
                tap(world.controls, action)
                world.step(config.FIXED_DT)
                player = world.player
                self.assertIs(player.active_move, STRONG_MOVES[action])
                self.assertEqual((player.sprite_image, player.sprite_row), (config.STRONG_ATTACK_IMAGE, row))
                self.assertEqual((player.active_move.damage, player.active_move.enemy_hit_row), (50, hit_row))
                advance(world, 0.6)
                self.assertIsNone(player.active_move)
                self.assertEqual(player.sprite_image, config.WEAPON_POSE_IMAGES.get(weapon, config.PLAYER_IMAGE))
                self.assertEqual(player.weapon, weapon)

    def test_five_attacks_hit_each_enemy_type_on_both_sides_once_with_the_requested_reaction(self):
        for action, move in STRONG_MOVES.items():
            for enemy_type in (Enemy, Enemy02):
                for side in (-1, 1):
                    with self.subTest(action=action, enemy=enemy_type, side=side):
                        world, enemy = encounter(enemy_type, side)
                        strike(world, enemy, action)
                        self.assertEqual((enemy.hp, enemy.state, enemy.animation.row),
                                         (150, "STRONG_HIT", move.enemy_hit_row))
                        self.assertEqual(enemy.sprite_image, config.STRONG_HIT_IMAGE)
                        self.assertIn(world.player.animation.frame, move.active_frames)
                        self.assertEqual(enemy.facing, -side)
                        self.assertEqual(enemy.vx, side * move.knockback_speed)
                        self.assertEqual([number.damage for number in world.damage_numbers], [50])
                        self.assertEqual(world.effects[-1].image_name, config.PUNCH_KICK_HIT_IMAGE)
                        self.assertGreater(world.camera.shake_remaining, 0)
                        advance(world, 0.1)
                        self.assertEqual(enemy.hp, 150)
                        while enemy.state == "STRONG_HIT":
                            world.step(config.FIXED_DT)
                        self.assertEqual((enemy.hp, enemy.state, enemy.sprite_image),
                                         (150, "IDLE", enemy.image_name))
                        self.assertFalse(enemy.knockback_started)

    def test_windup_and_recovery_never_deal_damage_and_each_motion_stays_single_hit(self):
        for action, move in STRONG_MOVES.items():
            world, enemy = encounter()
            tap(world.controls, action)
            hits = []
            for _ in range(75):
                hp = enemy.hp
                world.step(config.FIXED_DT)
                if enemy.hp != hp:
                    hits.append(world.player.animation.frame)
                if world.player.active_move is not None and world.player.animation.frame < min(move.active_frames):
                    self.assertEqual(enemy.hp, 200)
            self.assertEqual(len(hits), 1)
            self.assertIn(hits[0], move.active_frames)
            self.assertEqual(enemy.hp, 150)

    def test_range_depth_height_facing_and_dead_targets_filter_strong_hits(self):
        for move in STRONG_MOVES.values():
            for reason in ("range", "depth", "height", "back", "dead"):
                world, enemy = encounter()
                player = world.player
                player.start_move(move, 1)
                player.animation.elapsed = (min(move.active_frames) + 0.1) / move.fps
                if reason == "range":
                    enemy.x = player.x + move.reach + config.ENEMY_HALF_WIDTH + 1
                elif reason == "depth":
                    enemy.ground_y += config.ATTACK_DEPTH_TOLERANCE + 1
                elif reason == "height":
                    player.jump_height = config.ENEMY_HEIGHT + 1
                elif reason == "back":
                    enemy.x = player.x - 80
                else:
                    enemy.hp = 0
                self.assertFalse(player.try_hit(enemy))
                self.assertNotEqual(enemy.state, "STRONG_HIT")
                self.assertFalse(player.hit_enemies)

    def test_multiple_targets_and_lethal_damage_numbers_use_actual_damage_once(self):
        world, first = encounter()
        second = Enemy02(first.x, first.facing, ground_y=first.ground_y)
        second.hp = 15
        second.animation.set_state("HIT")
        world.enemies.append(second)
        strike(world, first, "combat_e")
        self.assertEqual((first.hp, second.hp), (150, 0))
        self.assertEqual(sorted(number.damage for number in world.damage_numbers), [15, 50])
        self.assertEqual(len(world.effects), 2)
        advance(world, 0.15)
        self.assertEqual((first.hp, second.hp), (150, 0))

    def test_basic_and_strong_attacks_switch_immediately_and_latest_input_wins(self):
        for action, move in STRONG_MOVES.items():
            world, _ = encounter()
            tap(world.controls, "combat_a")
            world.step(config.FIXED_DT)
            tap(world.controls, action)
            world.step(config.FIXED_DT)
            self.assertIs(world.player.active_move, move)
            elapsed = world.player.animation.elapsed
            tap(world.controls, action)
            world.step(config.FIXED_DT)
            self.assertAlmostEqual(world.player.animation.elapsed, elapsed + config.FIXED_DT)
            tap(world.controls, "combat_f")
            world.step(config.FIXED_DT)
            self.assertIs(world.player.active_move, MOVES["combat_f"])
            for key in ("combat_s", action, "combat_a"):
                tap(world.controls, key)
            world.step(config.FIXED_DT)
            self.assertIs(world.player.active_move, MOVES["combat_a"])
            for key in ("combat_s", "combat_a", action):
                tap(world.controls, key)
            world.step(config.FIXED_DT)
            self.assertIs(world.player.active_move, move)
            advance(world, 1)
            world.controls.press(action)
            world.step(config.FIXED_DT)
            self.assertIsNone(world.player.active_move)
            self.assertFalse(world.controls.pressed)

    def test_w_knockback_is_bounded_at_both_stage_edges_and_ai_can_resume(self):
        for stage_index in range(len(config.STAGE_IMAGES)):
            for enemy_type in (Enemy, Enemy02):
                for side in (-1, 1):
                    world, enemy = encounter(enemy_type, side)
                    world.select_stage(stage_index)
                    world.stage.traffic = None
                    left, bottom, right, top = world.stage.walkable.bounds
                    enemy.x = left + enemy.boundary_padding if side < 0 else right - enemy.boundary_padding
                    enemy.ground_y = bottom if side < 0 else top
                    world.player.x = enemy.x - side * 80
                    world.player.ground_y = enemy.ground_y
                    world.enemies = [enemy]
                    tap(world.controls, "combat_w")
                    for _ in range(100):
                        world.step(config.FIXED_DT)
                        self.assertTrue(world.stage.walkable.contains(enemy.x, enemy.ground_y,
                                                                     enemy.boundary_padding))
                    self.assertEqual(enemy.hp, 150)
                    self.assertFalse(enemy.knockback_started)
                    self.assertNotEqual(enemy.state, "STRONG_HIT")
        world, enemy = encounter()
        strike(world, enemy, "combat_w")
        start = enemy.x
        advance(world, 0.2)
        self.assertGreater(enemy.x, start + 50)
        advance(world, 1.5)
        self.assertIn(enemy.state, ("WALK", "RUN", "ATTACK", "IDLE"))
        self.assertLess(abs(enemy.x - world.player.x), 150)

    def test_lethal_hits_finish_the_selected_reaction_then_play_normal_death_and_fade(self):
        for action in STRONG_MOVES:
            for enemy_type in (Enemy, Enemy02):
                world, enemy = encounter(enemy_type)
                enemy.hp = 40
                strike(world, enemy, action)
                self.assertEqual((enemy.hp, enemy.state), (0, "STRONG_HIT"))
                self.assertIsNone(enemy.attack_box)
                self.assertFalse(enemy.blocks_movement)
                frames = set()
                while enemy.state == "STRONG_HIT":
                    frames.add(enemy.animation.frame)
                    world.step(config.FIXED_DT)
                self.assertEqual(frames, set(range(8)))
                self.assertEqual((enemy.state, enemy.sprite_image), ("DYING", enemy.image_name))
                advance(world, 5)
                self.assertNotIn(enemy, world.enemies)

    def test_normal_hits_counters_cars_and_death_knockback_replace_a_strong_reaction_cleanly(self):
        for enemy_type in (Enemy, Enemy02):
            for cause in ("hit", "counter", "car", "knockback"):
                world, enemy = encounter(enemy_type)
                strike(world, enemy, "combat_w")
                if cause == "hit":
                    enemy.take_damage(10)
                elif cause == "counter":
                    enemy.start_counter(COUNTERS["counter_h"], -1)
                elif cause == "car":
                    enemy.hit_by_car(1)
                else:
                    enemy.knockback(world.player.x)
                self.assertNotEqual(enemy.state, "STRONG_HIT")
                self.assertNotEqual(enemy.sprite_image, config.STRONG_HIT_IMAGE)

    def test_enemy02_airborne_leap_is_cancelled_and_natural_falling_continues(self):
        world, _ = encounter()
        enemy = Enemy02(world.player.x + 400, -1)
        world.enemies = [enemy]
        self.assertTrue(enemy.start_leap(world.player))
        advance(world, 0.3)
        self.assertGreater(enemy.jump_height, 0)
        enemy.take_strong_hit(STRONG_MOVES["combat_t"], 1)
        self.assertIsNone(enemy.leap_phase)
        self.assertEqual(enemy.sprite_image, config.STRONG_HIT_IMAGE)
        advance(world, 1.2)
        self.assertEqual(enemy.jump_height, 0)
        self.assertIsNone(enemy.leap_phase)

    def test_capture_consumes_strong_keys_and_a_later_strike_replaces_the_unlinked_reaction(self):
        for hp in (120, 200):
            world = World()
            enemy = attacker(world)
            enemy.hp = hp
            tap(world.controls, "counter_h")
            world.step(config.FIXED_DT)
            while not world.counter.holding:
                world.step(config.FIXED_DT)
            tap(world.controls, "combat_q")
            world.step(config.FIXED_DT)
            self.assertIsNone(world.player.active_move)
            self.assertFalse(world.controls.pressed)
            follow_up(world)
            while world.counter is not None:
                world.step(config.FIXED_DT)
            self.assertIsNotNone(enemy.counter_move)
            strike(world, enemy, "combat_q")
            self.assertEqual((enemy.hp, enemy.state), (max(0, hp - 130), "STRONG_HIT"))
            self.assertIsNone(enemy.counter_move)
            self.assertIsNone(enemy.counter_death)
            self.assertEqual(enemy.boundary_padding, config.ENEMY_BOUNDARY_PADDING)
            if not enemy.alive:
                advance(world, 1.5)
                self.assertEqual((enemy.state, enemy.animation.row), ("DEAD", 6))

    def test_player_hit_death_drop_and_slow_dive_switching_do_not_leave_a_pending_strong_attack(self):
        for state in ("HIT", "DYING", "DEAD"):
            world, enemy = encounter()
            world.player.invincible = False
            world.player.take_damage(20 if state == "HIT" else 500)
            if state == "DEAD":
                advance(world, 1)
            for action in STRONG_MOVES:
                tap(world.controls, action)
            world.step(config.FIXED_DT)
            advance(world, 1)
            self.assertIsNone(world.player.active_move)
            self.assertFalse(world.controls.pressed)
            self.assertEqual(enemy.hp, 200)
        world, enemy = encounter(weapon="steel_pipe")
        tap(world.controls, "combat_q")
        advance(world, 0.05)
        tap(world.controls, "weapon_interact")
        world.step(config.FIXED_DT)
        advance(world, 0.4)
        self.assertEqual(enemy.hp, 200)
        self.assertIsNone(world.player.weapon)
        for dive in (False, True):
            world = aim("combat_knife")
            if dive:
                tap(world.controls, "combat_d")
                world.step(config.FIXED_DT)
            tap(world.controls, "combat_e")
            world.step(config.FIXED_DT)
            self.assertEqual(world.time_scale, 1)
            self.assertIs(world.player.active_move, STRONG_MOVES["combat_e"])

    def test_loading_inactive_stage_and_restart_preserve_or_clear_the_reaction(self):
        world, enemy = encounter()
        strike(world, enemy, "combat_w")
        before = enemy.x, enemy.vx, enemy.animation.elapsed
        world.pending_stage_index, world.stage_loading_remaining = 1, 2
        tap(world.controls, "combat_t")
        world.update(0.5)
        self.assertEqual((enemy.x, enemy.vx, enemy.animation.elapsed), before)
        self.assertFalse(world.controls.pressed)
        world.select_stage(1)
        advance(world, 0.5)
        self.assertEqual((enemy.x, enemy.vx, enemy.animation.elapsed), before)
        world.select_stage(0)
        advance(world, 0.1)
        self.assertGreater(enemy.animation.elapsed, before[2])
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertTrue(all(not stage.enemies for stage in world.stages))
        self.assertIsNone(world.player.active_move)
        self.assertEqual(world.player.state, "IDLE")

    def test_strong_hit_has_priority_over_an_enemy_swing_and_is_render_rate_independent(self):
        for enemy_type in (Enemy, Enemy02):
            world, enemy = encounter(enemy_type)
            world.player.invincible = False
            move = STRONG_MOVES["combat_q"]
            world.player.start_move(move, 1)
            world.player.animation.elapsed = min(move.active_frames) / move.fps
            enemy.start_attack()
            enemy.animation.elapsed = min(enemy.attack_active_frames) / enemy.attack_fps
            world.step(config.FIXED_DT)
            self.assertEqual((world.player.hp, enemy.hp, enemy.state), (500, 150, "STRONG_HIT"))
        for action in STRONG_MOVES:
            results = []
            for fps in (30, 60, 120, 144):
                world, enemy = encounter(Enemy02)
                tap(world.controls, action)
                advance(world, 0.5, fps)
                results.append((enemy.hp, enemy.x, enemy.vx, enemy.state, enemy.animation.elapsed,
                                world.player.state, world.player.animation.elapsed))
            self.assertTrue(all(result == results[0] for result in results))


if __name__ == "__main__":
    unittest.main()
