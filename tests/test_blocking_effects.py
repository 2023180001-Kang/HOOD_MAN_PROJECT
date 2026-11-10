import unittest

import config
from combat import MOVES
from effects import HitEffect
from enemy import Enemy
from tests.helpers import advance
from world import World


def striker(world, side=1):
    enemy = Enemy(world.player.x + side * 80, facing=-side)
    enemy.animation.set_state("ATTACK")
    enemy.animation.elapsed = 4 / config.ENEMY_ANIMATIONS["ATTACK"][1]
    enemy.cooldown = 1
    world.enemies.append(enemy)
    return enemy


def guard(world, frame=3, facing=1):
    world.player.start_move(MOVES["combat_h"], facing)
    world.player.animation.elapsed = frame / config.COMBAT_FPS


class BlockingEffectTests(unittest.TestCase):
    def test_timed_frontal_block_halves_damage_without_restarting_guard(self):
        for facing in (-1, 1):
            with self.subTest(facing=facing):
                world = World(spawn_schedule=())
                guard(world, facing=facing)
                enemy = striker(world, facing)
                elapsed = world.player.animation.elapsed
                self.assertTrue(enemy.try_hit(world.player))
                self.assertEqual(world.player.hp, 490)
                self.assertEqual(world.player.state, "BLOCK")
                self.assertEqual(world.player.animation.elapsed, elapsed)
                self.assertFalse(enemy.try_hit(world.player))
                self.assertEqual(world.player.hp, 490)

    def test_early_late_and_rear_attacks_are_not_halved(self):
        for frame, side in ((0, 1), (5, 1), (3, -1)):
            with self.subTest(frame=frame, side=side):
                world = World(spawn_schedule=())
                guard(world, frame=frame)
                self.assertTrue(striker(world, side).try_hit(world.player))
                self.assertEqual(world.player.hp, 480)
                self.assertEqual(world.player.state, "HIT")
                self.assertIsNone(world.player.active_move)

    def test_first_and_last_valid_guard_frames_reduce_damage(self):
        for frame in (2, 4):
            world = World(spawn_schedule=())
            guard(world, frame=frame)
            striker(world).try_hit(world.player)
            self.assertEqual(world.player.hp, 490)

    def test_each_front_enemy_is_counted_during_a_timed_block(self):
        world = World(spawn_schedule=())
        guard(world)
        for _ in range(4):
            striker(world)
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 460)
        self.assertEqual(world.player.state, "BLOCK")
        self.assertEqual(len(world.effects), 4)
        advance(world, 0.1)
        self.assertEqual(world.player.hp, 460)
        self.assertEqual(len(world.effects), 4)

    def test_holding_block_does_not_create_permanent_protection(self):
        world = World(spawn_schedule=())
        world.controls.press("combat_h")
        advance(world, 0.5)
        striker(world)
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 480)
        self.assertEqual(world.player.state, "HIT")
        world.enemies.clear()
        advance(world, 1)
        world.controls.press("combat_h")
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.state, "IDLE")

    def test_reduced_lethal_damage_still_enters_death_and_cancels_guard(self):
        world = World(spawn_schedule=())
        world.player.hp = 10
        guard(world)
        enemy = striker(world)
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 0)
        self.assertEqual(world.player.state, "DYING")
        self.assertEqual(world.player.sprite_image, config.PLAYER_IMAGE)
        self.assertIsNone(world.player.active_move)
        self.assertTrue(enemy.knockback_started)
        self.assertEqual(len(world.effects), 1)

    def test_player_hits_spawn_at_contact_and_effects_follow_world_coordinates(self):
        for facing in (-1, 1):
            world = World(spawn_schedule=())
            enemy = Enemy(config.START_X + facing * 80, -facing)
            enemy.cooldown = 100
            world.enemies = [enemy]
            world.controls.press("left" if facing < 0 else "right")
            world.controls.press("combat_q")
            advance(world, 0.3)
            self.assertEqual(enemy.hp, 180)
            self.assertEqual(len(world.effects), 1)
            effect = world.effects[0]
            self.assertEqual(effect.facing, facing)
            self.assertGreaterEqual(effect.x, enemy.body.left)
            self.assertLessEqual(effect.x, enemy.body.right)
            self.assertGreaterEqual(effect.y, enemy.body.bottom)
            self.assertLessEqual(effect.y, enemy.body.top)
            position = (effect.x, effect.y)
            world.camera.shake()
            world.camera.update(0.05, world.player.x)
            self.assertEqual((effect.x, effect.y), position)
            advance(world, 0.5)
            self.assertEqual(world.effects, [])

    def test_enemy_hit_spawns_one_effect_with_the_incoming_direction(self):
        for side in (-1, 1):
            world = World(spawn_schedule=())
            striker(world, side)
            world.step(config.FIXED_DT)
            self.assertEqual(world.player.hp, 480)
            self.assertEqual(len(world.effects), 1)
            self.assertEqual(world.effects[0].facing, -side)
            advance(world, 0.1)
            self.assertEqual(len(world.effects), 1)

    def test_effect_plays_eight_frames_then_expires(self):
        effect = HitEffect(100, 150, 1)
        frames = []
        for _ in range(8):
            frames.append(effect.frame)
            self.assertFalse(effect.finished)
            effect.update(1 / config.HIT_EFFECT_FPS)
        self.assertEqual(frames, list(range(8)))
        self.assertTrue(effect.finished)

    def test_simultaneous_player_and_other_enemy_hits_spawn_both_effects(self):
        world = World(spawn_schedule=())
        victim = Enemy(config.START_X + 80, -1)
        victim.cooldown = 100
        world.enemies = [victim]
        striker(world, -1)
        world.player.start_move(MOVES["combat_q"], 1)
        world.player.animation.elapsed = 3 / config.COMBAT_FPS
        world.step(config.FIXED_DT)
        self.assertEqual((victim.hp, world.player.hp), (180, 480))
        self.assertEqual(len(world.effects), 2)
        self.assertNotEqual(world.effects[0].x, world.effects[1].x)

    def test_misses_and_dead_targets_never_spawn_hit_effects(self):
        for offset, defeated in ((-80, False), (80, True), (500, False)):
            world = World(spawn_schedule=())
            enemy = Enemy(config.START_X + offset)
            enemy.cooldown = 100
            if defeated:
                enemy.take_damage(200)
            world.enemies = [enemy]
            world.controls.press("combat_q")
            advance(world, 0.3)
            self.assertEqual(world.effects, [])

    def test_restart_clears_live_effects_and_guard(self):
        world = World(spawn_schedule=())
        guard(world)
        striker(world)
        world.step(config.FIXED_DT)
        self.assertTrue(world.effects)
        world.controls.press("restart")
        world.update(1 / 60)
        self.assertEqual(world.effects, [])
        self.assertIsNone(world.player.active_move)
        self.assertEqual(world.player.hp, 500)
        self.assertEqual(world.enemies, [])

    def test_attack_and_effect_state_are_identical_across_render_rates(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world = World(spawn_schedule=())
            enemy = Enemy(config.START_X + 80, -1)
            enemy.cooldown = 100
            world.enemies = [enemy]
            world.controls.press("combat_q")
            advance(world, 0.5, fps)
            outcomes.append((enemy.hp, world.player.state,
                             [(effect.x, effect.y, effect.frame) for effect in world.effects]))
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
