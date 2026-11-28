import unittest

import config
from combat import MOVES
from enemy import Enemy
from tests.helpers import advance, tap
from world import World


def striker(world, side=1):
    enemy = Enemy(world.player.x + side * 80, facing=-side)
    enemy.animation.set_state("ATTACK")
    enemy.animation.elapsed = 4 / config.ENEMY_ANIMATIONS["ATTACK"][1]
    enemy.cooldown = 1
    world.enemies.append(enemy)
    return enemy


class InvincibilityTests(unittest.TestCase):
    def test_immune_hits_from_both_sides_are_consumed_without_damage_or_feedback(self):
        world = World()
        self.assertFalse(world.player.invincible)
        world.controls.press("invincibility")
        enemies = [striker(world, side) for side in (-1, -1, 1, 1)]
        world.step(config.FIXED_DT)
        self.assertTrue(world.player.invincible)
        self.assertEqual(world.player.hp, 500)
        self.assertEqual(world.player.state, "IDLE")
        self.assertTrue(all(enemy.has_hit for enemy in enemies))
        self.assertEqual(world.effects, [])
        self.assertEqual(world.camera.shake_remaining, 0)

    def test_holding_p_does_not_retoggle_and_off_allows_only_new_attacks(self):
        world = World()
        world.player.hp = 120
        world.controls.press("invincibility")
        enemy = striker(world)
        world.step(config.FIXED_DT)
        world.controls.press("invincibility")
        advance(world, 0.1)
        self.assertTrue(world.player.invincible)
        self.assertEqual(world.player.hp, 120)
        tap(world.controls, "invincibility")
        world.step(config.FIXED_DT)
        self.assertFalse(world.player.invincible)
        self.assertEqual(world.player.hp, 120)
        self.assertTrue(enemy.has_hit)
        striker(world, -1)
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 100)
        self.assertEqual(world.player.state, "HIT")
        self.assertEqual(len(world.effects), 1)
        self.assertGreater(world.camera.shake_remaining, 0)

    def test_immune_hits_keep_all_player_attacks_active(self):
        for key, damage in zip("asdf", (10, 15, 20, 25)):
            with self.subTest(key=key):
                world = World()
                world.controls.press("invincibility")
                world.controls.press(f"combat_{key}")
                front, rear = striker(world), striker(world, -1)
                world.step(config.FIXED_DT)
                self.assertEqual(world.player.state, f"ATTACK_{key.upper()}")
                self.assertEqual(world.player.hp, 500)
                self.assertEqual(world.player.vx, 0)
                self.assertTrue(front.has_hit and rear.has_hit)
                self.assertEqual(world.effects, [])
                advance(world, 4 / MOVES[f"combat_{key}"].fps)
                self.assertEqual(front.hp, 200 - damage)
                self.assertEqual(rear.hp, 200)
                self.assertEqual([number.damage for number in world.damage_numbers], [damage])

    def test_enabling_during_hit_does_not_heal_or_restart_the_existing_pose(self):
        world = World()
        striker(world)
        world.step(config.FIXED_DT)
        elapsed = world.player.animation.elapsed
        shake = world.camera.shake_remaining
        world.controls.press("invincibility")
        striker(world, -1)
        world.step(config.FIXED_DT)
        self.assertTrue(world.player.invincible)
        self.assertEqual(world.player.hp, 480)
        self.assertEqual(world.player.state, "HIT")
        self.assertGreater(world.player.animation.elapsed, elapsed)
        self.assertEqual(len(world.effects), 1)
        self.assertLess(world.camera.shake_remaining, shake)

    def test_stage_travel_preserves_the_mode_and_restart_clears_pending_p(self):
        world = World()
        world.controls.press("invincibility")
        world.step(config.FIXED_DT)
        player = world.player
        world.stage.defeated_count = world.stage.defeats_required
        world.stage.arrows_visible = True
        player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
        player.vx = config.RUN_SPEED
        world.controls.press("right")
        world.controls.press("left_shift")
        world.step(config.FIXED_DT)
        self.assertEqual(world.stage_index, 1)
        self.assertIs(world.player, player)
        self.assertTrue(player.invincible)
        tap(world.controls, "invincibility")
        world.controls.press("restart")
        world.update(1 / 60)
        advance(world, 0.1)
        self.assertEqual(world.stage_index, 0)
        self.assertFalse(world.player.invincible)
        self.assertEqual(world.player.hp, 500)
        self.assertNotIn("invincibility", world.controls.held)
        self.assertNotIn("invincibility", world.controls.pressed)

    def test_p_is_consumed_during_death_without_reviving_the_player(self):
        world = World()
        world.player.take_damage(500)
        for duration in (0, 1):
            advance(world, duration)
            tap(world.controls, "invincibility")
            world.step(config.FIXED_DT)
            self.assertFalse(world.player.invincible)
            self.assertEqual(world.player.hp, 0)
            self.assertIn(world.player.state, ("DYING", "DEAD"))
            self.assertNotIn("invincibility", world.controls.pressed)


if __name__ == "__main__":
    unittest.main()
