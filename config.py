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
WALK_SPEED = 180.0
RUN_SPEED = 360.0
ACCELERATION = 1000.0
FRICTION = 1200.0
GRAVITY = 1800.0
JUMP_SPEED = 650.0
DOUBLE_JUMP_SPEED = 600.0
ENEMY_HALF_WIDTH = 32.0
ENEMY_HEIGHT = 145.0
ENEMY_SPEED = 120.0
ENEMY_ATTACK_DISTANCE = 88.0
ENEMY_DAMAGE = 20
ENEMY_ATTACK_INTERVAL = 1.0
ENEMY_ATTACK_REACH = 106.0
ENEMY_ACTIVE_FRAMES = (4, 5)  # zero-based columns of source row 4
HIT_INVULNERABILITY = 0.7
SHAKE_DURATION = 0.2
SHAKE_STRENGTH = 8.0
UI_SCALE = 0.25
UI_MARGIN = 20
# Source PNG coordinates, converted from top-left (420, 145)-(1989, 234).
HP_FILL = (420, 170, 1569, 89)
SPAWN_SCHEDULE = ((1.0, -1), (3.0, 1), (5.0, -1), (7.0, 1))

PLAYER_IMAGE = "HoodMan_Sprite.png"
ENEMY_IMAGE = "HoodMan_StreetThug_FINAL_2048x1536.png"
HP_IMAGE = "HoodMan_HP_pico2d.png"
STAGE_IMAGE = "stage.png"

# State: (one-based source row, frames per second, loop).
PLAYER_ANIMATIONS = {
    "IDLE": (1, 7.0, True),
    "WALK": (2, 10.0, True),
    "RUN": (3, 13.0, True),
    "JUMP": (4, 10.0, False),
    "HIT": (6, 12.0, False),
}
ENEMY_ANIMATIONS = {
    "IDLE": (1, 7.0, True),
    "WALK": (2, 10.0, True),
    "ATTACK": (4, 12.0, False),
}
