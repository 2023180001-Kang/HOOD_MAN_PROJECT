"""Boss rifleman: one warning, automatic fire, then a twenty-round reload."""

import config
from collision import same_floor
from projectiles import RifleBullet
from researcher import Researcher


class ARSoldier(Researcher):
    max_hp = config.AR_SOLDIER_MAX_HP
    image_name = config.AR_SOLDIER_IMAGE
    animations = config.AR_SOLDIER_ANIMATIONS
    magazine_size = config.AR_SOLDIER_MAGAZINE_SIZE
    reload_fps = config.AR_SOLDIER_RELOAD_FPS
    shoot_range = config.AR_SOLDIER_SHOOT_RANGE
    shoot_frame = config.AR_SOLDIER_SHOOT_FRAME
    aim_duration = config.AR_SOLDIER_AIM_DURATION
    muzzle_x = config.AR_SOLDIER_MUZZLE_X
    muzzle_height = config.AR_SOLDIER_MUZZLE_HEIGHT
    projectile_type = RifleBullet
    fire_interval = config.AR_SOLDIER_FIRE_INTERVAL

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fire_remaining = 0.0
        self.burst_shots = 0
        self.aim_cancel_remaining = 0.0
        self._last_player_ground_y = None

    @property
    def attack_damage(self):
        return config.AR_SOLDIER_DAMAGE

    def start_attack(self):
        self.fire_remaining = 0.0
        self.burst_shots = 0
        self.aim_cancel_remaining = 0.0
        super().start_attack()

    def start_reload(self):
        self.fire_remaining = 0.0
        self.burst_shots = 0
        self.aim_cancel_remaining = 0.0
        super().start_reload()

    def take_damage(self, damage):
        if not super().take_damage(damage):
            return False
        self.aim_cancel_remaining = 0.0
        return True

    def stop(self):
        self.aim_cancel_remaining = 0.0
        super().stop()

    def knockback(self, player_x, player_ground_y=None):
        self.aim_cancel_remaining = 0.0
        super().knockback(player_x, player_ground_y)

    def hit_by_car(self, direction):
        if not super().hit_by_car(direction):
            return False
        self.aim_cancel_remaining = 0.0
        return True

    def show_fire_pose(self):
        frames = config.AR_SOLDIER_FIRE_FRAMES
        frame = frames[max(0, self.burst_shots - 1) % len(frames)]
        self.animation.elapsed = (frame + 1e-9) / self.attack_fps

    def update_attack(self, dt):
        self.vx = self.ground_vy = 0.0
        if self.aim_remaining > 0:
            remaining = self.aim_remaining
            self.aim_remaining = max(0.0, remaining - dt)
            self.animation.elapsed = (self.shoot_frame - 1 + 1e-9) / self.attack_fps
            if self.aim_remaining > 1e-9:
                return
            self.aim_remaining = 0.0
            dt = max(0.0, dt - remaining)
        self.fire_remaining -= dt
        if self.ammo <= 0 and self.fire_remaining <= 1e-9:
            self.start_reload()
            return
        if self.fire_remaining <= 1e-9:
            self.has_hit = False
        # Stay on the original four firing poses, without replaying the warning
        # or finishing the single-shot animation between consecutive rounds.
        self.show_fire_pose()

    def take_projectile(self):
        if self.fire_remaining > 1e-9:
            return None
        bullet = super().take_projectile()
        if bullet is not None:
            self.burst_shots += 1
            self.fire_remaining = max(0.0, self.fire_remaining + self.fire_interval)
            self.show_fire_pose()
        return bullet

    def _update_ai(self, dt, player):
        player_changing_depth = (
            self._last_player_ground_y is not None
            and abs(player.ground_y - self._last_player_ground_y) > 1e-9)
        self._last_player_ground_y = player.ground_y
        if not self.aiming:
            self.aim_cancel_remaining = 0.0
        # Leaving the lane/range or crossing behind cancels both the warning and
        # an active burst. Only vertical evasion DURING aiming gets a delayed
        # reaction; normal pursuit and active-burst interruption stay unchanged.
        if self.alive and self.state == "ATTACK":
            dx = player.x - self.x
            if (not player.alive or not same_floor(self, player)
                    or abs(dx) > self.shoot_range
                    or dx * self.facing < 0):
                self.stop()
            elif self.aiming and (player_changing_depth or self.aim_cancel_remaining > 0):
                if self.aim_cancel_remaining > 0:
                    self.aim_cancel_remaining = max(0.0, self.aim_cancel_remaining - dt)
                else:
                    self.aim_cancel_remaining = config.AR_SOLDIER_AIM_CANCEL_DELAY
                # Freeze the original warning pose/lane and timer, so even a
                # last-tick dodge cannot fire while cancellation is pending.
                self.vx = self.ground_vy = 0.0
                if self.aim_cancel_remaining <= 1e-9:
                    self.stop()
                return  # Never cancel and immediately re-aim in the same tick.
            elif abs(player.ground_y - self.ground_y) > config.ATTACK_DEPTH_TOLERANCE:
                self.stop()
        super()._update_ai(dt, player)
