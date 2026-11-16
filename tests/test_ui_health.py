import unittest

import config
from player import Player
from ui import UI


class HealthBarTests(unittest.TestCase):
    def setUp(self):
        self.player = Player()
        self.ui = UI()
        self.ui.update(0, self.player)

    def hit(self, damage):
        self.assertTrue(self.player.take_damage(damage))
        self.ui.update(0, self.player)

    def test_damage_holds_then_drains_while_real_hp_stays_reduced(self):
        self.hit(20)
        self.assertEqual(self.player.hp, 480)
        self.assertEqual(self.ui.damage_hp, 500)
        self.ui.update(config.HP_DAMAGE_HOLD, self.player)
        self.assertEqual(self.ui.damage_hp, 500)
        self.ui.update(config.HP_DAMAGE_DURATION / 2, self.player)
        self.assertGreater(self.ui.damage_hp, 480)
        self.assertLess(self.ui.damage_hp, 500)
        self.assertEqual(self.player.hp, 480)
        self.ui.update(config.HP_DAMAGE_DURATION / 2, self.player)
        self.assertEqual(self.ui.damage_hp, 480)
        self.ui.update(1, self.player)
        self.assertEqual(self.ui.damage_hp, 480)

    def test_simultaneous_hits_show_the_total_lost_health(self):
        for _ in range(4):
            self.player.take_damage(20)
        self.ui.update(0, self.player)
        self.assertEqual(self.player.hp, 420)
        self.assertEqual(self.ui.damage_hp, 500)
        self.ui.update(config.HP_DAMAGE_HOLD + config.HP_DAMAGE_DURATION, self.player)
        self.assertEqual(self.ui.damage_hp, 420)

    def test_another_hit_extends_the_segment_without_moving_its_visible_end(self):
        self.hit(20)
        self.ui.update(config.HP_DAMAGE_HOLD + config.HP_DAMAGE_DURATION / 2, self.player)
        edge = self.ui.damage_hp
        self.hit(30)
        self.assertEqual(self.player.hp, 450)
        self.assertEqual(self.ui.damage_hp, edge)
        self.ui.update(config.HP_DAMAGE_HOLD, self.player)
        self.assertEqual(self.ui.damage_hp, edge)
        self.ui.update(config.HP_DAMAGE_DURATION, self.player)
        self.assertEqual(self.ui.damage_hp, 450)

    def test_ignored_damage_does_not_create_or_restart_a_trail(self):
        self.player.invincible = True
        self.assertFalse(self.player.take_damage(20))
        self.ui.update(0.1, self.player)
        self.assertEqual(self.ui.damage_hp, self.player.hp)
        self.player.invincible = False
        self.hit(20)
        self.ui.update(config.HP_DAMAGE_HOLD + 0.05, self.player)
        edge = self.ui.damage_hp
        self.player.invincible = True
        self.assertFalse(self.player.take_damage(20))
        self.ui.update(0.1, self.player)
        self.assertLess(self.ui.damage_hp, edge)
        self.assertEqual(self.player.hp, 480)

    def test_lethal_damage_only_trails_remaining_hp_and_finishes_at_zero(self):
        self.player.hp = 10
        self.ui = UI()
        self.ui.update(0, self.player)
        self.hit(20)
        self.assertEqual(self.player.hp, 0)
        self.assertEqual(self.ui.damage_hp, 10)
        self.ui.update(config.HP_DAMAGE_HOLD + config.HP_DAMAGE_DURATION, self.player)
        self.assertEqual(self.ui.damage_hp, 0)
        self.assertFalse(self.player.alive)

    def test_healing_and_new_players_clear_the_old_trail(self):
        self.hit(100)
        self.player.hp = 450
        self.ui.update(0, self.player)
        self.assertEqual(self.ui.damage_hp, 450)
        self.hit(20)
        replacement = Player()
        replacement.hp = 200
        self.ui.update(0, replacement)
        self.assertEqual(self.ui.damage_hp, 200)
        self.ui.update(0, Player())
        self.assertEqual(self.ui.damage_hp, config.MAX_HP)

    def test_zero_or_negative_time_does_not_advance_the_animation(self):
        self.hit(80)
        self.ui.update(config.HP_DAMAGE_HOLD + 0.1, self.player)
        edge = self.ui.damage_hp
        for dt in (0, -1, 0):
            self.ui.update(dt, self.player)
            self.assertEqual(self.ui.damage_hp, edge)

    def test_animation_timing_is_independent_of_frame_rate(self):
        edges = []
        for fps in (30, 60, 120, 144):
            self.setUp()
            self.hit(120)
            for seconds in (0.24, config.HP_DAMAGE_HOLD + config.HP_DAMAGE_DURATION - 0.24):
                frames = int(seconds * fps)
                for _ in range(frames):
                    self.ui.update(1 / fps, self.player)
                self.ui.update(seconds - frames / fps, self.player)
                edges.append(self.ui.damage_hp)
            self.assertEqual(self.ui.damage_hp, self.player.hp)
        for index in range(2, len(edges), 2):
            self.assertAlmostEqual(edges[index], edges[0])


if __name__ == "__main__":
    unittest.main()
