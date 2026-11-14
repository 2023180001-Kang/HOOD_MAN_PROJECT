"""Player state, movement and animation; graphics stay in the renderer."""

from math import hypot

import config
from animation import Animation
from collision import Rect
from combat import MOVES
from counter import COUNTERS
from physics import approach_vector
from traffic import start_car_hit, update_car_hit
from walkable import default_area


class Player:
    boundary_padding = config.PLAYER_BOUNDARY_PADDING

    def __init__(self):
        self.x = config.START_X
        self.previous_x = self.x
        self.ground_y = config.GROUND_Y
        self.previous_ground_y = self.ground_y
        self.jump_height = 0.0
        self.previous_jump_height = 0.0
        self.ground_vy = 0.0
        self.walkable = default_area()
        self.vx = 0.0
        self.vy = 0.0
        self.jump_count = 0
        self.facing = 1
        self.hp = config.MAX_HP
        self.invincible = False
        self.car_hit = False
        self.active_move = None
        self.counter_move = None
        self.hit_enemies = set()
        definitions = dict(config.PLAYER_ANIMATIONS)
        definitions.update({move.state: (move.row, move.fps, False)
                            for move in MOVES.values()})
        definitions.update({move.state: (move.row, move.fps, False)
                            for move in COUNTERS.values()})
        definitions.update({move.hold_state: (move.row, move.fps, False)
                            for move in COUNTERS.values()})
        self.animation = Animation(definitions)

    @property
    def state(self):
        return self.animation.state

    @property
    def alive(self):
        return self.hp > 0

    @property
    def y(self):
        """Projected feet; physics keeps ground_y and jump_height independent."""
        return self.ground_y + self.jump_height

    @y.setter
    def y(self, value):
        self.jump_height = max(0.0, value - self.ground_y)

    @property
    def sprite_image(self):
        if self.car_hit:
            return config.PLAYER_CAR_HIT_IMAGE
        if self.counter_move is not None:
            return config.COUNTER_PLAYER_IMAGE
        return config.COMBAT_IMAGE if self.active_move is not None else config.PLAYER_IMAGE

    def cancel_combat(self):
        self.active_move = None
        self.hit_enemies.clear()

    def start_move(self, move, direction):
        self.active_move = move
        self.hit_enemies.clear()
        self.vx = 0.0
        self.ground_vy = 0.0
        if direction:
            self.facing = direction
        self.animation.set_state(move.state)

    def start_counter(self, move, facing):
        self.cancel_combat()
        self.counter_move = move
        self.vx = self.ground_vy = 0.0
        self.facing = facing
        self.animation.set_state(move.state)

    @property
    def grounded(self):
        return self.jump_height <= 0.0 and self.vy == 0

    @property
    def counter_holding(self):
        return self.counter_move is not None and self.state == self.counter_move.hold_state

    @property
    def body(self):
        """x/height-plane AABB; ground-depth proximity is a separate condition."""
        base = config.GROUND_Y + self.jump_height
        return Rect(self.x - config.PLAYER_HALF_WIDTH, base,
                    self.x + config.PLAYER_HALF_WIDTH, base + config.PLAYER_HEIGHT)

    @property
    def attack_box(self):
        move = self.active_move
        if (not self.alive or move is None or self.state != move.state
                or self.animation.frame not in config.PLAYER_ACTIVE_FRAMES):
            return None
        near = self.x + self.facing * 10
        far = self.x + self.facing * move.reach
        base = config.GROUND_Y + self.jump_height
        return Rect(min(near, far), base + 20, max(near, far), base + move.height)

    def try_hit(self, enemy):
        box = self.attack_box
        if (box is None or not enemy.alive or enemy in self.hit_enemies
                or abs(self.ground_y - enemy.ground_y) > config.ATTACK_DEPTH_TOLERANCE
                or not box.overlaps(enemy.body)):
            return False
        self.hit_enemies.add(enemy)
        return enemy.take_damage(self.active_move.damage)

    def take_damage(self, damage):
        if (not self.alive or self.invincible
                or (self.counter_move is not None and not self.counter_holding)):
            return False
        self.hp = max(0, self.hp - damage)
        self.vx = 0.0
        self.ground_vy = 0.0
        self.cancel_combat()
        # Every enemy swing applies damage. Re-entering HIT preserves the
        # current animation clock; a lethal hit always overrides it with DYING.
        self.animation.set_state("HIT" if self.hp else "DYING")
        return True

    def hit_by_car(self, direction):
        if not self.alive:
            return False
        self.cancel_combat()
        self.counter_move = None
        self.invincible = False
        start_car_hit(self, direction)
        return True

    def update_vertical(self, dt):
        if not self.grounded:
            self.vy -= config.GRAVITY * dt
            self.jump_height += self.vy * dt
            if self.jump_height <= 0.0:
                self.jump_height = 0.0
                self.vy = 0.0
                self.jump_count = 0

    def update(self, dt, controls, walkable=None):
        if walkable is not None:
            self.walkable = walkable
        self.walkable.constrain(self, config.PLAYER_HALF_WIDTH)
        self.previous_x = self.x
        self.previous_ground_y = self.ground_y
        self.previous_jump_height = self.jump_height
        self._update(dt, controls)
        self.walkable.constrain(self, config.PLAYER_HALF_WIDTH)

    def _update(self, dt, controls):
        if controls.take_press("invincibility") and self.alive:
            self.invincible = not self.invincible
        jump_pressed = controls.take_press("jump")
        combat_pressed = controls.take_latest_press(MOVES)
        if self.state == "CAR_HIT":
            update_car_hit(self, dt)
            return
        if self.counter_move is not None:
            if self.counter_holding:
                self.move_on_ground(dt, controls, config.COUNTER_CARRY_SPEED, turn=False)
            else:
                self.vx = self.ground_vy = 0.0
            return  # The paired counter owns both animation clocks.
        if self.state in ("HIT", "DYING", "DEAD"):
            self.vx = 0.0
            self.ground_vy = 0.0
            self.update_vertical(dt)
            if self.state == "DEAD":
                return
            self.animation.update(dt)
            if self.animation.finished:
                if self.state == "DYING":
                    self.animation.set_state("DEAD")
                    self.animation.elapsed = 8 / config.PLAYER_ANIMATIONS["DEAD"][1]
                else:
                    self.animation.set_state("IDLE")
            return

        if combat_pressed is not None:
            move = MOVES[combat_pressed]
            if move != self.active_move:
                self.start_move(move, controls.direction)
        if self.active_move is not None:
            self.vx = 0.0
            self.ground_vy = 0.0
            self.update_vertical(dt)
            self.animation.update(dt)
            if self.animation.finished:
                self.cancel_combat()
                self.animation.set_state("IDLE")
            return

        if jump_pressed and self.jump_count < 2:
            if self.jump_count == 0:
                self.vy = config.JUMP_SPEED
            elif controls.running and controls.moving:
                self.vy = config.RUN_DOUBLE_JUMP_SPEED
            else:
                self.vy = config.DOUBLE_JUMP_SPEED
            self.jump_count += 1
            self.animation.set_state("JUMP")
            self.animation.elapsed = 0.0

        speed = config.RUN_SPEED if controls.running else config.WALK_SPEED
        self.move_on_ground(dt, controls, speed)
        self.update_vertical(dt)

        state = "IDLE"
        if hypot(self.vx, self.ground_vy) > 0.1:
            state = "RUN" if controls.running else "WALK"
        if not self.grounded:
            state = "JUMP"
        self.animation.set_state(state)
        self.animation.update(dt)

    def move_on_ground(self, dt, controls, speed, *, turn=True):
        move_x, move_y = controls.movement
        target_x, target_y = move_x * speed, move_y * speed
        magnitude = hypot(self.vx, self.ground_vy)
        if controls.moving and self.vx * move_x + self.ground_vy * move_y < 0:
            # Brake to zero first; only the remaining time accelerates the turn.
            stop_time = magnitude / config.FRICTION
            self.vx, self.ground_vy = approach_vector(self.vx, self.ground_vy, 0.0, 0.0,
                                                     config.FRICTION * dt)
            if stop_time < dt:
                self.vx, self.ground_vy = approach_vector(0.0, 0.0, target_x, target_y,
                                                         config.ACCELERATION * (dt - stop_time))
        else:
            # Releasing Shift must use the same strong braking as releasing a key.
            slowing = not controls.moving or magnitude > speed
            rate = config.FRICTION if slowing else config.ACCELERATION
            self.vx, self.ground_vy = approach_vector(self.vx, self.ground_vy, target_x, target_y,
                                                     rate * dt)
        self.x += self.vx * dt
        self.ground_y += self.ground_vy * dt
        self.walkable.constrain(self, config.PLAYER_HALF_WIDTH)
        if turn and controls.direction:
            self.facing = controls.direction
