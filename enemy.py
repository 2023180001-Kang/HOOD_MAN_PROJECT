"""Independent street-thug AI and animation state."""

from math import hypot

import config
from animation import Animation
from collision import Rect
from counter import COUNTERS
from physics import approach_vector
from walkable import default_area


class Enemy:
    boundary_padding = config.ENEMY_BOUNDARY_PADDING

    def __init__(self, x, facing=1, spawned_at=0.0, *, run_speed=None, ground_y=None,
                 attack_speed=1.0):
        self.x = x
        self.previous_x = x
        self.ground_y = config.GROUND_Y if ground_y is None else ground_y
        self.previous_ground_y = self.ground_y
        self.jump_height = 0.0
        self.ground_vy = 0.0
        self.walkable = default_area()
        self.vx = 0.0
        self.facing = facing
        self.spawned_at = spawned_at
        self.cooldown = 0.0
        self.has_hit = False
        self.knockback_started = False
        self.run_speed = config.ENEMY_RUN_SPEEDS[0] if run_speed is None else run_speed
        self.running = False
        self.hp = config.ENEMY_MAX_HP
        self.corpse_elapsed = 0.0
        self.counter_move = None
        self.counter_linked = False
        self.counter_padding = self.boundary_padding
        self.counter_death = None
        self.attack_speed = attack_speed
        self.attack_interval = config.ENEMY_ATTACK_INTERVAL / attack_speed
        definitions = dict(config.ENEMY_ANIMATIONS)
        row, fps, loop = definitions["ATTACK"]
        self.attack_fps = fps * attack_speed
        definitions["ATTACK"] = (row, self.attack_fps, loop)
        definitions.update({move.enemy_state: (move.row, move.enemy_fps, False)
                            for move in COUNTERS.values()})
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
        return (config.COUNTER_ENEMY_IMAGE if self.counter_move is not None
                or self.counter_death is not None else config.ENEMY_IMAGE)

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
        self.hp = max(0, self.hp - damage)
        self.vx = 0.0
        self.ground_vy = 0.0
        self.running = False
        self.has_hit = True
        self.knockback_started = False
        if self.counter_move is None:
            self.animation.set_state("HIT" if self.alive else "DYING")
        return True

    def start_counter(self, move, facing):
        self.counter_move = move
        self.counter_linked = True
        self.counter_padding = self.boundary_padding
        self.boundary_padding = max(self.boundary_padding, config.COUNTER_BOUNDARY_PADDING)
        self.vx = self.ground_vy = 0.0
        self.running = False
        self.has_hit = True
        self.facing = facing
        self.formation_slot = None
        self.target_x = self.target_ground_y = None
        self.animation.set_state(move.enemy_state)

    def release_counter(self):
        """Continue the slower reaction after the player is free to act."""
        self.counter_linked = False
        if self.animation.elapsed + 1e-9 >= self.counter_move.enemy_duration:
            self.finish_counter()

    def finish_counter(self):
        move = self.counter_move
        self.counter_move = None
        self.counter_linked = False
        self.cooldown = self.attack_interval
        if self.alive:
            self.boundary_padding = self.counter_padding
            self.animation.set_state("IDLE")
        else:
            # The supplied last pose already shows the defeated enemy on the
            # floor; keep it instead of replaying the standard death sheet.
            self.counter_death = move
            self.animation.definitions["DEAD"] = (move.row, move.enemy_fps, False)
            self.animation.set_state("DEAD")
            self.animation.elapsed = move.enemy_duration
            self.corpse_elapsed = 0.0

    @property
    def body(self):
        base = config.GROUND_Y + self.jump_height
        return Rect(self.x - config.ENEMY_HALF_WIDTH, base,
                    self.x + config.ENEMY_HALF_WIDTH, base + config.ENEMY_HEIGHT)

    @property
    def attack_box(self):
        if (not self.alive or self.state != "ATTACK" or self.has_hit
                or self.animation.frame not in config.ENEMY_ACTIVE_FRAMES):
            return None
        near = self.x + self.facing * 12
        far = self.x + self.facing * config.ENEMY_ATTACK_REACH
        base = config.GROUND_Y + self.jump_height
        return Rect(min(near, far), base + 20, max(near, far), base + config.ENEMY_HEIGHT)

    def try_hit(self, player):
        box = self.attack_box
        if (box is not None and abs(self.ground_y - player.ground_y) <= config.ATTACK_DEPTH_TOLERANCE
                and box.overlaps(player.body)):
            # Per-enemy swing consumption prevents repeated active-frame damage.
            self.has_hit = True
            return player.take_damage(config.ENEMY_DAMAGE)
        return False

    def knockback(self, player_x, player_ground_y=None):
        if not self.alive or self.knockback_started or self.counter_move is not None:
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
        self._update_ai(dt, player)
        self.walkable.constrain(self, config.ENEMY_HALF_WIDTH)

    def _update_ai(self, dt, player):
        if self.counter_move is not None:
            self.vx = self.ground_vy = 0.0
            self.running = False
            if not self.counter_linked:
                self.animation.update(dt)
                if self.animation.elapsed + 1e-9 >= self.counter_move.enemy_duration:
                    self.finish_counter()
            return  # Even a lethal counter finishes its reaction before corpse timing.
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
                    self.animation.elapsed = 8 / config.ENEMY_ANIMATIONS["DEAD"][1]
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
            self.animation.set_state("ATTACK")
            self.has_hit = False
            self.cooldown = self.attack_interval
            self.animation.update(dt)
            return
        travel_x, travel_y = self.vx * dt, self.ground_vy * dt
        if moving and hypot(travel_x, travel_y) > hypot(target_x, target_y):
            travel_x, travel_y = target_x, target_y
        self.x += travel_x
        self.ground_y += travel_y
        self.animation.set_state(state)
        self.animation.update(dt)
