import unittest

import config
from combat import MOVES
from tests.helpers import advance, tap
from world import World


class PlayerActionTests(unittest.TestCase):
    def test_asdf_use_the_correct_source_rows_and_return_to_idle(self):
        expected = (("a", 3, config.COMBAT_IMAGE), ("s", 4, config.COMBAT_IMAGE),
                    ("d", 1, config.COMBAT_IMAGE), ("f", 2, config.COMBAT_IMAGE))
        self.assertEqual(set(MOVES), {f"combat_{key}" for key, _, _ in expected})
        for letter, row, image in expected:
            key = f"combat_{letter}"
            move = MOVES[key]
            with self.subTest(key=key):
                world = World()
                world.controls.press(key)
                world.update(1 / 60)
                self.assertEqual(world.player.state, move.state)
                self.assertEqual(world.player.animation.row, row)
                self.assertEqual(world.player.sprite_image, image)
                advance(world, 0.8)
                self.assertEqual(world.player.state, "IDLE")
                self.assertEqual(world.player.sprite_image, config.PLAYER_IMAGE)
                self.assertIsNone(world.player.active_move)

    def test_punches_have_short_windup_and_finish_in_one_third_second(self):
        for key in ("combat_a", "combat_s"):
            with self.subTest(key=key):
                world = World()
                world.controls.press(key)
                advance(world, 0.1)
                self.assertIsNone(world.player.attack_box)
                advance(world, 0.05)
                self.assertIsNotNone(world.player.attack_box)
                advance(world, 0.15)
                self.assertIsNotNone(world.player.active_move)
                advance(world, 1 / 30)
                self.assertIsNone(world.player.active_move)
                self.assertEqual(world.player.state, "IDLE")

    def test_kicks_have_slower_windup_and_finish_after_four_ninths_second(self):
        for key in ("combat_d", "combat_f"):
            with self.subTest(key=key):
                world = World()
                world.controls.press(key)
                advance(world, 0.15)
                self.assertIsNone(world.player.attack_box)
                advance(world, 0.05)
                self.assertIsNotNone(world.player.attack_box)
                advance(world, 0.1)
                self.assertIsNone(world.player.attack_box)
                self.assertIsNotNone(world.player.active_move)
                advance(world, 2 / 15)
                self.assertIsNotNone(world.player.active_move)
                advance(world, 1 / 60)
                self.assertIsNone(world.player.active_move)
                self.assertEqual(world.player.state, "IDLE")

    def test_held_and_repeated_keys_do_not_loop_attacks(self):
        world = World()
        world.controls.press("combat_a")
        advance(world, 1)
        world.controls.press("combat_a")
        advance(world, 0.1)
        self.assertEqual(world.player.state, "IDLE")
        tap(world.controls, "combat_a")
        world.update(1 / 60)
        self.assertEqual(world.player.state, "ATTACK_A")

    def test_different_attack_switches_on_next_step_during_any_attack_phase(self):
        for first in MOVES:
            for second, move in MOVES.items():
                if first == second:
                    continue
                for elapsed in (config.FIXED_DT, 0.2, 0.3):
                    with self.subTest(first=first, second=second, elapsed=elapsed):
                        world = World()
                        world.controls.press(first)
                        advance(world, elapsed, fps=120)
                        world.controls.press(second)
                        world.update(config.FIXED_DT)
                        self.assertEqual(world.player.active_move, move)
                        self.assertEqual(world.player.state, move.state)
                        self.assertAlmostEqual(world.player.animation.elapsed, config.FIXED_DT)
                        self.assertEqual(world.player.animation.frame, 0)
                        self.assertIsNone(world.player.attack_box)
                        self.assertNotIn(second, world.controls.pressed)

    def test_latest_attack_wins_when_multiple_keys_arrive_before_one_update(self):
        for first in MOVES:
            for second in MOVES:
                if first == second:
                    continue
                for sequence in ((first, second), (first, second, first)):
                    with self.subTest(sequence=sequence):
                        world = World()
                        for key in sequence:
                            tap(world.controls, key)
                        world.update(config.FIXED_DT)
                        self.assertEqual(world.player.active_move, MOVES[sequence[-1]])
                        advance(world, 0.6)
                        self.assertEqual(world.player.state, "IDLE")
                        self.assertFalse(world.controls.pressed)

    def test_repressing_current_attack_does_not_restart_or_buffer_it(self):
        for key in MOVES:
            with self.subTest(key=key):
                world = World()
                world.controls.press(key)
                advance(world, 0.1)
                elapsed = world.player.animation.elapsed
                tap(world.controls, key)
                world.update(config.FIXED_DT)
                self.assertAlmostEqual(world.player.animation.elapsed, elapsed + config.FIXED_DT)
                advance(world, 0.6)
                self.assertEqual(world.player.state, "IDLE")
                self.assertNotIn(key, world.controls.pressed)

    def test_repeating_an_old_held_key_does_not_switch_back(self):
        world = World()
        world.controls.press("combat_a")
        world.update(config.FIXED_DT)
        world.controls.press("combat_s")
        world.update(config.FIXED_DT)
        world.controls.press("combat_a")
        world.update(config.FIXED_DT)
        self.assertEqual(world.player.state, "ATTACK_S")
        self.assertAlmostEqual(world.player.animation.elapsed, 2 * config.FIXED_DT)
        advance(world, 0.6)
        self.assertEqual(world.player.state, "IDLE")

    def test_switching_attacks_still_consumes_jump_and_locks_horizontal_movement(self):
        world = World()
        world.controls.press("combat_s")
        advance(world, 0.1)
        world.controls.press("combat_d")
        world.controls.press("jump")
        world.controls.press("right")
        x = world.player.x
        world.update(config.FIXED_DT)
        self.assertEqual(world.player.state, "ATTACK_D")
        self.assertEqual(world.player.jump_count, 0)
        self.assertEqual(world.player.x, x)
        self.assertEqual(world.player.vx, 0)
        self.assertFalse(world.controls.take_press("jump"))
        self.assertFalse(world.controls.take_press("combat_d"))

    def test_hit_dying_and_dead_consume_attacks_without_switching_or_buffering(self):
        for state in ("HIT", "DYING", "DEAD"):
            with self.subTest(state=state):
                world = World()
                world.controls.press("combat_a")
                world.update(config.FIXED_DT)
                world.player.take_damage(20 if state == "HIT" else 500)
                if state == "DEAD":
                    advance(world, 1)
                for key in MOVES:
                    tap(world.controls, key)
                world.update(config.FIXED_DT)
                self.assertEqual(world.player.state, state)
                self.assertIsNone(world.player.active_move)
                self.assertFalse(world.controls.pressed)
                advance(world, 1)
                self.assertEqual(world.player.state, "IDLE" if state == "HIT" else "DEAD")
                self.assertIsNone(world.player.active_move)

    def test_airborne_action_stops_horizontal_movement_but_keeps_gravity(self):
        world = World()
        world.controls.press("jump")
        advance(world, 0.2)
        height = world.player.y
        world.player.vx = 300
        world.controls.press("combat_f")
        world.update(1 / 60)
        self.assertEqual(world.player.vx, 0)
        self.assertNotEqual(world.player.y, height)
        self.assertEqual(world.player.state, "ATTACK_F")
        advance(world, 1)
        self.assertTrue(world.player.grounded)

    def test_damage_interrupts_an_action_and_death_keeps_original_sheet(self):
        world = World()
        world.controls.press("combat_s")
        world.update(1 / 60)
        world.player.take_damage(20)
        self.assertIsNone(world.player.active_move)
        self.assertEqual(world.player.state, "HIT")
        self.assertEqual(world.player.sprite_image, config.PLAYER_IMAGE)
        world.player.take_damage(500)
        self.assertEqual(world.player.state, "DYING")
        self.assertEqual(world.player.animation.row, 5)

    def test_facing_is_selected_at_start_then_locked_during_action(self):
        world = World()
        world.controls.press("left")
        world.controls.press("combat_a")
        world.update(1 / 60)
        self.assertEqual(world.player.facing, -1)
        world.controls.release("left")
        world.controls.press("right")
        advance(world, 0.2)
        self.assertEqual(world.player.facing, -1)
        self.assertEqual(world.player.x, config.START_X)
        world.controls.press("combat_s")
        world.update(config.FIXED_DT)
        self.assertEqual(world.player.state, "ATTACK_S")
        self.assertEqual(world.player.facing, 1)
        self.assertEqual(world.player.x, config.START_X)

    def test_restart_discards_active_move_and_repeated_target_state(self):
        world = World()
        world.controls.press("combat_a")
        world.update(1 / 60)
        world.player.hit_enemies.add(object())
        world.controls.press("restart")
        world.update(1 / 60)
        self.assertIsNone(world.player.active_move)
        self.assertEqual(world.player.hit_enemies, set())
        self.assertEqual(world.player.state, "IDLE")
        self.assertEqual(world.player.hp, 500)


if __name__ == "__main__":
    unittest.main()
