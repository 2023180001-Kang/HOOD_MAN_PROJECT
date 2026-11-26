from contextlib import contextmanager
import unittest
from unittest.mock import patch

import config
from combat import STRONG_MOVES
from walkable import default_area


@contextmanager
def archived_two_floor_map():
    """Opt legacy regressions into the archived scene for their entire lifetime."""
    default_area.cache_clear()
    try:
        with patch.multiple(
            config,
            STAGE_IMAGE=config.ARCHIVED_TWO_FLOOR_IMAGE,
            STAGE_IMAGES=(config.ARCHIVED_TWO_FLOOR_IMAGE, *config.STAGE_IMAGES[1:]),
            STAGE_WALKABLE_BOUNDS=(config.ARCHIVED_TWO_FLOOR_WALKABLE_BOUNDS,
                                   *config.STAGE_WALKABLE_BOUNDS[1:]),
        ):
            yield
    finally:
        default_area.cache_clear()


class ArchivedTwoFloorTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.enterContext(archived_two_floor_map())


def advance(world, seconds, fps=60):
    for _ in range(round(seconds * fps)):
        world.update(1 / fps)


def tap(controls, key):
    controls.release(key)
    controls.press(key)


def enter_kick_wait(world):
    """Start the real W follow-up wait without advancing unrelated encounter clocks."""
    move = STRONG_MOVES["combat_w"]
    world.player.start_move(move, world.player.facing)
    world.player.update_air_kick((move.active_frames[0] + 1) / move.fps, world.controls)


def clear_encounters(world):
    """Clear explicitly arranged actors in motion/transition test fixtures."""
    for stage in world.stages:
        stage.enemies.clear()
    return world


def spawn_encounter(world, count=4):
    """Arrange combat actors explicitly; input tests exercise numeric presses."""
    enemies = world.spawner.spawn(count, world.elapsed)
    world.enemies.extend(enemies)
    return enemies
