"""Basic, strong and equipped attacks, hit reactions and shared effect choices."""

from collections import deque
from dataclasses import dataclass, replace

import config


class CrowdEscape:
    """Track distinct attackers and alternating key presses on the input clock."""

    def __init__(self):
        self.now = 0.0
        self.immune_until = 0.0
        self.last_hits = {}
        self.presses = deque(maxlen=config.CROWD_ESCAPE_PRESSES)

    @property
    def active(self):
        return self.immune_until - self.now > 1e-9

    @property
    def ready(self):
        return len(self.last_hits) >= config.CROWD_ESCAPE_ATTACKERS

    def clear_encounter(self):
        self.last_hits.clear()
        self.presses.clear()

    def advance(self, dt):
        self.now += dt
        if self.last_hits:
            cutoff = self.now - config.CROWD_ESCAPE_HIT_WINDOW - 1e-9
            self.last_hits = {enemy: time for enemy, time in self.last_hits.items() if time >= cutoff}
            if not self.ready:
                self.presses.clear()

    def record_hit(self, attacker):
        self.last_hits[attacker] = self.now

    def press(self, key):
        if not self.ready or key not in config.CROWD_ESCAPE_KEYS:
            return False
        if self.presses and self.presses[-1][0] == key:
            self.presses.clear()
        self.presses.append((key, self.now))
        if (len(self.presses) < config.CROWD_ESCAPE_PRESSES
                or self.now - self.presses[0][1] > config.CROWD_ESCAPE_INPUT_WINDOW + 1e-9):
            return False
        self.immune_until = self.now + config.CROWD_ESCAPE_DURATION
        self.clear_encounter()
        return True


@dataclass(frozen=True)
class Move:
    key: str
    name: str
    row: int
    damage: int
    reach: float
    height: float
    fps: float
    image_name: str = config.COMBAT_IMAGE
    active_frames: tuple = config.PLAYER_ACTIVE_FRAMES
    hit_image: str = config.PUNCH_KICK_HIT_IMAGE
    jump_attack: bool = False
    enemy_hit_row: int | None = None
    strike_during_dive: bool = False

    @property
    def state(self):
        return f"ATTACK_{self.key.upper()}"


MOVES = {
    f"combat_{key}": Move(key, name, row, damage, reach, height, fps)
    for key, name, row, damage, reach, height, fps in config.COMBAT_MOVE_SPECS
}
STRONG_MOVES = {
    f"combat_{key}": Move(key, name, row, damage, reach, height,
                           config.STRONG_ATTACK_FPS, image_name=config.STRONG_ATTACK_IMAGE,
                           active_frames=active_frames, enemy_hit_row=enemy_row)
    for key, name, row, damage, enemy_row, reach, height, active_frames
    in config.STRONG_MOVE_SPECS
}
ALL_MOVES = {**MOVES, **STRONG_MOVES}
COMBAT_INPUTS = ALL_MOVES.keys() | {"combat_r"}
WEAPON_MOVES = {
    kind: {
        f"combat_{key}": Move(key, name, row, damage, reach, height, fps,
                               image_name=config.WEAPON_POSE_IMAGES[kind],
                               active_frames=active_frames,
                               hit_image=config.WEAPON_HIT_IMAGES[kind],
                               jump_attack=key == "d")
        for key, name, row, damage, reach, height, fps, active_frames in specs
    }
    for kind, specs in config.WEAPON_MOVE_SPECS.items()
}
WEAPON_LOADOUTS = {kind: {**MOVES, **moves} for kind, moves in WEAPON_MOVES.items()}
KNIFE_THROW = Move("s", "단검 던지기", 6, config.KNIFE_THROW_DAMAGE, 0, 0, 16.0,
                  image_name=config.WEAPON_POSE_IMAGES["combat_knife"], active_frames=(),
                  hit_image=config.CLUB_HIT_IMAGE)
WEAPON_LOADOUTS["combat_knife"]["combat_s"] = KNIFE_THROW
PIPE_THROW = replace(KNIFE_THROW, name="쇠파이프 던지기", damage=config.PIPE_THROW_DAMAGE,
                     image_name=config.WEAPON_POSE_IMAGES["steel_pipe"])
