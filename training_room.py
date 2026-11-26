"""Single-screen practice room with weapons placed on the supplied table."""

from dataclasses import dataclass

import config
from ar_soldier import ARSoldier
from axe_enemy import AxeEnemy
from drop_items import DropItem
from enemy import Enemy
from enemy02 import Enemy02
from researcher import Researcher
from shield_soldier import ShieldSoldier
from stage import Stage
from walkable import WalkableArea


@dataclass(frozen=True)
class PracticeOpponent:
    name: str
    enemy_type: type[Enemy]
    damage: int
    slam_damage: int | None = None


OPPONENTS = (
    PracticeOpponent("쇠몽둥이", Enemy, config.ENEMY_DAMAGE),
    PracticeOpponent("쌍몽둥이", Enemy02, config.ENEMY02_ATTACKS["clubs"][1], config.ENEMY02_ATTACKS["slam"][1]),
    PracticeOpponent("도끼", AxeEnemy, config.AXE_ENEMY_DAMAGE),
    PracticeOpponent("권총", Researcher, config.RESEARCHER_DAMAGE),
    PracticeOpponent("방패", ShieldSoldier, config.SHIELD_SOLDIER_DAMAGE),
    PracticeOpponent("AR 소총", ARSoldier, config.AR_SOLDIER_DAMAGE),
)
SELECTION_KEYS = {f"spawn_{i}": opponent for i, opponent in enumerate(OPPONENTS, 1)}


class TrainingTarget(Enemy):
    """Use the selected enemy's art and stats with passive practice behavior."""

    uses_melee_slots = False
    blocks_movement = False

    def __init__(self, opponent, x, facing, ground_y):
        self.opponent = opponent
        self.image_name = opponent.enemy_type.image_name
        self.animations = opponent.enemy_type.animations
        self.boundary_padding = opponent.enemy_type.boundary_padding
        self.max_hp = opponent.enemy_type.max_hp
        super().__init__(x, facing, ground_y=ground_y)

    @property
    def attack_damage(self):
        return self.opponent.damage

    def adjust_hp(self, delta):
        new_max = max(1, self.max_hp + delta)
        self.hp = max(1, self.hp + new_max - self.max_hp)
        self.max_hp = new_max

    def restore_hp(self):
        self.max_hp = self.opponent.enemy_type.max_hp
        self.hp = self.max_hp

    def take_damage(self, damage):
        self.last_hit_damage = damage
        self.hp = max(1, self.hp - damage)
        self.animation.set_state("HIT")
        self.animation.elapsed = 0.0
        return True

    def take_strong_hit(self, move, direction):
        return self.take_damage(move.damage)

    def start_rush_carry(self, move, direction):
        return self.take_damage(move.damage)

    def _update_ai(self, dt, player):
        self.animation.update(dt)
        if self.state == "HIT" and self.animation.finished:
            self.animation.set_state("IDLE")


class TrainingRoom(Stage):
    image_name = config.TRAINING_ROOM_IMAGE
    width = config.SCREEN_WIDTH
    camera_y_bounds = (0, 0)
    arrow_sides = ()
    table_slots = dict(config.TRAINING_TABLE_ITEMS)

    def __init__(self):
        super().__init__(walkable=WalkableArea.rectangle(*config.TRAINING_FLOOR), drop_items=[])
        self.selected_opponent = OPPONENTS[0]
        for kind in self.table_slots:
            self.place_on_table(kind)

    def can_return_to_table(self, player, kind):
        left, right = config.TRAINING_TABLE_X_BOUNDS
        return (kind in self.table_slots and player.grounded and left <= player.x <= right
                and abs(player.ground_y - config.TRAINING_TABLE_APPROACH_Y) <= config.WEAPON_PICKUP_DEPTH)

    def place_on_table(self, kind, pistol_ammo=None, rifle_ammo=None):
        approach = config.TRAINING_TABLE_APPROACH_Y
        item = DropItem(kind, self.table_slots[kind], approach, pistol_ammo=pistol_ammo, rifle_ammo=rifle_ammo,
                        support_height=config.TRAINING_TABLE_SURFACE_Y - approach)
        self.drop_items.append(item)
        return item

    @property
    def target(self):
        return self.enemies[0] if self.enemies else None

    def handle_target_input(self, controls, player):
        for key in controls.take_presses((*SELECTION_KEYS, "training_target")):
            if key == "training_target":
                if player.alive:
                    self.summon_target(player)
            else:
                self.selected_opponent = SELECTION_KEYS[key]

    def summon_target(self, player):
        # Leave room for a jab, including when the player faces the nearest wall.
        facing = player.facing
        distance = 92
        padding = self.selected_opponent.enemy_type.boundary_padding
        left, right = self.walkable.x_limits(player.ground_y, padding)
        if not left <= player.x + facing * distance <= right:
            facing = -facing
        x, y = self.walkable.project(player.x + facing * distance, player.ground_y, padding)
        self.enemies[:] = [TrainingTarget(self.selected_opponent, x, -facing, y)]
