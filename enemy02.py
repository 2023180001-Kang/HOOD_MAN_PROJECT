"""City dual-club enemy with close swings and a committed ranged leap slam."""

from math import hypot, sqrt

import config
from collision import Rect, body_contact_time, same_floor
from enemy import Enemy
from physics import jump_apex


def leap_height():
    """Match a normal player double jump with its second input at the first apex."""
    return sum(jump_apex(speed, config.GRAVITY, config.FIXED_DT)
               for speed in (config.JUMP_SPEED, config.DOUBLE_JUMP_SPEED))


class Enemy02(Enemy):
    death_drop_kind = None
    image_name = config.ENEMY02_IMAGE
    animations = config.ENEMY02_ANIMATIONS
    boundary_padding = config.ENEMY02_BOUNDARY_PADDING
    formation_ground_min = config.GROUND_Y
    attacks = config.ENEMY02_ATTACKS
    basic_attack = "clubs"
    airborne_frames = (2, 3)
    leap_min_distance = config.ENEMY02_LEAP_MIN_DISTANCE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attack_kind = self.basic_attack
        self.vy = 0.0
        self.leap_phase = None
        self.leap_cooldown = 0.0
        self.leap_elapsed = self.leap_duration = self.leap_launch_speed = 0.0
        self.leap_origin = self.leap_target = None
        self.leap_blocked = False
        self.air_contact_attack = self.air_contact_pending = False

    @property
    def sprite_image(self):
        return self.image_name

    @property
    def attack_damage(self):
        return self.attacks[self.attack_kind][1]

    @property
    def attack_active_frames(self):
        return self.attacks[self.attack_kind][2]

    @property
    def leaping(self):
        return self.leap_phase == "AIR"

    @property
    def blocks_movement(self):
        return self.alive

    @property
    def attack_box(self):
        if self.attack_kind == "slam" and (self.leap_phase != "LANDING" or self.jump_height > 0):
            return None
        box = super().attack_box
        if box is not None and self.air_contact_attack:
            # A meeting at the feet/head is still a real midair body contact.
            return Rect(box.left, self.body.bottom, box.right, box.top)
        return box

    def start_attack(self, *, air_contact=False):
        self.attack_kind = self.basic_attack
        self.air_contact_attack = self.air_contact_pending = air_contact
        row, _, _ = self.attacks[self.attack_kind]
        self.animation.definitions["ATTACK"] = (row, self.attack_fps, False)
        super().start_attack()

    def start_leap(self, player):
        gap = hypot(player.x - self.x, player.ground_y - self.ground_y)
        if (not same_floor(self, player) or not self.alive or not player.alive
                or self.car_hit or self.knockback_started
                or self.jump_height > 0
                or self.state not in ("IDLE", "WALK", "RUN")
                or self.cooldown > 0 or self.leap_cooldown > 0
                or not self.leap_min_distance <= gap <= config.ENEMY02_LEAP_MAX_DISTANCE):
            return False
        self.attack_kind = "slam"
        self.leap_blocked = False
        self.air_contact_attack = self.air_contact_pending = False
        row, _, _ = self.attacks[self.attack_kind]
        self.animation.definitions["ATTACK"] = (row, self.attack_fps, False)
        self.leap_phase = "WINDUP"
        self.running = False
        self.vx = self.ground_vy = self.vy = 0.0
        if player.x != self.x:
            self.facing = 1 if player.x > self.x else -1
        self.formation_slot = None
        self.target_x = self.target_ground_y = None
        super().start_attack()
        return True

    def _launch(self, player):
        dx = player.x - self.x
        if dx:
            self.facing = 1 if dx > 0 else -1
        travel_x, travel_y = dx, player.ground_y - self.ground_y
        distance = hypot(travel_x, travel_y)
        maximum = config.ENEMY02_LEAP_MAX_DISTANCE
        if distance > maximum:
            travel_x, travel_y = travel_x * maximum / distance, travel_y * maximum / distance
        self.leap_origin = (self.x, self.ground_y)
        self.leap_target = self.walkable.project(self.x + travel_x, self.ground_y + travel_y,
                                                self.boundary_padding)
        self.leap_launch_speed = sqrt(2 * config.GRAVITY * leap_height())
        self.leap_duration = 2 * self.leap_launch_speed / config.GRAVITY
        self.leap_elapsed = 0.0
        self.leap_phase = "AIR"
        self.vy = self.leap_launch_speed

    def _resolve_leap_contact(self, player):
        contact = body_contact_time(player, self)
        if contact is None:
            return False
        self.x = self.previous_x + (self.x - self.previous_x) * contact
        self.ground_y = (self.previous_ground_y
                         + (self.ground_y - self.previous_ground_y) * contact)
        self.vx = self.ground_vy = 0.0
        player_height = (player.previous_jump_height
                         + (player.jump_height - player.previous_jump_height) * contact)
        height = (self.previous_jump_height
                  + (self.jump_height - self.previous_jump_height) * contact)
        if player_height > 1e-9 and height > 1e-9:
            self.jump_height = height
            self._cancel_leap()
            self.start_attack(air_contact=True)
            # Contact is the strike, not another windup that could miss after
            # the two bodies have already been separated by collision handling.
            # Stay inside the active frame after conversion back to a frame index.
            self.animation.elapsed = (min(self.attack_active_frames) + 1e-9) / self.attack_fps
            return True
        # An occupied landing point stops horizontal/depth travel at the body
        # edge. Keep descending and use the landing attack.
        self.leap_blocked = True
        return False

    def _update_leap(self, dt, player):
        remaining = dt
        while remaining > 1e-12:
            if self.leap_phase == "WINDUP":
                deadline = 2 / self.attack_fps
                step = min(remaining, max(0.0, deadline - self.animation.elapsed))
                self.animation.update(step)
                remaining -= step
                if self.animation.elapsed + 1e-9 < deadline:
                    break
                self._launch(player)
            elif self.leaping:
                step = min(remaining, self.leap_duration - self.leap_elapsed)
                self.leap_elapsed += step
                remaining -= step
                ratio = min(1.0, self.leap_elapsed / self.leap_duration)
                start_x, start_y = self.leap_origin
                end_x, end_y = self.leap_target
                if not self.leap_blocked:
                    self.vx = (end_x - start_x) / self.leap_duration
                    self.ground_vy = (end_y - start_y) / self.leap_duration
                    self.x = start_x + (end_x - start_x) * ratio
                    self.ground_y = start_y + (end_y - start_y) * ratio
                self.vy = self.leap_launch_speed - config.GRAVITY * self.leap_elapsed
                self.jump_height = max(0.0, self.leap_launch_speed * self.leap_elapsed
                                       - config.GRAVITY * self.leap_elapsed ** 2 / 2)
                frames = self.airborne_frames
                frame = frames[min(int(ratio * len(frames)), len(frames) - 1)]
                self.animation.elapsed = (frame + 0.05) / self.attack_fps
                if self._resolve_leap_contact(player):
                    return
                if self.leap_elapsed + 1e-9 >= self.leap_duration:
                    if not self.leap_blocked:
                        self.x, self.ground_y = self.leap_target
                    self.jump_height = self.vy = self.vx = self.ground_vy = 0.0
                    self.leap_phase = "LANDING"
                    self.leap_cooldown = config.ENEMY02_LEAP_COOLDOWN
                    self.animation.elapsed = (self.airborne_frames[-1] + 1) / self.attack_fps
            elif self.leap_phase == "LANDING":
                self.animation.update(remaining)
                remaining = 0.0
                if self.animation.finished:
                    self.animation.set_state("IDLE")
                    self._cancel_leap(interrupted=False)
            else:
                break

    def _cancel_leap(self, *, interrupted=True):
        if self.leap_phase is not None and interrupted:
            self.leap_cooldown = max(self.leap_cooldown, config.ENEMY02_LEAP_COOLDOWN)
        self.leap_phase = None
        self.leap_origin = self.leap_target = None
        self.leap_elapsed = self.leap_duration = self.leap_launch_speed = 0.0
        self.leap_blocked = False
        self.air_contact_attack = self.air_contact_pending = False

    def try_hit(self, player):
        if not same_floor(self, player):
            return False
        if self.air_contact_pending and self.attack_box is not None:
            # The swept contact was already validated at one common instant.
            # Preserve that hit even if separation or fast motion ends overlap.
            self.air_contact_pending = False
            self.has_hit = True
            return player.take_damage(self.attack_damage, attacker=self)
        return super().try_hit(player)

    def _fall(self, dt):
        if self.jump_height > 0:
            self.vy -= config.GRAVITY * dt
            self.jump_height = max(0.0, self.jump_height + self.vy * dt)
            if self.jump_height == 0:
                self.vy = 0.0

    def _update_ai(self, dt, player):
        if self.falling_from_upper:
            super()._update_ai(dt, player)
            return
        if self.alive and player.alive and not self.car_hit:
            self.leap_cooldown = max(0.0, self.leap_cooldown - dt)
        if self.leap_phase is not None:
            if (self.state == "ATTACK" and self.attack_kind == "slam" and self.alive and player.alive
                    and not self.car_hit and not self.knockback_started):
                self.cooldown = max(0.0, self.cooldown - dt)
                self._update_leap(dt, player)
                return
            self._cancel_leap()
        if self.start_leap(player):
            self._update_leap(dt, player)
            return
        if self.jump_height > 0 and self.state in ("IDLE", "WALK", "RUN") and player.alive:
            self.vx = self.ground_vy = 0.0
            self.cooldown = max(0.0, self.cooldown - dt)
            self.animation.set_state("IDLE")
            self.animation.update(dt)
            self._fall(dt)
            return
        super()._update_ai(dt, player)
        if self.state != "ATTACK":
            self.air_contact_attack = self.air_contact_pending = False
        if not self.car_hit:
            self._fall(dt)

    def take_damage(self, damage):
        applied = super().take_damage(damage)
        if applied:
            self._cancel_leap()
        return applied

    def take_strong_hit(self, move, direction):
        if not super().take_strong_hit(move, direction):
            return False
        # Strong hits must use this enemy's own hit art.
        row = self.animations["HIT"][0]
        self.animation.definitions["STRONG_HIT"] = (row, config.STRONG_HIT_FPS, False)
        return True

    def knockback(self, player_x, player_ground_y=None):
        super().knockback(player_x, player_ground_y)
        if self.knockback_started:
            self._cancel_leap()

    def stop(self):
        self._cancel_leap()
        super().stop()

    def hit_by_car(self, direction):
        if not super().hit_by_car(direction):
            return False
        self._cancel_leap()
        self.animation.definitions["DEAD"] = (7, config.CAR_HIT_FPS, False)
        return True
