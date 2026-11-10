"""Horizontal tracking and render-only, deterministic impact shake."""

from math import cos, sin

import config
from physics import clamp


class Camera:
    def __init__(self, player_x):
        self.x = 0.0
        self.shake_remaining = 0.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.update(0, player_x)

    def shake(self):
        self.shake_remaining = config.SHAKE_DURATION
        self.offset_x = config.SHAKE_STRENGTH
        self.offset_y = config.SHAKE_STRENGTH / 2

    def update(self, dt, player_x):
        self.x = clamp(player_x - config.SCREEN_WIDTH / 2, 0,
                       config.WORLD_WIDTH - config.SCREEN_WIDTH)
        self.shake_remaining = max(0.0, self.shake_remaining - dt)
        if self.shake_remaining:
            strength = config.SHAKE_STRENGTH * self.shake_remaining / config.SHAKE_DURATION
            phase = (config.SHAKE_DURATION - self.shake_remaining) * 95
            self.offset_x = cos(phase) * strength
            self.offset_y = sin(phase * 1.3) * strength / 2
        else:
            self.offset_x = self.offset_y = 0.0

    @property
    def render_x(self):
        return clamp(self.x + self.offset_x, 0,
                     config.WORLD_WIDTH - config.SCREEN_WIDTH)

    @property
    def render_y(self):
        return self.offset_y
