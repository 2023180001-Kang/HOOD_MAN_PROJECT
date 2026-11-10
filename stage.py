"""A single flat street; buildings and stairs are background decorations."""

import config


class Stage:
    def draw(self, assets, camera_x=0.0):
        # Preserve the source aspect ratio, aligning its street to the ground.
        image = assets.images[config.STAGE_IMAGE]
        height = config.WORLD_WIDTH * image.h / image.w
        image.draw(config.WORLD_WIDTH / 2 - camera_x,
                   height / 2 - 120, config.WORLD_WIDTH, height)
