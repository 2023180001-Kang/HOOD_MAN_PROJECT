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
            for name in (config.TITLE_IMAGE, config.STAGE_LOADING_IMAGE,
                         config.PLAYER_IMAGE, config.COMBAT_IMAGE,
                         config.ENEMY_IMAGE, config.BLOOD_IMAGE, config.HP_IMAGE,
                         *config.STAGE_IMAGES, *config.STAGE_ARROW_IMAGES.values())
        }
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            self.frames = json.load(file)
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "malgun.ttf"
        self.font = pico2d.load_font(str(font_path), 17) if font_path.is_file() else None
        self.damage_font = (pico2d.load_font(str(font_path), config.DAMAGE_NUMBER_FONT_SIZE)
                            if font_path.is_file() else None)

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
        for font in (self.font, self.damage_font):
            if font is not None:
                pico2d.TTF_CloseFont(font.font)
        self.font = self.damage_font = None

    def draw_hit_effect(self, effect, camera_x, camera_y):
        image = self.images[config.BLOOD_IMAGE]
        width = image.w // config.HIT_EFFECT_COLUMNS
        height = image.h // config.HIT_EFFECT_ROWS
        column = effect.frame % config.HIT_EFFECT_COLUMNS
        row = effect.frame // config.HIT_EFFECT_COLUMNS
        scale = config.HIT_EFFECT_SCALE
        image.clip_composite_draw(
            column * width, image.h - (row + 1) * height, width, height,
            0, "h" if effect.facing < 0 else "",
            effect.x - camera_x + (width / 2 - config.HIT_EFFECT_ANCHOR_X) * scale * effect.facing,
            effect.y - camera_y + (height / 2 - config.HIT_EFFECT_ANCHOR_Y) * scale,
            width * scale, height * scale,
        )
