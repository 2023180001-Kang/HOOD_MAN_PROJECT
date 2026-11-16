"""Player state, movement and animation; graphics stay in the renderer."""

from math import hypot

import config
from animation import Animation
from collision import Rect
from combat import ALL_MOVES, STRONG_MOVES, moves_for_weapon
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
        self.weapon = None
        self.active_move = None
        self.weapon_leap_phase = None
        self.weapon_leap_direction = (1.0, 0.0)
        self.weapon_leap_velocity = (0.0, 0.0)
        self.air_kick_phase = None
        self.air_kick_strike_frame = config.AIR_KICK_STRIKE_FRAMES[0]
        self.air_kick_count = 0
        self.air_kicks_used = 0
        self.raise_punch_phase = None
        self.rush_phase = None
        self.counter_move = None
        self.hit_enemies = set()
        definitions = dict(config.PLAYER_ANIMATIONS)
        definitions.update({move.state: (move.row, move.fps, False)
                            for move in ALL_MOVES.values()})
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
    def moves(self):
        return moves_for_weapon(self.weapon)

    @property
    def time_scale(self):
        if self.alive and self.active_move is not None and self.air_kick_phase == "WAIT":
            return config.AIR_KICK_TIME_SCALE
        if self.alive and self.active_move is not None and self.raise_punch_phase == "RAISE":
            return config.R_RAISE_TIME_SCALE
        if self.alive and self.active_move is not None and self.active_move.jump_attack:
            if self.weapon_leap_phase == "AIM":
                return config.WEAPON_AIM_TIME_SCALE
            if self.weapon_leap_phase in ("DIVE", "LANDING"):
                return config.WEAPON_DIVE_TIME_SCALE
        return 1.0

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
        if self.active_move is not None:
            return self.active_move.image_name
        if self.state in config.WEAPON_POSE_ROWS.get(self.weapon, {}):
            return config.WEAPON_POSE_IMAGES[self.weapon]
        return config.PLAYER_IMAGE

    @property
    def sprite_row(self):
        if self.active_move is not None:
            return self.active_move.row
        if self.sprite_image in config.WEAPON_POSE_IMAGES.values():
            return config.WEAPON_POSE_ROWS[self.weapon][self.state]
        return self.animation.row

    def cancel_combat(self):
        self.active_move = None
        self.hit_enemies.clear()
        self.weapon_leap_phase = None
        self.weapon_leap_direction = (float(self.facing), 0.0)
        self.weapon_leap_velocity = (0.0, 0.0)
        self.air_kick_phase = None
        self.air_kick_strike_frame = config.AIR_KICK_STRIKE_FRAMES[0]
        self.air_kick_count = 0
        self.raise_punch_phase = None
        self.rush_phase = None

    def finish_move(self):
        self.cancel_combat()
        self.vx = self.ground_vy = 0.0
        self.animation.set_state("IDLE" if self.grounded else "JUMP")

    def equip_weapon(self, weapon):
        if weapon == self.weapon:
            return
        self.weapon = weapon
        if self.active_move is not None:
            # Dropping/swapping a weapon cannot leave its old strike pending.
            self.cancel_combat()
            self.animation.set_state("IDLE" if self.grounded else "JUMP")

    def start_move(self, move, direction):
        if move.jump_attack and (self.grounded or self.jump_count != 2):
            return
        if move is STRONG_MOVES["combat_e"]:
            if not self.grounded and self.air_kicks_used >= config.AIR_KICK_MAX_COUNT:
                return
            if self.grounded:
                self.air_kicks_used = 0
        velocity = self.vx, self.ground_vy
        self.cancel_combat()
        self.active_move = move
        self.vx = 0.0
        self.ground_vy = 0.0
        if direction:
            self.facing = direction
        self.animation.definitions[move.state] = (move.row, move.fps, False)
        self.animation.set_state(move.state)
        self.animation.elapsed = 0.0
        if move is STRONG_MOVES["combat_e"]:
            self.air_kick_phase = "KICK"
            self.air_kick_count = 1
            self.air_kicks_used += 1
        elif move is STRONG_MOVES["combat_r"]:
            self.raise_punch_phase = "RAISE"
        elif move is STRONG_MOVES["combat_w"]:
            self.rush_phase = "WINDUP"
        if move.jump_attack:
            self.weapon_leap_phase = "AIM"
            self.weapon_leap_direction = (float(self.facing), 0.0)
            self.vx, self.ground_vy = velocity
            self.animation.elapsed = 2.05 / move.fps

    def resume_air_kick(self):
        if (self.air_kick_count >= config.AIR_KICK_MAX_COUNT
                or self.air_kicks_used >= config.AIR_KICK_MAX_COUNT):
            return
        self.air_kick_count += 1
        self.air_kicks_used += 1
        self.air_kick_strike_frame = config.AIR_KICK_STRIKE_FRAMES[1]
        self.air_kick_phase = "KICK"
        self.hit_enemies.clear()
        self.animation.elapsed = (self.air_kick_strike_frame - 1) / self.active_move.fps

    def update_air_kick(self, dt, controls):
        self.vx = self.ground_vy = 0.0
        if controls.direction:
            self.facing = controls.direction
        self.update_vertical(dt)
        if self.air_kick_phase == "KICK":
            self.animation.update(dt)
            deadline = (self.air_kick_strike_frame + 1) / self.active_move.fps
            if self.animation.elapsed + 1e-9 >= deadline:
                if (self.air_kick_count >= config.AIR_KICK_MAX_COUNT
                        or self.air_kicks_used >= config.AIR_KICK_MAX_COUNT):
                    self.air_kick_phase = "RECOVERY"
                    self.animation.elapsed = deadline
                else:
                    self.air_kick_phase = "WAIT"
        elif self.air_kick_phase == "RECOVERY":
            self.animation.update(dt)
            if self.animation.finished:
                self.finish_move()
                return
        if self.air_kick_phase == "WAIT":
            # Retract the leg between fresh E presses; this pose never attacks.
            self.animation.elapsed = config.AIR_KICK_HOLD_FRAME / self.active_move.fps

    def update_raise_punch(self, dt):
        self.vx = self.ground_vy = 0.0
        self.update_vertical(dt)
        if self.raise_punch_phase == "RAISE":
            self.animation.update(dt)
            self.animation.elapsed = min(self.animation.elapsed,
                                         (config.R_READY_FRAME + 0.05) / self.active_move.fps)
        else:
            self.animation.update(dt)
            if self.animation.finished:
                self.finish_move()

    def release_rush(self):
        self.vx = self.ground_vy = 0.0
        if self.rush_phase == "WINDUP":
            self.finish_move()
        elif self.rush_phase == "FLY":
            self.rush_phase = "RECOVERY"
            self.vy = 0.0
            self.animation.elapsed = 6 / self.active_move.fps

    def update_rush(self, dt, controls):
        move = self.active_move
        if self.rush_phase in ("WINDUP", "FLY") and controls.direction:
            self.facing = controls.direction
        if self.rush_phase == "WINDUP":
            self.update_vertical(dt)
            self.animation.update(dt)
            if self.animation.elapsed + 1e-9 >= 3 / move.fps:
                self.rush_phase = "FLY"
                self.jump_height = max(self.jump_height, config.RUSH_HEIGHT)
                self.vy = 0.0
                self.jump_count = max(1, self.jump_count)
                self.animation.elapsed = (config.RUSH_PLAYER_HOLD_FRAME + 0.05) / move.fps
        elif self.rush_phase == "FLY":
            self.vx, self.ground_vy = self.facing * config.RUSH_SPEED, 0.0
            self.x += self.vx * dt
            self.animation.elapsed = (config.RUSH_PLAYER_HOLD_FRAME + 0.05) / move.fps
        else:
            self.vx = self.ground_vy = 0.0
            self.update_vertical(dt)
            self.animation.update(dt)
            if self.animation.finished:
                self.finish_move()

    def start_weapon_dive(self, controls):
        direction = controls.movement if controls.moving else self.weapon_leap_direction
        if direction[0]:
            self.facing = 1 if direction[0] > 0 else -1
        self.weapon_leap_direction = direction
        self.weapon_leap_velocity = tuple(axis * config.WEAPON_DIVE_SPEED for axis in direction)
        self.vx, self.ground_vy = self.weapon_leap_velocity
        self.vy = -config.WEAPON_DIVE_FALL_SPEED
        self.weapon_leap_phase = "DIVE"
        self.animation.elapsed = 3.05 / self.active_move.fps

    def update_weapon_leap(self, dt, controls):
        move = self.active_move
        if self.weapon_leap_phase == "AIM":
            speed = config.RUN_SPEED if controls.running else config.WALK_SPEED
            self.move_on_ground(dt, controls, speed)
            if controls.moving:
                self.weapon_leap_direction = controls.movement
            self.update_vertical(dt)
            self.animation.elapsed = (2.05 if self.vy >= 0 else 3.05) / move.fps
            if self.grounded:
                # Waiting out the jump without a second D never releases a hit.
                self.cancel_combat()
                self.animation.set_state("IDLE")
            return
        if self.weapon_leap_phase == "DIVE":
            self.vx, self.ground_vy = self.weapon_leap_velocity
            self.x += self.vx * dt
            self.ground_y += self.ground_vy * dt
            self.walkable.constrain(self, config.PLAYER_HALF_WIDTH)
            self.update_vertical(dt)
            self.animation.elapsed = 3.05 / move.fps
            if self.grounded:
                self.weapon_leap_phase = "LANDING"
                self.vx = self.ground_vy = 0.0
                self.animation.elapsed = 4 / move.fps
            return
        self.vx = self.ground_vy = 0.0
        self.animation.update(dt)
        if self.animation.finished:
            self.cancel_combat()
            self.animation.set_state("IDLE")

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
                or self.animation.frame not in move.active_frames):
            return None
        if move.jump_attack and (self.weapon_leap_phase != "LANDING" or not self.grounded):
            return None
        if self.rush_phase is not None or self.raise_punch_phase == "RAISE":
            return None
        if self.air_kick_phase is not None and (
                self.air_kick_phase != "KICK" or self.animation.frame != self.air_kick_strike_frame):
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
        if self.active_move.enemy_hit_row is not None:
            return enemy.take_strong_hit(self.active_move, self.facing)
        return enemy.take_damage(self.active_move.damage)

    def take_damage(self, damage):
        if (not self.alive or self.invincible
                or (self.counter_move is not None and not self.counter_holding)):
            return False
        self.hp = max(0, self.hp - damage)
        self.vx = 0.0
        self.ground_vy = 0.0
        self.cancel_combat()
        if self.hp and self.state != "HIT":
            # Choose recovery speed once per reaction; further hits must not
            # restart or prolong it, even if equipment changes during HIT.
            row, fps, loop = config.PLAYER_ANIMATIONS["HIT"]
            if self.weapon in config.WEAPON_POSE_IMAGES:
                fps = config.WEAPON_HIT_FPS
            self.animation.definitions["HIT"] = (row, fps, loop)
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
                self.air_kicks_used = 0

    def update(self, dt, controls, walkable=None, *, process_input=True):
        if walkable is not None:
            self.walkable = walkable
        self.walkable.constrain(self, config.PLAYER_HALF_WIDTH)
        self.previous_x = self.x
        self.previous_ground_y = self.ground_y
        self.previous_jump_height = self.jump_height
        if process_input:
            self.handle_input(controls)
        self._update(dt, controls)
        self.walkable.constrain(self, config.PLAYER_HALF_WIDTH)

    def handle_input(self, controls):
        """Resolve fresh actions before World samples the simulation time scale."""
        if controls.take_press("invincibility") and self.alive:
            self.invincible = not self.invincible
        jump_pressed = controls.take_press("jump")
        combat_pressed = controls.take_latest_press(ALL_MOVES)
        if self.counter_move is not None or self.state in ("CAR_HIT", "HIT", "DYING", "DEAD"):
            return
        if self.rush_phase in ("WINDUP", "FLY") and "combat_w" not in controls.held:
            self.release_rush()
        move = STRONG_MOVES.get(combat_pressed) or self.moves.get(combat_pressed)
        if (jump_pressed and self.active_move is None and self.jump_count < 2
                and (move is None or move.jump_attack)):
            if self.jump_count == 0:
                self.vy = config.JUMP_SPEED
                self.air_kicks_used = 0
            elif controls.running and controls.moving:
                self.vy = config.RUN_DOUBLE_JUMP_SPEED
            else:
                self.vy = config.DOUBLE_JUMP_SPEED
            self.jump_count += 1
            self.animation.set_state("JUMP")
            self.animation.elapsed = 0.0
        if move is not None:
            if move == self.active_move:
                if move.jump_attack and self.weapon_leap_phase == "AIM":
                    self.start_weapon_dive(controls)
                elif self.air_kick_phase == "WAIT":
                    self.resume_air_kick()
                elif self.raise_punch_phase == "RAISE":
                    self.raise_punch_phase = "STRIKE"
                    self.animation.elapsed = config.R_READY_FRAME / move.fps
            else:
                self.start_move(move, controls.direction)

    def _update(self, dt, controls):
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

        if self.active_move is not None:
            if self.air_kick_phase is not None:
                self.update_air_kick(dt, controls)
                return
            if self.raise_punch_phase is not None:
                self.update_raise_punch(dt)
                return
            if self.rush_phase is not None:
                self.update_rush(dt, controls)
                return
            if self.active_move.jump_attack:
                self.update_weapon_leap(dt, controls)
                return
            self.vx = 0.0
            self.ground_vy = 0.0
            self.update_vertical(dt)
            self.animation.update(dt)
            if self.animation.finished:
                self.cancel_combat()
                self.animation.set_state("IDLE")
            return

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
