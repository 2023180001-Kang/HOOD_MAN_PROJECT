from pathlib import Path
import random
import unittest
from unittest.mock import patch

from PIL import Image

import config
from assets import Assets
from tests.helpers import advance, tap
from world import World


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
        self.assertIn("cityStage-1.png", assets.images)


if __name__ == "__main__":
    unittest.main()
