"""Bounded horizontal/vertical player framing and render-only impact shake."""

from math import cos, sin

import config
from physics import clamp


class Camera:
    def __init__(self, player_x):
        self.x = 0.0
        self.y = 0.0
        self.vertical_bounds = None
        self.shake_remaining = 0.0
        self.shake_strength = config.SHAKE_STRENGTH
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.update(0, player_x)

    def shake(self, strength=None):
        self.shake_strength = config.SHAKE_STRENGTH if strength is None else strength
        self.shake_remaining = config.SHAKE_DURATION
        self.offset_x = self.shake_strength
        self.offset_y = self.shake_strength / 2

    def update(self, dt, player_x, *, player_y=None, vertical_bounds=None):
        self.x = clamp(player_x - config.SCREEN_WIDTH / 2, 0,
                       config.WORLD_WIDTH - config.SCREEN_WIDTH)
        if vertical_bounds is not None:
            self.vertical_bounds = vertical_bounds
        if player_y is not None and self.vertical_bounds is not None:
            target = max(0.0, player_y + config.CAMERA_PLAYER_HEIGHT
                         - (config.SCREEN_HEIGHT - config.CAMERA_TOP_MARGIN))
            if player_y < config.CAMERA_BOTTOM_MARGIN:
                target = player_y - config.CAMERA_BOTTOM_MARGIN
            self.y = clamp(target, *self.vertical_bounds)
        self.shake_remaining = max(0.0, self.shake_remaining - dt)
        if self.shake_remaining:
            strength = self.shake_strength * self.shake_remaining / config.SHAKE_DURATION
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
        y = self.y + self.offset_y
        return y if self.vertical_bounds is None else clamp(y, *self.vertical_bounds)
