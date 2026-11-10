"""Fixed-step simulation usable without pico2d or a display."""

import config
from camera import Camera
from controls import Controls
from player import Player


class World:
    def __init__(self):
        self.controls = Controls()
        self.player = Player()
        self.camera = Camera(self.player.x)
        self.elapsed = 0.0
        self.accumulator = 0.0

    def update(self, dt):
        self.accumulator += min(max(dt, 0.0), config.MAX_FRAME_DT)
        while self.accumulator + 1e-12 >= config.FIXED_DT:
            self.step(config.FIXED_DT)
            self.accumulator = max(0.0, self.accumulator - config.FIXED_DT)

    def step(self, dt):
        self.elapsed += dt
        self.player.update(dt, self.controls)
        self.camera.update(dt, self.player.x)
