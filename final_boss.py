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
        "AIM": (6, 4, False), "FIRE": (6, 10, False), "RELOAD": (7, 8, False),
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
        self.shot_origin = None
        self.has_knife = True
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
        self.animation.set_state("AIM")

    def _update_rifle(self, dt, player):
        if self.state == "AIM":
            self.animation.update(dt)
            if self.animation.elapsed + 1e-9 >= self.aim_duration:
                self.fire_remaining = self.aim_duration - self.animation.elapsed
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
        self.animation.definitions["ATTACK"] = (self.attacks[kind][0], self.attack_fps, False)
        self.vx = self.ground_vy = 0.0
        Enemy.start_attack(self)

    def start_attack(self, *, air_contact=False):
        if air_contact:
            self._start_move("air_slam", air_contact=True)
            return
        kind = next(self.melee_sequence)
        while not self.has_knife and kind in ("stab", "throw"):
            kind = next(self.melee_sequence)
        self._start_move(kind)

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

    def recover_knife(self, items, player):
        if (self.has_knife or not self.alive or not player.alive or self.knockback_started
                or self.navigation_target is not None or self.state not in ("IDLE", "WALK", "RUN")):
            return
        knives = (item for item in items if item.kind == "combat_knife" and item.grounded
                  and not item.support_height and same_floor(self, item))
        nearest = min(knives, key=lambda item: hypot(item.x - self.x, item.ground_y - self.ground_y), default=None)
        if nearest is None:
            return
        if (abs(nearest.x - self.x) <= config.WEAPON_PICKUP_RANGE
                and abs(nearest.ground_y - self.ground_y) <= config.WEAPON_PICKUP_DEPTH):
            items.remove(nearest)
            self.has_knife = True
        else:
            self.navigation_target = weapon_pickup_waypoint(self, nearest, player)
