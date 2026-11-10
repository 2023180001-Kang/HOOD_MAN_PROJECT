"""Horizontal world camera with a fixed vertical reference."""

import config
from physics import clamp


class Camera:
    def __init__(self, player_x):
        self.x = 0.0
        self.update(0, player_x)

    def update(self, dt, player_x):
        self.x = clamp(player_x - config.SCREEN_WIDTH / 2, 0,
                       config.WORLD_WIDTH - config.SCREEN_WIDTH)

    @property
    def render_x(self):
        return self.x

    @property
    def render_y(self):
        return 0.0
