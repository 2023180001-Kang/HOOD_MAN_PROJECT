"""Factory gunner with a half-second shot telegraph and seven-round magazines."""

from math import hypot

import config
from collision import same_floor
from enemy import Enemy
from projectiles import ResearcherBullet


class Researcher(Enemy):
    uses_melee_slots = False
    max_hp = config.RESEARCHER_MAX_HP
    image_name = config.RESEARCHER_IMAGE
    animations = config.RESEARCHER_ANIMATIONS
    magazine_size = config.RESEARCHER_MAGAZINE_SIZE
    reload_fps = config.RESEARCHER_RELOAD_FPS
    shoot_range = config.RESEARCHER_SHOOT_RANGE
    shoot_frame = config.RESEARCHER_SHOOT_FRAME
    aim_duration = config.RESEARCHER_AIM_DURATION
    muzzle_x = config.RESEARCHER_MUZZLE_X
    muzzle_height = config.RESEARCHER_MUZZLE_HEIGHT
    projectile_type = ResearcherBullet

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ammo = self.magazine_size
        self.aim_remaining = 0.0

    @property
    def sprite_image(self):
        return self.image_name

    @property
    def attack_damage(self):
        return config.RESEARCHER_DAMAGE

    @property
    def attack_box(self):
        return None  # Only a real bullet touching the player can cause damage.

    @property
    def aiming(self):
        return (self.alive and self.state == "ATTACK" and not self.has_hit
                and not self.knockback_started and not self.falling_from_upper
                and self.staircase is None and self.aim_remaining > 0)

    @property
    def aim_line(self):
        if not self.aiming:
            return None
        # Predict the unchanged horizontal bullet lane, not a homing shot.
        muzzle_x = self.x + self.facing * self.muzzle_x
        height = self.y + self.muzzle_height
        end_x = max(0.0, min(config.WORLD_WIDTH,
                            self.x + self.facing * self.shoot_range))
        return muzzle_x, height, end_x, height

    def start_reload(self):
        self.aim_remaining = 0.0
        self.vx = self.ground_vy = 0.0
        self.running = False
        self.has_hit = True
        self.animation.set_state("RELOAD")

    def start_attack(self):
        if self.ammo <= 0:
            self.start_reload()
        else:
            super().start_attack()
            self.vx = self.ground_vy = 0.0
            self.running = False
            self.aim_remaining = self.aim_duration
            # Hold the original raised-pistol pose just before the muzzle flash.
            self.animation.elapsed = (self.shoot_frame - 1 + 1e-9) / self.attack_fps

    def update_attack(self, dt):
        self.vx = self.ground_vy = 0.0
        if self.aim_remaining > 0:
            remaining = self.aim_remaining
            self.aim_remaining = max(0.0, remaining - dt)
            self.animation.elapsed = (self.shoot_frame - 1 + 1e-9) / self.attack_fps
            if self.aim_remaining > 1e-9:
                return
            self.aim_remaining = 0.0
            self.animation.elapsed = (self.shoot_frame + 1e-9) / self.attack_fps
            dt = max(0.0, dt - remaining)
        self.animation.update(dt)
        if self.animation.finished:
            if self.ammo == 0:
                self.start_reload()
            else:
                self.animation.set_state("IDLE")

    def take_projectile(self):
        if (not self.alive or self.state != "ATTACK" or self.has_hit or self.ammo <= 0
                or self.aim_remaining > 0 or self.staircase is not None or self.falling_from_upper
                or self.animation.finished or self.animation.frame < self.shoot_frame):
            return None
        self.has_hit = True
        self.ammo -= 1
        return self.projectile_type(
            self.x + self.facing * (self.muzzle_x + self.projectile_type.half_width),
            self.ground_y, self.jump_height + self.muzzle_height, self.facing, self.floor)

    def pursuit_delta(self, dx, dy):
        return (self.facing * max(0.0, abs(dx) - self.shoot_range),
                dy if abs(dy) > config.ATTACK_DEPTH_TOLERANCE else 0.0)

    def at_firing_position(self, dx, dy):
        return abs(dx) <= self.shoot_range + 1e-9 and abs(dy) <= config.ATTACK_DEPTH_TOLERANCE

    def _update_ai(self, dt, player):
        if (not self.alive or not player.alive or self.knockback_started
                or self.falling_from_upper or self.navigation_target is not None
                or self.state in ("HIT", "CAR_HIT", "STRONG_HIT", "RUSH_CARRIED", "RUSH_RELEASED")):
            self.aim_remaining = 0.0
            super()._update_ai(dt, player)
            return
        self.cooldown = max(0.0, self.cooldown - dt)
        if self.state == "RELOAD":
            self.vx = self.ground_vy = 0.0
            self.animation.update(dt)
            if self.animation.elapsed + 1e-9 >= 8 / self.reload_fps:
                self.ammo = self.magazine_size
                self.animation.set_state("IDLE")
            return
        if self.state == "ATTACK":
            self.update_attack(dt)
            return
        if not same_floor(self, player):
            self.stop()
            self.animation.update(dt)
            return
        if self.ammo == 0:
            self.start_reload()
            self.animation.update(dt)
            return
        dx, dy = player.x - self.x, player.ground_y - self.ground_y
        gap = hypot(dx, dy)
        if dx:
            self.facing = 1 if dx > 0 else -1
        self.vx = self.ground_vy = 0.0
        target_x, target_y = self.pursuit_delta(dx, dy)
        if abs(target_x) <= 1e-9 and abs(target_y) <= 1e-9:
            self.running = False
            if self.cooldown <= 0 and self.at_firing_position(dx, dy):
                self.start_attack()
                return  # Start a full warning; do not spend time before it is visible.
            else:
                self.animation.set_state("IDLE")
            self.animation.update(dt)
            return
        if gap >= config.ENEMY_RUN_START_DISTANCE:
            self.running = True
        elif gap <= config.ENEMY_RUN_STOP_DISTANCE:
            self.running = False
        # Align to the firing lane instead of walking into a melee slot.
        distance = hypot(target_x, target_y)
        speed = self.run_speed if self.running else config.ENEMY_SPEED
        if distance:
            travel = min(distance, speed * dt)
            self.vx, self.ground_vy = target_x / distance * speed, target_y / distance * speed
            if self.vx:
                self.facing = 1 if self.vx > 0 else -1
            self.x += target_x / distance * travel
            self.ground_y += target_y / distance * travel
        self.animation.set_state("RUN" if self.running else "WALK")
        self.animation.update(dt)

    def take_damage(self, damage):
        if not super().take_damage(damage):
            return False
        self.aim_remaining = 0.0
        return True

    def stop(self):
        self.aim_remaining = 0.0
        super().stop()

    def knockback(self, player_x, player_ground_y=None):
        self.aim_remaining = 0.0
        super().knockback(player_x, player_ground_y)

    def take_strong_hit(self, move, direction):
        if not super().take_strong_hit(move, direction):
            return False
        self.animation.definitions["STRONG_HIT"] = (
            self.animations["HIT"][0], config.STRONG_HIT_FPS, False)
        return True

    def hit_by_car(self, direction):
        if not super().hit_by_car(direction):
            return False
        self.aim_remaining = 0.0
        self.animation.definitions["DEAD"] = self.animations["CAR_HIT"]
        return True
