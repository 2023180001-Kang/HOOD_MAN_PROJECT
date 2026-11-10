"""Main game loop and shared-resource lifetime."""

from time import perf_counter, sleep

import pico2d

import config
from assets import Assets
from stage import Stage


class Game:
    def __init__(self):
        self.assets = Assets()
        self.stage = Stage()
        self.elapsed = 0.0
        self.running = True

    def handle_events(self):
        for event in pico2d.get_events():
            if event.type == pico2d.SDL_QUIT:
                self.running = False

    def update(self, dt):
        self.elapsed += dt

    def draw(self):
        pico2d.clear_canvas()
        camera_x = config.START_X - config.SCREEN_WIDTH / 2
        self.stage.draw(self.assets, camera_x)
        self.assets.draw_sprite(config.PLAYER_IMAGE, 1, int(self.elapsed * 7) % 8,
                                config.SCREEN_WIDTH / 2, config.GROUND_Y)
        pico2d.update_canvas()

    def run(self, max_frames=None):
        previous = perf_counter()
        frames = 0
        while self.running and (max_frames is None or frames < max_frames):
            start = perf_counter()
            dt = min(start - previous, config.MAX_FRAME_DT)
            previous = start
            self.handle_events()
            if not self.running:
                break
            self.update(dt)
            self.draw()
            frames += 1
            sleep(max(0, 1 / config.TARGET_FPS - (perf_counter() - start)))
        return frames

    def close(self):
        self.assets.release()
