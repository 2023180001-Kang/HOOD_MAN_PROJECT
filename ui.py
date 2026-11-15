"""Screen-fixed controls/HP and world-space enemy health/damage feedback."""

import config
from combat import MOVES
from counter import COUNTERS
from physics import clamp


class UI:
    def __init__(self):
        self.details_visible = True

    def draw_attack_help(self, assets):
        import pico2d

        pico2d.draw_rectangle(688, 616, config.SCREEN_WIDTH - 20, 704,
                              12, 21, 33, filled=True)
        assets.font.draw(704, 686, "기본 공격 · 피해량", (244, 204, 66))
        for index, move in enumerate(MOVES.values()):
            x = 704 + index % 2 * 270
            y = 659 - index // 2 * 24
            assets.font.draw(x, y, f"{move.key.upper()} {move.name} ({move.damage})",
                             (218, 228, 240))

    def draw_enemy_health(self, assets, world, camera_x, camera_y):
        if not self.details_visible:
            return
        import pico2d

        for enemy in world.enemies:
            if not enemy.alive:
                continue
            tile = assets.frames[enemy.sprite_image][enemy.animation.row - 1][enemy.animation.frame]
            height = (tile["clip"][3] + tile.get("offset_y", 0)) * config.SPRITE_SCALE
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
            assets.font.draw(x + image.w * scale + 16, y + 56,
                             f"{world.player.hp} / {config.MAX_HP}", (218, 228, 240))
            if not self.details_visible:
                return
            self.draw_attack_help(assets)
            if world.player.invincible:
                assets.font.draw(x + image.w * scale + 16, y + 32, "무적 ON", (126, 238, 164))
            for index, move in enumerate(COUNTERS.values()):
                assets.font.draw(22 + index * 310, 74,
                                 f"{move.key.upper()} {move.name} ({move.damage})", (244, 204, 66))
            if world.player.counter_holding:
                counter_help = "제압 유지: 방향키로 적을 들고 이동 / A 새 입력으로 후속 공격"
            elif world.stage.image_name in config.ENEMY02_STAGE_IMAGES:
                clubs, slam = config.ENEMY02_ATTACKS["clubs"][1], config.ENEMY02_ATTACKS["slam"][1]
                counter_help = (f"적 공격: 몽둥이 {clubs} / 착지 {slam}   "
                                f"반격: 지상 공격 중 {config.COUNTER_RANGE:g}px 내")
            else:
                counter_help = (f"적 공격 피해: {config.ENEMY_DAMAGE}   "
                                f"반격: 쇠파이프 공격 중 {config.COUNTER_RANGE:g}px 내")
            assets.font.draw(22, 48, counter_help, (205, 218, 231))
            assets.font.draw(740, 48, "1~9: 해당 수만큼 적 소환 (좌우 무작위)", (205, 218, 231))
            assets.font.draw(22, 25,
                             "← → ↑ ↓ 이동   Shift 달리기   Space 이단 점프   F5 다시 시작",
                             (205, 218, 231))
            mode = "ON" if world.player.invincible else "OFF"
            assets.font.draw(740, 25, f"N 이동 화살표   P 무적: {mode}   U 설명 숨김/표시",
                             (205, 218, 231))
            if world.stage.traffic is not None:
                assets.font.draw(22, 107, "도로 주의! 차량에 부딪히면 즉사합니다.", (255, 183, 100))
            if world.player.state in ("CAR_HIT", "DYING", "DEAD"):
                center = config.SCREEN_WIDTH / 2
                pico2d.draw_rectangle(center - 240, 322, center + 240, 400,
                                      12, 21, 33, filled=True)
                assets.font.draw(center - 175, 365, "쓰러졌습니다. F5 키로 다시 시작하세요.",
                                 (240, 211, 194))
