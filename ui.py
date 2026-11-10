"""Screen-fixed HP image. Only the interior fill is masked as health falls."""

import config
from physics import clamp


class UI:
    def draw(self, assets, world):
        import pico2d

        image = assets.images[config.HP_IMAGE]
        scale = config.UI_SCALE
        x = config.UI_MARGIN
        y = config.SCREEN_HEIGHT - config.UI_MARGIN - image.h * scale
        image.draw_to_origin(x, y, image.w * scale, image.h * scale)
        left, bottom, width, height = config.HP_FILL
        ratio = clamp(world.player.hp / config.MAX_HP, 0.0, 1.0)
        if ratio < 1:
            mask_left = x + (left + width * ratio) * scale
            mask_bottom = y + bottom * scale
            pico2d.draw_rectangle(
                mask_left, mask_bottom, x + (left + width) * scale - 1,
                mask_bottom + height * scale - 1, 8, 15, 24, filled=True,
            )
        if assets.font is not None:
            assets.font.draw(x + image.w * scale + 16, y + 56,
                             f"{world.player.hp} / {config.MAX_HP}", (218, 228, 240))
            assets.font.draw(22, 28,
                             "← → 이동   Shift 달리기   Space 이단 점프   R 다시 시작",
                             (205, 218, 231))
            if world.player.state in ("DYING", "DEAD"):
                center = config.SCREEN_WIDTH / 2
                pico2d.draw_rectangle(center - 240, 322, center + 240, 400,
                                      12, 21, 33, filled=True)
                assets.font.draw(center - 175, 365, "쓰러졌습니다. R 키로 다시 시작하세요.",
                                 (240, 211, 194))
