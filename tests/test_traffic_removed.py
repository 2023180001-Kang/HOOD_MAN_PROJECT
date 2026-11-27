import hashlib
from pathlib import Path
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

import config
from assets import Assets
from tests.helpers import advance, tap
from tools.check_traffic import city
from tests.helpers import ManualSpawnWorld as World


CAR_SHEET = "HOOD_MAN_car_attached_wheels_8f_pico2d.png"


class RemovedTrafficTests(unittest.TestCase):
    def test_no_stage_creates_traffic_and_the_city_road_stays_safe_on_revisit_and_restart(self):
        world = World(rng=random.Random(7))
        self.assertTrue(all(stage.traffic is None for stage in world.stages))
        for index in (2, 3, 2):
            world.select_stage(index)
            world.player.ground_y = config.CAR_GROUND_Y
            advance(world, 10)
            self.assertIsNone(world.stage.traffic)
            self.assertEqual(world.player.hp, config.MAX_HP)
            self.assertFalse(world.player.car_hit)
            self.assertEqual(world.effects, [])
        tap(world.controls, "restart")
        world.update(config.FIXED_DT)
        self.assertEqual(world.stage_index, 0)
        self.assertTrue(all(stage.traffic is None for stage in world.stages))
        world.select_stage(2)
        world.player.ground_y = config.CAR_GROUND_Y
        advance(world, 5)
        self.assertEqual(world.player.hp, config.MAX_HP)
        self.assertIsNone(world.stage.traffic)

    def test_car_sheet_is_archived_and_no_longer_present_in_the_project_root(self):
        archived = config.ROOT / "before_sheets" / CAR_SHEET
        self.assertTrue(archived.is_file())
        self.assertFalse((config.ROOT / CAR_SHEET).exists())
        self.assertEqual(config.ROOT / config.CAR_IMAGE, archived)
        with Image.open(archived) as image:
            self.assertEqual(image.size, (2048, 512))

    def test_normal_asset_loading_does_not_open_or_register_the_archived_car_sheet(self):
        with (patch("assets.pico2d.load_image") as load_image,
              patch("assets.pico2d.load_font", return_value=None)):
            assets = Assets()
        self.assertNotIn(config.CAR_IMAGE, assets.images)
        self.assertNotIn(CAR_SHEET, [Path(call.args[0]).name for call in load_image.call_args_list])
        self.assertIn(config.ENEMY02_IMAGE, assets.images)
        self.assertIn(config.CITY_STAGE_IMAGES[0], assets.images)

    def test_both_car_hit_sheets_are_archived_byte_identically_without_root_copies(self):
        expected = (
            ("before_sheets/hoodman_car_hit_8frames_2048x256.png",
             "defc3f097f767b8e6049e3683b4a04bca50baf9ae2b3a24506e4f5ecc640b6b4"),
            ("before_sheets/street_thug_car_hit_8frames_2048x256.png",
             "003328722278f678e53c4e9c65f8b3f0a5c630f6becbe4a7f157455bcbd66314"),
        )
        self.assertEqual(config.ARCHIVED_CAR_HIT_IMAGES, (config.PLAYER_CAR_HIT_IMAGE,
                                                        config.ENEMY_CAR_HIT_IMAGE))
        for actual, (name, digest) in zip(config.ARCHIVED_CAR_HIT_IMAGES, expected):
            self.assertEqual(actual, name)
            path = config.ROOT / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            self.assertFalse((config.ROOT / path.name).exists())
            with Image.open(path) as image:
                self.assertEqual((image.size, image.mode), ((2048, 256), "RGBA"))

    def test_normal_loading_excludes_both_car_hit_textures_but_keeps_archived_clip_coordinates(self):
        with (patch("assets.pico2d.load_image") as load_image,
              patch("assets.pico2d.load_font", return_value=None)):
            assets = Assets()
        opened = {Path(call.args[0]).name for call in load_image.call_args_list}
        for name in config.ARCHIVED_CAR_HIT_IMAGES:
            self.assertNotIn(name, assets.images)
            self.assertNotIn(Path(name).name, opened)
            self.assertNotIn(Path(name).name, assets.frames)
            self.assertEqual(len(assets.frames[name]), 1)
            self.assertEqual(len(assets.frames[name][0]), 8)

    def test_legacy_vehicle_diagnostics_explicitly_load_archived_textures_only_once(self):
        with (patch("assets.pico2d.load_image"),
              patch("assets.pico2d.load_font", return_value=None)):
            game = SimpleNamespace(assets=Assets())
        textures = dict(game.assets.images)
        with patch("pico2d.load_image") as load_image:
            city(game)
            city(game)
        expected = (config.CAR_IMAGE, *config.ARCHIVED_CAR_HIT_IMAGES)
        self.assertEqual([call.args[0] for call in load_image.call_args_list],
                         [str(config.ROOT / name) for name in expected])
        self.assertEqual(set(game.assets.images) - textures.keys(), set(expected))
        self.assertTrue(all(game.assets.images[name] is texture for name, texture in textures.items()))


if __name__ == "__main__":
    unittest.main()
