"""Main game loop and shared-resource lifetime."""

import ctypes
from time import perf_counter, sleep

import pico2d
from pico2d import pico2d as backend
from sdl2 import SDL_Event, SDL_PollEvent, SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST

import config
from assets import Assets
from ui import UI
from world import World


KEYS = {
    pico2d.SDLK_LEFT: "left",
    pico2d.SDLK_RIGHT: "right",
    pico2d.SDLK_UP: "up",
    pico2d.SDLK_DOWN: "down",
    pico2d.SDLK_LSHIFT: "left_shift",
    pico2d.SDLK_RSHIFT: "right_shift",
    pico2d.SDLK_SPACE: "jump",
    pico2d.SDLK_F5: "restart",
    pico2d.SDLK_n: "stage_exits",
    pico2d.SDLK_p: "invincibility",
}
KEYS.update({getattr(pico2d, f"SDLK_{key}"): f"combat_{key}"
             for key, *_ in config.COMBAT_MOVE_SPECS})
KEYS.update({getattr(pico2d, f"SDLK_{prefix}{count}"): f"spawn_{count}"
             for count in config.SPAWN_COUNTS for prefix in ("", "KP_")})


class Game:
    def __init__(self):
        self.assets = Assets()
        self.ui = UI()
        self.world = World()
        self.running = True
        pico2d.SDL_SetWindowTitle(backend.window, b"HOOD_MAN_PROJECT")

    def handle_events(self):
        # pico2d.get_events filters out focus events, so poll its SDL event queue
        # directly to prevent stuck keys after Alt+Tab or clicking another window.
        event = SDL_Event()
        while SDL_PollEvent(ctypes.byref(event)):
            if event.type == pico2d.SDL_QUIT:
                self.running = False
            elif event.type == SDL_WINDOWEVENT and event.window.event == SDL_WINDOWEVENT_FOCUS_LOST:
                self.world.controls.held.clear()
                self.world.controls.pressed.clear()
            elif event.type in (pico2d.SDL_KEYDOWN, pico2d.SDL_KEYUP):
                key = KEYS.get(event.key.keysym.sym)
                if key is not None:
                    if event.type == pico2d.SDL_KEYDOWN and not event.key.repeat:
                        self.world.controls.press(key)
                    elif event.type == pico2d.SDL_KEYUP:
                        self.world.controls.release(key)

    def update(self, dt):
        self.world.update(dt)

    def draw(self, present=True):
        pico2d.clear_canvas()
        camera_x = self.world.camera.render_x
        camera_y = self.world.camera.render_y
        self.world.stage.draw(self.assets, camera_x, camera_y, elapsed=self.world.elapsed)
        player = self.world.player
        sprites = [(enemy.ground_y, enemy, config.ENEMY_IMAGE) for enemy in self.world.enemies]
        sprites.append((player.ground_y, player, player.sprite_image))
        for _, actor, image in sorted(sprites, key=lambda entry: entry[0], reverse=True):
            self.assets.draw_sprite(image, actor.animation.row, actor.animation.frame,
                                    actor.x - camera_x, actor.y - camera_y, actor.facing)
        for effect in self.world.effects:
            self.assets.draw_hit_effect(effect, camera_x, camera_y)
        self.ui.draw_enemy_health(self.assets, self.world, camera_x, camera_y)
        self.ui.draw(self.assets, self.world)
        if present:
            pico2d.update_canvas()

    def run(self, max_frames=None):
        previous = perf_counter()
        deadline = previous
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
            # Absolute deadlines avoid accumulating Windows sleep overshoot.
            deadline += 1 / config.TARGET_FPS
            remaining = deadline - perf_counter()
            if remaining > 0:
                sleep(remaining)
            elif remaining < -config.MAX_FRAME_DT:
                deadline = perf_counter()
        return frames

    def close(self):
        self.assets.release()
