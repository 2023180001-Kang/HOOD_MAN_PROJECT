"""Single-screen practice room with weapons placed on the supplied table."""

from dataclasses import dataclass

import config
from ar_soldier import ARSoldier
from axe_enemy import AxeEnemy
from drop_items import DropItem
from effects import DamageNumber
from enemy import Enemy
from enemy02 import Enemy02
from physics import clamp
from player import Player
from projectiles import PlayerProjectile
from researcher import Researcher
from shield_soldier import ShieldSoldier
from stage import Stage
from sword_enemy import SwordEnemy
from walkable import WalkableArea


@dataclass(frozen=True)
class PracticeOpponent:
    name: str
    enemy_type: type[Enemy]
    slam_damage: int | None = None


class TrainingPlayer(Player):
    def __init__(self, room):
        super().__init__()
        self.room = room

    def _apply_damage(self, damage):
        self.last_hit_damage = damage
        self.hp = max(1, self.hp - damage)
        self.room.damage_numbers.append(DamageNumber.above_body(
            self.body, damage, depth=self.ground_y - config.GROUND_Y, on_player=True))

    def adjust_hp(self, delta):
        if delta > 0:
            self.max_hp += delta
        self.hp = clamp(self.hp + delta, 1, self.max_hp)

    def restore_hp(self):
        self.hp = self.max_hp


class TrainingTarget:
    """Keep each opponent in place and use its native close-range attack."""

    uses_melee_slots = False
    uses_ranged_spacing = False
    blocks_movement = False
    practice_reach = config.ENEMY_ATTACK_REACH + config.PLAYER_HALF_WIDTH

    def __init__(self, opponent, x, facing, ground_y):
        self.opponent = opponent
        super().__init__(x, facing, ground_y=ground_y)

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
        dx = player.x - self.x
        nearby = (abs(dx) < self.practice_reach
                  and abs(player.ground_y - self.ground_y) <= config.ATTACK_DEPTH_TOLERANCE)
        if self.state == "ATTACK" and (not nearby or dx * self.facing < 0):
            self.stop()
        if self.state != "IDLE":
            super()._update_ai(dt, player)
            return
        self.cooldown = max(0.0, self.cooldown - dt)
        if nearby and self.cooldown == 0:
            if dx:
                self.facing = 1 if dx > 0 else -1
            self.start_attack()
        else:
            self.animation.update(dt)


class TrainingThug(TrainingTarget, Enemy):
    pass


class TrainingDualClub(TrainingTarget, Enemy02):
    pass


class TrainingSwordEnemy(TrainingTarget, SwordEnemy):
    pass


class TrainingAxe(TrainingTarget, AxeEnemy):
    def _update_ai(self, dt, player):
        if (self.navigation_target is not None
                or (self.state == "ATTACK" and self.attack_kind == "throw")):
            AxeEnemy._update_ai(self, dt, player)
        else:
            if self.state in ("WALK", "RUN"):
                self.stop()
            if self.state == "IDLE" and self.try_start_throw(dt, player):
                self.animation.update(dt)
                return
            super()._update_ai(dt, player)


class TrainingShield(TrainingTarget, ShieldSoldier):
    start_attack = ShieldSoldier.start_swing


class TrainingGunner(TrainingTarget):
    practice_reach = 200

    def _update_ai(self, dt, player):
        # Keep a point-blank shot from starting on the far side of the player.
        gap = abs(player.x - self.x)
        self.muzzle_x = min(type(self).muzzle_x, max(0, gap - self.projectile_type.half_width))
        super()._update_ai(dt, player)


class TrainingResearcher(TrainingGunner, Researcher):
    pass


class TrainingARSoldier(TrainingGunner, ARSoldier):
    pass


OPPONENTS = (
    PracticeOpponent("쇠몽둥이", TrainingThug),
    PracticeOpponent("쌍몽둥이", TrainingDualClub, config.ENEMY02_ATTACKS["slam"][1]),
    PracticeOpponent("도끼", TrainingAxe),
    PracticeOpponent("권총", TrainingResearcher),
    PracticeOpponent("방패", TrainingShield),
    PracticeOpponent("AR 소총", TrainingARSoldier),
    PracticeOpponent("검병", TrainingSwordEnemy, config.SWORD_ENEMY_ATTACKS["slam"][1]),
)
SELECTION_KEYS = {f"spawn_{i}": opponent for i, opponent in enumerate(OPPONENTS, 1)}


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
        self.projectiles[:] = [shot for shot in self.projectiles if isinstance(shot, PlayerProjectile)]
        self.enemies[:] = [self.selected_opponent.enemy_type(self.selected_opponent, x, -facing, y)]
