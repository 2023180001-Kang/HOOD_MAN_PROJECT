"""Final boss with two rifle magazines, a recoverable knife and a leaping strike."""

from itertools import cycle
from math import hypot

import config
from collision import same_floor
from enemy import Enemy
from enemy02 import Enemy02
from enemy_spacing import weapon_pickup_waypoint
from projectiles import EnemyKnifeProjectile, RifleBullet


class FinalBoss(Enemy02):
    max_hp = 400
    image_name = config.FINAL_BOSS_IMAGE
    boundary_padding = 96
    formation_ground_min = None
    animations = {
        **config.ENEMY_ANIMATIONS,
        "AIM": (6, 8, False), "FIRE": (6, 10, False), "RELOAD": (7, 8, False),
        "HIT": (11, 12, False), "KNOCKBACK": (11, 12, False),
        "DYING": (12, 10, False), "DEAD": (12, 10, False), "CAR_HIT": (12, 10, False),
    }
    basic_attack = "punch"
    attacks = {
        "punch": (4, 40, (4, 5)), "kick": (5, 50, (4, 5)),
        "stab": (8, 30, (4, 5)), "throw": (9, EnemyKnifeProjectile.damage, ()),
        "slam": (10, 60, (6,)), "air_slam": (10, 60, (5,)),
    }
    airborne_frames = (2, 3, 4, 5)
    leap_min_distance = 0
    aim_duration = 1.0
    bullet_damage = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ammo = config.AR_SOLDIER_MAGAZINE_SIZE
        self.reserve_magazines = 1
        self.reload_elapsed = 0.0
        self.fire_remaining = 0.0
        self.aim_remaining = 0.0
        self.shot_origin = None
        self.has_knife = True
        self.knife_role = None
        self.melee_sequence = cycle(("punch", "kick", "stab", "throw"))

    @property
    def uses_melee_slots(self):
        return self.ammo == 0 and self.reserve_magazines == 0 and self.state != "FIRE"

    @property
    def death_drop_kind(self):
        return "combat_knife" if self.has_knife else None

    @property
    def attack_damage(self):
        if self.ammo or self.reserve_magazines or self.state == "FIRE":
            return self.bullet_damage
        return super().attack_damage

    @property
    def aim_line(self):
        if self.state != "AIM":
            return None
        x, lane, height, facing = self.shot_origin
        end = x + facing * RifleBullet.straight_range
        left, _, right, _ = self.walkable.bounds
        return x, lane + height, min(right, max(left, end)), lane + height

    def _aim_at(self, player):
        gap = player.x - self.x
        if gap:
            self.facing = 1 if gap > 0 else -1
        muzzle = min(65.0, abs(gap))
        self.shot_origin = (self.x + self.facing * muzzle, self.ground_y, 92.0, self.facing)
        self.vx = self.ground_vy = 0.0
        self.running = False
        self.aim_remaining = self.aim_duration
        self.animation.set_state("AIM")

    def _update_rifle(self, dt, player):
        if self.state == "AIM":
            # Hold the fourth cell with the rifle raised. The muzzle flash starts at cell five.
            ready_pose = 3 / self.animations["AIM"][1]
            self.animation.elapsed = min(ready_pose, self.animation.elapsed + dt)
            self.aim_remaining -= dt
            if self.aim_remaining <= 1e-9:
                self.fire_remaining = self.aim_remaining
                self.animation.set_state("FIRE")
            return
        if self.state == "FIRE":
            self.fire_remaining -= dt
            if self.ammo or self.fire_remaining > 1e-9:
                return
            self.animation.set_state("IDLE")
        if self.ammo == 0:
            if self.reserve_magazines:
                self.animation.set_state("RELOAD")
                self.reload_elapsed += dt
                # Resume the same reload after hit stun.
                self.animation.elapsed = self.reload_elapsed
                if self.animation.finished:
                    self.reserve_magazines -= 1
                    self.ammo = config.AR_SOLDIER_MAGAZINE_SIZE
                    self.animation.set_state("IDLE")
            return
        if (same_floor(self, player) and abs(player.x - self.x) <= config.AR_SOLDIER_SHOOT_RANGE
                and abs(player.ground_y - self.ground_y) <= config.ATTACK_DEPTH_TOLERANCE):
            self._aim_at(player)
        else:
            Enemy._update_ai(self, dt, player)

    def _start_move(self, kind, *, air_contact=False):
        self.attack_kind = kind
        self.air_contact_attack = self.air_contact_pending = air_contact
        speed = 1.5 if kind in ("punch", "kick") else 1.0
        self.animation.definitions["ATTACK"] = (self.attacks[kind][0], self.attack_fps * speed, False)
        self.vx = self.ground_vy = 0.0
        Enemy.start_attack(self)
        self.cooldown /= speed

    def start_attack(self, *, air_contact=False):
        if air_contact:
            self._start_move("air_slam", air_contact=True)
            return
        if self.has_knife:
            self._start_move(next(self.melee_sequence))
        elif self.attack_kind == "kick" and self.leap_cooldown <= 0 and self.jump_height == 0:
            self._begin_leap()
        else:
            self._start_move("kick" if self.attack_kind == "punch" else "punch")

    def start_leap(self, player):
        if self.navigation_target is not None:
            return False
        gap = hypot(player.x - self.x, player.ground_y - self.ground_y)
        if gap < config.ENEMY02_LEAP_MIN_DISTANCE and self.attack_kind != "throw":
            return False
        return super().start_leap(player)

    def _update_ai(self, dt, player):
        ready = (self.alive and player.alive and not self.knockback_started
                 and not self.falling_from_upper and self.navigation_target is None)
        if (ready and self.state in ("IDLE", "WALK", "RUN", "AIM", "FIRE", "RELOAD")
                and (self.ammo or self.reserve_magazines or self.state == "FIRE")):
            self._update_rifle(dt, player)
            return
        if (ready and self.has_knife and self.state in ("IDLE", "WALK", "RUN") and self.cooldown <= 0
                and same_floor(self, player) and abs(player.ground_y - self.ground_y) <= config.ATTACK_DEPTH_TOLERANCE
                and config.ENEMY_ATTACK_REACH + config.PLAYER_HALF_WIDTH <= abs(player.x - self.x)
                < config.ENEMY02_LEAP_MIN_DISTANCE):
            self.facing = 1 if player.x > self.x else -1
            self._start_move("throw")
            return
        super()._update_ai(dt, player)

    def take_projectile(self):
        if not self.alive:
            return None
        if self.state == "FIRE" and self.ammo and self.fire_remaining <= 1e-9:
            x, lane, height, facing = self.shot_origin
            bullet = RifleBullet(x + facing * RifleBullet.half_width, lane, height, facing, self.floor, shooter=self)
            bullet.damage = self.bullet_damage
            shots_fired = config.AR_SOLDIER_MAGAZINE_SIZE - self.ammo
            self.animation.elapsed = (4 + shots_fired % 4 + 1e-9) / self.animations["FIRE"][1]
            self.ammo -= 1
            self.fire_remaining += config.AR_SOLDIER_FIRE_INTERVAL
            return bullet
        if (self.state == "ATTACK" and self.attack_kind == "throw" and self.has_knife
                and self.animation.frame >= EnemyKnifeProjectile.release_frame):
            self.has_knife = False
            forward, height = EnemyKnifeProjectile.release_offset
            return EnemyKnifeProjectile(self.x + self.facing * forward * config.SPRITE_SCALE, self.ground_y,
                                        self.jump_height + height * config.SPRITE_SCALE, self.facing,
                                        self.floor, shooter=self)
        return None


