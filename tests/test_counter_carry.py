from math import hypot
import unittest
from unittest.mock import patch

import config
from counter import COUNTERS
from tests.helpers import advance, tap
from tests.test_counters import attacker, follow_up, hold_counter
from traffic import Car
from walkable import WalkableArea
from world import World


def holding_world(key="j", *, side=1):
    world = World()
    enemy = attacker(world, side)
    world.controls.press(f"counter_{key}")
    world.step(config.FIXED_DT)
    hold_counter(world)
    return world, enemy


# Carry geometry is checked with explicitly arranged opponents.
@patch.object(config, "ENEMIES_PER_STAGE", 0)
class CounterCarryTests(unittest.TestCase):
    def assert_pair(self, world, enemy):
        self.assertIsNotNone(world.counter)
        self.assertTrue(world.counter.holding)
        self.assertAlmostEqual(enemy.x - world.player.x,
                               world.counter.side * config.COUNTER_PAIR_DISTANCE)
        self.assertEqual(enemy.ground_y, world.player.ground_y)
        self.assertEqual(enemy.jump_height, config.COUNTER_CARRY_HEIGHT)
        for actor in (world.player, enemy):
            self.assertTrue(world.stage.walkable.contains(actor.x, actor.ground_y,
                                                         actor.boundary_padding))

    def test_all_four_hold_poses_can_carry_in_eight_normalized_directions(self):
        for key in "hjkl":
            for side in (-1, 1):
                for keys in (("left",), ("right",), ("up",), ("down",),
                             ("left", "up"), ("left", "down"),
                             ("right", "up"), ("right", "down")):
                    with self.subTest(key=key, side=side, keys=keys):
                        world, enemy = holding_world(key, side=side)
                        start = world.player.x, world.player.ground_y
                        frames = world.player.animation.frame, enemy.animation.frame
                        for action in keys:
                            world.controls.press(action)
                        advance(world, 0.15)
                        self.assert_pair(world, enemy)
                        self.assertAlmostEqual(hypot(world.player.vx, world.player.ground_vy),
                                               config.COUNTER_CARRY_SPEED)
                        self.assertNotEqual((world.player.x, world.player.ground_y), start)
                        self.assertEqual((world.player.facing, enemy.facing), (side, -side))
                        self.assertEqual((world.player.animation.frame, enemy.animation.frame), frames)
                        self.assertEqual(enemy.hp, 200)

    def test_both_feet_stay_inside_every_stage_corner_while_carrying(self):
        for index in range(len(config.STAGE_IMAGES)):
            for side in (-1, 1):
                for sx, sy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
                    with self.subTest(stage=index, side=side, corner=(sx, sy)):
                        world = World()
                        world.stage_index = index
                        world.stage.traffic = None
                        world.player.x = 300 if sx < 0 else config.WORLD_WIDTH - 300
                        enemy = attacker(world, side)
                        world.controls.press("counter_j")
                        world.step(config.FIXED_DT)
                        hold_counter(world)
                        world.controls.press("left" if sx < 0 else "right")
                        world.controls.press("down" if sy < 0 else "up")
                        for _ in range(360):
                            world.step(config.FIXED_DT)
                            self.assert_pair(world, enemy)
                        self.assertEqual(enemy.hp, 200)

    def test_pair_footprint_respects_a_slanted_convex_walkable_area(self):
        for side in (-1, 1):
            world = World()
            world.stage.walkable = WalkableArea(((300, 56), (1900, 56),
                                                 (2400, 148), (800, 148)))
            enemy = attacker(world, side)
            world.controls.press("counter_k")
            world.step(config.FIXED_DT)
            hold_counter(world)
            for key in ("right", "up"):
                world.controls.press(key)
            for _ in range(600):
                world.step(config.FIXED_DT)
                self.assert_pair(world, enemy)

    def test_carry_releases_direction_input_and_ignores_shift_jump_and_other_attacks(self):
        world, enemy = holding_world()
        for key in ("right", "left_shift", "jump", "combat_s", "combat_d", "combat_f", "counter_h"):
            world.controls.press(key)
        advance(world, 0.2)
        self.assert_pair(world, enemy)
        self.assertEqual(world.player.vx, config.COUNTER_CARRY_SPEED)
        self.assertEqual((world.player.jump_height, world.player.jump_count), (0, 0))
        self.assertIsNone(world.player.active_move)
        self.assertEqual(set(world.controls.pressed), {"right", "left_shift"})
        world.controls.release("right")
        advance(world, 0.1)
        self.assertEqual((world.player.vx, world.player.ground_vy), (0, 0))
        self.assert_pair(world, enemy)
        self.assertEqual(enemy.hp, 200)

    def test_an_early_or_held_a_press_never_buffers_the_follow_up(self):
        world = World()
        enemy = attacker(world)
        world.controls.press("counter_h")
        world.controls.press("combat_a")
        world.step(config.FIXED_DT)
        hold_counter(world)
        for _ in range(120):
            world.controls.press("combat_a")  # Simulate a held/repeated key.
            world.step(config.FIXED_DT)
        self.assert_pair(world, enemy)
        self.assertEqual(enemy.hp, 200)
        self.assertFalse(world.controls.pressed)
        tap(world.controls, "combat_a")
        world.step(config.FIXED_DT)
        self.assertFalse(world.counter.holding)
        self.assertEqual(world.counter.phase, "FOLLOW_UP")

    def test_fresh_a_wins_over_other_attacks_and_targets_only_the_carried_enemy(self):
        world, enemy = holding_world("h")
        other = attacker(world, gap=110)
        other.animation.set_state("HIT")
        for key in ("right", "combat_a", "combat_f"):
            world.controls.press(key)
        position = world.player.x, enemy.x
        for _ in range(70):
            world.step(config.FIXED_DT)
        self.assertEqual((world.player.x, enemy.x), position)
        self.assertEqual((enemy.hp, other.hp), (120, 200))
        self.assertIsNone(world.player.active_move)
        advance(world, 0.6)
        self.assertEqual(enemy.hp, 120)  # No queued A jab or repeated finishing damage.

    def test_follow_up_feedback_uses_the_position_after_carrying(self):
        for side in (-1, 1):
            world, enemy = holding_world("j", side=side)
            original = enemy.x
            world.controls.press("right")
            advance(world, 0.6)
            world.controls.release("right")
            follow_up(world)
            while enemy.hp == 200:
                world.step(config.FIXED_DT)
            self.assertGreater(enemy.x, original + 80)
            self.assertEqual([number.damage for number in world.damage_numbers], [80])
            self.assertEqual(world.effects[0].x, enemy.x)
            self.assertEqual(world.damage_numbers[0].x, enemy.x)
            self.assertEqual(world.player.vx, 0)

    def test_an_enemy_attack_interrupts_the_hold_and_releases_the_carried_enemy(self):
        for hp in (500, 20):
            world, enemy = holding_world("h")
            world.player.hp = hp
            attacker(world, -1, frame=4)
            world.step(config.FIXED_DT)
            self.assertIsNone(world.counter)
            self.assertIsNone(world.player.counter_move)
            self.assertIsNone(enemy.counter_move)
            self.assertFalse(enemy.counter_linked)
            self.assertEqual(enemy.jump_height, 0)
            self.assertEqual(world.player.hp, hp - 20)
            self.assertEqual(world.player.state, "HIT" if hp > 20 else "DYING")
            self.assertEqual(world.player.boundary_padding, config.PLAYER_BOUNDARY_PADDING)
            self.assertEqual(enemy.boundary_padding, config.ENEMY_BOUNDARY_PADDING)

    def test_direct_damage_or_removing_or_killing_the_target_cannot_leave_a_stuck_grip(self):
        for action in ("player_hit", "player_death", "remove_enemy", "kill_enemy"):
            world, enemy = holding_world()
            if action.startswith("player"):
                world.player.take_damage(20 if action == "player_hit" else 500)
            elif action == "remove_enemy":
                world.enemies.remove(enemy)
            else:
                enemy.take_damage(200)
            world.step(config.FIXED_DT)
            self.assertIsNone(world.counter)
            self.assertIsNone(world.player.counter_move)
            self.assertIsNone(enemy.counter_move)
            self.assertEqual(enemy.jump_height, 0)

    def test_p_invincibility_can_protect_the_hold_but_a_vehicle_still_kills_both(self):
        world, enemy = holding_world()
        world.player.invincible = True
        attacker(world, -1, frame=4)
        world.step(config.FIXED_DT)
        self.assert_pair(world, enemy)
        self.assertEqual(world.player.hp, 500)
        world.stage_index = 2
        # Keep the pair's floor consistent when setting up the road fixture.
        world.enemies = [enemy]
        world.player.ground_y = config.CAR_GROUND_Y
        world.counter.sync_pair()
        world.stage.traffic.car = Car(world.player.x, 1, 1400)
        world.step(config.FIXED_DT)
        self.assertIsNone(world.counter)
        self.assertEqual((world.player.hp, enemy.hp), (0, 0))
        self.assertEqual((world.player.state, enemy.state), ("CAR_HIT", "CAR_HIT"))
        self.assertIsNone(enemy.counter_move)

    def test_stage_travel_is_blocked_and_f5_clears_every_phase_of_the_grip(self):
        for phase in ("CAPTURE", "HOLD", "FOLLOW_UP"):
            world = World()
            enemy = attacker(world)
            world.controls.press("counter_h")
            world.step(config.FIXED_DT)
            if phase != "CAPTURE":
                hold_counter(world)
            if phase == "FOLLOW_UP":
                follow_up(world)
            world.stage.arrows_visible = True
            world.player.x = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN
            world.player.vx = 180
            self.assertFalse(world.try_stage_transition())
            player = world.player
            world.controls.press("restart")
            world.update(config.FIXED_DT)
            self.assertIsNone(world.counter)
            self.assertIsNone(player.counter_move)
            self.assertIsNone(enemy.counter_move)
            self.assertEqual(enemy.jump_height, 0)
            self.assertEqual((world.player.hp, world.player.state, world.stage_index), (500, "IDLE", 0))

    def test_holding_and_finishing_a_carried_enemy_are_render_fps_independent(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world = World()
            enemy = attacker(world)
            world.controls.press("counter_j")
            advance(world, 0.5, fps)
            world.controls.press("right")
            advance(world, 1, fps)
            self.assert_pair(world, enemy)
            held = (world.player.x, world.player.ground_y, enemy.x, enemy.animation.frame)
            world.controls.release("right")
            tap(world.controls, "combat_a")
            advance(world, 1.5, fps)
            outcomes.append((held, world.player.hp, enemy.hp, world.player.state,
                             enemy.state, enemy.animation.elapsed, world.counter))
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
