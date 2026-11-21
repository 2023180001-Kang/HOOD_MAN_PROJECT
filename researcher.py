"""Factory-interior gunner with seven-round magazines and explicit reloads."""

from math import hypot

import config
from collision import same_floor
from enemy import Enemy
from projectiles import ResearcherBullet


class Researcher(Enemy):
    uses_melee_slots = False
    death_drop_kind = None
    max_hp = config.RESEARCHER_MAX_HP
    image_name = config.RESEARCHER_IMAGE
    animations = config.RESEARCHER_ANIMATIONS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ammo = config.RESEARCHER_MAGAZINE_SIZE

    @property
    def sprite_image(self):
        return self.image_name

    @property
    def attack_damage(self):
        return config.RESEARCHER_DAMAGE

    @property
    def attack_box(self):
        return None  # Only a real bullet touching the player can cause damage.

    def start_reload(self):
        self.vx = self.ground_vy = 0.0
        self.running = False
        self.has_hit = True
        self.animation.set_state("RELOAD")

    def start_attack(self):
        if self.ammo <= 0:
            self.start_reload()
        else:
            super().start_attack()

    def take_projectile(self):
        if (not self.alive or self.state != "ATTACK" or self.has_hit or self.ammo <= 0
                or self.animation.finished or self.animation.frame < config.RESEARCHER_SHOOT_FRAME):
            return None
        self.has_hit = True
        self.ammo -= 1
        return ResearcherBullet(
            self.x + self.facing * (config.RESEARCHER_MUZZLE_X + config.RESEARCHER_BULLET_HALF_WIDTH),
            self.ground_y, self.jump_height + config.RESEARCHER_MUZZLE_HEIGHT, self.facing, self.floor)

    def _update_ai(self, dt, player):
        if (not self.alive or not player.alive or self.knockback_started
                or self.falling_from_upper
                or self.state in ("HIT", "CAR_HIT", "STRONG_HIT", "RUSH_CARRIED", "RUSH_RELEASED")):
            super()._update_ai(dt, player)
            return
        self.cooldown = max(0.0, self.cooldown - dt)
        if self.state == "RELOAD":
            self.vx = self.ground_vy = 0.0
            self.animation.update(dt)
            if self.animation.elapsed + 1e-9 >= 8 / config.RESEARCHER_RELOAD_FPS:
                self.ammo = config.RESEARCHER_MAGAZINE_SIZE
                self.animation.set_state("IDLE")
            return
        if self.state == "ATTACK":
            self.vx = self.ground_vy = 0.0
            self.animation.update(dt)
            if self.animation.finished:
                if self.ammo == 0:
                    self.start_reload()
                else:
                    self.animation.set_state("IDLE")
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
        if (abs(dx) <= config.RESEARCHER_SHOOT_RANGE
                and abs(dy) <= config.ATTACK_DEPTH_TOLERANCE):
            self.running = False
            if self.cooldown <= 0:
                self.start_attack()
            else:
                self.animation.set_state("IDLE")
            self.animation.update(dt)
            return
        if gap >= config.ENEMY_RUN_START_DISTANCE:
            self.running = True
        elif gap <= config.ENEMY_RUN_STOP_DISTANCE:
            self.running = False
        # Align to the firing lane instead of walking into a melee slot.
        target_x = self.facing * max(0.0, abs(dx) - config.RESEARCHER_SHOOT_RANGE)
        target_y = dy if abs(dy) > config.ATTACK_DEPTH_TOLERANCE else 0.0
        distance = hypot(target_x, target_y)
        speed = self.run_speed if self.running else config.ENEMY_SPEED
        if distance:
            travel = min(distance, speed * dt)
            self.vx, self.ground_vy = target_x / distance * speed, target_y / distance * speed
            self.x += target_x / distance * travel
            self.ground_y += target_y / distance * travel
        self.animation.set_state("RUN" if self.running else "WALK")
        self.animation.update(dt)

    def take_strong_hit(self, move, direction):
        if not super().take_strong_hit(move, direction):
            return False
        self.animation.definitions["STRONG_HIT"] = (
            self.animations["HIT"][0], config.STRONG_HIT_FPS, False)
        return True

    def hit_by_car(self, direction):
        if not super().hit_by_car(direction):
            return False
        self.animation.definitions["DEAD"] = self.animations["CAR_HIT"]
        return True
