import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import config
from assets import Assets
from player import Player
from projectiles import ResearcherBullet, RifleBullet
from tests.helpers import advance
from world import World


def stationary_player(x=1280, *, height=0, depth=100):
    player = Player()
    player.x = player.previous_x = x
    player.ground_y = player.previous_ground_y = depth
    player.jump_height = player.previous_jump_height = height
    return player


class RifleBulletTests(unittest.TestCase):
    def test_rifle_profile_does_not_change_the_researcher_profile(self):
        rifle, pistol = RifleBullet(100, 100, 81, 1), ResearcherBullet(100, 100, 81, 1)
        self.assertEqual((rifle.damage, rifle.speed, rifle.half_width, rifle.half_height), (5, 1200, 7.5, 2.5))
        self.assertEqual((pistol.damage, pistol.speed, pistol.half_width, pistol.half_height), (30, 900, 5, 2.5))
        self.assertEqual((rifle.scale, pistol.scale), (0.0625, 0.125))

    def test_level_flight_expires_at_exactly_1200_pixels_even_with_a_large_update(self):
        player = stationary_player(height=500)
        for facing, x in ((1, 100), (-1, 2400)):
            for dt in (1, 3):
                with self.subTest(facing=facing, dt=dt):
                    bullet = RifleBullet(x, 100, 81, facing)
                    self.assertFalse(bullet.update(dt, player))
                    self.assertEqual((bullet.x, bullet.height, bullet.elapsed, bullet.vy),
                                     (x + facing * 1200, 81, 1, 0))
                    self.assertTrue(bullet.finished)
                    self.assertFalse(bullet.falling)
                    snapshot = bullet.x, bullet.height
                    bullet.update(2, player)
                    self.assertEqual((bullet.x, bullet.height), snapshot)

    def test_swept_round_hits_once_for_five_in_both_facings(self):
        for facing in (-1, 1):
            player = stationary_player()
            bullet = RifleBullet(player.x - facing * 300, 100, 81, facing)
            self.assertTrue(bullet.update(0.5, player))
            self.assertEqual((player.hp, player.state), (495, "IDLE"))
            self.assertTrue(bullet.spent)
            self.assertFalse(bullet.update(1, player))
            self.assertEqual(player.hp, 495)

    def test_p_invincibility_consumes_the_round_without_damage_and_multiple_rounds_are_independent(self):
        player = stationary_player()
        player.invincible = True
        bullet = RifleBullet(player.x - 100, 100, 81, 1)
        self.assertFalse(bullet.update(0.2, player))
        self.assertTrue(bullet.finished)
        self.assertEqual(player.hp, 500)
        player.invincible = False
        for _ in range(2):
            bullet = RifleBullet(player.x - 100, 100, 81, 1)
            self.assertTrue(bullet.update(0.2, player))
        self.assertEqual(player.hp, 490)

    def test_depth_height_floor_and_dead_player_reject_contact(self):
        for reason in ("depth", "jump", "floor", "dead"):
            with self.subTest(reason=reason):
                player = stationary_player(height=200 if reason == "jump" else 0)
                if reason == "dead":
                    player.take_damage(500)
                bullet = RifleBullet(player.x - 100, 132.01 if reason == "depth" else 100,
                                     81, 1, floor=1 if reason == "floor" else 0)
                hp = player.hp
                self.assertFalse(bullet.update(0.2, player))
                self.assertEqual(player.hp, hp)
                self.assertFalse(bullet.spent)

    def test_fast_crossing_requires_simultaneous_x_and_depth_contact(self):
        player = stationary_player(x=500, depth=0)
        player.previous_ground_y, player.ground_y = 200, 0
        # The bullet passes x=500 early, before the player reaches its depth.
        bullet = RifleBullet(400, 0, 81, 1)
        self.assertFalse(bullet.update(0.5, player))
        self.assertEqual(player.hp, 500)
        player = stationary_player(x=500, depth=0)
        player.previous_ground_y, player.ground_y = 40, 0
        bullet = RifleBullet(400, 0, 81, 1)
        self.assertTrue(bullet.update(0.5, player))
        self.assertEqual(player.hp, 495)

    def test_new_round_does_not_sweep_back_through_the_players_old_position(self):
        player = stationary_player(x=900)
        player.previous_x = 500
        bullet = RifleBullet(500, 100, 81, 1)
        self.assertFalse(bullet.update(0, player))
        self.assertEqual(player.hp, 500)
        self.assertFalse(bullet.spent)

    def test_expiry_happens_before_a_target_beyond_the_flight_range(self):
        player = stationary_player(x=1500)
        bullet = RifleBullet(100, 100, 81, 1)
        self.assertFalse(bullet.update(3, player))
        self.assertEqual((player.hp, bullet.x, bullet.elapsed), (500, 1300, 1))
        self.assertTrue(bullet.spent)

    def test_world_edges_remove_rounds_and_zero_or_negative_time_does_not_advance_them(self):
        player = stationary_player(height=500)
        for x, facing in ((0, -1), (2560, 1)):
            bullet = RifleBullet(x, 100, 81, facing)
            for dt in (0, -1):
                self.assertFalse(bullet.update(dt, player))
                self.assertEqual((bullet.x, bullet.elapsed), (x, 0))
            bullet.update(0.1, player)
            self.assertTrue(bullet.finished)

    def test_eight_frames_both_facings_use_small_nose_anchored_clips(self):
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            metadata = json.load(file)
        image = Mock(w=2048, h=256)
        assets = SimpleNamespace(images={config.RIFLE_BULLET_IMAGE: image}, frames=metadata)
        for facing in (-1, 1):
            bullet = RifleBullet(1000, 100, 81, facing)
            for frame in range(8):
                bullet.elapsed = (frame + 0.05) / bullet.fps
                Assets.draw_projectile(assets, bullet, 20, 30)
                args = image.clip_composite_draw.call_args.args
                self.assertEqual(args[:4], tuple(metadata[bullet.image_name][0][frame]["clip"]))
                self.assertEqual(args[5], "h" if facing < 0 else "")
                self.assertLessEqual(args[8], 16)
                self.assertLessEqual(args[9], 6)
                self.assertAlmostEqual(args[6] + facing * args[8] / 2, bullet.impact_x - 20)

    def test_fired_round_survives_its_shooter_and_scenes_loading_and_f5_preserve_lifecycle(self):
        world = World()
        world.select_stage(10)
        enemy = world.spawner.spawn(1, 0)[0]
        world.enemies = [enemy]
        bullet = RifleBullet(world.player.x - 100, 100, 81, 1)
        world.projectiles.append(bullet)
        enemy.take_damage(300)
        world.step(config.FIXED_DT)
        self.assertIn(bullet, world.projectiles)
        snapshot = bullet.x, bullet.elapsed
        world.select_stage(9)
        advance(world, 0.2)
        world.select_stage(10)
        self.assertEqual((bullet.x, bullet.elapsed), snapshot)
        world.pending_stage_index, world.stage_loading_remaining = 9, 2
        world.update(0.2)
        self.assertEqual((bullet.x, bullet.elapsed), snapshot)
        world.reset()
        self.assertFalse(any(stage.projectiles for stage in world.stages))

    def test_frame_and_motion_are_identical_at_all_render_rates(self):
        results = []
        for fps in (30, 60, 120, 144):
            world = World()
            world.select_stage(10)
            bullet = RifleBullet(100, 100, 400, 1)
            world.projectiles.append(bullet)
            advance(world, 0.5, fps)
            results.append((bullet.x, bullet.height, bullet.elapsed, bullet.frame))
        self.assertTrue(all(result == results[0] for result in results))


if __name__ == "__main__":
    unittest.main()
