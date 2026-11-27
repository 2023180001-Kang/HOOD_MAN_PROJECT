import unittest

import config
from ar_soldier import ARSoldier
from enemy import Enemy
from researcher import Researcher
from tests.helpers import enter_kick_wait
from tests.test_combat import attacking_enemy
from world import World


LEFT_FIRST = ("left", "right", "left", "right")
RIGHT_FIRST = ("right", "left", "right", "left")


def tick(world, count=1):
    for _ in range(count):
        world.step(config.FIXED_DT)


def tap_keys(world, *keys):
    for key in keys:
        world.controls.press(key)
        world.controls.release(key)
    tick(world)


def melee_group(world, count=4):
    for index in range(count):
        side = (-1, 1)[index % 2]
        world.enemies.append(attacking_enemy(world.player.x + 80 * side, -side))
    tick(world)


def fire_at_player(world, shooter):
    shooter.start_attack()
    shooter.aim_remaining = 0
    shooter.animation.elapsed = (shooter.shoot_frame + 0.05) / shooter.attack_fps
    bullet = shooter.take_projectile()
    world.projectiles.append(bullet)
    return bullet


class CrowdEscapeTests(unittest.TestCase):
    def test_four_melee_hits_and_alternating_keys_release_hit_and_allow_movement(self):
        for sequence in (LEFT_FIRST, RIGHT_FIRST):
            with self.subTest(sequence=sequence):
                world = World()
                player = world.player
                melee_group(world)
                self.assertEqual((player.hp, player.state), (420, "HIT"))
                for key in sequence[:3]:
                    tap_keys(world, key)
                    tick(world, 10)
                self.assertFalse(player.crowd_escape.active)
                world.controls.press(sequence[-1])
                tick(world)
                self.assertEqual((player.hp, player.state), (420, "WALK"))
                tick(world, 75)
                direction = 1 if sequence[-1] == "right" else -1
                self.assertGreater((player.x - config.START_X) * direction, 100)
                self.assertTrue(player.crowd_escape.active)

    def test_mixed_melee_pistol_and_rifle_hits_count_the_shooters_on_impact(self):
        world = World()
        melee_group(world, 2)
        for shooter_type in (Researcher, ARSoldier):
            shooter = shooter_type(world.player.x - 260, 1)
            fire_at_player(world, shooter)
            shooter.take_damage(shooter.hp)  # The emitted round keeps its source.
        self.assertFalse(world.player.crowd_escape.ready)
        tick(world, 45)
        self.assertEqual(world.player.hp, 370)
        tap_keys(world, *RIGHT_FIRST)  # Four distinct keydown edges in a single event batch.
        self.assertTrue(world.player.crowd_escape.active)

    def test_one_rifle_burst_counts_once_even_with_other_enemies_present(self):
        world = World()
        melee_group(world, 2)
        rifleman = ARSoldier(world.player.x - 220, 1)
        for _ in range(4):
            fire_at_player(world, rifleman)
        world.enemies.append(Enemy(world.player.x + 600))
        tick(world, 30)
        self.assertEqual(world.player.hp, 260)
        tap_keys(world, *LEFT_FIRST)
        self.assertFalse(world.player.crowd_escape.active)

    def test_four_ranged_attackers_qualify_and_blocked_or_missed_rounds_do_not(self):
        world = World()
        player = world.player
        shooters = [Researcher(player.x - 260, 1) for _ in range(4)]
        player.invincible = True
        for shooter in shooters:
            fire_at_player(world, shooter)
        tick(world, 45)
        self.assertEqual(player.hp, 500)
        self.assertFalse(player.crowd_escape.ready)
        player.invincible = False
        shooters[-1].ground_y += 80
        for shooter in shooters:
            fire_at_player(world, shooter)
        tick(world, 45)
        self.assertEqual(player.hp, 380)
        self.assertFalse(player.crowd_escape.ready)
        shooters[-1].ground_y = player.ground_y
        fire_at_player(world, shooters[-1])
        tick(world, 45)
        tap_keys(world, *LEFT_FIRST)
        self.assertTrue(player.crowd_escape.active)

    def test_holding_one_key_and_slow_taps_do_not_activate(self):
        for inputs in ("held", "single_key", "slow"):
            with self.subTest(inputs=inputs):
                world = World()
                melee_group(world)
                if inputs == "held":
                    for key in LEFT_FIRST * 2:
                        world.controls.press(key)
                        tick(world)
                elif inputs == "single_key":
                    tap_keys(world, "left", "left", "left", "left")
                else:
                    tap_keys(world, "left", "right", "left")
                    tick(world, 74)
                    tap_keys(world, "right")
                self.assertFalse(world.player.crowd_escape.active)

    def test_expired_hits_and_preemptive_taps_cannot_complete_an_escape(self):
        world = World()
        tap_keys(world, "left", "right", "left")
        melee_group(world)
        tap_keys(world, "right")
        self.assertFalse(world.player.crowd_escape.active)
        world.enemies.clear()
        tick(world, 121)
        tap_keys(world, *LEFT_FIRST)
        self.assertFalse(world.player.crowd_escape.active)
        self.assertIsNone(world.player.active_move)

    def test_d_and_f_do_not_trigger_escape_and_can_attack_during_immunity(self):
        world = World()
        melee_group(world)
        tap_keys(world, "combat_d", "combat_f", "combat_d", "combat_f")
        self.assertFalse(world.player.crowd_escape.active)
        tap_keys(world, *LEFT_FIRST)
        for key in ("d", "f"):
            tap_keys(world, f"combat_{key}")
            self.assertTrue(world.player.crowd_escape.active)
            self.assertEqual(world.player.active_move.key, key)

    def test_one_second_blocks_bullets_and_melee_then_new_hits_apply(self):
        world = World()
        player = world.player
        melee_group(world)
        tap_keys(world, *LEFT_FIRST)
        world.enemies = [attacking_enemy(player.x - 80)]
        bullet = fire_at_player(world, ARSoldier(player.x - 200, 1))
        tick(world, 20)
        self.assertTrue(world.enemies[0].has_hit and bullet.spent)
        self.assertEqual((player.hp, bullet.impact_damage), (420, 0))
        world.enemies.clear()
        tap_keys(world, *LEFT_FIRST)
        tick(world, 98)
        self.assertTrue(player.crowd_escape.active)  # 119 of 120 ticks.
        world.enemies.append(attacking_enemy(player.x - 80))
        tick(world)
        self.assertFalse(player.crowd_escape.active)
        self.assertEqual(player.hp, 400)
        self.assertFalse(player.crowd_escape.ready)

    def test_restart_stage_change_and_lethal_hits_discard_escape_opportunity(self):
        world = World()
        melee_group(world)
        tap_keys(world, "left", "right", "left")
        world.select_stage(1)
        tap_keys(world, "right")
        self.assertFalse(world.player.crowd_escape.active)
        melee_group(world)
        tap_keys(world, *LEFT_FIRST)
        self.assertTrue(world.player.crowd_escape.active)
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertFalse(world.player.crowd_escape.active)
        world.player.hp = 80
        melee_group(world)
        tap_keys(world, *LEFT_FIRST)
        self.assertEqual((world.player.hp, world.player.state), (0, "DYING"))
        self.assertFalse(world.player.crowd_escape.active)

    def test_five_attackers_p_toggle_and_slow_motion_use_independent_clocks(self):
        world = World()
        player = world.player
        melee_group(world, 5)
        world.enemies.clear()
        tap_keys(world, *LEFT_FIRST)
        self.assertTrue(player.crowd_escape.active)
        world.controls.press("invincibility")
        enter_kick_wait(world)
        tick(world)
        self.assertLess(world.time_scale, 1.0)
        tick(world, 119)
        self.assertFalse(player.crowd_escape.active)
        self.assertTrue(player.invincible)
        self.assertFalse(player.take_damage(20))
