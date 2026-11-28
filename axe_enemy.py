"""Factory axe fighter with a recoverable weapon and unarmed attacks."""

import config
from collision import same_floor
from enemy import Enemy
from enemy_spacing import weapon_pickup_waypoint
from projectiles import EnemyAxeProjectile


class AxeEnemy(Enemy):
    max_hp = config.AXE_ENEMY_MAX_HP
    image_name = config.AXE_ENEMY_IMAGE
    animations = config.AXE_ENEMY_ANIMATIONS

    attacks = {
        "swing": (4, config.AXE_ENEMY_DAMAGE),
        "throw": (7, config.AXE_ENEMY_THROW_DAMAGE),
        "punch": (4, config.AXE_ENEMY_PUNCH_DAMAGE),
        "kick": (5, config.AXE_ENEMY_KICK_DAMAGE),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.armed = True
        self.recovery_target = None
        self.has_swung = False
        self.attack_kind = "swing"
        self.throw_retry = 0.0

    @property
    def death_drop_kind(self):
        return "axe" if self.armed else None

    @property
    def sprite_image(self):
        if self.armed or (self.state == "ATTACK" and self.attack_kind == "throw"):
            return self.image_name
        return config.AXE_ENEMY_UNARMED_IMAGE

    @property
    def attack_damage(self):
        return self.attacks[self.attack_kind][1]

    @property
    def attack_box(self):
        return None if self.attack_kind == "throw" else super().attack_box

    @property
    def preparing_throw(self):
        return (self.armed and self.alive and self.state == "ATTACK" and self.attack_kind == "throw"
                and self.staircase is None and not self.falling_from_upper)

    def _start_move(self, kind):
        self.attack_kind = kind
        fps = (EnemyAxeProjectile.release_frame / config.AXE_ENEMY_THROW_WARNING
               if kind == "throw" else self.attack_fps)
        self.animation.definitions["ATTACK"] = (self.attacks[kind][0], fps, False)
        self.vx = self.ground_vy = 0.0
        super().start_attack()

    def start_attack(self):
        self._start_move("swing" if self.armed else self.rng.choice(("punch", "kick")))

    def try_start_throw(self, dt, player):
        self.throw_retry = max(0.0, self.throw_retry - dt)
        dx = player.x - self.x
        if (not self.armed or not self.has_swung or self.knockback_started
                or self.cooldown > dt or self.throw_retry
                or self.navigation_target is not None or self.falling_from_upper
                or not player.alive or not same_floor(self, player)
                or not config.AXE_ENEMY_THROW_MIN_DISTANCE <= abs(dx) <= EnemyAxeProjectile.straight_range
                or abs(player.ground_y - self.ground_y) > config.ATTACK_DEPTH_TOLERANCE):
            return False
        self.throw_retry = config.AXE_ENEMY_THROW_RETRY
        if self.rng.random() >= config.AXE_ENEMY_THROW_CHANCE:
            return False
        self.facing = 1 if dx > 0 else -1
        self._start_move("throw")
        return True

    def _update_ai(self, dt, player):
        if self.state in ("IDLE", "WALK", "RUN") and self.try_start_throw(dt, player):
            return
        super()._update_ai(dt, player)
        if (self.state == "ATTACK" and self.attack_kind == "swing"
                and self.animation.frame >= self.attack_active_frames[0]):
            self.has_swung = True

    def _set_armed(self, armed):
        self.armed = armed
        self.recovery_target = None
        poses = self.animations if armed else config.AXE_ENEMY_UNARMED_ANIMATIONS
        # ATTACK stays on the throw row until its empty-handed follow-through ends.
        for state in ("HIT", "KNOCKBACK", "DYING", "DEAD", "CAR_HIT"):
            self.animation.definitions[state] = poses[state]
        self.animation.definitions["FALL"] = poses["HIT"]
        self.has_swung = False
        if armed:
            self.attack_kind = "swing"
            self.animation.definitions["ATTACK"] = (self.attacks["swing"][0], self.attack_fps, False)

    def _new_thrown_axe(self):
        forward, height = EnemyAxeProjectile.release_offset
        return EnemyAxeProjectile(self.x + self.facing * forward * config.SPRITE_SCALE,
                                  self.ground_y, self.jump_height + height * config.SPRITE_SCALE,
                                  self.facing, self.floor, shooter=self)

    def throw_warning_points(self, world_width):
        if not self.preparing_throw:
            return
        axe = self._new_thrown_axe()
        axe.world_width = world_width
        interval = config.RESEARCHER_AIM_DOT_SPACING / axe.speed
        while not axe.finished:
            yield axe.x, axe.y
            axe.update(interval, None)

    def take_projectile(self):
        if not self.preparing_throw or self.animation.elapsed + 1e-9 < config.AXE_ENEMY_THROW_WARNING:
            return None
        # Resume the fighter's normal speed at the empty-handed release frame.
        overshoot = max(0.0, self.animation.elapsed - config.AXE_ENEMY_THROW_WARNING)
        self.animation.definitions["ATTACK"] = (self.attacks["throw"][0], self.attack_fps, False)
        self.animation.elapsed = (EnemyAxeProjectile.release_frame + 1e-9) / self.attack_fps + overshoot
        self._set_armed(False)
        return self._new_thrown_axe()

    def seek_axe(self, item, player):
        """Claim a reachable axe, or set this tick's movement waypoint toward it."""
        if (self.armed or not self.alive or not player.alive or self.knockback_started
                or self.state not in ("IDLE", "WALK", "RUN") or not item.grounded
                or self.falling_from_upper or not same_floor(self, item)
                or self.navigation_target is not None):
            return False
        if (abs(self.x - item.x) <= config.WEAPON_PICKUP_RANGE
                and abs(self.ground_y - item.ground_y) <= config.WEAPON_PICKUP_DEPTH):
            self._set_armed(True)
            return True
        self.recovery_target = item
        self.navigation_target = weapon_pickup_waypoint(self, item, player)
        return False

    def abandon_axe_recovery(self):
        if self.recovery_target is not None:
            self.recovery_target.axe_owner = None
            self.recovery_target = None
            self.navigation_target = None

    def take_damage(self, damage):
        if not super().take_damage(damage):
            return False
        self.abandon_axe_recovery()
        return True

    def take_strong_hit(self, move, direction):
        if not super().take_strong_hit(move, direction):
            return False
        self.animation.definitions["STRONG_HIT"] = (
            self.animation.definitions["HIT"][0], config.STRONG_HIT_FPS, False)
        return True

    def hit_by_car(self, direction):
        if not super().hit_by_car(direction):
            return False
        self.animation.definitions["DEAD"] = self.animation.definitions["CAR_HIT"]
        return True
