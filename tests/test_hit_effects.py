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


class HitEffectTests(unittest.TestCase):
    def test_player_hits_spawn_at_contact_and_effects_follow_world_coordinates(self):
        for facing in (-1, 1):
            world = World()
            enemy = Enemy(config.START_X + facing * 80, -facing)
            enemy.cooldown = 100
            world.enemies = [enemy]
            world.controls.press("left" if facing < 0 else "right")
            world.controls.press("combat_a")
            advance(world, 0.2)
            self.assertEqual(enemy.hp, 190)
            self.assertEqual(len(world.effects), 1)
            self.assertGreater(world.camera.shake_remaining, 0)
            effect = world.effects[0]
            self.assertEqual(effect.facing, facing)
            self.assertGreaterEqual(effect.x, enemy.body.left)
            self.assertLessEqual(effect.x, enemy.body.right)
            self.assertGreaterEqual(effect.y, enemy.body.bottom)
            self.assertLessEqual(effect.y, enemy.body.top)
            position = (effect.x, effect.y)
            world.camera.update(0.05, world.player.x)
            self.assertEqual((effect.x, effect.y), position)
            advance(world, 0.5)
            self.assertEqual(world.effects, [])

    def test_enemy_hit_spawns_one_effect_with_the_incoming_direction(self):
        for side in (-1, 1):
            world = World()
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
        world = World()
        victim = Enemy(config.START_X + 80, -1)
        victim.cooldown = 100
        world.enemies = [victim]
        striker(world, -1)
        world.player.start_move(MOVES["combat_a"], 1)
        world.player.animation.elapsed = 3 / MOVES["combat_a"].fps
        world.step(config.FIXED_DT)
        self.assertEqual((victim.hp, world.player.hp), (190, 480))
        self.assertEqual(len(world.effects), 2)
        self.assertNotEqual(world.effects[0].x, world.effects[1].x)

    def test_misses_and_dead_targets_never_spawn_hit_effects(self):
        for offset, defeated in ((-80, False), (80, True), (500, False)):
            world = World()
            enemy = Enemy(config.START_X + offset)
            enemy.cooldown = 100
            if defeated:
                enemy.take_damage(200)
            world.enemies = [enemy]
            world.controls.press("combat_a")
            advance(world, 0.3)
            self.assertEqual(world.effects, [])
            self.assertEqual(world.camera.shake_remaining, 0)

    def test_only_new_player_hits_restart_shake_and_it_expires(self):
        world = World()
        enemy = Enemy(config.START_X + 80, -1)
        enemy.cooldown = 100
        world.enemies = [enemy]
        world.controls.press("combat_a")
        advance(world, 0.175)
        remaining = world.camera.shake_remaining
        self.assertGreater(remaining, 0)
        advance(world, 0.05)
        self.assertLess(world.camera.shake_remaining, remaining)
        self.assertEqual(enemy.hp, 190)
        advance(world, 0.2)
        self.assertEqual(world.camera.shake_remaining, 0)
        self.assertEqual((world.camera.offset_x, world.camera.offset_y), (0, 0))

    def test_restart_clears_live_effects_and_combat(self):
        world = World()
        world.controls.press("combat_a")
        striker(world)
        world.step(config.FIXED_DT)
        world.effects.append(HitEffect(100, 150, 1))
        self.assertTrue(world.effects)
        world.controls.press("restart")
        world.update(1 / 60)
        self.assertEqual(world.effects, [])
        self.assertIsNone(world.player.active_move)
        self.assertEqual(world.player.hp, 500)
        self.assertEqual(world.player.vx, 0)
        self.assertEqual(world.player.x, config.START_X)
        self.assertEqual(world.enemies, [])

    def test_attack_and_effect_state_are_identical_across_render_rates(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world = World()
            enemy = Enemy(config.START_X + 80, -1)
            enemy.cooldown = 100
            world.enemies = [enemy]
            world.controls.press("combat_a")
            advance(world, 0.5, fps)
            outcomes.append((enemy.hp, world.player.state,
                             [(effect.x, effect.y, effect.frame) for effect in world.effects]))
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
