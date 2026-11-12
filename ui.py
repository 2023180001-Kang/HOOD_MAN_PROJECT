"""Screen-fixed controls/HP and world-space enemy health/damage feedback."""

import config
from combat import MOVES
from physics import clamp


class UI:
    def draw_attack_help(self, assets):
        import pico2d

        pico2d.draw_rectangle(688, 568, config.SCREEN_WIDTH - 20, 704,
                              12, 21, 33, filled=True)
        assets.font.draw(704, 686, "공격 키 · 피해량", (244, 204, 66))
        attacks = [move for move in MOVES.values() if not move.blocking]
        for index, move in enumerate(attacks):
            x = 704 + index % 2 * 270
            y = 659 - index // 2 * 24
            assets.font.draw(x, y, f"{move.key.upper()} {move.name} ({move.damage})",
                             (218, 228, 240))

    def draw_enemy_health(self, assets, world, camera_x, camera_y):
        import pico2d

        for enemy in world.enemies:
            if not enemy.alive:
                continue
            height = assets.frames[config.ENEMY_IMAGE][enemy.animation.row - 1][
                enemy.animation.frame]["clip"][3] * config.SPRITE_SCALE
            left = enemy.x - camera_x - config.ENEMY_HP_BAR_WIDTH / 2
            bottom = enemy.y - camera_y + height + config.ENEMY_HP_BAR_GAP
            right = left + config.ENEMY_HP_BAR_WIDTH
            ratio = clamp(enemy.hp / config.ENEMY_MAX_HP, 0.0, 1.0)
            pico2d.draw_rectangle(left - 1, bottom - 1, right,
                                  bottom + config.ENEMY_HP_BAR_HEIGHT, 12, 12, 16, filled=True)
            pico2d.draw_rectangle(left, bottom, right - 1,
                                  bottom + config.ENEMY_HP_BAR_HEIGHT - 1, 50, 15, 20, filled=True)
            if ratio > 0:
                pico2d.draw_rectangle(left, bottom, left + config.ENEMY_HP_BAR_WIDTH * ratio - 1,
                                      bottom + config.ENEMY_HP_BAR_HEIGHT - 1,
                                      215, 38, 45, filled=True)
        if assets.damage_font is not None:
            for number in world.damage_numbers:
                text = f"-{number.damage}"
                x = number.x - camera_x - len(text) * config.DAMAGE_NUMBER_FONT_SIZE / 4
                y = number.display_y - camera_y
                assets.damage_font.draw(x + 1, y - 1, text, (12, 15, 20))
                assets.damage_font.draw(x, y, text, (255, 224, 110))

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
            self.draw_attack_help(assets)
            assets.font.draw(x + image.w * scale + 16, y + 56,
                             f"{world.player.hp} / {config.MAX_HP}", (218, 228, 240))
            if world.player.invincible:
                assets.font.draw(x + image.w * scale + 16, y + 32, "무적 ON", (126, 238, 164))
            assets.font.draw(22, 48,
                             f"H 유지: 정면 방어 (피해 0)   적 공격 피해: {config.ENEMY_DAMAGE}",
                             (205, 218, 231))
            assets.font.draw(740, 48, "숫자 1~9: 해당 수만큼 적 소환", (205, 218, 231))
            assets.font.draw(22, 25,
                             "← → 이동   Shift 달리기   Space 이단 점프   F5 다시 시작",
                             (205, 218, 231))
            mode = "ON" if world.player.invincible else "OFF"
            assets.font.draw(740, 25, f"N 스테이지 이동 화살표 표시   P 무적 전환: {mode}",
                             (205, 218, 231))
            if world.player.state in ("DYING", "DEAD"):
                center = config.SCREEN_WIDTH / 2
                pico2d.draw_rectangle(center - 240, 322, center + 240, 400,
                                      12, 21, 33, filled=True)
                assets.font.draw(center - 175, 365, "쓰러졌습니다. F5 키로 다시 시작하세요.",
                                 (240, 211, 194))
