"""Basic, strong and equipped attacks, hit reactions and shared effect choices."""

from dataclasses import dataclass

import config


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
    knockback_speed: float = 0.0

    @property
    def state(self):
        return f"ATTACK_{self.key.upper()}"


MOVES = {
    f"combat_{key}": Move(key, name, row, damage, reach, height, fps)
    for key, name, row, damage, reach, height, fps in config.COMBAT_MOVE_SPECS
}
STRONG_MOVES = {
    f"combat_{key}": Move(key, name, row, config.STRONG_ATTACK_DAMAGE, reach, height,
                           config.STRONG_ATTACK_FPS, image_name=config.STRONG_ATTACK_IMAGE,
                           active_frames=active_frames, enemy_hit_row=enemy_row,
                           knockback_speed=knockback_speed)
    for key, name, row, enemy_row, reach, height, active_frames, knockback_speed
    in config.STRONG_MOVE_SPECS
}
ALL_MOVES = {**MOVES, **STRONG_MOVES}
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
# F remains the right-foot kick; A/S/D are replaced by the equipped attacks.
WEAPON_LOADOUTS = {kind: {**MOVES, **moves} for kind, moves in WEAPON_MOVES.items()}
WEAPON_LOADOUTS["pistol"] = {key: move for key, move in MOVES.items() if key != "combat_a"}
STEEL_CLUB_SWING = Move("a", "쇠몽둥이 휘두르기", 5, 40, 105.0, 146.0, 16.0,
                       image_name=config.PLAYER_STEEL_CLUB_IMAGE, active_frames=(4, 5),
                       hit_image=config.CLUB_HIT_IMAGE)
STEEL_CLUB_THROW = Move("s", "쇠몽둥이 던지기", 6, config.STEEL_CLUB_THROW_DAMAGE, 0, 0, 16.0,
                       image_name=config.PLAYER_STEEL_CLUB_IMAGE, active_frames=())
WEAPON_LOADOUTS["steel_club"] = {**MOVES, "combat_a": STEEL_CLUB_SWING, "combat_s": STEEL_CLUB_THROW}


def moves_for_weapon(weapon):
    return WEAPON_LOADOUTS.get(weapon, MOVES)
