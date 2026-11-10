"""A single flat street; buildings and stairs are background decorations."""

from math import ceil, floor

import config


class Stage:
    def draw(self, assets, camera_x=0.0, camera_y=0.0):
        # Keep the supplied character/building scale instead of enlarging the
        # artwork to the full world width. Mirrored tiles join without a cut.
        image = assets.images[config.STAGE_IMAGE]
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
