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
WEAPON_DIVE_SHAKE_STRENGTH = 16.0  # Successful double-jump D landing hits only.
CAMERA_PLAYER_HEIGHT = 192.0  # Covers every current player/weapon/attack sprite.
CAMERA_TOP_MARGIN = 100.0
CAMERA_BOTTOM_MARGIN = 80.0
UI_SCALE = 0.25
UI_MARGIN = 20
# Source PNG coordinates, converted from top-left (420, 145)-(1989, 234).
HP_FILL = (420, 170, 1569, 89)
HP_DAMAGE_HOLD = 0.12
HP_DAMAGE_DURATION = 0.3
HP_DAMAGE_COLOR = (225, 50, 60)
KNOCKBACK_SPEED = 450.0
KNOCKBACK_FRICTION = 900.0
KNOCKBACK_RADIUS = 160.0
SPAWN_COUNTS = tuple(range(1, 10))

TITLE_IMAGE = "HOOD_MAN_TITLE_SCREEN_1280x720.png"
TITLE_SCREEN_DURATION = 2.0
PLAYER_IMAGE = "HoodMan_Sprite.png"
WEAPON_POSE_IMAGES = {
    "combat_knife": "HOOD_MAN_DAGGER_move and fight.png",
    "steel_pipe": "HOOD_MAN_STEEL_PIPE_move and fight.png",
}
WEAPON_POSE_SCALE = SPRITE_SCALE
WEAPON_SHEET_ROWS = {"combat_knife": 9, "steel_pipe": 8}
WEAPON_POSE_ROWS = {
    "combat_knife": {"IDLE": 1, "WALK": 2, "RUN": 3, "JUMP": 4,
                     "HIT": 5, "DYING": 6, "DEAD": 6},
    # The pipe sheet has attacks in rows 6..8, so use the shared death sprite.
    "steel_pipe": {"IDLE": 1, "WALK": 2, "RUN": 3, "JUMP": 4, "HIT": 5},
}
WEAPON_AIRBORNE_ROWS = {"combat_knife": 9, "steel_pipe": 8}
WEAPON_AIM_TIME_SCALE = 0.2
WEAPON_DIVE_TIME_SCALE = 2.0
WEAPON_DIVE_SPEED = 720.0
WEAPON_DIVE_FALL_SPEED = 1000.0
WEAPON_DIVE_AFTERIMAGE_INTERVAL = 0.04
WEAPON_DIVE_AFTERIMAGE_DURATION = 0.32
WEAPON_DIVE_AFTERIMAGE_OPACITY = 0.5
WEAPON_HIT_FPS = 40.0  # Brief 8-frame flinch, then equipped IDLE after 0.2 seconds.
COMBAT_IMAGE = "HoodMan_BasicAttack_4Moves_8Frames_2048x1024.png"
STRONG_ATTACK_IMAGE = "HoodMan_StrongAttacks_Uppercut_IDLE_FINAL_2048x1280.png"
STRONG_HIT_IMAGE = "HoodMan_Enemy_StrongHit_2048x1280.png"
STRONG_ATTACK_DAMAGE = 50
STRONG_ATTACK_FPS = 16.0
STRONG_HIT_FPS = 16.0
AIR_KICK_TIME_SCALE = 0.2
AIR_KICK_STRIKE_FRAMES = (3, 5)
AIR_KICK_HOLD_FRAME = 4
AIR_KICK_MAX_COUNT = 2
R_RAISE_TIME_SCALE = 0.2
R_READY_FRAME = 4
RUSH_SPEED = 720.0
RUSH_HEIGHT = 32.0
RUSH_PLAYER_HOLD_FRAME = 4
RUSH_ENEMY_HOLD_FRAME = 4
RUSH_CARRY_DISTANCE = PLAYER_HALF_WIDTH + ENEMY_HALF_WIDTH
RUSH_RELEASE_SPEED = 360.0
RUSH_RELEASE_FRICTION = 900.0
RUSH_RELEASE_SETTLE = 0.15
# The new artwork occupies less of each cell; match the existing actor heights.
SPRITE_IMAGE_SCALES = {
    **dict.fromkeys(WEAPON_POSE_IMAGES.values(), WEAPON_POSE_SCALE),
    STRONG_ATTACK_IMAGE: 1.0,
    STRONG_HIT_IMAGE: 1.0,
}
# Key, name, player row, enemy hit row, reach, height, active frames, knockback speed.
STRONG_MOVE_SPECS = (
    ("q", "양주먹 내지르기", 1, 1, 140.0, 146.0, (3, 4, 5), 0.0),
    ("w", "도약 양주먹 넉백", 2, 5, 150.0, 170.0, (3, 4, 5), KNOCKBACK_SPEED),
    ("e", "공중 연속 발차기", 3, 4, 140.0, 170.0, AIR_KICK_STRIKE_FRAMES, 0.0),
    ("r", "양주먹 올려치기", 4, 2, 130.0, 190.0, (4, 5), 0.0),
    ("t", "어퍼컷", 5, 3, 120.0, 190.0, (3, 4), 0.0),
)
COMBAT_JAB_FPS = 32.0
COMBAT_STRAIGHT_FPS = 20.0
COMBAT_KICK_FPS = 14.0
PLAYER_ACTIVE_FRAMES = (3, 4)
CLUB_HIT_IMAGE = "club_hit_effect_4x2.png"
PUNCH_KICK_HIT_IMAGE = "punch_kick_hit_effect_4x2.png"
HIT_EFFECT_IMAGES = (CLUB_HIT_IMAGE, PUNCH_KICK_HIT_IMAGE)
HIT_EFFECT_FPS = 20.0
HIT_EFFECT_COLUMNS = 4
HIT_EFFECT_ROWS = 2
HIT_EFFECT_SIZE = 128.0  # Display cell width; both 512px source cells use 0.25 scale.
# Key, name, one-based source row, damage, horizontal reach, attack height, FPS.
COMBAT_MOVE_SPECS = (
    ("a", "왼손 잽", 3, 10, 95.0, 146.0, COMBAT_JAB_FPS),
    ("s", "오른손 스트레이트", 4, 40, 105.0, 146.0, COMBAT_STRAIGHT_FPS),
    ("d", "왼발 차기", 1, 50, 115.0, 146.0, COMBAT_KICK_FPS),
    ("f", "오른발 차기", 2, 60, 130.0, 146.0, COMBAT_KICK_FPS),
)
WEAPON_NAMES = {"combat_knife": "단검", "steel_pipe": "쇠파이프"}
WEAPON_HIT_IMAGES = {"combat_knife": PUNCH_KICK_HIT_IMAGE, "steel_pipe": CLUB_HIT_IMAGE}
# The three new attacks inherit the existing A/S/D balance. Impact windows
# follow the source strike poses; overhead/jump attacks hit on their downswing.
WEAPON_MOVE_SPECS = {
    "combat_knife": (
        ("a", "단검 찌르기", 7, 10, 95.0, 146.0, COMBAT_JAB_FPS, (3, 4)),
        ("s", "단검 베기", 8, 40, 105.0, 146.0, COMBAT_STRAIGHT_FPS, (3, 4)),
        ("d", "도약 내려찌르기", 9, 50, 115.0, 146.0, COMBAT_KICK_FPS, (5, 6)),
    ),
    "steel_pipe": (
        ("a", "쇠파이프 찌르기", 6, 10, 95.0, 146.0, COMBAT_JAB_FPS, (3, 4)),
        ("s", "쇠파이프 휘두르기", 7, 40, 105.0, 146.0, COMBAT_STRAIGHT_FPS, (4, 5)),
        ("d", "도약 내려치기", 8, 50, 115.0, 146.0, COMBAT_KICK_FPS, (5, 6)),
    ),
}
# Retired H/J/K/L art is preserved but never loaded by normal gameplay.
ARCHIVED_COUNTER_IMAGES = (
    "before_sheets/HoodMan_Counter_Player_2048x1024.png",
    "before_sheets/HoodMan_Counter_Enemy_2048x1024.png",
)
ENEMY_IMAGE = "HoodMan_StreetThug_FINAL_2048x1536.png"
AXE_ENEMY_IMAGE = "axe_enemy_pico2d_2048x1792.png"
AXE_ENEMY_MAX_HP = 400
AXE_ENEMY_DAMAGE = 60
SHIELD_SOLDIER_IMAGE = "hoodman_shield_soldier.png"
SHIELD_SOLDIER_MAX_HP = 400
SHIELD_SOLDIER_DAMAGE = 40
SHIELD_SOLDIER_ACTIVE_FRAMES = (3, 4)  # Fifth-row shield swing, zero-based columns.
SHIELD_SOLDIER_GUARD_CHANCE = 0.5
SHIELD_SOLDIER_GUARD_DAMAGE_SCALE = 0.5
RESEARCHER_IMAGE = "hoodman_researcher_.png"  # Preserve the supplied filename.
RESEARCHER_MAX_HP = 200
RESEARCHER_DAMAGE = 30
RESEARCHER_MAGAZINE_SIZE = 7
RESEARCHER_SHOOT_RANGE = 480.0
RESEARCHER_SHOOT_FRAME = 3  # Muzzle flash in the fourth row, zero-based column.
RESEARCHER_AIM_DURATION = 0.5  # Game-time warning, independent of attack-speed rolls.
RESEARCHER_AIM_DOT_SPACING = 12.0
RESEARCHER_AIM_DOT_RADIUS = 2
RESEARCHER_AIM_COLOR = (255, 45, 55)
RESEARCHER_RELOAD_FPS = 8.0
# Source firing pose: cell center x=128, barrel exit (190, 120), feet y=231.
RESEARCHER_MUZZLE_X = 46.5
RESEARCHER_MUZZLE_HEIGHT = 83.25
RESEARCHER_BULLET_IMAGE = "bullet_for_researcher.png"
RESEARCHER_BULLET_SCALE = 0.125  # Copper body about 10x5px; trail grows backward.
RESEARCHER_BULLET_ANCHOR_Y = 127.5
RESEARCHER_BULLET_HALF_WIDTH = 5.0
RESEARCHER_BULLET_HALF_HEIGHT = 2.5
RESEARCHER_BULLET_SPEED = 900.0
RESEARCHER_BULLET_FPS = 16.0
RESEARCHER_BULLET_STRAIGHT_RANGE = 1125.0  # Preserve the former 1.25s straight flight.
RESEARCHER_BULLET_GRAVITY = 900.0  # After the straight range, in world px/s².
AR_SOLDIER_IMAGE = "AR_soldier_pico2d_2048x1792.png"
ARCHIVED_AR_SOLDIER_IMAGE = "before_sheets/AR_soldier.png"
AR_SOLDIER_MAX_HP = 300
AR_SOLDIER_DAMAGE = 10
AR_SOLDIER_MAGAZINE_SIZE = 20
AR_SOLDIER_RELOAD_FPS = 8.0
AR_SOLDIER_FIRE_INTERVAL = 0.1  # Ten rounds/second on the shared gameplay clock.
AR_SOLDIER_FIRE_FRAMES = (2, 3, 4, 5)  # Row-4 muzzle-flash/recoil loop, zero-based.
AR_SOLDIER_SHOOT_RANGE = 600.0
AR_SOLDIER_SHOOT_FRAME = 2  # First muzzle flash in source row 4, zero-based column.
AR_SOLDIER_AIM_DURATION = 1.0
# New planted firing pose: center x=128, barrel exit near (208, 143), feet y=248.
AR_SOLDIER_MUZZLE_X = 60.0
AR_SOLDIER_MUZZLE_HEIGHT = 78.75
RIFLE_BULLET_IMAGE = "rifle_bullet_flying_8frames_pico2d.png"
RIFLE_BULLET_SCALE = 0.0625  # Visible round/trail about 14x5px, not a full-size sprite.
RIFLE_BULLET_ANCHOR_Y = 127.5
RIFLE_BULLET_HALF_WIDTH = 7.5
RIFLE_BULLET_HALF_HEIGHT = 2.5
RIFLE_BULLET_SPEED = 1200.0
RIFLE_BULLET_FPS = 16.0
RIFLE_BULLET_RANGE = 1200.0  # Straight flight only, then expire; no landed ammunition.
ENEMY02_IMAGE = "HOOD_MAN_enemy02.png"
CITY_STAGE_IMAGES = ("cityStage1_ground_300px_1672x941.png", "cityStage2_ground_300px_1672x941.png")
ARCHIVED_CITY_STAGE_IMAGES = ("before_sheets/cityStage-1.png", "before_sheets/cityStage-2.png")
ENEMY02_STAGE_IMAGES = CITY_STAGE_IMAGES
ENEMY02_BOUNDARY_PADDING = 128.0  # Living attack/effect envelope reaches 126.75px.
# Attack name: (one-based source row, damage for the whole motion, active frames).
ENEMY02_ATTACKS = {
    "clubs": (4, 60, (3, 4, 5)),
    "slam": (5, 80, (5, 6)),
}
ENEMY02_LEAP_MIN_DISTANCE = 320.0
ENEMY02_LEAP_MAX_DISTANCE = 640.0
ENEMY02_LEAP_COOLDOWN = 2.0  # From landing/interruption until the next leap.
CAR_IMAGE = "before_sheets/HOOD_MAN_car_attached_wheels_8f_pico2d.png"  # Legacy diagnostics only.
PLAYER_CAR_HIT_IMAGE = "before_sheets/hoodman_car_hit_8frames_2048x256.png"
ENEMY_CAR_HIT_IMAGE = "before_sheets/street_thug_car_hit_8frames_2048x256.png"
ARCHIVED_CAR_HIT_IMAGES = (PLAYER_CAR_HIT_IMAGE, ENEMY_CAR_HIT_IMAGE)  # Legacy diagnostics only.
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
DROP_ITEM_IMAGES = {
    "combat_knife": "hoodman_drop_combat_knife_8f.png",
    "steel_pipe": "hoodman_drop_steel_pipe_8f.png",
}
DROP_ITEM_COUNT_RANGE = (15, 15)  # Fixed total per stage; kinds and positions stay random.
DROP_ITEM_FRAMES = 8
DROP_ITEM_FPS = 8.0
DROP_ITEM_SCALE = 0.5
# Source weapons bob above a separate shadow. Clip them independently so each
# frame's weapon bottom and the fixed shadow center share the same ground_y.
DROP_ITEM_BODY_TOPS = {
    "combat_knife": (102, 101, 100, 99, 100, 101, 102, 103),
    "steel_pipe": (96, 95, 94, 93, 94, 95, 96, 97),
}
DROP_ITEM_BODY_HEIGHTS = {"combat_knife": 40, "steel_pipe": 53}
DROP_ITEM_SHADOW_TOP = 155
DROP_ITEM_SHADOW_HEIGHT = 9
DROP_ITEM_HALF_WIDTH = 48.0
DROP_ITEM_HEIGHT = max(DROP_ITEM_BODY_HEIGHTS.values()) * DROP_ITEM_SCALE
DROP_ITEM_SHADOW_HALF_DEPTH = DROP_ITEM_SHADOW_HEIGHT / 2 * DROP_ITEM_SCALE
DROP_ITEM_EXIT_GAP = 24.0
WEAPON_PICKUP_RANGE = 72.0
WEAPON_PICKUP_DEPTH = 32.0
WEAPON_DROP_HAND_HEIGHT = 70.0
WEAPON_PROMPT_GAP = 14.0
HP_IMAGE = "HoodMan_HP_pico2d.png"
STAGE_IMAGE = "changed_first_map_no_door.png"
SECOND_STAGE_IMAGE = "newStage-2_floor300_1672x941.png"
ARCHIVED_SECOND_STAGE_IMAGE = "before_sheets/newStage-2.png"
ARCHIVED_TWO_FLOOR_IMAGE = "before_sheets/HoodMan_2F_Map_1672x941.png"
ARCHIVED_TWO_FLOOR_WALKABLE_BOUNDS = (0.0, 56.0, WORLD_WIDTH, 136.0)
DOOR_IMAGES = {
    "door": "HoodMan_Door_pico2d.png",
    "warehouse_shutter": "HoodMan_Warehouse_Shutter_pico2d.png",
}
DOOR_CELL_SIZE = 256
DOOR_FRAMES = 8
DOOR_FPS = 12.0
# Closed artwork bounds within a cell: left, top, width, height. Keep the hinge
# and shutter header fixed while the full transparent cell changes pose.
DOOR_CLOSED_BOUNDS = {
    "door": (69, 11, 110, 210),
    "warehouse_shutter": (17, 11, 219, 215),
}
# Opening rectangles measured in the background's top-left source coordinates.
STAGE_DOOR_SPECS = {
    STAGE_IMAGE: (
        ("door", (250, 400, 83, 173)),
        ("warehouse_shutter", (1333, 417, 211, 202)),
    ),
    ARCHIVED_TWO_FLOOR_IMAGE: (
        ("door", (182, 567, 83, 137)),
        ("door", (412, 253, 83, 137)),
        ("door", (1366, 253, 85, 137)),
        ("warehouse_shutter", (1334, 544, 214, 201)),
    ),
}
STAGE_DOOR_FLOORS = {STAGE_IMAGE: (0, 0), ARCHIVED_TWO_FLOOR_IMAGE: (0, 1, 1, 0)}
STAGE_DOOR_MAP_SIZE = (1672, 941)
# Source-background foreground props that must stay in front of animated doors.
# Preserve the warehouse air conditioner, its lower edge and mounting shadow.
STAGE_DOOR_FOREGROUND_RECTS = {STAGE_IMAGE: ((1482, 375, 78, 60),)}
# Archived map only: source rows 395..445, above the metal fascia.
STAGE_UPPER_FLOOR_BOUNDS = {ARCHIVED_TWO_FLOOR_IMAGE: (0.0, 452.0, WORLD_WIDTH, 502.0)}
UPPER_PLATFORM_JUMP_CLEARANCE = 24.0
# Feet follow the steps, not a vertical teleport. Both endpoints are on a floor.
STAGE_STAIR_PATHS = {
    ARCHIVED_TWO_FLOOR_IMAGE: (((238.0, 136.0), (252.0, 168.0),
                               (484.0, 454.0), (500.0, 476.0)),),
}
STAIR_SPEED = 240.0
STAIR_FOLLOW_DISTANCE = 100.0  # Enemy spacing along the steps, not on the waiting floor.
STAIR_ENTRY_RADIUS = 40.0
STAIR_QUEUE_RADIUS = 200.0
STAIR_QUEUE_GAP = 100.0
STAIR_JUMP_CATCH_RADIUS = 28.0
STAIR_JUMP_CATCH_MIN_HEIGHT = 16.0
STAIR_REGRAB_DELAY = 0.2
ENEMY_DROP_DELAY_RANGE = (0.0, 0.35)
FACTORY_OUTSIDE_IMAGE = "factory_loading_dock_no_stairs_1672x941.png"
ARCHIVED_FACTORY_OUTSIDE_IMAGE = "before_sheets/hood_man_factory_loading_dock_1672x941.png"
FACTORY_EXTERIOR_IMAGE = "factoryOutside_floor300.px.png"
ARCHIVED_FACTORY_EXTERIOR_IMAGE = "before_sheets/HOOD_MAN_Factory_Exterior_1672x941.png"
FACTORY_INSIDE_IMAGES = ("factoryInside-1.png", "factoryStage-2.png")
LAB_STAGE_IMAGES = ("labStage-1_floor300_1672x941.png", "labStage-2_floor300_1672x941.png")
ARCHIVED_LAB_STAGE_IMAGES = ("before_sheets/labStage-1_new_1672x941.png",
                            "before_sheets/labStage-2_new_1672x941.png")
