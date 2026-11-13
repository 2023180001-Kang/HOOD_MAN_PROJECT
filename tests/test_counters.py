import unittest

import config
from combat import MOVES
from counter import COUNTERS
from enemy import Enemy
from tests.helpers import advance, tap
from walkable import WalkableArea
from world import World


def attacker(world, side=1, gap=80, depth=0, frame=2, attack_speed=1.0):
    enemy = Enemy(world.player.x + side * gap, -side,
                  ground_y=world.player.ground_y + depth, attack_speed=attack_speed)
    enemy.animation.set_state("ATTACK")
    enemy.animation.elapsed = (frame + 0.05) / enemy.attack_fps
    enemy.cooldown = enemy.attack_interval
    world.enemies.append(enemy)
    return enemy


class CounterTests(unittest.TestCase):
    def begin(self, key="h", *, side=1, hp=200):
        world = World()
        enemy = attacker(world, side)
        enemy.hp = hp
        world.controls.press(f"counter_{key}")
        world.step(config.FIXED_DT)
        self.assertIsNotNone(world.counter)
        return world, enemy

    def finish(self, world):
        while world.counter is not None:
            world.step(config.FIXED_DT)

    def test_all_four_keys_use_matching_rows_and_one_shared_animation_clock(self):
        for key, row in zip("hjkl", (1, 2, 3, 4)):
            for side in (-1, 1):
                with self.subTest(key=key, side=side):
                    world, enemy = self.begin(key, side=side)
                    move = COUNTERS[f"counter_{key}"]
                    self.assertEqual((world.player.sprite_image, enemy.sprite_image),
                                     (config.COUNTER_PLAYER_IMAGE, config.COUNTER_ENEMY_IMAGE))
                    frames = set()
                    while world.counter is not None:
                        self.assertEqual((world.player.animation.row, enemy.animation.row), (row, row))
                        self.assertEqual(world.player.animation.frame, enemy.animation.frame)
                        self.assertEqual(world.player.animation.elapsed, enemy.animation.elapsed)
                        self.assertEqual((world.player.facing, enemy.facing), (side, -side))
                        frames.add(enemy.animation.frame)
                        expected_hp = 120 if world.counter.damage_applied else 200
                        self.assertEqual(enemy.hp, expected_hp)
                        self.assertEqual(world.player.hp, 500)
                        world.step(config.FIXED_DT)
                    self.assertEqual(frames, set(range(8)))
                    self.assertEqual(enemy.hp, 200 - move.damage)
                    self.assertEqual((world.player.state, enemy.state), ("IDLE", "IDLE"))

    def test_each_counter_deals_eighty_once_at_its_strike_frame_with_feedback(self):
        for key in "hjkl":
            with self.subTest(key=key):
                world, enemy = self.begin(key)
                sequence = world.counter
                impact_time = sequence.move.impact_frame / sequence.move.fps
                while sequence.elapsed + config.FIXED_DT < impact_time - 1e-9:
                    world.step(config.FIXED_DT)
                    self.assertEqual(enemy.hp, 200)
                    self.assertEqual(world.damage_numbers, [])
                world.step(config.FIXED_DT)
                self.assertEqual(enemy.hp, 120)
                self.assertEqual([number.damage for number in world.damage_numbers], [80])
                self.assertEqual(len(world.effects), 1)
                effect = world.effects[0]
                self.assertGreater(world.camera.shake_remaining, 0)
                self.finish(world)
                advance(world, 0.1)
                self.assertEqual(enemy.hp, 120)
                self.assertTrue(all(current is effect for current in world.effects))

    def test_counter_precedes_same_tick_pipe_damage(self):
        for key in "hjkl":
            with self.subTest(key=key):
                world = World()
                enemy = attacker(world, frame=4)
                world.controls.press(f"counter_{key}")
                world.step(config.FIXED_DT)
                self.assertIs(world.counter.enemy, enemy)
                self.assertEqual(world.player.hp, 500)
                self.assertTrue(enemy.has_hit)
        control = World()
        attacker(control, frame=4)
        control.step(config.FIXED_DT)
        self.assertEqual(control.player.hp, 480)

    def test_range_and_depth_edges_are_inclusive_and_outside_presses_are_consumed(self):
        for gap, depth, succeeds in ((140, 0, True), (140.001, 0, False),
                                      (80, 32, True), (80, -32, True),
                                      (80, 32.001, False), (80, -32.001, False)):
            with self.subTest(gap=gap, depth=depth):
                world = World()
                attacker(world, gap=gap, depth=depth)
                world.controls.press("counter_h")
                world.step(config.FIXED_DT)
                self.assertEqual(world.counter is not None, succeeds)
                self.assertNotIn("counter_h", world.controls.pressed)

    def test_only_an_unspent_pipe_swing_in_frames_one_through_five_is_counterable(self):
        for frame in range(8):
            with self.subTest(frame=frame):
                world = World()
                attacker(world, frame=frame)
                world.controls.press("counter_j")
                world.step(config.FIXED_DT)
                self.assertEqual(world.counter is not None, frame in (1, 2, 3, 4, 5))
        for condition in ("idle", "hit", "spent", "facing_away", "dead", "knockback"):
            with self.subTest(condition=condition):
                world = World()
                enemy = attacker(world)
                if condition in ("idle", "hit"):
                    enemy.animation.set_state(condition.upper())
                elif condition == "spent":
                    enemy.has_hit = True
                elif condition == "facing_away":
                    enemy.facing = 1
                elif condition == "dead":
                    enemy.take_damage(200)
                else:
                    enemy.knockback(world.player.x)
                world.controls.press("counter_j")
                world.step(config.FIXED_DT)
                self.assertIsNone(world.counter)

    def test_airborne_hit_dying_and_dead_players_cannot_start_or_buffer_a_counter(self):
        for state in ("JUMP", "HIT", "DYING", "DEAD"):
            with self.subTest(state=state):
                world = World()
                attacker(world)
                world.player.animation.set_state(state)
                if state == "JUMP":
                    world.player.jump_height, world.player.vy = 100, 200
                elif state in ("DYING", "DEAD"):
                    world.player.hp = 0
                world.controls.press("counter_k")
                world.step(config.FIXED_DT)
                self.assertIsNone(world.counter)
                self.assertNotIn("counter_k", world.controls.pressed)

    def test_nearest_eligible_attacker_is_selected_and_player_turns_toward_it(self):
        world = World()
        idle = Enemy(world.player.x + 65, -1)
        world.enemies.append(idle)
        far = attacker(world, 1, gap=120)
        near = attacker(world, -1, gap=90)
        world.controls.press("counter_l")
        world.step(config.FIXED_DT)
        self.assertIs(world.counter.enemy, near)
        self.assertEqual(world.player.facing, -1)
        self.assertIsNone(far.counter_move)
        self.assertIsNone(idle.counter_move)
        self.finish(world)
        self.assertEqual((idle.hp, far.hp, near.hp), (200, 200, 120))

    def test_latest_fresh_counter_key_wins_without_changing_an_active_counter(self):
        world = World()
        attacker(world)
        for key in ("h", "j", "k", "l"):
            world.controls.press(f"counter_{key}")
        world.step(config.FIXED_DT)
        sequence = world.counter
        self.assertEqual(sequence.move.key, "l")
        tap(world.controls, "counter_h")
        world.controls.press("combat_f")
        world.controls.press("jump")
        world.step(config.FIXED_DT)
        self.assertIs(world.counter, sequence)
        self.assertGreater(sequence.elapsed, config.FIXED_DT)
        self.assertEqual(world.player.jump_count, 0)
        self.assertIsNone(world.player.active_move)
        self.assertFalse(world.controls.pressed)
        self.finish(world)
        advance(world, 0.1)
        self.assertEqual(world.player.state, "IDLE")

    def test_holding_or_pressing_without_a_target_does_not_automatically_counter_later(self):
        world = World()
        world.controls.press("counter_h")
        world.step(config.FIXED_DT)
        enemy = attacker(world)
        world.controls.press("counter_h")
        world.step(config.FIXED_DT)
        self.assertIsNone(world.counter)
        tap(world.controls, "counter_h")
        world.step(config.FIXED_DT)
        self.assertIs(world.counter.enemy, enemy)
        self.finish(world)
        enemy.animation.set_state("ATTACK")
        enemy.animation.elapsed = 2 / enemy.attack_fps
        enemy.has_hit = False
        world.step(config.FIXED_DT)
        self.assertIsNone(world.counter)

    def test_a_successful_counter_cancels_a_basic_attack_before_it_can_deal_damage(self):
        world = World()
        enemy = attacker(world)
        world.player.start_move(MOVES["combat_f"], 1)
        world.player.animation.elapsed = 3 / MOVES["combat_f"].fps
        world.controls.press("counter_h")
        world.step(config.FIXED_DT)
        self.assertIsNone(world.player.active_move)
        self.assertEqual(enemy.hp, 200)
        self.finish(world)
        self.assertEqual(enemy.hp, 120)

    def test_survivor_returns_to_idle_then_resumes_its_original_chase_profile(self):
        world = World()
        enemy = attacker(world, attack_speed=1.25)
        original = (enemy.attack_speed, enemy.attack_fps, enemy.attack_interval, enemy.run_speed)
        world.controls.press("counter_j")
        world.step(config.FIXED_DT)
        self.finish(world)
        self.assertEqual((enemy.state, enemy.hp), ("IDLE", 120))
        self.assertEqual(enemy.sprite_image, config.ENEMY_IMAGE)
        self.assertEqual(enemy.boundary_padding, config.ENEMY_BOUNDARY_PADDING)
        world.player.x += 500
        world.step(config.FIXED_DT)
        self.assertEqual(enemy.state, "RUN")
        self.assertGreater(enemy.vx, 0)
        self.assertEqual((enemy.attack_speed, enemy.attack_fps, enemy.attack_interval,
                          enemy.run_speed), original)

    def test_lethal_counter_finishes_the_reaction_then_keeps_its_last_pose_dead(self):
        for key in "hjkl":
            with self.subTest(key=key):
                world, enemy = self.begin(key, hp=40)
                while enemy.hp:
                    world.step(config.FIXED_DT)
                self.assertIsNotNone(world.counter)
                self.assertEqual(enemy.state, COUNTERS[f"counter_{key}"].enemy_state)
                self.assertEqual([number.damage for number in world.damage_numbers], [40])
                self.finish(world)
                self.assertEqual(enemy.state, "DEAD")
                self.assertEqual(enemy.sprite_image, config.COUNTER_ENEMY_IMAGE)
                pose = (enemy.animation.row, enemy.animation.frame, enemy.x, enemy.y)
                self.assertEqual(pose[:2], (COUNTERS[f"counter_{key}"].row, 7))
                advance(world, 1)
                self.assertEqual((enemy.animation.row, enemy.animation.frame, enemy.x, enemy.y), pose)
                self.assertIsNone(enemy.attack_box)
                self.assertEqual(config.ENEMY_ANIMATIONS["DEAD"][0], 6)

    def test_three_counters_deal_eighty_each_without_resurrecting_a_defeated_enemy(self):
        world = World()
        enemy = attacker(world)
        for key, hp in zip("hjk", (120, 40, 0)):
            enemy.animation.set_state("ATTACK")
            enemy.animation.elapsed = 2 / enemy.attack_fps
            enemy.has_hit = False
            tap(world.controls, f"counter_{key}")
            world.step(config.FIXED_DT)
            self.finish(world)
            self.assertEqual(enemy.hp, hp)
        tap(world.controls, "counter_l")
        world.step(config.FIXED_DT)
        self.assertIsNone(world.counter)
        self.assertEqual(enemy.state, "DEAD")

    def test_counter_protection_is_temporary_and_other_attacks_are_consumed(self):
        world, target = self.begin()
        other = attacker(world, -1, frame=4)
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 500)
        self.assertFalse(world.player.invincible)
        self.assertTrue(other.has_hit)
        self.finish(world)
        attacker(world, -1, frame=4)
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 480)
        self.assertEqual(world.player.state, "HIT")
        self.assertEqual(target.hp, 120)

    def test_pair_stays_fixed_and_in_bounds_during_crowded_corner_counters_on_every_map(self):
        for index in range(len(config.STAGE_IMAGES)):
            for side in (-1, 1):
                for at_top in (False, True):
                    with self.subTest(stage=index, side=side, at_top=at_top):
                        world = World()
                        world.stage_index = index
                        _, bottom, _, top = world.stage.walkable.bounds
                        world.player.x = (config.PLAYER_BOUNDARY_PADDING if side > 0 else
                                          config.WORLD_WIDTH - config.PLAYER_BOUNDARY_PADDING)
                        world.player.ground_y = top if at_top else bottom
                        enemy = attacker(world, side)
                        for _ in range(5):
                            attacker(world, side, gap=100, frame=4)
                        world.controls.press("counter_l")
                        world.step(config.FIXED_DT)
                        self.assertIs(world.counter.enemy, enemy)
                        fixed = (world.player.x, world.player.ground_y, enemy.x, enemy.ground_y)
                        while world.counter is not None:
                            world.step(config.FIXED_DT)
                            self.assertEqual((world.player.x, world.player.ground_y,
                                              enemy.x, enemy.ground_y), fixed)
                            for actor in (world.player, *world.enemies):
                                self.assertTrue(world.stage.walkable.contains(
                                    actor.x, actor.ground_y, actor.boundary_padding))
                        self.assertEqual(world.player.hp, 500)
                        self.assertEqual(world.player.boundary_padding, config.PLAYER_BOUNDARY_PADDING)

    def test_counter_is_rejected_if_the_pair_cannot_fit_inside_a_narrow_floor(self):
        world = World()
        world.stage.walkable = WalkableArea.rectangle(100, 56, 310, 148)
        world.player.x = 200
        enemy = attacker(world, gap=10)
        world.controls.press("counter_h")
        world.step(config.FIXED_DT)
        self.assertIsNone(world.counter)
        self.assertIsNone(enemy.counter_move)
        self.assertEqual(world.player.boundary_padding, config.PLAYER_BOUNDARY_PADDING)

    def test_f5_releases_the_pair_and_clears_the_counter_before_and_after_damage(self):
        for seconds in (0.05, 0.5):
            with self.subTest(seconds=seconds):
                world, enemy = self.begin()
                player = world.player
                advance(world, seconds)
                world.controls.press("restart")
                world.update(config.FIXED_DT)
                self.assertIsNone(world.counter)
                self.assertIsNone(player.counter_move)
                self.assertIsNone(enemy.counter_move)
                self.assertEqual(world.player.hp, 500)
                self.assertEqual(world.stage_index, 0)
                self.assertTrue(all(not stage.enemies for stage in world.stages))

    def test_counter_blocks_stage_travel_and_cancels_cleanly_if_target_is_removed(self):
        world, enemy = self.begin()
        world.stage.arrows_visible = True
        world.player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
        self.assertFalse(world.try_stage_transition())
        world.enemies.clear()
        world.controls.held.clear()
        world.step(config.FIXED_DT)
        self.assertIsNone(world.counter)
        self.assertIsNone(world.player.counter_move)
        self.assertIsNone(enemy.counter_move)
        self.assertEqual(world.player.state, "IDLE")

    def test_counter_outcomes_are_identical_at_different_render_frame_rates(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world = World()
            enemy = attacker(world, attack_speed=1.4)
            world.controls.press("counter_k")
            advance(world, 1, fps)
            outcomes.append((world.player.hp, enemy.hp, world.player.state, enemy.state,
                             enemy.animation.elapsed, enemy.cooldown, world.counter))
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
