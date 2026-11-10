"""Load shared pico2d resources once, independent of the working directory."""

import json
import os
from pathlib import Path

import pico2d

import config


class Assets:
    def __init__(self):
        self.images = {
            name: pico2d.load_image(str(config.ROOT / name))
            for name in (config.PLAYER_IMAGE, config.COMBAT_IMAGE, config.ENEMY_IMAGE,
                         config.HP_IMAGE, config.STAGE_IMAGE)
        }
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            self.frames = json.load(file)
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "malgun.ttf"
        self.font = pico2d.load_font(str(font_path), 17) if font_path.is_file() else None

    def draw_sprite(self, name, row, frame, x, feet_y, facing=1):
        tile = self.frames[name][row - 1][frame]
        left, bottom, width, height = tile["clip"]
        scale = config.SPRITE_SCALE
        self.images[name].clip_composite_draw(
            left, bottom, width, height, 0, "h" if facing < 0 else "",
            x + tile["offset_x"] * scale * facing,
            feet_y + height * scale / 2, width * scale, height * scale,
        )

    def release(self):
        # Destroy textures before pico2d destroys the renderer.
        self.images.clear()
        if self.font is not None:
            pico2d.TTF_CloseFont(self.font.font)
            self.font = None
