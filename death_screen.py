"""Screen-space death message and mouse actions, timed independently of combat."""

import ctypes

import pico2d
from pico2d import pico2d as backend
from sdl2 import (SDL_BLENDMODE_ADD, SDL_BLENDMODE_BLEND, SDL_GetMouseFocus, SDL_GetMouseState,
                  SDL_GetRenderDrawBlendMode, SDL_SetRenderDrawBlendMode, SDL_SetTextureBlendMode)

import config
from main_menu import MenuButton


def draw_black_overlay(alpha):
    previous_mode = ctypes.c_int()
    SDL_GetRenderDrawBlendMode(backend.renderer, ctypes.byref(previous_mode))
    SDL_SetRenderDrawBlendMode(backend.renderer, SDL_BLENDMODE_BLEND)
    try:
        pico2d.draw_rectangle(0, 0, config.SCREEN_WIDTH - 1, config.SCREEN_HEIGHT - 1,
                              0, 0, 0, alpha, filled=True)
    finally:
        SDL_SetRenderDrawBlendMode(backend.renderer, previous_mode.value)


class DeathScreen:
    center_x = config.SCREEN_WIDTH / 2
    center_y = config.SCREEN_HEIGHT / 2
    # Top-to-bottom order matches the two rows of the supplied sprite sheet.
    buttons = (MenuButton("retry", config.DEATH_BUTTONS_IMAGE, center_x, center_y - 122, 200, 90),
               MenuButton("main_menu", config.DEATH_BUTTONS_IMAGE, center_x, center_y - 224, 200, 90))
    reveal_times = (0.65, 0.95)

    def __init__(self):
        self.elapsed = 0.0
        self.pointer = None

    def update(self, dt, alive):
        if alive:
            self.elapsed = 0.0
            self.pointer = None
            return
        if self.elapsed == 0 and dt > 0 and self.pointer is None and SDL_GetMouseFocus():
            # Hover also works if the cursor was already there when the player died.
            x, y = ctypes.c_int(), ctypes.c_int()
            SDL_GetMouseState(ctypes.byref(x), ctypes.byref(y))
            self.pointer = (x.value, config.SCREEN_HEIGHT - 1 - y.value)
        self.elapsed += max(0.0, dt)

    def button_at(self, x, y):
        for button, delay in zip(self.buttons, self.reveal_times):
            if self.elapsed > delay and button.contains(x, y):
                return button
        return None

    def draw(self, assets):
        draw_black_overlay(round(215 * min(1.0, self.elapsed / 0.45)))
        title = assets.images[config.DEATH_TITLE_IMAGE]
        frame = int(self.elapsed * 10) % 8
        width = title.w // 8
        # The supplied lettering is translucent charcoal. Add its own light
        # over the dimmed scene to expose the grain in the letters.
        title.opacify(min(1.0, self.elapsed / 0.3))
        SDL_SetTextureBlendMode(title.texture, SDL_BLENDMODE_ADD)
        try:
            for _ in range(4):
                title.clip_draw(frame * width, 0, width, title.h, self.center_x, self.center_y, 640, 160)
        finally:
            SDL_SetTextureBlendMode(title.texture, SDL_BLENDMODE_BLEND)
            title.opacify(1.0)

        image = assets.images[config.DEATH_BUTTONS_IMAGE]
        hovered = self.button_at(*self.pointer) if self.pointer is not None else None
        for row, (button, delay) in enumerate(zip(self.buttons, self.reveal_times)):
            if self.elapsed <= delay:
                continue
            frame = (3, 4, 5, 4)[int(self.elapsed * 8) % 4] if button is hovered else 0
            image.opacify(min(1.0, (self.elapsed - delay) / 0.18))
            try:
                # Crop transparent cell padding so the hit box fits the visible border.
                image.clip_draw(frame * 256 + 6, (1 - row) * 128 + 8, 245, 110,
                                button.x, button.y, button.width, button.height)
            finally:
                image.opacify(1.0)
