"""Load shared pico2d resources once, independent of the working directory."""

import json
import os
from math import radians, tau
from pathlib import Path

import pico2d

import config
from projectiles import ThrownWeaponProjectile


class Assets:
    def __init__(self):
        self.images = {
            name: pico2d.load_image(str(config.ROOT / name))
            for name in (config.MAIN_MENU_IMAGE, config.STAGE_PROGRESS_IMAGE, config.STAGE_LOCK_IMAGE,
                         config.STAGE_LOADING_IMAGE, config.TRAINING_ROOM_IMAGE,
                         *(image for _, image in config.MAIN_MENU_BUTTONS),
                         config.BAG_UI_IMAGE, config.BAG_BUTTON_IMAGE,
                         *(image for _, image, _ in config.BAG_ITEM_SPECS),
                         config.PLAYER_IMAGE, *config.PLAYER_EQUIPPED_SHEETS.values(), config.COMBAT_IMAGE,
                         *(sprite.image for sprite in config.THROWN_WEAPON_SPRITES.values()),
                         config.STRONG_ATTACK_IMAGE, config.STRONG_HIT_IMAGE,
                         config.ENEMY_IMAGE, config.ENEMY02_IMAGE, config.AXE_ENEMY_IMAGE,
                         config.AXE_ENEMY_UNARMED_IMAGE,
                         config.RESEARCHER_IMAGE, config.RESEARCHER_BULLET_IMAGE,
                         config.AR_SOLDIER_IMAGE, config.RIFLE_BULLET_IMAGE,
                         config.SHIELD_SOLDIER_IMAGE, config.SWORD_ENEMY_IMAGE,
                         config.HP_IMAGE,
                         *config.HIT_EFFECT_IMAGES,
                         *config.DROP_ITEM_IMAGES.values(),
                         *config.WEAPON_POSE_IMAGES.values(),
                         *config.DOOR_IMAGES.values(),
                         *config.STAGE_IMAGES, *config.STAGE_ARROW_IMAGES.values())
        }
        # Archived car-hit clips remain for opt-in diagnostics, without textures.
        with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
            self.frames = json.load(file)
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "malgun.ttf"
        self.font = pico2d.load_font(str(font_path), 17) if font_path.is_file() else None
        self.damage_font = (pico2d.load_font(str(font_path), config.DAMAGE_NUMBER_FONT_SIZE)
                            if font_path.is_file() else None)

    def draw_sprite(self, name, row, frame, x, feet_y, facing=1, opacity=1.0, *, scale=None):
        tile = self.frames[name][row - 1][frame]
        left, bottom, width, height = tile["clip"]
        if scale is None:
            scale = config.SPRITE_IMAGE_SCALES.get(name, config.SPRITE_SCALE)
        image = self.images[name]
        fading = opacity < 1.0
        if fading:
            image.opacify(opacity)
        try:
            image.clip_composite_draw(
                left, bottom, width, height, 0, "h" if facing < 0 else "",
                x + tile["offset_x"] * scale * facing,
                feet_y + (height / 2 + tile.get("offset_y", 0)) * scale,
                width * scale, height * scale,
            )
        finally:
            if fading:
                # Actors and afterimages share textures; never dim the next sprite.
                image.opacify(1.0)

    def release(self):
        # Destroy textures before pico2d destroys the renderer.
        self.images.clear()
        for font in (self.font, self.damage_font):
            if font is not None:
                pico2d.TTF_CloseFont(font.font)
        self.font = self.damage_font = None

    def draw_car(self, car, camera_x, camera_y):
        image = self.images[config.CAR_IMAGE]
        width, height = image.w // 4, image.h // 2
        column, row = car.animation.frame % 4, car.animation.frame // 4
        scale = config.CAR_SCALE
        image.clip_composite_draw(
            column * width, image.h - (row + 1) * height, width, height,
            0, "h" if car.facing < 0 else "",
            car.x - camera_x,
            car.ground_y - camera_y + (config.CAR_GROUND_ANCHOR - height / 2) * scale,
            width * scale, height * scale,
        )

    def draw_projectile(self, bullet, camera_x, camera_y):
        if isinstance(bullet, ThrownWeaponProjectile):
            self.draw_thrown_weapon(bullet.weapon_kind, bullet.x - camera_x, bullet.y - camera_y,
                                   bullet.facing, bullet.elapsed)
            return
        image = self.images[bullet.image_name]
        tile = self.frames[bullet.image_name][0][bullet.frame]
        left, bottom, width, height = tile["clip"]
        scale = bullet.scale
        # Keep the copper nose on the physics body while the animated trail
        # extends backward, never moving the impact point as clips get wider.
        image.clip_composite_draw(
            left, bottom, width, height, 0, "h" if bullet.facing < 0 else "",
            bullet.x - camera_x + bullet.facing * (
                bullet.half_width - width * scale / 2),
            bullet.y - camera_y + (
                bottom + height / 2 - image.h + bullet.anchor_y) * scale,
            width * scale, height * scale,
        )

    def draw_researcher_aim(self, researcher, camera_x, camera_y):
        line = researcher.aim_line
        if line is None:
            return
        start_x, height, end_x, _ = line
        radius = config.RESEARCHER_AIM_DOT_RADIUS
        y = height - camera_y
        if not -radius <= y < config.SCREEN_HEIGHT + radius:
            return
        distance = abs(end_x - start_x)
        for index in range(int(distance / config.RESEARCHER_AIM_DOT_SPACING) + 1):
            x = (start_x + researcher.facing * index * config.RESEARCHER_AIM_DOT_SPACING
                 - camera_x)
            if -radius <= x < config.SCREEN_WIDTH + radius:
                pico2d.draw_circle(x, y, radius, *config.RESEARCHER_AIM_COLOR, filled=True)

    def draw_stage_door(self, door, background, tile_x, bottom, scale, *, mirrored=False):
        image = self.images[door.image_name]
        cell = config.DOOR_CELL_SIZE
        left, top, width, height = door.source_rect
        anchor_x, anchor_y, closed_width, closed_height = config.DOOR_CLOSED_BOUNDS[door.kind]
        scale_x, scale_y = width / closed_width, height / closed_height
        center_x = left + (cell / 2 - anchor_x) * scale_x
        center_y = top + (cell / 2 - anchor_y) * scale_y
        if mirrored:
            center_x = background.w - center_x
        image.clip_composite_draw(
            door.frame * cell, image.h - door.row * cell, cell, cell,
            0, "h" if mirrored else "",
            tile_x + center_x * scale, bottom + (background.h - center_y) * scale,
            cell * scale_x * scale, cell * scale_y * scale,
        )

    def draw_thrown_weapon(self, kind, x, y, facing, elapsed, *, grounded=False):
        sprite = config.THROWN_WEAPON_SPRITES[kind]
        image = self.images[sprite.image]
        if kind == "dual_black_batons":
            # Each row animates one baton spinning in the opposite direction to its partner.
            cell = image.h // 2
            columns = image.w // cell
            frame = 0 if grounded else int(elapsed * config.THROWN_WEAPON_TURNS_PER_SECOND * columns) % columns
            for row, side in enumerate((1, -1)):
                image.clip_composite_draw(frame * cell, (1 - row) * cell, cell, cell,
                                          0, "h" if facing < 0 else "",
                                          x + facing * side * 20 * sprite.scale, y + side * 12 * sprite.scale,
                                          cell * sprite.scale, cell * sprite.scale)
            return
        angle = radians(sprite.rest_angle) if grounded else -tau * config.THROWN_WEAPON_TURNS_PER_SECOND * elapsed
        image.clip_composite_draw(0, 0, image.w, image.h, facing * angle,
                                  "h" if facing < 0 else "", x, y,
                                  image.w * sprite.scale, image.h * sprite.scale)

    def draw_drop_item(self, item, camera_x, camera_y):
        x, ground_y = item.x - camera_x, item.surface_y - camera_y
        if item.kind in config.THROWN_WEAPON_SPRITES:
            self.draw_thrown_weapon(item.kind, x, ground_y + item.jump_height + item.display_height / 2,
                                   item.facing, item.elapsed, grounded=item.grounded)
            return
        image = self.images[item.image_name]
        if item.kind in config.FIREARM_DROP_SPRITES:
            _, (left, bottom, width, height), scale = config.FIREARM_DROP_SPRITES[item.kind]
            image.clip_composite_draw(
                left, bottom, width, height, 0, "h" if item.facing < 0 else "",
                x, ground_y + item.jump_height + item.display_height / 2,
                width * scale, height * scale,
            )
            return
        width = image.w // config.DROP_ITEM_FRAMES
        left = item.frame * width
        scale = config.DROP_ITEM_SCALE
        flip = "h" if item.facing < 0 else ""
        # The source shadow stays still while the weapon hovers above it. Keep
        # the shadow on the floor, then pin every weapon frame's bottom to it.
        shadow_height = config.DROP_ITEM_SHADOW_HEIGHT
        image.clip_composite_draw(
            left, image.h - config.DROP_ITEM_SHADOW_TOP - shadow_height, width, shadow_height,
            0, flip, x, ground_y, width * scale, shadow_height * scale,
        )
        height = config.DROP_ITEM_BODY_HEIGHTS[item.kind]
        top = config.DROP_ITEM_BODY_TOPS[item.kind][item.frame]
        image.clip_composite_draw(
            left, image.h - top - height, width, height,
            0, flip, x, ground_y + item.jump_height + height * scale / 2,
            width * scale, height * scale,
        )

    def draw_hit_effect(self, effect, camera_x, camera_y):
        image = self.images[effect.image_name]
        width = image.w // config.HIT_EFFECT_COLUMNS
        height = image.h // config.HIT_EFFECT_ROWS
        column = effect.frame % config.HIT_EFFECT_COLUMNS
        row = effect.frame // config.HIT_EFFECT_COLUMNS
        scale = config.HIT_EFFECT_SIZE / width
        image.clip_composite_draw(
            column * width, image.h - (row + 1) * height, width, height,
            0, "h" if effect.facing < 0 else "",
            effect.x - camera_x, effect.y - camera_y,
            width * scale, height * scale,
        )
