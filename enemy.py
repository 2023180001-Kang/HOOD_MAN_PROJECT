"""Independent street-thug AI and animation state."""

from math import hypot
import random

import config
from animation import Animation
from collision import Rect, same_floor
from physics import approach_vector
from traffic import start_car_hit, update_car_hit
from walkable import default_area


class Enemy:
    stair_following = True
    uses_melee_slots = True
    uses_ranged_spacing = False
    max_hp = config.ENEMY_MAX_HP
    boundary_padding = config.ENEMY_BOUNDARY_PADDING
    image_name = config.ENEMY_IMAGE
    animations = config.ENEMY_ANIMATIONS
    formation_ground_min = None

    def __init__(self, x, facing=1, spawned_at=0.0, *, run_speed=None, ground_y=None,
                 attack_speed=1.0, rng=None):
        self.rng = random.Random() if rng is None else rng
        self.x = x
        self.previous_x = x
        self.ground_y = config.GROUND_Y if ground_y is None else ground_y
        self.previous_ground_y = self.ground_y
        self.jump_height = 0.0
        self.previous_jump_height = 0.0
        self.ground_vy = 0.0
        self.walkable = default_area()
        self.floor = 0
        self.staircase = None
        self.stair_arrival = False
        self.navigation_target = None
        self.descent_route = None
        self.descent_delay = 0.0
        self.falling_from_upper = False
        self.vx = 0.0
        self.vy = 0.0
        self.facing = facing
        self.spawned_at = spawned_at
        self.cooldown = 0.0
        self.has_hit = False
        self.knockback_started = False
        self.run_speed = config.ENEMY_RUN_SPEEDS[0] if run_speed is None else run_speed
        self.running = False
        self.hp = self.max_hp
        self.last_hit_damage = 0
        self.corpse_elapsed = 0.0
        self.defeat_counted = False
        self.car_hit = False
        self.attack_speed = attack_speed
        self.attack_interval = config.ENEMY_ATTACK_INTERVAL / attack_speed
        definitions = dict(self.animations)
        definitions["FALL"] = self.animations["HIT"]
        row, fps, loop = definitions["ATTACK"]
        self.attack_fps = fps * attack_speed
        definitions["ATTACK"] = (row, self.attack_fps, loop)
        self.animation = Animation(definitions)
        self.formation_side = None
        self.formation_slot = None
        self.target_x = None
        self.target_ground_y = None

    @property
    def state(self):
        return self.animation.state

    @property
    def alive(self):
        return self.hp > 0

    @property
    def leaping(self):
        return False

    @property
    def blocks_movement(self):
        return self.alive and not self.leaping

    @property
    def opacity(self):
        if self.faded_out:
            return 0.0
        if self.alive or self.state != "DEAD" or self.corpse_elapsed <= config.ENEMY_CORPSE_DELAY + 1e-9:
            return 1.0
        return max(0.0, 1.0 - (self.corpse_elapsed - config.ENEMY_CORPSE_DELAY)
                   / config.ENEMY_FADE_DURATION)

    @property
    def faded_out(self):
        return (not self.alive and self.state == "DEAD"
                and self.corpse_elapsed + 1e-9 >= config.ENEMY_CORPSE_DELAY + config.ENEMY_FADE_DURATION)

    @property
    def sprite_image(self):
        if self.car_hit:
            return config.ENEMY_CAR_HIT_IMAGE
        if self.state == "STRONG_HIT":
            return config.STRONG_HIT_IMAGE
        return self.image_name

    @property
    def y(self):
        return self.ground_y + self.jump_height

    @y.setter
    def y(self, value):
        self.jump_height = max(0.0, value - self.ground_y)

    @property
    def depth(self):
        """Legacy relative depth accessor; it now represents actual floor position."""
        return self.ground_y - config.GROUND_Y

    @depth.setter
    def depth(self, value):
        self.ground_y = config.GROUND_Y + value

    @property
    def target_depth(self):
        return (self.target_ground_y - config.GROUND_Y
                if self.target_ground_y is not None else 0.0)

    def take_damage(self, damage):
        if not self.alive:
            return False
        self.last_hit_damage = min(self.hp, damage)
        self.hp -= self.last_hit_damage
        self.vx = 0.0
        self.ground_vy = 0.0
        self.running = False
        self.has_hit = True
        self.knockback_started = False
        self.animation.set_state("HIT" if self.alive else "DYING")
        if not self.alive and self.staircase is not None:
            self.begin_floor_fall(self.staircase.lower_area)
        return True

    def take_strong_hit(self, move, direction):
        if not self.take_damage(move.damage):
            return False
        if self.staircase is not None:
            self.begin_floor_fall(self.staircase.lower_area)
        self.facing = -direction
        self.vx = self.ground_vy = 0.0
        self.formation_slot = None
        self.target_x = self.target_ground_y = None
        self.cooldown = self.attack_interval
        self.animation.definitions["STRONG_HIT"] = (move.enemy_hit_row, config.STRONG_HIT_FPS, False)
        self.animation.set_state("STRONG_HIT")
        self.animation.elapsed = 0.0
        return True

    def update_strong_hit(self, dt):
        self.x += self.vx * dt
        self.ground_y += self.ground_vy * dt
        self.walkable.constrain(self, config.ENEMY_HALF_WIDTH)
        self.vx, self.ground_vy = approach_vector(self.vx, self.ground_vy, 0.0, 0.0,
                                                 config.KNOCKBACK_FRICTION * dt)
        self.animation.update(dt)
        if self.animation.finished:
            self.vx = self.ground_vy = 0.0
            self.animation.set_state("IDLE" if self.alive else "DYING")

    def begin_floor_fall(self, lower_area, *, ground_y=None):
        feet = self.y
        previous_feet = self.previous_ground_y + self.previous_jump_height
        if self.staircase is not None:
            self.staircase.detach(self)
        self.floor, self.walkable = 0, lower_area
        landing_y = lower_area.bounds[3] if ground_y is None else ground_y
        self.x, self.ground_y = lower_area.project(self.x, landing_y, self.boundary_padding)
        self.jump_height = max(0.0, feet - self.ground_y)
        self.previous_ground_y = self.ground_y
        self.previous_jump_height = max(0.0, previous_feet - self.ground_y)
        self.vy = self.vx = self.ground_vy = 0.0
        self.falling_from_upper = True
        self.running = False
        self.has_hit = True
        self.navigation_target = self.target_x = self.target_ground_y = None
        self.formation_slot = None
        self.descent_delay = 0.0
        if self.state in ("IDLE", "WALK", "RUN"):
            self.animation.set_state("FALL")

    def update_floor_fall(self, dt):
        self.vy -= config.GRAVITY * dt
        self.jump_height = max(0.0, self.jump_height + self.vy * dt)
        if self.jump_height == 0:
            self.vy = 0.0
            self.falling_from_upper = False
            self.descent_route = None
            if self.state == "FALL":
                self.animation.set_state("IDLE" if self.alive else "DYING")
                self.cooldown = self.attack_interval

    def hit_by_car(self, direction):
        if not self.alive:
            return False
        self.running = self.knockback_started = False
        self.has_hit = True
        self.cooldown = 0.0
        self.formation_side = self.formation_slot = None
        self.target_x = self.target_ground_y = None
        self.corpse_elapsed = 0.0
        start_car_hit(self, direction)
        return True

    @property
    def body(self):
        base = config.GROUND_Y + self.jump_height
        return Rect(self.x - config.ENEMY_HALF_WIDTH, base,
                    self.x + config.ENEMY_HALF_WIDTH, base + config.ENEMY_HEIGHT)

    @property
    def attack_damage(self):
        return config.ENEMY_DAMAGE

    @property
    def attack_active_frames(self):
        return config.ENEMY_ACTIVE_FRAMES

    def start_attack(self):
        self.animation.set_state("ATTACK")
        self.animation.elapsed = 0.0
        self.has_hit = False
        self.cooldown = self.attack_interval

    @property
    def attack_box(self):
        if (not self.alive or self.staircase is not None or self.falling_from_upper
                or self.state != "ATTACK" or self.has_hit
                or self.animation.frame not in self.attack_active_frames):
            return None
        near = self.x + self.facing * 12
        far = self.x + self.facing * config.ENEMY_ATTACK_REACH
        base = config.GROUND_Y + self.jump_height
        return Rect(min(near, far), base + 20, max(near, far), base + config.ENEMY_HEIGHT)

    def try_hit(self, player):
        box = self.attack_box
        if (box is not None and same_floor(self, player)
                and abs(self.ground_y - player.ground_y) <= config.ATTACK_DEPTH_TOLERANCE
                and box.overlaps(player.body)):
            # Per-enemy swing consumption prevents repeated active-frame damage.
            self.has_hit = True
            return player.take_damage(self.attack_damage, attacker=self)
        return False

    def take_projectile(self):
        return None  # Melee enemies never emit a projectile.

    def knockback(self, player_x, player_ground_y=None):
        if not self.alive or self.knockback_started:
            return
        self.knockback_started = True
        self.running = False
        distance = self.x - player_x
        direction = (1 if distance > 0 else -1) if distance else -self.facing
        self.vx = direction * config.KNOCKBACK_SPEED
        self.ground_vy = 0.0
        if player_ground_y is not None:
            depth = self.ground_y - player_ground_y
            length = hypot(distance, depth)
            if length:
                self.vx = distance / length * config.KNOCKBACK_SPEED
                self.ground_vy = depth / length * config.KNOCKBACK_SPEED
        self.cooldown = 0.0
        self.has_hit = True
        self.animation.set_state("KNOCKBACK")
        # Facing deliberately stays unchanged while sliding away.

    def stop(self):
        """Cancel pursuit and attacks without moving or turning the enemy."""
        if not self.alive:
            return
        self.vx = 0.0
        self.ground_vy = 0.0
        self.running = False
        self.cooldown = 0.0
        self.has_hit = True
        self.animation.set_state("IDLE")

    def update_knockback(self, dt):
        if self.state == "KNOCKBACK":
            self.x += self.vx * dt
            self.ground_y += self.ground_vy * dt
            self.walkable.constrain(self, config.ENEMY_HALF_WIDTH)
            self.vx, self.ground_vy = approach_vector(self.vx, self.ground_vy, 0.0, 0.0,
                                                     config.KNOCKBACK_FRICTION * dt)
            self.animation.update(dt)
            if self.vx == self.ground_vy == 0 and self.animation.finished:
                self.animation.set_state("IDLE")
        else:
            self.animation.update(dt)

    def update(self, dt, player, walkable=None):
        if walkable is not None:
            self.walkable = walkable
        self.walkable.constrain(self, config.ENEMY_HALF_WIDTH)
        self.previous_x = self.x
        self.previous_ground_y = self.ground_y
        self.previous_jump_height = self.jump_height
        if self.falling_from_upper:
            self.update_floor_fall(dt)
        self._update_ai(dt, player)
        self.walkable.constrain(self, config.ENEMY_HALF_WIDTH)

    def _update_ai(self, dt, player):
        if self.state == "CAR_HIT":
            update_car_hit(self, dt)
            return
        if self.state == "STRONG_HIT":
            self.update_strong_hit(dt)
            return
        if not self.alive:
            self.vx = 0.0
            self.ground_vy = 0.0
            self.running = False
            if self.state == "DEAD":
                self.corpse_elapsed += dt
            else:
                self.animation.update(dt)
                if self.animation.finished:
                    self.animation.set_state("DEAD")
                    self.animation.elapsed = 8 / self.animation.definitions["DEAD"][1]
                    self.corpse_elapsed = 0.0
            return
        if self.knockback_started:
            self.update_knockback(dt)
            return
        if not player.alive:
            self.stop()
            self.animation.update(dt)
            return
        self.cooldown = max(0.0, self.cooldown - dt)
        if self.state == "HIT":
            self.vx = self.ground_vy = 0.0
            self.animation.update(dt)
            if self.animation.finished:
                self.animation.set_state("IDLE")
            return
        if self.state == "ATTACK":
            self.vx = 0.0
            self.ground_vy = 0.0
            self.animation.update(dt)
            if self.animation.finished:
                self.animation.set_state("IDLE")
            return

        if self.falling_from_upper:
            distance = player.x - self.x
            self.vx = self.ground_vy = 0.0
            if abs(distance) > config.ENEMY_SPACING_TOLERANCE:
                self.facing = 1 if distance > 0 else -1
                self.vx = self.facing * self.run_speed
                self.x += self.facing * min(abs(distance), self.run_speed * dt)
            self.animation.set_state("FALL")
            self.animation.update(dt)
            return

        if self.navigation_target is not None:
            dx, dy = self.navigation_target[0] - self.x, self.navigation_target[1] - self.ground_y
            distance = hypot(dx, dy)
            # Stair/queue waypoints are transit targets, not melee targets.
            # Keep running up to entry; only stop once the waiting slot is reached.
            # Droppers must actually reach the edge, not stop just short of it.
            tolerance = 1e-9 if self.descent_route == "DROP" else config.ENEMY_SPACING_TOLERANCE
            moving = distance > tolerance
            self.vx = self.ground_vy = 0.0
            if moving:
                speed = self.run_speed
                travel = min(distance, speed * dt)
                self.vx, self.ground_vy = dx / distance * speed, dy / distance * speed
                self.x += dx / distance * travel
                self.ground_y += dy / distance * travel
                if dx:
                    self.facing = 1 if dx > 0 else -1
            self.running = moving
            self.animation.set_state("RUN" if moving else "IDLE")
            self.animation.update(dt)
            return
        if not same_floor(self, player):
            self.stop()
            self.animation.update(dt)
            return

        distance = player.x - self.x
        depth = player.ground_y - self.ground_y
        gap = hypot(distance, depth)
        if distance:
            self.facing = 1 if distance > 0 else -1
        # Separate entry/exit thresholds prevent rapid WALK/RUN flickering.
        if gap >= config.ENEMY_RUN_START_DISTANCE:
            self.running = True
        elif gap <= config.ENEMY_RUN_STOP_DISTANCE:
            self.running = False
        self.vx = 0.0
        self.ground_vy = 0.0
        state = "IDLE"
        in_reach = (abs(distance) < config.ENEMY_ATTACK_REACH + config.PLAYER_HALF_WIDTH
                    and abs(depth) <= config.ATTACK_DEPTH_TOLERANCE)
        if self.target_x is not None:
            target_x = self.target_x - self.x
            target_y = self.target_ground_y - self.ground_y
            moving = hypot(target_x, target_y) > config.ENEMY_SPACING_TOLERANCE
        else:
            target_x = self.facing * max(0.0, abs(distance) - config.ENEMY_ATTACK_DISTANCE)
            target_y = depth
            moving = abs(distance) > config.ENEMY_ATTACK_DISTANCE or not in_reach
        approaching = player.vx * distance < 0 or player.ground_vy * depth < 0
        if self.target_x is not None and approaching and in_reach:
            # Stand and fight an advancing player instead of kiting away to
            # maintain a slot. This also preserves running/double-jump escapes.
            moving = False
        if moving:
            speed = self.run_speed if self.running else config.ENEMY_SPEED
            length = hypot(target_x, target_y)
            if length:
                self.vx = target_x / length * speed
                self.ground_vy = target_y / length * speed
            state = "RUN" if self.running else "WALK"
        elif self.cooldown <= 0 and in_reach:
            self.start_attack()
            self.animation.update(dt)
            return
        travel_x, travel_y = self.vx * dt, self.ground_vy * dt
        if moving and hypot(travel_x, travel_y) > hypot(target_x, target_y):
            travel_x, travel_y = target_x, target_y
        self.x += travel_x
        self.ground_y += travel_y
        self.animation.set_state(state)
        self.animation.update(dt)
