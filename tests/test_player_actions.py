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

    def test_fast_attacks_have_short_windup_and_finish_in_one_third_second(self):
        for key in MOVES:
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

    def test_busy_inputs_are_consumed_without_buffering_or_interrupting(self):
        world = World()
        world.controls.press("combat_s")
        advance(world, 0.1)
        world.controls.press("combat_d")
        world.controls.press("jump")
        world.controls.press("right")
        x = world.player.x
        advance(world, 0.8)
        self.assertNotEqual(world.player.state, "ATTACK_D")
        self.assertEqual(world.player.jump_count, 0)
        self.assertFalse(world.controls.take_press("combat_d"))
        self.assertGreaterEqual(world.player.x, x)

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
