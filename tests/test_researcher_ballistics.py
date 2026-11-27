from math import sqrt
import unittest
from unittest.mock import PropertyMock, patch

import config
from player import Player
from projectiles import ResearcherBullet
from tests.helpers import advance, tap
from tests.test_researcher import encounter, until
from world import World


def straight_time():
    return config.RESEARCHER_BULLET_STRAIGHT_RANGE / config.RESEARCHER_BULLET_SPEED


def ground_time(height):
    return straight_time() + sqrt(2 * (height - config.RESEARCHER_BULLET_HALF_HEIGHT)
                                  / config.RESEARCHER_BULLET_GRAVITY)


def round_for(facing=1, height=config.RESEARCHER_MUZZLE_HEIGHT):
    return ResearcherBullet(300 if facing > 0 else config.WORLD_WIDTH - 300, 100, height, facing)


def missed_player():
    player = Player()
    player.floor = 1
    return player


class ResearcherBallisticsTests(unittest.TestCase):
    def test_former_expiry_distance_is_straight_then_falls_without_disappearing(self):
        self.assertEqual(config.RESEARCHER_BULLET_STRAIGHT_RANGE, 1125)
        for facing in (-1, 1):
            bullet, player = round_for(facing), missed_player()
            origin, height = bullet.x, bullet.height
            bullet.update((config.RESEARCHER_BULLET_STRAIGHT_RANGE - 0.5)
                          / config.RESEARCHER_BULLET_SPEED, player)
            self.assertFalse(bullet.falling)
            self.assertEqual((bullet.height, bullet.vy), (height, 0))
            bullet.update(0.5 / config.RESEARCHER_BULLET_SPEED, player)
            self.assertTrue(bullet.falling)
            self.assertFalse(bullet.finished)
            self.assertAlmostEqual(abs(bullet.x - origin), 1125)
            self.assertEqual((bullet.height, bullet.vy), (height, 0))
            bullet.update(0.1, player)
            self.assertFalse(bullet.finished)
            self.assertAlmostEqual(bullet.x, origin + facing * (1125 + 90))
            self.assertAlmostEqual(bullet.height, height - 4.5)
            self.assertAlmostEqual(bullet.vy, -90)
            self.assertEqual((bullet.floor, bullet.ground_y), (0, 100))

    def test_fall_is_an_accelerating_parabola_not_a_linear_downward_slide(self):
        for facing in (-1, 1):
            bullet, player = round_for(facing), missed_player()
            bullet.update(straight_time(), player)
            previous_height = bullet.height
            drops = []
            for step in range(1, 4):
                bullet.update(0.1, player)
                fall_time = step * 0.1
                self.assertAlmostEqual(bullet.height, config.RESEARCHER_MUZZLE_HEIGHT
                                       - config.RESEARCHER_BULLET_GRAVITY * fall_time ** 2 / 2)
                self.assertAlmostEqual(bullet.vy, -config.RESEARCHER_BULLET_GRAVITY * fall_time)
                drops.append(previous_height - bullet.height)
                previous_height = bullet.height
            self.assertTrue(drops[0] < drops[1] < drops[2])

    def test_one_large_update_splits_at_range_and_matches_many_small_updates(self):
        for facing in (-1, 1):
            single, split = round_for(facing), round_for(facing)
            player = missed_player()
            single.update(straight_time() + 0.2, player)
            for _ in range(174):
                split.update(config.FIXED_DT, player)
            for attribute in ("x", "height", "elapsed", "vy"):
                self.assertAlmostEqual(getattr(single, attribute), getattr(split, attribute))
            self.assertFalse(single.finished)
            self.assertFalse(split.finished)

    def test_ground_contact_removes_in_the_same_update_at_each_interior_depth(self):
        for index in (6, 7):
            for depth in config.STAGE_WALKABLE_BOUNDS[index][1::2]:
                for facing in (-1, 1):
                    for height in (config.RESEARCHER_MUZZLE_HEIGHT,
                                   config.RESEARCHER_MUZZLE_HEIGHT + 120):
                        with self.subTest(index=index, depth=depth, facing=facing, height=height):
                            world = World()
                            world.select_stage(index)
                            world.player.ground_y = world.player.previous_ground_y = (
                                world.stage.walkable.bounds[3] if depth == world.stage.walkable.bounds[1]
                                else world.stage.walkable.bounds[1])
                            bullet = round_for(facing, height)
                            bullet.ground_y = depth
                            origin = bullet.x
                            world.projectiles.append(bullet)
                            duration = ground_time(height)
                            world.update_projectiles(duration - 1e-6)
                            self.assertIn(bullet, world.projectiles)
                            self.assertGreater(bullet.height, config.RESEARCHER_BULLET_HALF_HEIGHT)
                            world.update_projectiles(1e-6)
                            self.assertNotIn(bullet, world.projectiles)
                            self.assertTrue(bullet.finished)
                            self.assertEqual(bullet.height, config.RESEARCHER_BULLET_HALF_HEIGHT)
                            self.assertAlmostEqual(bullet.elapsed, duration)
                            self.assertAlmostEqual(bullet.x, origin
                                                   + facing * config.RESEARCHER_BULLET_SPEED * duration)
                            self.assertEqual((world.player.hp, len(world.stage.drop_items)), (500, 15))
                            self.assertFalse(world.effects)
                            self.assertEqual(world.camera.shake_remaining, 0)
                            self.assertFalse(bullet.update(1, world.player))

    def test_a_large_update_stops_at_ground_and_cannot_hit_a_player_just_beyond_landing(self):
        for facing in (-1, 1):
            world = World()
            world.select_stage(6)
            bullet = round_for(facing)
            duration = ground_time(bullet.height)
            landing_x = bullet.x + facing * config.RESEARCHER_BULLET_SPEED * duration
            half_width = config.PLAYER_HALF_WIDTH + config.RESEARCHER_BULLET_HALF_WIDTH
            player = world.player
            player.x = player.previous_x = landing_x + facing * (half_width + 1)
            world.projectiles.append(bullet)
            world.update_projectiles(duration + 1)
            self.assertFalse(world.projectiles)
            self.assertAlmostEqual(bullet.x, landing_x)
            self.assertAlmostEqual(bullet.elapsed, duration)
            self.assertEqual((player.hp, player.state), (500, "IDLE"))
            self.assertFalse(world.effects)

    def test_falling_rounds_hit_at_the_actual_curve_height_and_only_once(self):
        for index in (6, 7):
            for facing in (-1, 1):
                world = World()
                world.select_stage(index)
                bullet = round_for(facing, height=300)
                player = world.player
                player.x = player.previous_x = (bullet.x + facing
                                                * (1125 + config.RESEARCHER_BULLET_SPEED * 0.6))
                world.projectiles.append(bullet)
                world.update_projectiles(straight_time() + 0.62)
                self.assertEqual((player.hp, player.state), (460, "IDLE"))
                self.assertFalse(world.projectiles)
                self.assertTrue(bullet.falling)
                self.assertTrue(bullet.spent)
                self.assertAlmostEqual(bullet.height,
                                       config.PLAYER_HEIGHT + config.RESEARCHER_BULLET_HALF_HEIGHT)
                self.assertEqual(len(world.effects), 1)
                self.assertEqual(world.effects[0].image_name, config.CLUB_HIT_IMAGE)
                self.assertAlmostEqual(world.effects[0].y, bullet.y)
                self.assertGreater(world.camera.shake_remaining, 0)
                self.assertFalse(bullet.update(1, player))
                self.assertEqual(player.hp, 460)

    def test_falling_rounds_keep_depth_floor_jump_stair_death_and_p_filters(self):
        for facing in (-1, 1):
            for situation in ("depth_edge", "deep", "jump", "floor", "stair", "dead", "invincible"):
                with self.subTest(facing=facing, situation=situation):
                    player = Player()
                    if situation == "jump":
                        player.jump_height = player.previous_jump_height = 200
                    elif situation == "floor":
                        player.floor = 1
                    elif situation == "stair":
                        player.staircase = object()
                    elif situation == "dead":
                        player.take_damage(500)
                    elif situation == "invincible":
                        player.invincible = True
                    depth = 32 if situation == "depth_edge" else 32.01 if situation == "deep" else 0
                    bullet = ResearcherBullet(player.x - facing * 100, player.ground_y + depth,
                                              100, facing, elapsed=straight_time())
                    self.assertEqual(bullet.update(0.2, player), situation == "depth_edge")
                    self.assertEqual(player.hp, 460 if situation == "depth_edge"
                                     else 0 if situation == "dead" else 500)
                    self.assertEqual(bullet.spent, situation in ("depth_edge", "invincible"))

    def test_quadratic_sweep_rejects_a_false_hit_on_the_straight_endpoint_chord(self):
        for facing in (-1, 1):
            player = Player()
            player.jump_height = player.previous_jump_height = 220
            bullet = ResearcherBullet(player.x - facing * 180, 100, 400, facing,
                                      elapsed=straight_time())
            # At t=.2 the chord is y=364, but the real parabola is y=382.
            # The arc stays above the player's top throughout the x-overlap.
            self.assertFalse(bullet.update(0.4, player))
            self.assertEqual(player.hp, 500)

    def test_quadratic_sweep_catches_a_real_arc_hit_that_the_endpoint_chord_misses(self):
        for facing in (-1, 1):
            player = Player()
            player.jump_height = player.previous_jump_height = 375
            bullet = ResearcherBullet(player.x - facing * 180, 100, 400, facing,
                                      elapsed=straight_time())
            self.assertTrue(bullet.update(0.4, player))
            self.assertEqual(player.hp, 460)
            self.assertGreater(bullet.height, 375)

    def test_range_split_keeps_one_shared_clock_for_the_players_depth_sweep(self):
        for toward in (False, True):
            player = Player()
            player.x = player.previous_x = 1600
            player.previous_ground_y, player.ground_y = (300, 100) if toward else (100, 300)
            bullet = ResearcherBullet(300, 100, 83.25, 1)
            self.assertEqual(bullet.update(1.5, player), toward)
            self.assertEqual(player.hp, 460 if toward else 500)

    def test_zero_or_negative_time_never_advances_fall_or_sweeps_a_prebirth_position(self):
        player = Player()
        player.previous_x = player.x - 200
        bullet = ResearcherBullet(player.previous_x, 100, 60, 1, elapsed=straight_time() + 0.2)
        snapshot = bullet.x, bullet.height, bullet.elapsed, bullet.vy
        for dt in (0, -0.2):
            self.assertFalse(bullet.update(dt, player))
            self.assertEqual((bullet.x, bullet.height, bullet.elapsed, bullet.vy), snapshot)
            self.assertEqual(player.hp, 500)

    def test_fall_uses_common_slow_and_fast_game_time(self):
        for index in (6, 7):
            for scale in (0.2, 1, 2):
                world = World()
                world.select_stage(index)
                bullet = ResearcherBullet(600, world.stage.walkable.bounds[3], 78.75, 1,
                                          elapsed=straight_time() + 0.1)
                world.projectiles.append(bullet)
                duration = 0.05 * scale
                height, vy = bullet.height, bullet.vy
                with patch.object(Player, "time_scale", new_callable=PropertyMock, return_value=scale):
                    advance(world, 0.05)
                self.assertAlmostEqual(bullet.x, 600 + config.RESEARCHER_BULLET_SPEED * duration)
                self.assertAlmostEqual(bullet.height, height + vy * duration
                                       - config.RESEARCHER_BULLET_GRAVITY * duration ** 2 / 2)
                self.assertAlmostEqual(bullet.vy, vy - config.RESEARCHER_BULLET_GRAVITY * duration)
                self.assertAlmostEqual(bullet.elapsed, straight_time() + 0.1 + duration)

    def test_inactive_stage_and_loading_freeze_the_full_fall_and_f5_clears_it(self):
        for index in (6, 7):
            world = World()
            world.select_stage(index)
            bullet = ResearcherBullet(600, 100, 78.75, 1, elapsed=straight_time() + 0.1)
            world.projectiles.append(bullet)
            snapshot = bullet.x, bullet.height, bullet.elapsed, bullet.vy
            world.select_stage(5)
            advance(world, 1)
            world.select_stage(index)
            self.assertIs(world.projectiles[0], bullet)
            self.assertEqual((bullet.x, bullet.height, bullet.elapsed, bullet.vy), snapshot)
            world.pending_stage_index, world.stage_loading_remaining = 5, 2
            world.update(1.999)
            self.assertEqual((bullet.x, bullet.height, bullet.elapsed, bullet.vy), snapshot)
            world.update(0.001)
            world.select_stage(index)
            world.step(config.FIXED_DT)
            self.assertLess(bullet.height, snapshot[1])
            self.assertLess(bullet.vy, snapshot[3])
            tap(world.controls, "restart")
            world.update(config.FIXED_DT)
            self.assertTrue(all(not stage.projectiles for stage in world.stages))

    def test_real_emitted_round_survives_shooter_death_then_falls_to_the_same_floor(self):
        for index in (6, 7):
            for side in (-1, 1):
                world, enemy = encounter(side, index=index)
                until(world, lambda: bool(world.projectiles))
                bullet = world.projectiles[0]
                height, origin = bullet.height, bullet.x
                enemy.take_damage(enemy.hp)
                player = world.player
                player.ground_y = player.previous_ground_y = world.stage.walkable.bounds[1]
                advance(world, 1.3)
                self.assertIn(bullet, world.projectiles)
                self.assertTrue(bullet.falling)
                self.assertLess(bullet.height, height)
                until(world, lambda: not world.projectiles)
                self.assertAlmostEqual(bullet.elapsed, ground_time(height))
                self.assertAlmostEqual(bullet.x, origin + bullet.facing
                                       * config.RESEARCHER_BULLET_SPEED * ground_time(height))
                self.assertEqual(player.hp, 500)
                self.assertFalse(world.effects)

    def test_world_edge_still_cleans_up_falling_rounds_without_ground_effects(self):
        for facing in (-1, 1):
            bullet = ResearcherBullet(10 if facing < 0 else config.WORLD_WIDTH - 10,
                                      100, 70, facing, elapsed=straight_time() + 0.1)
            self.assertFalse(bullet.update(1, missed_player()))
            self.assertTrue(bullet.finished)
            self.assertGreater(bullet.height, config.RESEARCHER_BULLET_HALF_HEIGHT)
            self.assertAlmostEqual(bullet.x, -5 if facing < 0 else config.WORLD_WIDTH + 5)

    def test_direct_ballistics_and_exact_landing_are_render_rate_independent(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            bullet, player = round_for(), missed_player()
            for _ in range(round(1.5 * fps)):
                bullet.update(1 / fps, player)
            self.assertFalse(bullet.finished)
            snapshot = bullet.x, bullet.height, bullet.elapsed, bullet.vy
            for _ in range(fps):
                bullet.update(1 / fps, player)
            self.assertTrue(bullet.finished)
            outcomes.append((*snapshot, bullet.x, bullet.height, bullet.elapsed))
        for outcome in outcomes[1:]:
            for expected, actual in zip(outcomes[0], outcome):
                self.assertAlmostEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
