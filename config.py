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
PLAYER_BOUNDARY_PADDING = 68.0
PLAYER_HEIGHT = 146.0
BODY_DEPTH_TOLERANCE = 12.0
ATTACK_DEPTH_TOLERANCE = 32.0
WALK_SPEED = 300.0
RUN_SPEED = 720.0
ACCELERATION = 2400.0
FRICTION = 8000.0
GRAVITY = 1800.0
JUMP_SPEED = 650.0
DOUBLE_JUMP_SPEED = 850.0
RUN_DOUBLE_JUMP_SPEED = 1000.0
ENEMY_HALF_WIDTH = 32.0
ENEMY_BOUNDARY_PADDING = 88.0  # Occupied sprite envelope reaches 86.25px from the feet.
ENEMY_HEIGHT = 145.0
ENEMY_MAX_HP = 200
ENEMY_CORPSE_DELAY = 3.0
ENEMY_FADE_DURATION = 1.0
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
ENEMY_ATTACK_SPEED_RANGE = (0.8, 1.4)
ENEMY_ATTACK_REACH = 106.0
ENEMY_ACTIVE_FRAMES = (4, 5)  # zero-based columns of source row 4
ENEMY_FORMATION_DISTANCE = 240.0
ENEMY_FORMATION_RELEASE_DISTANCE = 320.0
ENEMY_FORMATION_LANES = 4
ENEMY_SPACING_MARGIN = 4.0
ENEMY_SPACING_TOLERANCE = 1.0
ENEMY_DEPTH_STEP = 32.0
ENEMY_ATTACK_SEPARATION_SPEED = 18.0
ENEMY_ATTACK_SEPARATION_SLOP = 8.0
ENEMY_SEPARATION_RATE = 10.0
SHAKE_DURATION = 0.2
SHAKE_STRENGTH = 8.0
PLAYER_HIT_SHAKE_STRENGTH = 16.0
UI_SCALE = 0.25
UI_MARGIN = 20
# Source PNG coordinates, converted from top-left (420, 145)-(1989, 234).
HP_FILL = (420, 170, 1569, 89)
KNOCKBACK_SPEED = 450.0
KNOCKBACK_FRICTION = 900.0
KNOCKBACK_RADIUS = 160.0
SPAWN_COUNTS = tuple(range(1, 10))

TITLE_IMAGE = "HOOD_MAN_TITLE_SCREEN_1280x720.png"
TITLE_SCREEN_DURATION = 2.0
PLAYER_IMAGE = "HoodMan_Sprite.png"
COMBAT_IMAGE = "HoodMan_BasicAttack_4Moves_8Frames_2048x1024.png"
COMBAT_JAB_FPS = 32.0
COMBAT_STRAIGHT_FPS = 20.0
COMBAT_KICK_FPS = 14.0
PLAYER_ACTIVE_FRAMES = (3, 4)
BLOOD_IMAGE = "Hood_man_blood_hit_effect_4x2.png"
HIT_EFFECT_FPS = 20.0
HIT_EFFECT_COLUMNS = 4
HIT_EFFECT_ROWS = 2
HIT_EFFECT_SCALE = 0.5
HIT_EFFECT_ANCHOR_X = 80.0
HIT_EFFECT_ANCHOR_Y = 128.0
# Key, name, one-based source row, damage, horizontal reach, attack height, FPS.
COMBAT_MOVE_SPECS = (
    ("a", "왼손 잽", 3, 10, 95.0, 146.0, COMBAT_JAB_FPS),
    ("s", "오른손 스트레이트", 4, 40, 105.0, 146.0, COMBAT_STRAIGHT_FPS),
    ("d", "왼발 차기", 1, 50, 115.0, 146.0, COMBAT_KICK_FPS),
    ("f", "오른발 차기", 2, 60, 130.0, 146.0, COMBAT_KICK_FPS),
)
COUNTER_PLAYER_IMAGE = "HoodMan_Counter_Player_2048x1024.png"
COUNTER_ENEMY_IMAGE = "HoodMan_Counter_Enemy_2048x1024.png"
COUNTER_DAMAGE = 80
COUNTER_FPS = 8.0
COUNTER_ENEMY_FPS = 6.0
COUNTER_RANGE = 140.0
COUNTER_DEPTH_TOLERANCE = 32.0
COUNTER_TRIGGER_FRAMES = (1, 2, 3, 4, 5)
COUNTER_PAIR_DISTANCE = 80.0
COUNTER_BOUNDARY_PADDING = 90.0
COUNTER_CARRY_SPEED = 180.0
COUNTER_CARRY_HEIGHT = 24.0
# Zero-based player/enemy poses held before the A-triggered follow-up.
COUNTER_HOLD_FRAMES = {"h": (1, 1), "j": (2, 2), "k": (1, 1), "l": (1, 0)}
# Key, technique, matching one-based player/enemy row, zero-based impact frame.
COUNTER_MOVE_SPECS = (
    ("h", "쳐내고 연타", 1, 4),
    ("j", "잡아 메치기", 2, 6),
    ("k", "단검 반격", 3, 4),
    ("l", "회전 발차기", 4, 5),
)
ENEMY_IMAGE = "HoodMan_StreetThug_FINAL_2048x1536.png"
CAR_IMAGE = "HOOD_MAN_car_attached_wheels_8f_pico2d.png"
PLAYER_CAR_HIT_IMAGE = "hoodman_car_hit_8frames_2048x256.png"
ENEMY_CAR_HIT_IMAGE = "street_thug_car_hit_8frames_2048x256.png"
CAR_STAGE_IMAGE = "cityStage-1.png"
CAR_SCALE = 0.75
CAR_FPS = 16.0
CAR_GROUND_Y = 64.0
CAR_GROUND_ANCHOR = 198.0  # Wheel contact measured from the top of a 512x256 cell.
CAR_HALF_WIDTH = 164.0  # Solid body only; exclude the exhaust trail.
CAR_HEIGHT = 90.0
CAR_DEPTH_TOLERANCE = 24.0
CAR_SPEED_RANGE = (1120.0, 1680.0)
CAR_INITIAL_DELAY = 0.35
CAR_PASS_DELAY = (0.4, 1.0)
CAR_SPAWN_MARGIN = 220.0
CAR_HIT_FPS = 12.0
CAR_HIT_SPEED = 360.0
CAR_HIT_FRICTION = 600.0
HP_IMAGE = "HoodMan_HP_pico2d.png"
STAGE_IMAGE = "newStage.png"
FACTORY_OUTSIDE_IMAGE = "factoryOutside-1_pico2d_1280x720.png"
FACTORY_EXTERIOR_IMAGE = "HOOD_MAN_Factory_Exterior_1672x941.png"
FACTORY_INSIDE_IMAGES = ("factoryInside-1.png", "factoryStage-2.png")
STAGE_IMAGES = (STAGE_IMAGE, "newStage-2.png", "cityStage-1.png", "cityStage-2.png",
                FACTORY_OUTSIDE_IMAGE, FACTORY_EXTERIOR_IMAGE, *FACTORY_INSIDE_IMAGES)
