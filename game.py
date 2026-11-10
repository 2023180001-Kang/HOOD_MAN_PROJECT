"""Main game loop and shared-resource lifetime."""

from time import perf_counter, sleep

import pico2d

import config
from assets import Assets
from stage import Stage
from world import World


KEYS = {
    pico2d.SDLK_LEFT: "left",
    pico2d.SDLK_RIGHT: "right",
    pico2d.SDLK_LSHIFT: "left_shift",
    pico2d.SDLK_RSHIFT: "right_shift",
    pico2d.SDLK_SPACE: "jump",
}


class Game:
    def __init__(self):
        self.assets = Assets()
        self.stage = Stage()
        self.world = World()
        self.running = True

    def handle_events(self):
        for event in pico2d.get_events():
            if event.type == pico2d.SDL_QUIT:
                self.running = False
            elif event.key in KEYS:
                if event.type == pico2d.SDL_KEYDOWN:
                    self.world.controls.press(KEYS[event.key])
                elif event.type == pico2d.SDL_KEYUP:
                    self.world.controls.release(KEYS[event.key])

    def update(self, dt):
        self.world.update(dt)

    def draw(self, present=True):
        pico2d.clear_canvas()
        camera_x = self.world.camera.render_x
        camera_y = self.world.camera.render_y
        self.stage.draw(self.assets, camera_x, camera_y)
        for enemy in self.world.enemies:
            self.assets.draw_sprite(config.ENEMY_IMAGE, enemy.animation.row,
                                    enemy.animation.frame, enemy.x - camera_x,
                                    enemy.y - camera_y, enemy.facing)
        player = self.world.player
        self.assets.draw_sprite(config.PLAYER_IMAGE, player.animation.row,
                                player.animation.frame, player.x - camera_x,
                                player.y - camera_y, player.facing)
        if present:
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