WEAPON_LOADOUTS["steel_pipe"]["combat_s"] = PIPE_THROW
WEAPON_LOADOUTS["pistol"] = {key: move for key, move in MOVES.items() if key != "combat_a"}
WEAPON_LOADOUTS["ar_rifle"] = WEAPON_LOADOUTS["pistol"]
STEEL_CLUB_SWING = Move("a", "쇠몽둥이 휘두르기", 5, 40, 130.0, 146.0, 16.0,
                       image_name=config.PLAYER_STEEL_CLUB_IMAGE, active_frames=(4, 5),
                       hit_image=config.CLUB_HIT_IMAGE)
STEEL_CLUB_THROW = Move("s", "쇠몽둥이 던지기", 6, config.STEEL_CLUB_THROW_DAMAGE, 0, 0, 16.0,
                       image_name=config.PLAYER_STEEL_CLUB_IMAGE, active_frames=())
WEAPON_LOADOUTS["steel_club"] = {**MOVES, "combat_a": STEEL_CLUB_SWING, "combat_s": STEEL_CLUB_THROW}
STEEL_CLUB_DIVE = replace(MOVES["combat_d"], name="쇠몽둥이 내려찍기", damage=50, reach=140.0,
                          image_name=STEEL_CLUB_SWING.image_name, row=STEEL_CLUB_SWING.row,
                          active_frames=STEEL_CLUB_SWING.active_frames,
                          hit_image=STEEL_CLUB_SWING.hit_image, jump_attack=True)

AXE_SWING = Move("a", "도끼 휘두르기", 5, 60, 130.0, 146.0, 16.0,
                 image_name=config.PLAYER_AXE_IMAGE, active_frames=(4, 5), hit_image=config.CLUB_HIT_IMAGE)
AXE_THROW = Move("s", "도끼 던지기", 6, config.AXE_THROW_DAMAGE, 0, 0, 16.0,
                 image_name=config.PLAYER_AXE_IMAGE, active_frames=())
WEAPON_LOADOUTS["axe"] = {**MOVES, "combat_a": AXE_SWING, "combat_s": AXE_THROW}
AXE_DIVE = replace(AXE_SWING, key="d", name="도끼 내려찍기", damage=40, jump_attack=True)
SWORD_SLASH = Move("a", "검 베기", 5, 70, 140.0, 146.0, 16.0, image_name=config.PLAYER_SWORD_IMAGE,
                   active_frames=(3, 4, 5), hit_image=config.CLUB_HIT_IMAGE)
SWORD_DIVE = replace(SWORD_SLASH, key="d", name="검 급강하 베기", jump_attack=True, strike_during_dive=True)
WEAPON_LOADOUTS["sword"] = {"combat_a": SWORD_SLASH, "combat_d": MOVES["combat_d"], "combat_f": MOVES["combat_f"]}
SHIELD_BASH = replace(STEEL_CLUB_SWING, name="방패 밀치기", damage=20, reach=110.0,
                      image_name=config.PLAYER_SHIELD_IMAGE, active_frames=(3, 4, 5))
SHIELD_THROW = replace(STEEL_CLUB_THROW, key="d", name="방패 던지기", row=7, damage=config.SHIELD_THROW_DAMAGE,
                       image_name=config.PLAYER_SHIELD_IMAGE)
WEAPON_LOADOUTS["shield_item"] = {"combat_a": SHIELD_BASH, "combat_d": SHIELD_THROW, "combat_f": MOVES["combat_f"]}
DOUBLE_JUMP_LOADOUTS = {
    "steel_club": {**WEAPON_LOADOUTS["steel_club"], "combat_d": STEEL_CLUB_DIVE},
    "axe": {**WEAPON_LOADOUTS["axe"], "combat_d": AXE_DIVE},
    "sword": {**WEAPON_LOADOUTS["sword"], "combat_d": SWORD_DIVE},
}


def moves_for_weapon(weapon, *, double_jump=False):
    if double_jump and weapon in DOUBLE_JUMP_LOADOUTS:
        return DOUBLE_JUMP_LOADOUTS[weapon]
    return WEAPON_LOADOUTS.get(weapon, MOVES)
