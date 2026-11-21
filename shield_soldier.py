"""Lab shield soldier: committed random guard/swing actions and half guard damage."""

import config
from enemy import Enemy


class ShieldSoldier(Enemy):
    death_drop_kind = None
    max_hp = config.SHIELD_SOLDIER_MAX_HP
    image_name = config.SHIELD_SOLDIER_IMAGE
    animations = config.SHIELD_SOLDIER_ANIMATIONS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        row, fps, loop = self.animation.definitions["GUARD"]
        self.animation.definitions["GUARD"] = (row, fps * self.attack_speed, loop)

    @property
    def sprite_image(self):
        return self.image_name

    @property
    def attack_damage(self):
        return config.SHIELD_SOLDIER_DAMAGE

    @property
    def attack_active_frames(self):
        return config.SHIELD_SOLDIER_ACTIVE_FRAMES

    @property
    def guarding(self):
        return (self.alive and self.state == "GUARD" and not self.animation.finished
                and not self.knockback_started and not self.falling_from_upper
                and self.staircase is None)

    def start_guard(self):
        self.vx = self.ground_vy = 0.0
        self.running = False
        self.has_hit = True
        self.cooldown = self.attack_interval
        self.animation.set_state("GUARD")
        self.animation.elapsed = 0.0

    def start_swing(self):
        self.vx = self.ground_vy = 0.0
        self.running = False
        super().start_attack()

    def start_attack(self):
        # Called once by the inherited melee AI when an action is due, not per hit/frame.
        if self.rng.random() < config.SHIELD_SOLDIER_GUARD_CHANCE:
            self.start_guard()
        else:
            self.start_swing()

    def take_damage(self, damage):
        guarded = self.guarding
        elapsed = self.animation.elapsed
        if guarded:
            reduced = damage * config.SHIELD_SOLDIER_GUARD_DAMAGE_SCALE
            damage = int(reduced) if reduced.is_integer() else reduced
        if not super().take_damage(damage):
            return False
        if guarded and self.alive:
            # A normal block keeps the committed defense without restarting its timer.
            self.animation.set_state("GUARD")
            self.animation.elapsed = elapsed
        return True

    def _update_ai(self, dt, player):
        if (self.state == "GUARD" and self.alive and player.alive
                and not self.knockback_started and not self.falling_from_upper
                and self.staircase is None):
            self.cooldown = max(0.0, self.cooldown - dt)
            self.vx = self.ground_vy = 0.0
            self.running = False
            self.animation.update(dt)
            if self.animation.finished:
                self.animation.set_state("IDLE")
            return
        super()._update_ai(dt, player)

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
