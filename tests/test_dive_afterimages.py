import unittest
from math import ceil

import config
from tests.helpers import advance, tap
from tests.test_weapon_leap import aim


def release_dive(world):
    tap(world.controls, "combat_d")
    world.step(config.FIXED_DT)


class DiveAfterimageTests(unittest.TestCase):
    def test_only_second_d_emits_frozen_weapon_poses_behind_both_dive_directions(self):
        for kind in config.WEAPON_AIRBORNE_ROWS:
            for side in (-1, 1):
                world = aim(kind)
                advance(world, 1)
                self.assertFalse(world.afterimages)
                player = world.player
                world.controls.press("right" if side > 0 else "left")
                start = player.x, player.ground_y, player.jump_height
                release_dive(world)
                image = world.afterimages[0]
                self.assertEqual((image.image_name, image.row, image.frame, image.facing),
                                 (config.WEAPON_POSE_IMAGES[kind], config.WEAPON_AIRBORNE_ROWS[kind], 3, side))
                self.assertEqual((image.x, image.ground_y, image.jump_height), start)
                self.assertGreater((player.x - image.x) * side, 0)
                self.assertLess(player.y, image.y)
                advance(world, 0.05)
                self.assertGreaterEqual(len(world.afterimages), 3)
                self.assertEqual((image.x, image.ground_y, image.jump_height), start)
                self.assertLess(image.opacity, world.afterimages[-1].opacity)
                self.assertTrue(all(0 < echo.opacity <= config.WEAPON_DIVE_AFTERIMAGE_OPACITY
                                    for echo in world.afterimages))

    def test_landing_stops_emission_and_the_remaining_trail_fades_away(self):
        for kind in config.WEAPON_AIRBORNE_ROWS:
            world = aim(kind)
            advance(world, 1)
            release_dive(world)
            while not world.player.grounded:
                world.step(config.FIXED_DT)
            images = tuple(world.afterimages)
            self.assertTrue(images)
            oldest = images[0]
            opacity = oldest.opacity
            world.step(config.FIXED_DT)
            self.assertEqual(tuple(world.afterimages), images)
            self.assertLess(oldest.opacity, opacity)
            advance(world, 0.5)
            self.assertFalse(world.afterimages)
            self.assertTrue(all(image.finished and image.opacity == 0 for image in images))
            self.assertEqual(world.time_scale, 1)

    def test_cancelled_attacks_leave_only_existing_fading_snapshots(self):
        for kind in config.WEAPON_AIRBORNE_ROWS:
            for cause in ("hit", "drop", "swap", "attack", "car"):
                with self.subTest(kind=kind, cause=cause):
                    world = aim(kind)
                    advance(world, 1)
                    release_dive(world)
                    images = tuple(world.afterimages)
                    if cause == "hit":
                        world.player.invincible = False
                        world.player.take_damage(20)
                    elif cause == "drop":
                        tap(world.controls, "weapon_interact")
                    elif cause == "swap":
                        world.player.equip_weapon("steel_pipe" if kind == "combat_knife" else "combat_knife")
                    elif cause == "attack":
                        tap(world.controls, "combat_a")
                    else:
                        world.player.hit_by_car(1)
                    world.step(config.FIXED_DT)
                    self.assertEqual(tuple(world.afterimages), images)
                    self.assertTrue(all(image.image_name == config.WEAPON_POSE_IMAGES[kind]
                                        and image.frame == 3 for image in images))
                    advance(world, 0.5)
                    self.assertFalse(world.afterimages)

    def test_loading_and_inactive_stages_pause_trails_and_f5_clears_every_stage(self):
        world = aim("steel_pipe")
        release_dive(world)
        first = world.stage
        image = first.afterimages[0]
        world.pending_stage_index, world.stage_loading_remaining = 1, 2
        elapsed = image.elapsed
        world.update(0.5)
        self.assertEqual(image.elapsed, elapsed)
        world.select_stage(1)
        world.player.cancel_combat()
        world.player.animation.set_state("JUMP")
        advance(world, 0.5)
        self.assertFalse(world.afterimages)
        self.assertEqual(image.elapsed, elapsed)
        self.assertEqual(first.afterimages, [image])
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertTrue(all(not stage.afterimages for stage in world.stages))

    def test_trail_density_is_bounded_and_identical_at_different_render_rates(self):
        for kind in config.WEAPON_AIRBORNE_ROWS:
            results = []
            for fps in (30, 60, 120, 144):
                world = aim(kind)
                # Sustain a long dive to exercise the live trail's upper bound.
                world.player.jump_height = 2000
                tap(world.controls, "combat_d")
                advance(world, 0.5, fps)
                self.assertGreater(len(world.afterimages), 3)
                self.assertLessEqual(len(world.afterimages),
                                     ceil(config.WEAPON_DIVE_AFTERIMAGE_DURATION
                                          / config.WEAPON_DIVE_AFTERIMAGE_INTERVAL) + 1)
                results.append([(image.image_name, image.row, image.frame, image.x, image.y,
                                 image.ground_y, image.facing, image.elapsed, image.opacity)
                                for image in world.afterimages])
            self.assertTrue(all(result == results[0] for result in results))


if __name__ == "__main__":
    unittest.main()