BOSS_STAGE_IMAGES = ("bossStage_floor300_1672x941.png", "bossStage-2_floor300_1672x941.png")
ARCHIVED_BOSS_STAGE_IMAGES = ("before_sheets/bossStage-1.png", "before_sheets/bossStage-2.png")
STAGE_IMAGES = (STAGE_IMAGE, SECOND_STAGE_IMAGE, *CITY_STAGE_IMAGES,
                FACTORY_OUTSIDE_IMAGE, FACTORY_EXTERIOR_IMAGE, *FACTORY_INSIDE_IMAGES,
                *LAB_STAGE_IMAGES, *BOSS_STAGE_IMAGES)
STAGE_LOADING_IMAGE = "HOOD_MAN_STAGE_LOADING_1280x720.png"
STAGE_LOADING_DURATION = 2.0
STAGE_LOADING_TRANSITIONS = ((1, 2), (2, 1), (3, 4), (4, 3), (5, 6), (6, 5),
                             (7, 8), (8, 7), (9, 10), (10, 9))
STAGE_ARROW_IMAGES = {-1: "arrow_left_yellow.png", 1: "arrow_right_yellow.png"}
STAGE_ARROW_WIDTH = 96.0
STAGE_ARROW_Y = GROUND_Y
STAGE_ARROW_SWAY_AMPLITUDE = 6.0
STAGE_ARROW_SWAY_PERIOD = 1.6
STAGE_EXIT_MARGIN = 80.0
STAGE_ENTRY_MARGIN = 128.0
STAGE_SCALE = 1.0
STAGE_IMAGE_HEIGHT = 941.0
# Walking line measured upward from the source image's bottom edge (941 - 797).
STAGE_GROUND_Y = 144.0
STAGE_GROUND_ANCHORS = {
    FACTORY_OUTSIDE_IMAGE: 100.0,
    FACTORY_EXTERIOR_IMAGE: 100.0,
    # Keep feet on the raised lab walkway, above the foreground machinery.
    **dict.fromkeys(LAB_STAGE_IMAGES, 280.0),
}
# World-space foot regions, below the buildings/props and above the foreground.
# Optional convex polygons override a stage's rectangle (counterclockwise vertices).
STAGE_WALKABLE_BOUNDS = (
    # Flat first map: the full paved floor, source rows 620..900.
    # World y = 100 - 144 + 941 - source_y; stop before the foreground curb/drain.
    (0.0, -3.0, WORLD_WIDTH, 277.0),
    # Expanded second alley: source rows 658..941, below the entrance step bases.
    # The floor reaches the source bottom edge; pictured steps are background only.
    (0.0, -44.0, WORLD_WIDTH, 239.0),
    # New cities: the complete sidewalk and road, down to the source bottom edge.
    # World y = 100 - 144 + 941 - source_y; building feet are at rows 650 / 618.
    (0.0, -44.0, WORLD_WIDTH, 247.0),
    (0.0, -44.0, WORLD_WIDTH, 279.0),
    # Stair-free loading dock: full concrete floor, source rows 683..896.
    # The raised loading platform/fascia and foreground drainage grate are not floor.
    (0.0, 45.0, WORLD_WIDTH, 258.0),
    # Expanded factory exterior: source rows 657..941, below wall/prop bases.
    # Keep the original 100px ground anchor: world y = 941 - source_y.
    (0.0, 0.0, WORLD_WIDTH, 284.0),
    # factoryInside-1: full tiled floor below equipment/chair feet, before the front fascia.
    # Keep the 144px ground anchor: world y = 897 - source_y; source rows 725..900.
    (0.0, -3.0, WORLD_WIDTH, 172.0),
    # factoryStage-2: source rows 697..881, below equipment and inside the viewport.
    (0.0, 16.0, WORLD_WIDTH, 200.0),
    # New lab floors: below equipment/platform bases, before foreground metal grates.
    # Keep anchor 280: world y = 761 - source_y; source rows 583..870 / 522..809.
    (0.0, -109.0, WORLD_WIDTH, 178.0),
    (0.0, -48.0, WORLD_WIDTH, 239.0),
    # Expanded boss floors: below equipment/furniture, through the front tile lip.
    # Keep anchor 144: world y = 897 - source_y; source rows 650..925 / 655..917.
    (0.0, -28.0, WORLD_WIDTH, 247.0),
    (0.0, -20.0, WORLD_WIDTH, 242.0),
)
STAGE_WALKABLE_POLYGONS = {}
# Spawn on the sidewalk, while pursuit can still use the full city floor.
STAGE_ENEMY_SPAWN_BOUNDS = {
    CITY_STAGE_IMAGES[0]: (0.0, 200.0, WORLD_WIDTH, 247.0),
    CITY_STAGE_IMAGES[1]: (0.0, 208.0, WORLD_WIDTH, 279.0),
}
# City 1's pavement moved upward in the replacement art.
# Source rows 657..689 keep the whole weapon and shadow clear of the curb/road.
STAGE_DROP_ITEM_SPAWN_BOUNDS = {
    CITY_STAGE_IMAGES[0]: (0.0, 208.0, WORLD_WIDTH, 240.0),
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
# Rows 1..6 match the street thug. Row 7 is reserved stun art, never a state.
AXE_ENEMY_ANIMATIONS = {
    **ENEMY_ANIMATIONS,
    "CAR_HIT": (6, CAR_HIT_FPS, False),
}
RESEARCHER_ANIMATIONS = {
    **ENEMY_ANIMATIONS,
    "RELOAD": (5, RESEARCHER_RELOAD_FPS, False),
    "HIT": (6, 12.0, False),
    "KNOCKBACK": (6, 12.0, False),
    "DYING": (7, 10.0, False),
    "DEAD": (7, 10.0, False),
    "CAR_HIT": (7, CAR_HIT_FPS, False),
}
AR_SOLDIER_ANIMATIONS = {
    **ENEMY_ANIMATIONS,
    "RELOAD": (6, AR_SOLDIER_RELOAD_FPS, False),
    "HIT": (5, 12.0, False),
    "KNOCKBACK": (5, 12.0, False),
    "DYING": (7, 10.0, False),
    "DEAD": (7, 10.0, False),
    "CAR_HIT": (7, CAR_HIT_FPS, False),
}
SHIELD_SOLDIER_ANIMATIONS = {
    **ENEMY_ANIMATIONS,
    "GUARD": (4, 12.0, False),
    "ATTACK": (5, 12.0, False),
    "HIT": (6, 12.0, False),
    "KNOCKBACK": (6, 12.0, False),
    "DYING": (7, 10.0, False),
    "DEAD": (7, 10.0, False),
    "CAR_HIT": (7, CAR_HIT_FPS, False),
}
ENEMY02_ANIMATIONS = {
    **ENEMY_ANIMATIONS,
    "HIT": (6, 12.0, False),
    "KNOCKBACK": (6, 12.0, False),
    "DYING": (7, 10.0, False),
    "DEAD": (7, 10.0, False),
    "CAR_HIT": (7, CAR_HIT_FPS, False),
}
