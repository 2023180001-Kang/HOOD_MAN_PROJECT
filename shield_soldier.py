"""Lab shield soldier with a close-range swing and reactive guard."""

import config
from collision import same_floor
from combat import STRONG_MOVES
from enemy import Enemy


class ShieldSoldier(Enemy):
    death_drop_kind = "shield_item"
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

    def start_attack(self):
        self.vx = self.ground_vy = 0.0
        self.running = False
        super().start_attack()

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
        if (not self.alive or not player.alive or self.knockback_started or self.falling_from_upper
                or self.staircase is not None or self.state not in ("IDLE", "WALK", "RUN", "ATTACK", "GUARD")):
            super()._update_ai(dt, player)
            return

        dx = player.x - self.x
        in_lane = (same_floor(self, player)
                   and abs(self.ground_y - player.ground_y) <= config.ATTACK_DEPTH_TOLERANCE)
        move = player.active_move
        threat = (in_lane and move is not None and (move.jump_attack or move in STRONG_MOVES.values())
                  and abs(dx) < move.reach + config.ENEMY_HALF_WIDTH
                  and player.air_kick_phase not in ("WAIT", "RECOVERY") and self not in player.hit_enemies)
        if threat and self.state != "GUARD":
            if dx:
                self.facing = 1 if dx > 0 else -1
            self.start_guard()
        if self.state == "GUARD":
            self.cooldown = max(0.0, self.cooldown - dt)
            self.animation.update(dt)
            if self.animation.finished:
                if threat:
                    self.animation.elapsed = 0.0
                else:
                    self.animation.set_state("IDLE")
        elif (in_lane and self.state != "ATTACK" and self.cooldown <= dt
              and abs(dx) < config.ENEMY_ATTACK_REACH + config.PLAYER_HALF_WIDTH):
            if dx:
                self.facing = 1 if dx > 0 else -1
            self.start_attack()
            self.animation.update(dt)
        else:
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
