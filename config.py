"""Shared tuning values. Distances are world pixels; times are seconds."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
TARGET_FPS = 60
FIXED_DT = 1 / 120
MAX_FRAME_DT = 0.1
WORLD_WIDTH = 2560.0
GROUND_Y = 100.0
SPRITE_SCALE = 0.75
START_X = WORLD_WIDTH / 2
MAX_HP = 500
PLAYER_HALF_WIDTH = 29.0
PLAYER_HEIGHT = 146.0
WALK_SPEED = 300.0
RUN_SPEED = 720.0
ACCELERATION = 2400.0
FRICTION = 8000.0
GRAVITY = 1800.0
JUMP_SPEED = 650.0
DOUBLE_JUMP_SPEED = 850.0
RUN_DOUBLE_JUMP_SPEED = 1000.0
ENEMY_HALF_WIDTH = 32.0
ENEMY_HEIGHT = 145.0
ENEMY_MAX_HP = 200
ENEMY_HP_BAR_WIDTH = 48
ENEMY_HP_BAR_HEIGHT = 5
ENEMY_HP_BAR_GAP = 10
DAMAGE_NUMBER_DURATION = 0.45
DAMAGE_NUMBER_RISE = 18.0
DAMAGE_NUMBER_GAP = 24.0
DAMAGE_NUMBER_FONT_SIZE = 16
ENEMY_SPEED = 120.0
ENEMY_RUN_SPEEDS = (360.0, 420.0, 480.0, 540.0)
ENEMY_RUN_START_DISTANCE = 360.0
ENEMY_RUN_STOP_DISTANCE = 220.0
ENEMY_ATTACK_DISTANCE = 88.0
ENEMY_DAMAGE = 20
ENEMY_ATTACK_INTERVAL = 1.0
ENEMY_ATTACK_REACH = 106.0
ENEMY_ACTIVE_FRAMES = (4, 5)  # zero-based columns of source row 4
SHAKE_DURATION = 0.2
SHAKE_STRENGTH = 8.0
UI_SCALE = 0.25
UI_MARGIN = 20
# Source PNG coordinates, converted from top-left (420, 145)-(1989, 234).
HP_FILL = (420, 170, 1569, 89)
KNOCKBACK_SPEED = 450.0
KNOCKBACK_FRICTION = 900.0
KNOCKBACK_RADIUS = 160.0
SPAWN_COUNTS = tuple(range(1, 10))

PLAYER_IMAGE = "HoodMan_Sprite.png"
COMBAT_IMAGE = "HoodMan_BasicAttack_4Moves_8Frames_2048x1024.png"
COMBAT_FPS = 24.0
PLAYER_ACTIVE_FRAMES = (3, 4)
BLOOD_IMAGE = "Hood_man_blood_hit_effect_4x2.png"
HIT_EFFECT_FPS = 20.0
HIT_EFFECT_COLUMNS = 4
HIT_EFFECT_ROWS = 2
HIT_EFFECT_SCALE = 0.5
HIT_EFFECT_ANCHOR_X = 80.0
HIT_EFFECT_ANCHOR_Y = 128.0
# Key, name, one-based source row, damage, horizontal reach, attack height.
COMBAT_MOVE_SPECS = (
    ("a", "왼손 잽", 3, 20, 95.0, 146.0),
    ("s", "오른손 스트레이트", 4, 30, 105.0, 146.0),
    ("d", "왼발 차기", 1, 40, 115.0, 146.0),
    ("f", "오른발 차기", 2, 50, 130.0, 146.0),
)
ENEMY_IMAGE = "HoodMan_StreetThug_FINAL_2048x1536.png"
HP_IMAGE = "HoodMan_HP_pico2d.png"
STAGE_IMAGE = "newStage.png"
STAGE_IMAGES = (STAGE_IMAGE, "newStage-2.png")
STAGE_ARROW_IMAGES = {-1: "arrow_left_yellow.png", 1: "arrow_right_yellow.png"}
STAGE_ARROW_WIDTH = 96.0
STAGE_ARROW_Y = GROUND_Y
STAGE_ARROW_SWAY_AMPLITUDE = 6.0
STAGE_ARROW_SWAY_PERIOD = 1.6
STAGE_EXIT_MARGIN = 80.0
STAGE_ENTRY_MARGIN = 128.0
STAGE_SCALE = 1.0
# Walking line measured upward from the source image's bottom edge (941 - 797).
STAGE_GROUND_Y = 144.0

# State: (one-based source row, frames per second, loop).
PLAYER_ANIMATIONS = {
    "IDLE": (1, 7.0, True),
    "WALK": (2, 10.0, True),
    "RUN": (3, 13.0, True),
    "JUMP": (4, 10.0, False),
    "HIT": (6, 12.0, False),
    "DYING": (5, 10.0, False),
    "DEAD": (5, 10.0, False),
}
ENEMY_ANIMATIONS = {
    "IDLE": (1, 7.0, True),
    "WALK": (2, 10.0, True),
    "RUN": (3, 13.0, True),
    "ATTACK": (4, 12.0, False),
    "HIT": (5, 12.0, False),
    "KNOCKBACK": (5, 12.0, False),
    "DYING": (6, 10.0, False),
    "DEAD": (6, 10.0, False),
}
