"""Factory axe fighter with a recoverable weapon and unarmed attacks."""

import config
from collision import same_floor
from enemy import Enemy
from enemy_spacing import clear_route
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
        self.has_swung = False
        self.attack_kind = "swing"
        self.throw_retry = 0.0

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

    def _start_move(self, kind):
        self.attack_kind = kind
        self.animation.definitions["ATTACK"] = (self.attacks[kind][0], self.attack_fps, False)
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
            self.animation.update(dt)
            return
        super()._update_ai(dt, player)
        if (self.state == "ATTACK" and self.attack_kind == "swing"
                and self.animation.frame >= self.attack_active_frames[0]):
            self.has_swung = True

    def _set_armed(self, armed):
        self.armed = armed
        poses = self.animations if armed else config.AXE_ENEMY_UNARMED_ANIMATIONS
        # ATTACK stays on the throw row until its empty-handed follow-through ends.
        for state in ("HIT", "KNOCKBACK", "DYING", "DEAD", "CAR_HIT"):
            self.animation.definitions[state] = poses[state]
        self.animation.definitions["FALL"] = poses["HIT"]
        self.has_swung = False
        if armed:
            self.attack_kind = "swing"
            self.animation.definitions["ATTACK"] = (self.attacks["swing"][0], self.attack_fps, False)

    def take_projectile(self):
        if (not self.armed or not self.alive or self.state != "ATTACK" or self.attack_kind != "throw"
                or self.animation.frame < EnemyAxeProjectile.release_frame):
            return None
        self._set_armed(False)
        forward, height = EnemyAxeProjectile.release_offset
        return EnemyAxeProjectile(self.x + self.facing * forward * config.SPRITE_SCALE,
                                  self.ground_y, self.jump_height + height * config.SPRITE_SCALE,
                                  self.facing, self.floor, shooter=self)

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
        goal = self.walkable.project(item.x, item.ground_y, self.boundary_padding)
        if same_floor(self, player):
            # The player may be standing on the axe. Approach its pickup area
            # from either depth lane even when its centre is blocked at a wall.
            obstacle = (player.x, player.ground_y, config.PLAYER_HALF_WIDTH + config.ENEMY_HALF_WIDTH,
                        config.BODY_DEPTH_TOLERANCE)
            lane_gap = config.BODY_DEPTH_TOLERANCE + config.ENEMY_SPACING_TOLERANCE
            lanes = (player.ground_y - lane_gap, player.ground_y + lane_gap)
            approaches = [goal] + [self.walkable.project(item.x, y, self.boundary_padding) for y in lanes
                                    if abs(y - item.ground_y) <= config.WEAPON_PICKUP_DEPTH]
            for approach in approaches:
                waypoint = clear_route(self, approach, [obstacle], config.ENEMY_SPACING_TOLERANCE)
                if waypoint is not None:
                    goal = waypoint
                    break
        self.navigation_target = goal
        return False

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
