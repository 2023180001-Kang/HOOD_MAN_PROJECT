import unittest

import config
from combat import MOVES
from enemy import Enemy
from tests.helpers import advance, tap
from world import World


def target(world, offset=80):
    enemy = Enemy(world.player.x + offset, facing=-1 if offset > 0 else 1)
    enemy.cooldown = 100
    world.enemies.append(enemy)
    return enemy


class PlayerDamageTests(unittest.TestCase):
    def test_each_offensive_key_deals_its_requested_damage_once(self):
        for key, damage in zip("qwerasdf", (20, 30, 20, 20, 20, 20, 50, 40)):
            with self.subTest(key=key):
                world = World(spawn_schedule=())
                enemy = target(world)
                self.assertEqual(enemy.hp, 200)
                world.controls.press(f"combat_{key}")
                advance(world, 0.1)
                self.assertEqual(enemy.hp, 200)  # Wind-up is not a hit.
                advance(world, 0.4)
                self.assertEqual(enemy.hp, 200 - damage)
                self.assertEqual(enemy.state, "HIT")

    def test_one_swing_hits_each_overlapping_enemy_once_and_next_swing_can_hit_again(self):
        world = World(spawn_schedule=())
        first, second = target(world, 80), target(world, 100)
        world.controls.press("combat_q")
        advance(world, 1)
        self.assertEqual((first.hp, second.hp), (180, 180))
        tap(world.controls, "combat_q")
        advance(world, 0.5)
        self.assertEqual((first.hp, second.hp), (160, 160))

    def test_block_has_no_attack_box_or_damage(self):
        world = World(spawn_schedule=())
        enemy = target(world)
        world.controls.press("combat_h")
        advance(world, 0.5)
        self.assertIsNone(world.player.attack_box)
        self.assertEqual(enemy.hp, 200)

    def test_attack_misses_behind_outside_reach_and_above_the_hit_area(self):
        for offset, height in ((-80, 0), (500, 0), (80, 300)):
            with self.subTest(offset=offset, height=height):
                world = World(spawn_schedule=())
                enemy = target(world, offset)
                enemy.y += height
                world.controls.press("combat_e")
                advance(world, 0.5)
                self.assertEqual(enemy.hp, 200)

    def test_left_attack_and_uppercut_vertical_reach(self):
        world = World(spawn_schedule=())
        enemy = target(world, -80)
        world.controls.press("left")
        world.controls.press("combat_d")
        advance(world, 0.5)
        self.assertEqual(enemy.hp, 150)
        for key, expected in (("combat_e", 200), ("combat_d", 150)):
            world = World(spawn_schedule=())
            enemy = target(world)
            enemy.y += 170
            world.controls.press(key)
            advance(world, 0.5)
            self.assertEqual(enemy.hp, expected)

    def test_player_hit_interrupts_the_enemy_attack_in_the_same_step(self):
        world = World(spawn_schedule=())
        enemy = target(world)
        enemy.animation.set_state("ATTACK")
        enemy.animation.elapsed = 4 / config.ENEMY_ANIMATIONS["ATTACK"][1]
        world.player.start_move(MOVES["combat_q"], 1)
        world.player.animation.elapsed = 3 / config.COMBAT_FPS
        world.step(config.FIXED_DT)
        self.assertEqual(enemy.hp, 180)
        self.assertEqual(enemy.state, "HIT")
        self.assertEqual(world.player.hp, 500)
        self.assertIsNone(enemy.attack_box)

    def test_four_uppercuts_kill_and_dead_enemy_cannot_block_or_resurrect(self):
        world = World(spawn_schedule=())
        enemy = target(world)
        for index in range(4):
            tap(world.controls, "combat_d")
            advance(world, 0.8)
            self.assertEqual(enemy.hp, max(0, 200 - (index + 1) * 50))
        self.assertEqual(enemy.state, "DYING")
        self.assertEqual(enemy.animation.row, 6)
        self.assertFalse(enemy.take_damage(50))
        advance(world, 1)
        self.assertEqual(enemy.state, "DEAD")
        self.assertEqual(enemy.animation.frame, 7)
        world.controls.press("right")
        advance(world, 0.8)
        self.assertGreater(world.player.x, enemy.x)
        world.player.take_damage(500)
        world.step(config.FIXED_DT)
        self.assertEqual(enemy.state, "DEAD")
        self.assertFalse(enemy.knockback_started)

    def test_lethal_overkill_clamps_hp_and_restart_restores_two_hundred(self):
        world = World(spawn_schedule=())
        enemy = target(world)
        enemy.hp = 10
        world.controls.press("combat_d")
        advance(world, 0.5)
        self.assertEqual(enemy.hp, 0)
        self.assertEqual(enemy.state, "DYING")
        world.controls.press("restart")
        world.update(1 / 60)
        self.assertEqual(world.enemies, [])
        self.assertEqual(world.player.hit_enemies, set())
        fresh = target(world)
        self.assertEqual(fresh.hp, 200)
        self.assertTrue(fresh.alive)


if __name__ == "__main__":
    unittest.main()
