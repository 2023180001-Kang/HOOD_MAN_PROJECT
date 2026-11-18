import unittest

import config
from enemy import Enemy
from enemy02 import Enemy02
from player import Player
from tests.helpers import advance, tap
from tests.test_strong_attacks import encounter


def kick(world, enemy=None):
    tap(world.controls, "combat_e")
    hits = []
    for _ in range(120):
        hp = enemy.hp if enemy is not None else 0
        world.step(config.FIXED_DT)
        if enemy is not None and hp != enemy.hp:
            hits.append((world.player.animation.frame, hp - enemy.hp))
        if world.player.air_kick_phase in ("WAIT", "RECOVERY"):
            return hits
    raise AssertionError("E did not finish one kick")


class AirKickChainTests(unittest.TestCase):
    def test_first_kick_then_slow_wait_never_attacks_again_without_a_fresh_e(self):
        world, enemy = encounter()
        self.assertEqual(kick(world, enemy), [(3, 50)])
        player = world.player
        self.assertEqual((player.animation.frame, world.time_scale), (4, 0.2))
        elapsed = world.elapsed
        advance(world, 3)
        self.assertAlmostEqual(world.elapsed - elapsed, 0.6)
        self.assertEqual((player.air_kick_phase, player.animation.frame, enemy.hp), ("WAIT", 4, 150))
        self.assertIsNone(player.attack_box)

    def test_two_kicks_deal_fifty_each_then_automatically_restore_the_loadout(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for enemy_type in (Enemy, Enemy02):
                for side in (-1, 1):
                    world, enemy = encounter(enemy_type, side, weapon)
                    for frame, hp in ((3, 150), (5, 100)):
                        self.assertEqual(kick(world, enemy), [(frame, 50)])
                        image, row = ((config.ENEMY02_IMAGE, 6) if enemy_type is Enemy02
                                      else (config.STRONG_HIT_IMAGE, 4))
                        self.assertEqual((enemy.hp, enemy.sprite_image, enemy.animation.row),
                                         (hp, image, row))
                        self.assertIsNone(world.player.attack_box)
                    self.assertEqual(world.player.air_kick_phase, "RECOVERY")
                    advance(world, 0.2)
                    self.assertEqual(world.time_scale, 1)
                    self.assertIsNone(world.player.air_kick_phase)
                    self.assertEqual(enemy.hp, 100)
                    self.assertEqual(world.player.sprite_image,
                                     config.WEAPON_POSE_IMAGES.get(weapon, config.PLAYER_IMAGE))

    def test_held_keys_and_early_represses_do_not_restart_or_buffer_a_kick(self):
        world, enemy = encounter()
        tap(world.controls, "combat_e")
        advance(world, 0.05)
        elapsed = world.player.animation.elapsed
        tap(world.controls, "combat_e")
        world.step(config.FIXED_DT)
        self.assertAlmostEqual(world.player.animation.elapsed, elapsed + config.FIXED_DT)
        advance(world, 1)
        self.assertEqual((world.player.air_kick_phase, enemy.hp), ("WAIT", 150))
        world.controls.press("combat_e")
        advance(world, 1)
        self.assertEqual((world.player.air_kick_phase, enemy.hp), ("WAIT", 150))
        self.assertEqual(kick(world, enemy), [(5, 50)])

    def test_wait_scales_enemy_motion_and_airborne_gravity_but_not_input_response(self):
        for enemy_type in (Enemy, Enemy02):
            world, _ = encounter()
            kick(world)
            world.enemies = [enemy_type(200, 1, ground_y=world.player.ground_y)]
            enemy = world.enemies[0]
            player = world.player
            player.jump_height, player.vy = 140, -100
            reference = Player()
            reference.jump_height, reference.vy = player.jump_height, player.vy
            for _ in range(60):
                world.step(config.FIXED_DT)
                reference.update_vertical(config.FIXED_DT * config.AIR_KICK_TIME_SCALE)
            self.assertAlmostEqual(enemy.x - 200, enemy.run_speed * 0.1)
            self.assertAlmostEqual(player.jump_height, reference.jump_height)
            self.assertAlmostEqual(player.vy, reference.vy)
            self.assertEqual(player.animation.frame, config.AIR_KICK_HOLD_FRAME)
            tap(world.controls, "combat_e")
            elapsed = world.elapsed
            world.step(config.FIXED_DT)
            self.assertEqual((player.air_kick_phase, world.time_scale), ("KICK", 1))
            self.assertAlmostEqual(world.elapsed - elapsed, config.FIXED_DT)

    def test_wait_is_harmless_to_new_targets_and_repress_hits_each_target_once(self):
        world, first = encounter()
        kick(world, first)
        second = Enemy02(first.x, first.facing, ground_y=first.ground_y)
        second.animation.set_state("HIT")
        second.cooldown = 100
        world.enemies.append(second)
        advance(world, 1)
        self.assertEqual((first.hp, second.hp), (150, 200))
        kick(world, first)
        self.assertEqual((first.hp, second.hp), (100, 150))
        advance(world, 0.5)
        self.assertEqual((first.hp, second.hp), (100, 150))

    def test_interruptions_loading_and_restart_clear_or_pause_the_wait(self):
        for cause in ("hit", "death", "car", "drop", "swap", "attack", "counter", "restart"):
            with self.subTest(cause=cause):
                world, enemy = encounter(weapon="steel_pipe")
                kick(world, enemy)
                player = world.player
                if cause in ("hit", "death"):
                    player.invincible = False
                    player.take_damage(20 if cause == "hit" else 500)
                elif cause == "car":
                    player.hit_by_car(1)
                elif cause == "drop":
                    tap(world.controls, "weapon_interact")
                elif cause == "swap":
                    player.equip_weapon("combat_knife")
                elif cause == "attack":
                    tap(world.controls, "combat_q")
                elif cause == "counter":
                    enemy.start_attack()
                    enemy.animation.elapsed = 2 / enemy.attack_fps
                    tap(world.controls, "counter_h")
                else:
                    tap(world.controls, "restart")
                world.update(config.FIXED_DT)
                self.assertIsNone(world.player.air_kick_phase)
                self.assertEqual(world.time_scale, 1)
        world, enemy = encounter()
        kick(world, enemy)
        before = (world.player.animation.elapsed, world.elapsed, enemy.animation.elapsed)
        world.pending_stage_index, world.stage_loading_remaining = 1, 2
        tap(world.controls, "combat_e")
        world.update(0.5)
        self.assertEqual((world.player.animation.elapsed, world.elapsed, enemy.animation.elapsed), before)
        self.assertFalse(world.controls.pressed)
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertIsNone(world.player.air_kick_phase)
        self.assertEqual(world.time_scale, 1)

    def test_chain_timing_damage_and_slow_motion_are_render_rate_independent(self):
        results = []
        for fps in (30, 60, 120, 144):
            world, enemy = encounter(Enemy02)
            snapshots = []
            for action in ("combat_e", "combat_e", None, "combat_r", "combat_r"):
                if action is not None:
                    tap(world.controls, action)
                advance(world, 0.5, fps)
                player = world.player
                snapshots.append((player.state, player.air_kick_phase, player.air_kick_strike_frame,
                                  player.animation.elapsed, world.time_scale, world.elapsed,
                                  enemy.hp, enemy.state, enemy.animation.elapsed))
            self.assertEqual([snapshot[6] for snapshot in snapshots], [150, 100, 100, 100, 50])
            results.append(snapshots)
        self.assertTrue(all(result == results[0] for result in results))

    def test_left_right_turning_changes_the_next_kick_target(self):
        for early in (False, True):
            world, right = encounter()
            left = Enemy(world.player.x - 80, 1)
            left.animation.set_state("HIT")
            left.cooldown = 100
            world.enemies.append(left)
            if early:
                tap(world.controls, "combat_e")
                advance(world, 0.05)
                world.controls.press("left")
                advance(world, 0.5)
                self.assertEqual((left.hp, right.hp), (150, 200))
            else:
                kick(world, right)
                world.controls.press("left")
                world.step(config.FIXED_DT)
                self.assertEqual(world.player.facing, -1)
                kick(world, left)
                self.assertEqual((left.hp, right.hp), (150, 150))

    def test_cancelling_and_restarting_e_cannot_bypass_two_kicks_per_airtime(self):
        for cancel in (False, True):
            world, _ = encounter()
            world.enemies.clear()
            world.player.jump_height, world.player.vy, world.player.jump_count = 600, 0, 1
            kick(world)
            if cancel:
                tap(world.controls, "combat_a")
                world.step(config.FIXED_DT)
            kick(world)
            while world.player.air_kick_phase == "RECOVERY":
                world.step(config.FIXED_DT)
            self.assertFalse(world.player.grounded)
            self.assertEqual(world.player.air_kicks_used, 2)
            tap(world.controls, "combat_e")
            world.step(config.FIXED_DT)
            self.assertIsNone(world.player.active_move)
            self.assertEqual(world.player.state, "JUMP")
            advance(world, 1)
            self.assertTrue(world.player.grounded)
            self.assertEqual(world.player.air_kicks_used, 0)
            tap(world.controls, "combat_e")
            world.step(config.FIXED_DT)
            self.assertEqual(world.player.air_kick_phase, "KICK")

    def test_a_ground_chain_does_not_spend_the_next_jumps_kick_allowance(self):
        world, _ = encounter()
        world.enemies.clear()
        kick(world)
        kick(world)
        advance(world, 0.2)
        self.assertEqual(world.player.air_kicks_used, 2)
        tap(world.controls, "jump")
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.air_kicks_used, 0)
        tap(world.controls, "combat_e")
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.air_kick_phase, "KICK")


if __name__ == "__main__":
    unittest.main()