STAGE_LOADING_IMAGE = "HOOD_MAN_STAGE_LOADING_1280x720.png"
STAGE_LOADING_DURATION = 2.0
STAGE_LOADING_TRANSITIONS = ((1, 2), (2, 1), (3, 4), (4, 3), (5, 6), (6, 5))
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
STAGE_GROUND_ANCHORS = {FACTORY_OUTSIDE_IMAGE: 100.0, FACTORY_EXTERIOR_IMAGE: 100.0}
# World-space foot regions, below the buildings/props and above the foreground.
# Optional convex polygons override a stage's rectangle (counterclockwise vertices).
STAGE_WALKABLE_BOUNDS = (
    (0.0, 56.0, WORLD_WIDTH, 148.0),
    (0.0, 56.0, WORLD_WIDTH, 116.0),
    (0.0, 56.0, WORLD_WIDTH, 148.0),
    (0.0, 56.0, WORLD_WIDTH, 116.0),
    (0.0, 56.0, WORLD_WIDTH, 116.0),
    (0.0, 56.0, WORLD_WIDTH, 100.0),
    (0.0, 56.0, WORLD_WIDTH, 148.0),
    (0.0, 56.0, WORLD_WIDTH, 148.0),
)
STAGE_WALKABLE_POLYGONS = {}
# Spawn on the sidewalk, while pursuit can still use the full city floor.
STAGE_ENEMY_SPAWN_BOUNDS = {
    "cityStage-1.png": (0.0, GROUND_Y, WORLD_WIDTH, 148.0),
}

# State: (one-based source row, frames per second, loop).
PLAYER_ANIMATIONS = {
    "IDLE": (1, 7.0, True),
    "WALK": (2, 10.0, True),
    "RUN": (3, 13.0, True),
    "JUMP": (4, 10.0, False),
    "HIT": (6, 12.0, False),
    "CAR_HIT": (1, CAR_HIT_FPS, False),
    "DYING": (5, 10.0, False),
    "DEAD": (5, 10.0, False),
}
ENEMY_ANIMATIONS = {
    "IDLE": (1, 7.0, True),
    "WALK": (2, 10.0, True),
    "RUN": (3, 13.0, True),
    "ATTACK": (4, 12.0, False),
    "HIT": (5, 12.0, False),
    "CAR_HIT": (1, CAR_HIT_FPS, False),
    "KNOCKBACK": (5, 12.0, False),
    "DYING": (6, 10.0, False),
    "DEAD": (6, 10.0, False),
}
