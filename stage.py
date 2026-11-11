"""Independent street scenes and world-space backgrounds/exit markers."""

from math import ceil, floor

import config
from spawn_manager import SpawnManager


class Stage:
    def __init__(self, index=0, *, rng=None):
        self.index = index
        self.arrows_visible = False
        self.enemies = []
        self.effects = []
        self.spawner = SpawnManager(rng=rng)

    @property
    def image_name(self):
        return config.STAGE_IMAGES[self.index]

    @property
    def arrow_sides(self):
        if not self.arrows_visible:
            return ()
        return (1,) if self.index == 0 else (-1, 1)

    def destination(self, side):
        target = self.index + side
        if side in self.arrow_sides and 0 <= target < len(config.STAGE_IMAGES):
            return target
        return None

    def draw(self, assets, camera_x=0.0, camera_y=0.0):
        # Keep the supplied character/building scale instead of enlarging the
        # artwork to the full world width. Mirrored tiles join without a cut.
        image = assets.images[self.image_name]
        scale = config.STAGE_SCALE
        width = image.w * scale
        height = image.h * scale
        bottom = config.GROUND_Y - config.STAGE_GROUND_Y * scale
        first = max(0, floor(camera_x / width))
        last = min(ceil(config.WORLD_WIDTH / width),
                   ceil((camera_x + config.SCREEN_WIDTH) / width))
        for index in range(first, last):
            image.composite_draw(
                0, "h" if index % 2 else "",
                index * width + width / 2 - camera_x,
                bottom + height / 2 - camera_y, width, height,
            )
        for side in self.arrow_sides:
            arrow = assets.images[config.STAGE_ARROW_IMAGES[side]]
            x = (config.STAGE_EXIT_MARGIN if side < 0 else
                 config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN)
            arrow.draw(x - camera_x, config.STAGE_ARROW_Y - camera_y,
                       config.STAGE_ARROW_WIDTH, config.STAGE_ARROW_WIDTH * arrow.h / arrow.w)
            if assets.font is not None:
                label = "이전 스테이지" if side < 0 else "다음 스테이지"
                if self.destination(side) is None:
                    label = "다음 스테이지 준비 중"
                text_x = 24 if side < 0 else config.WORLD_WIDTH - 240
                assets.font.draw(text_x - camera_x, config.STAGE_ARROW_Y + 50 - camera_y,
                                 label, (244, 204, 66))
