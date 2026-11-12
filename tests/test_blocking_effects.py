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
    world.controls.press("combat_h")
    world.player.start_move(MOVES["combat_h"], facing)
    world.player.animation.elapsed = frame / config.BLOCK_FPS


class BlockingEffectTests(unittest.TestCase):
    def test_frontal_block_prevents_damage_and_consumes_the_enemy_swing(self):
        for facing in (-1, 1):
            with self.subTest(facing=facing):
                world = World()
                guard(world, facing=facing)
                enemy = striker(world, facing)
                elapsed = world.player.animation.elapsed
                self.assertFalse(enemy.try_hit(world.player))
                self.assertTrue(enemy.has_hit)
                self.assertEqual(world.player.hp, 500)
                self.assertEqual(world.player.state, "BLOCK")
                self.assertEqual(world.player.animation.elapsed, elapsed)
                self.assertFalse(enemy.try_hit(world.player))
                self.assertEqual(world.player.hp, 500)

    def test_rear_attacks_deal_full_damage_and_cancel_block(self):
        for facing in (-1, 1):
            with self.subTest(facing=facing):
                world = World()
                guard(world, facing=facing)
                self.assertFalse(striker(world, facing).try_hit(world.player))
                self.assertTrue(striker(world, -facing).try_hit(world.player))
                self.assertEqual(world.player.hp, 480)
                self.assertEqual(world.player.state, "HIT")
                self.assertIsNone(world.player.active_move)
                self.assertEqual(world.player.vx, 0)

    def test_blocked_hit_recoils_backwards_then_stops_with_guard_and_direction_held(self):
        for facing in (-1, 1):
            with self.subTest(facing=facing):
                world = World()
                guard(world, facing=facing)
                enemy = striker(world, facing)
                world.step(config.FIXED_DT)
                start = world.player.x
                advance(world, 0.05)
                self.assertGreater((start - world.player.x) * facing, 0)
                speed = world.player.vx
                self.assertFalse(enemy.try_hit(world.player))
                self.assertEqual(world.player.vx, speed)
                advance(world, 0.2)
                distance = (start - world.player.x) * facing
                self.assertGreater(distance, 10)
                self.assertLess(distance, 30)
                self.assertEqual(world.player.vx, 0)
                self.assertEqual(world.player.hp, 500)
                self.assertEqual(world.player.state, "BLOCK")
                self.assertEqual(world.player.facing, facing)
                self.assertIn("combat_h", world.controls.held)
                self.assertEqual(world.player.animation.frame, config.BLOCK_HOLD_FRAME)
                self.assertEqual(world.effects, [])
                self.assertEqual(world.camera.shake_remaining, 0)
                striker(world, facing)
                world.step(config.FIXED_DT)
                advance(world, 0.2)
                self.assertGreater((start - world.player.x) * facing, distance + 10)
                self.assertEqual(world.player.hp, 500)
                self.assertEqual(world.player.state, "BLOCK")

    def test_simultaneous_blocks_do_not_stack_recoil_and_render_rates_match(self):
        distances = []
        for fps in (30, 60, 120, 144):
            for count in (1, 4):
                with self.subTest(fps=fps, count=count):
                    world = World()
                    guard(world)
                    for _ in range(count):
                        striker(world)
                    world.step(config.FIXED_DT)
                    advance(world, 0.5, fps)
                    distances.append(config.START_X - world.player.x)
                    self.assertEqual(world.player.hp, 500)
                    self.assertEqual(world.player.state, "BLOCK")
                    self.assertEqual(world.player.vx, 0)
                    self.assertTrue(all(enemy.has_hit for enemy in world.enemies))
        self.assertTrue(all(distance == distances[0] for distance in distances))
        self.assertGreater(distances[0], 10)
        self.assertLess(distances[0], 30)

    def test_guard_recoil_stops_at_map_edges_and_rear_bodies(self):
        for facing in (-1, 1):
            for at_edge in (False, True):
                with self.subTest(facing=facing, at_edge=at_edge):
                    world = World()
                    if at_edge:
                        world.player.x = (config.PLAYER_HALF_WIDTH if facing > 0 else
                                          config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)
                    else:
                        rear = Enemy(world.player.x - facing * 66, facing)
                        rear.cooldown = 100
                        world.enemies.append(rear)
                    start = world.player.x
                    guard(world, facing=facing)
                    striker(world, facing)
                    world.step(config.FIXED_DT)
                    advance(world, 0.2)
                    self.assertGreaterEqual(world.player.x, config.PLAYER_HALF_WIDTH)
                    self.assertLessEqual(world.player.x,
                                         config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)
                    self.assertLessEqual(abs(world.player.x - start), 0 if at_edge else 5)
                    self.assertEqual(world.player.vx, 0)
                    self.assertEqual(world.player.hp, 500)
                    self.assertEqual(world.player.state, "BLOCK")
                    self.assertTrue(all(not world.player.body.overlaps(enemy.body)
                                        for enemy in world.enemies))

    def test_guard_protects_immediately_and_after_long_holds(self):
        for duration in (0, 0.1, 0.5, 3):
            world = World()
            world.controls.press("combat_h")
            world.step(config.FIXED_DT)
            advance(world, duration)
            enemy = striker(world)
            world.step(config.FIXED_DT)
            self.assertEqual(world.player.hp, 500)
            self.assertTrue(enemy.has_hit)
            self.assertEqual(world.effects, [])
            self.assertEqual(world.camera.shake_remaining, 0)

    def test_all_front_enemies_are_blocked_including_their_next_attacks(self):
        world = World()
        guard(world)
        for _ in range(4):
            striker(world)
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 500)
        self.assertEqual(world.player.state, "BLOCK")
        self.assertTrue(all(enemy.has_hit for enemy in world.enemies))
        advance(world, 3)
        self.assertEqual(world.player.hp, 500)
        self.assertEqual(world.effects, [])
        self.assertEqual(world.player.animation.frame, config.BLOCK_HOLD_FRAME)

    def test_releasing_h_ends_protection_and_a_new_press_restores_it(self):
        world = World()
        world.controls.press("combat_h")
        advance(world, 0.5)
        striker(world)
        world.step(config.FIXED_DT)
        advance(world, 0.05)
        world.controls.release("combat_h")
        position = world.player.x
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.x, position)
        self.assertEqual(world.player.vx, 0)
        striker(world)
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 480)
        self.assertEqual(world.player.state, "HIT")
        world.enemies.clear()
        advance(world, 1)
        world.controls.press("combat_h")
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.state, "BLOCK")

    def test_rear_lethal_damage_enters_death_and_cancels_guard(self):
        world = World()
        world.player.hp = 10
        guard(world)
        enemy = striker(world, -1)
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 0)
        self.assertEqual(world.player.state, "DYING")
        self.assertEqual(world.player.sprite_image, config.PLAYER_IMAGE)
        self.assertIsNone(world.player.active_move)
        self.assertTrue(enemy.knockback_started)
        self.assertEqual(len(world.effects), 1)

    def test_guard_direction_is_locked_and_held_h_resumes_after_rear_hit(self):
        world = World()
        world.controls.press("left")
        world.controls.press("combat_h")
        world.step(config.FIXED_DT)
        world.controls.release("left")
        world.controls.press("right")
        advance(world, 1)
        self.assertEqual(world.player.facing, -1)
        striker(world, -1)
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 500)
        striker(world, 1)
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 480)
        self.assertEqual(world.player.state, "HIT")
        world.enemies.clear()
        advance(world, 0.8)
        self.assertEqual(world.player.state, "BLOCK")
        self.assertEqual(world.player.facing, 1)

    def test_player_hits_spawn_at_contact_and_effects_follow_world_coordinates(self):
        for facing in (-1, 1):
            world = World()
            enemy = Enemy(config.START_X + facing * 80, -facing)
            enemy.cooldown = 100
            world.enemies = [enemy]
            world.controls.press("left" if facing < 0 else "right")
            world.controls.press("combat_q")
            advance(world, 0.3)
            self.assertEqual(enemy.hp, 180)
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
        world.player.start_move(MOVES["combat_q"], 1)
        world.player.animation.elapsed = 3 / config.COMBAT_FPS
        world.step(config.FIXED_DT)
        self.assertEqual((victim.hp, world.player.hp), (180, 480))
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
            world.controls.press("combat_q")
            advance(world, 0.3)
            self.assertEqual(world.effects, [])
            self.assertEqual(world.camera.shake_remaining, 0)

    def test_only_new_player_hits_restart_shake_and_it_expires(self):
        world = World()
        enemy = Enemy(config.START_X + 80, -1)
        enemy.cooldown = 100
        world.enemies = [enemy]
        world.controls.press("combat_q")
        advance(world, 0.175)
        remaining = world.camera.shake_remaining
        self.assertGreater(remaining, 0)
        advance(world, 0.05)
        self.assertLess(world.camera.shake_remaining, remaining)
        self.assertEqual(enemy.hp, 180)
        advance(world, 0.2)
        self.assertEqual(world.camera.shake_remaining, 0)
        self.assertEqual((world.camera.offset_x, world.camera.offset_y), (0, 0))

    def test_restart_clears_live_effects_and_guard(self):
        world = World()
        guard(world)
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
            world.controls.press("combat_q")
            advance(world, 0.5, fps)
            outcomes.append((enemy.hp, world.player.state,
                             [(effect.x, effect.y, effect.frame) for effect in world.effects]))
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
