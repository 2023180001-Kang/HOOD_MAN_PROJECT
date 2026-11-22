"""Boss rifleman with a half-second warning and a twenty-round magazine."""

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

    @property
    def attack_damage(self):
        return config.AR_SOLDIER_DAMAGE

    def _update_ai(self, dt, player):
        # Leaving the lane/range or crossing behind the gun cancels an unspent
        # warning. Re-entering always requires a fresh, fully visible 0.5 seconds.
        if self.alive and self.state == "ATTACK" and not self.has_hit:
            dx = player.x - self.x
            if (not player.alive or not same_floor(self, player)
                    or abs(dx) > self.shoot_range
                    or abs(player.ground_y - self.ground_y) > config.ATTACK_DEPTH_TOLERANCE
                    or dx * self.facing < 0):
                self.stop()
        super()._update_ai(dt, player)
