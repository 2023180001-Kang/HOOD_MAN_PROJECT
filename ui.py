"""Screen-fixed controls/HP and world-space enemy health/damage feedback."""

from math import ceil, floor, hypot

import config
from combat import STRONG_MOVES
from physics import clamp


PLAYER_BOUNDS_COLOR = (80, 220, 255)
ENEMY_BOUNDS_COLOR = (255, 185, 70)
STAIR_BOUNDS_COLOR = (180, 255, 150)


class UI:
    def __init__(self):
        self.details_visible = True
        self.floor_bounds_visible = False
        self._hp_player = None
        self._hp = config.MAX_HP
        self.damage_hp = float(config.MAX_HP)
        self._damage_start_hp = self.damage_hp
        self._damage_elapsed = 0.0

    def update(self, dt, player):
        """Keep the blue fill immediate while a red damage trail catches up."""
        hp = clamp(player.hp, 0, config.MAX_HP)
        if player is not self._hp_player or hp > self._hp:
            # A new player (F5) or healing must not retain an old damage trail.
            self._hp_player = player
            self._hp = hp
            self.damage_hp = self._damage_start_hp = float(hp)
            self._damage_elapsed = 0.0
            return
        if hp < self._hp:
            # Consecutive hits extend the red segment without jumping its end.
            self.damage_hp = self._damage_start_hp = max(self.damage_hp, self._hp)
            self._hp = hp
            self._damage_elapsed = 0.0
            return
        if self.damage_hp <= hp:
            return
        self._damage_elapsed += max(0.0, dt)
        if self._damage_elapsed + 1e-9 >= config.HP_DAMAGE_HOLD + config.HP_DAMAGE_DURATION:
            self.damage_hp = float(hp)
            return
        progress = clamp((self._damage_elapsed - config.HP_DAMAGE_HOLD)
                         / config.HP_DAMAGE_DURATION, 0.0, 1.0)
        self.damage_hp = hp + (self._damage_start_hp - hp) * (1 - progress) ** 2

    def draw_floor_bounds(self, world, camera_x, camera_y):
        """Outline actual foot limits on the floor, independently of jump height."""
        if not self.floor_bounds_visible:
            return
        import pico2d

        outlines = (
            (world.player.boundary_padding, PLAYER_BOUNDS_COLOR, False),
            (world.stage.spawner.enemy_type.boundary_padding, ENEMY_BOUNDS_COLOR, True),
        )
        for area in world.stage.floor_areas:
            for padding, color, dashed in outlines:
                self._draw_floor_outline(area.inset(padding), color, dashed, camera_x, camera_y)
        for stair in world.stage.stairs:
            for (ax, ay), (bx, by) in zip(stair.path, stair.path[1:]):
                pico2d.draw_line(ax - camera_x, ay - camera_y, bx - camera_x, by - camera_y,
                                 *STAIR_BOUNDS_COLOR)

    @staticmethod
    def _draw_floor_outline(vertices, color, dashed, camera_x, camera_y):
        import pico2d

        for index, (ax, ay) in enumerate(vertices):
            bx, by = vertices[(index + 1) % len(vertices)]
            if not dashed:
                pico2d.draw_line(ax - camera_x, ay - camera_y,
                                 bx - camera_x, by - camera_y, *color)
                continue
            # Shared limits stay readable as cyan between orange dashes.
            dx, dy = bx - ax, by - ay
            length = hypot(dx, dy)
            if length < 1e-9:
                continue
            for offset in range(0, ceil(length), 24):
                start, end = offset / length, min(offset + 12, length) / length
                pico2d.draw_line(ax + dx * start - camera_x, ay + dy * start - camera_y,
                                 ax + dx * end - camera_x, ay + dy * end - camera_y, *color)

    def draw_attack_help(self, assets, player):
        import pico2d

        pico2d.draw_rectangle(688, 616, config.SCREEN_WIDTH - 20, 704,
                              12, 21, 33, filled=True)
        title = ("권총 장착 · 근접 공격" if player.weapon == "pistol" else
                 f"{config.WEAPON_NAMES[player.weapon]} 공격 · 피해량"
                 if player.weapon in config.WEAPON_NAMES else "기본 공격 · 피해량")
        assets.font.draw(704, 686, title, (244, 204, 66))
        for index, move in enumerate(player.moves.values()):
            x = 704 + index % 2 * 270
            y = 659 - index // 2 * 24
            assets.font.draw(x, y, f"{move.key.upper()} {move.name} ({move.damage})",
                             (218, 228, 240))
        pico2d.draw_rectangle(688, 436, config.SCREEN_WIDTH - 20, 610,
                             12, 21, 33, filled=True)
        assets.font.draw(704, 590, "강화 기본 공격 · 피해량", (126, 218, 255))
        strong_moves = [move for move in STRONG_MOVES.values()
                        if player.weapon != "pistol" or move.key != "r"]
        for index, move in enumerate(strong_moves):
            x = 704 + index % 2 * 270
            y = 565 - index // 2 * 23
            assets.font.draw(x, y, f"{move.key.upper()} {move.name} ({move.damage})",
                             (218, 228, 240))
        kick_help = ("슬로 대기 중: ←/→ 전환 · E 두 번째 발차기 (1/2)"
                     if player.air_kick_phase == "WAIT" else
                     "E: ←/→ 공중 방향 전환 · 최대 2회 후 복귀")
        assets.font.draw(704, 493, kick_help, (126, 218, 255))
        if player.weapon == "pistol":
            r_help = "R 권총 재장전 · 점프 중에도 사용 가능"
        elif player.raise_punch_phase == "RAISE":
            r_help = "R 슬로 모션: R 다시 눌러 공격"
        else:
            r_help = "R: 주변 슬로 모션 → R 재입력으로 타격"
        assets.font.draw(704, 470, r_help, (126, 218, 255))
        assets.font.draw(704, 447, "W 유지: ←/→ 비행 전환 · 적 동반 / 놓으면 해제", (126, 218, 255))

    def draw_enemy_health(self, assets, world, camera_x, camera_y):
        import pico2d

        for enemy in world.enemies:
            if not enemy.alive:
                continue
            tile = assets.frames[enemy.sprite_image][enemy.animation.row - 1][enemy.animation.frame]
            scale = config.SPRITE_IMAGE_SCALES.get(enemy.sprite_image, config.SPRITE_SCALE)
            height = (tile["clip"][3] + tile.get("offset_y", 0)) * scale
            left = enemy.x - camera_x - config.ENEMY_HP_BAR_WIDTH / 2
            bottom = enemy.y - camera_y + height + config.ENEMY_HP_BAR_GAP
            right = left + config.ENEMY_HP_BAR_WIDTH
            ratio = clamp(enemy.hp / enemy.max_hp, 0.0, 1.0)
            pico2d.draw_rectangle(left - 1, bottom - 1, right,
                                  bottom + config.ENEMY_HP_BAR_HEIGHT, 12, 12, 16, filled=True)
            pico2d.draw_rectangle(left, bottom, right - 1,
                                  bottom + config.ENEMY_HP_BAR_HEIGHT - 1, 50, 15, 20, filled=True)
            if ratio > 0:
                pico2d.draw_rectangle(left, bottom, left + config.ENEMY_HP_BAR_WIDTH * ratio - 1,
                                      bottom + config.ENEMY_HP_BAR_HEIGHT - 1,
                                      215, 38, 45, filled=True)
        if self.details_visible and assets.damage_font is not None:
            for number in world.damage_numbers:
                text = f"-{number.damage}"
                x = number.x - camera_x - len(text) * config.DAMAGE_NUMBER_FONT_SIZE / 4
                y = number.display_y - camera_y
                assets.damage_font.draw(x + 1, y - 1, text, (12, 15, 20))
                assets.damage_font.draw(x, y, text, (255, 224, 110))

    def draw_pickup_prompt(self, assets, world, camera_x, camera_y):
        if not self.details_visible or assets.font is None:
            return
        item = world.pickup_item
        if item is None:
            return
        x = item.x - camera_x - 5
        y = (item.ground_y - camera_y
             + item.display_height
             + config.WEAPON_PROMPT_GAP)
        assets.font.draw(x + 1, y - 1, "G", (12, 15, 20))
        assets.font.draw(x, y, "G", (255, 224, 110))

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
            # Cover whole pixels: SDL truncates fractional rectangle sizes,
            # otherwise leaving blue slivers along the bottom and right edges.
            mask_left = floor(x + (left + width * ratio) * scale)
            mask_bottom = floor(y + bottom * scale)
            mask_right = ceil(x + (left + width) * scale)
            mask_top = ceil(y + (bottom + height) * scale)
            pico2d.draw_rectangle(
                mask_left, mask_bottom, mask_right - 1, mask_top - 1,
                8, 15, 24, filled=True,
            )
            if self._hp_player is world.player and self._hp == world.player.hp:
                damage_ratio = clamp(self.damage_hp / config.MAX_HP, ratio, 1.0)
                if damage_ratio > ratio:
                    damage_right = ceil(x + (left + width * damage_ratio) * scale)
                    pico2d.draw_rectangle(
                        mask_left, mask_bottom, damage_right - 1, mask_top - 1,
                        *config.HP_DAMAGE_COLOR, filled=True,
                    )
        if assets.font is not None:
            assets.font.draw(x + image.w * scale + 16, y + 56,
                             f"{world.player.hp} / {config.MAX_HP}", (218, 228, 240))
            if world.player.weapon == "pistol":
                assets.font.draw(x + image.w * scale + 16, y + 8,
                                 f"권총 {world.player.pistol_ammo} / {config.PLAYER_PISTOL_MAGAZINE_SIZE}",
                                 (255, 224, 110))
            if not self.details_visible:
                return
            # Help is screen-fixed UI, independent of the world camera.
            self.draw_attack_help(assets, world.player)
            floor_mode = "ON" if self.floor_bounds_visible else "OFF"
            assets.font.draw(22, y - 22, f"F4 바닥 이동 범위: {floor_mode}", (205, 218, 231))
            if self.floor_bounds_visible:
                assets.font.draw(22, y - 46, "주인공: 하늘색 실선", PLAYER_BOUNDS_COLOR)
                assets.font.draw(250, y - 46, "적: 주황색 점선", ENEMY_BOUNDS_COLOR)
            if world.stage.doors:
                assets.font.draw(22, y - 70, "F3 문 / 창고문 열기·닫기", (205, 218, 231))
            if world.stage.stairs:
                floor_label = ("계단 정지 중" if world.player.staircase and world.player.state == "IDLE" else
                               "계단 이동 중" if world.player.staircase else
                               "1층으로 낙하 중" if world.player.falling_from_upper else
                               f"{world.player.floor + 1}층")
                assets.font.draw(22, y - 94, f"{floor_label} · 계단 ↑/↓ 이동·반전 / 키 놓기: 정지",
                                 (180, 255, 150))
                assets.font.draw(22, y - 118, "점프로 계단 진입 · Space/←/→: 이탈 · 이단 점프 후 ↑: 2층 착지",
                                 (180, 255, 150))
            if world.player.invincible:
                assets.font.draw(x + image.w * scale + 16, y + 32, "무적 ON", (126, 238, 164))
            if world.player.weapon == "pistol":
                action = "재장전 중" if world.player.state == "RELOAD" else "A키 사격"
                assets.font.draw(22, 132, f"권총 {action} · 피해 20 · 7발 후 자동 재장전",
                                 (126, 218, 255))
            elif world.player.weapon == "steel_club":
                assets.font.draw(22, 132, "A 휘두르기 · S 던지기 · 바닥에 떨어진 쇠몽둥이 근처에서 G 회수",
                                 (126, 218, 255))
            elif world.player.weapon in config.WEAPON_NAMES:
                phase = world.player.weapon_leap_phase
                if phase == "AIM":
                    help_text = "슬로 모션: 방향키로 공중 조준 / D 다시 눌러 빠르게 내려찍기"
                elif phase in ("DIVE", "LANDING"):
                    help_text = "시간 가속: 선택한 방향으로 내려찍기!"
                else:
                    help_text = "무기 내려찍기: Space 두 번 → D 슬로 모션 / 방향키 조준 → D 급강하"
                assets.font.draw(22, 132, help_text, (126, 218, 255))
            source_index = world.stage.spawn_enemy_stage_index
            source_image = config.STAGE_IMAGES[source_index]
            if source_image in config.ENEMY02_STAGE_IMAGES:
                enemy_name = "도시 적"
                clubs, slam = config.ENEMY02_ATTACKS["clubs"][1], config.ENEMY02_ATTACKS["slam"][1]
                enemy_help = f"적 공격: 몽둥이 {clubs} / 착지 {slam}"
            elif source_image in config.AXE_ENEMY_STAGE_IMAGES:
                enemy_name = "도끼 적"
                enemy_help = f"적 공격: 도끼 {config.AXE_ENEMY_DAMAGE}"
            elif source_image in config.FACTORY_INSIDE_IMAGES:
                enemy_name = "연구원"
                enemy_help = (f"적 권총 {config.RESEARCHER_DAMAGE} · "
                              f"{config.RESEARCHER_MAGAZINE_SIZE}발 후 재장전")
            elif source_image in config.LAB_STAGE_IMAGES:
                enemy_name = "방패 병사"
                enemy_help = (f"적 공격: 방패 {config.SHIELD_SOLDIER_DAMAGE} · "
                               f"HP {config.SHIELD_SOLDIER_MAX_HP} · 방어 중 받는 피해 50%")
            elif source_image in config.BOSS_STAGE_IMAGES:
                enemy_name = "AR 병사"
                enemy_help = (f"적 공격: 소총 연사 {config.AR_SOLDIER_DAMAGE} · "
                              f"HP {config.AR_SOLDIER_MAX_HP} · "
                              f"{config.AR_SOLDIER_MAGAZINE_SIZE}발 후 재장전")
            else:
                enemy_name = "기본 적"
                enemy_help = f"적 공격 피해: {config.ENEMY_DAMAGE}"
            assets.font.draw(22, 48, enemy_help, (205, 218, 231))
            cycle_label = "M 소환 적 고정" if world.stage.index == 0 else "M 소환 적 순환"
            assets.font.draw(740, 72, f"{cycle_label}: {source_index + 1}번 맵 · {enemy_name}",
                             (205, 218, 231))
            sources = "좌우/열린 문 무작위" if world.stage.doors else "좌우 무작위"
            assets.font.draw(740, 48, f"1~9: 해당 수만큼 적 소환 ({sources})", (205, 218, 231))
            assets.font.draw(22, 25,
                             "← → ↑ ↓ 이동   Shift 달리기   Space 이단 점프   G 획득/버리기   F5 재시작",
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