def assign_knife_roles(distant, rng):
    roles = {boss.knife_role for boss in distant}
    if len(distant) < 2 or roles == {"pursue", "recover"}:
        return
    deciding = [boss for boss in distant if boss.knife_role is None]
    if not deciding:
        # The remaining group lost everyone in one role.
        deciding = distant
        roles.clear()
    # Existing assignments survive later throwers joining the same retreat.
    minimum = int("recover" not in roles)
    maximum = len(deciding) - int("pursue" not in roles)
    recovering = set(rng.sample(deciding, rng.randint(minimum, maximum)))
    for boss in deciding:
        boss.knife_role = "recover" if boss in recovering else "pursue"


def update_knife_recovery(enemies, items, player, rng):
    """Split distant unarmed bosses between pursuit and recovery on the player's floor."""
    if not player.alive:
        return
    bosses = [e for e in enemies if isinstance(e, FinalBoss) and e.alive and same_floor(e, player)]
    distant = []
    for boss in bosses:
        gap = hypot(player.x - boss.x, player.ground_y - boss.ground_y)
        if boss.has_knife or gap <= config.ENEMY_FORMATION_DISTANCE:
            boss.knife_role = None
        else:
            distant.append(boss)
    if not distant:
        return
    if len(bosses) == 1:
        distant[0].knife_role = None
    else:
        assign_knife_roles(distant, rng)

    knives = [item for item in items if item.kind == "combat_knife" and item.grounded
              and not item.support_height and same_floor(item, player)]
    for boss in distant:
        if not knives:
            return
        if (boss.knife_role == "pursue" or boss.knockback_started or boss.falling_from_upper
                or boss.navigation_target is not None or boss.state not in ("IDLE", "WALK", "RUN")):
            continue
        nearest = min(knives, key=lambda item: hypot(item.x - boss.x, item.ground_y - boss.ground_y))
        knives.remove(nearest)
        if (abs(nearest.x - boss.x) <= config.WEAPON_PICKUP_RANGE
                and abs(nearest.ground_y - boss.ground_y) <= config.WEAPON_PICKUP_DEPTH):
            items.remove(nearest)
            boss.has_knife = True
            boss.knife_role = None
        else:
            boss.navigation_target = weapon_pickup_waypoint(boss, nearest, player)
