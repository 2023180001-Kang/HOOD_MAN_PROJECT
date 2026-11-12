"""Player state, movement and animation; graphics stay in the renderer."""

from math import sin, tau

import config
from animation import Animation
from collision import Rect
from combat import MOVES
from physics import approach, clamp


class Player:
    def __init__(self):
        self.x = config.START_X
        self.previous_x = self.x
        self.y = config.GROUND_Y
        self.vx = 0.0
        self.vy = 0.0
        self.jump_count = 0
        self.facing = 1
        self.hp = config.MAX_HP
        self.invincible = False
        self.active_move = None
        self.block_elapsed = 0.0
        self.hit_enemies = set()
        definitions = dict(config.PLAYER_ANIMATIONS)
        definitions.update({move.state: (move.row, config.BLOCK_FPS if move.blocking
                                         else config.COMBAT_FPS, False)
                            for move in MOVES.values()})
        self.animation = Animation(definitions)

    @property
    def state(self):
        return self.animation.state

    @property
    def alive(self):
        return self.hp > 0

    @property
    def blocking(self):
        return (self.alive and self.active_move is not None
                and self.active_move.blocking and self.state == "BLOCK")

    @property
    def sprite_image(self):
        return config.COMBAT_IMAGE if self.active_move is not None else config.PLAYER_IMAGE

    @property
    def sprite_offset_x(self):
        """Subtle held-guard sway, applied only to the drawn sprite."""
        if not self.blocking:
            return 0.0
        elapsed = max(0.0, self.block_elapsed - config.BLOCK_HOLD_FRAME / config.BLOCK_FPS)
        return (sin(tau * elapsed / config.BLOCK_SWAY_PERIOD)
                * config.BLOCK_SWAY_AMPLITUDE * self.facing)

    def cancel_combat(self):
        self.active_move = None
        self.block_elapsed = 0.0
        self.hit_enemies.clear()

    def start_move(self, move, direction):
        self.active_move = move
        self.block_elapsed = 0.0
        self.hit_enemies.clear()
        self.vx = 0.0
        if direction:
            self.facing = direction
        self.animation.set_state(move.state)

    @property
    def grounded(self):
        return self.y <= config.GROUND_Y and self.vy == 0

    @property
    def body(self):
        return Rect(self.x - config.PLAYER_HALF_WIDTH, self.y,
                    self.x + config.PLAYER_HALF_WIDTH, self.y + config.PLAYER_HEIGHT)

    @property
    def attack_box(self):
        move = self.active_move
        if (not self.alive or move is None or move.blocking or self.state != move.state
                or self.animation.frame not in config.PLAYER_ACTIVE_FRAMES):
            return None
        near = self.x + self.facing * 10
        far = self.x + self.facing * move.reach
        return Rect(min(near, far), self.y + 20, max(near, far), self.y + move.height)

    def try_hit(self, enemy):
        box = self.attack_box
        if (box is None or not enemy.alive or enemy in self.hit_enemies
                or not box.overlaps(enemy.body)):
            return False
        self.hit_enemies.add(enemy)
        return enemy.take_damage(self.active_move.damage)

    def take_damage(self, damage, *, source_x=None):
        if not self.alive or self.invincible:
            return False
        if (self.blocking and source_x is not None
                and (source_x - self.x) * self.facing >= 0):
            # Recoil refreshes without stacking or interrupting the held guard.
            self.vx = -self.facing * config.BLOCK_KNOCKBACK_SPEED
            return False
        self.hp = max(0, self.hp - damage)
        self.vx = 0.0
        self.cancel_combat()
        # Every enemy swing applies damage. Re-entering HIT preserves the
        # current animation clock; a lethal hit always overrides it with DYING.
        self.animation.set_state("HIT" if self.hp else "DYING")
        return True

    def update_vertical(self, dt):
        if not self.grounded:
            self.vy -= config.GRAVITY * dt
            self.y += self.vy * dt
            if self.y <= config.GROUND_Y:
                self.y = config.GROUND_Y
                self.vy = 0.0
                self.jump_count = 0

    def update(self, dt, controls):
        self.previous_x = self.x
        if controls.take_press("invincibility") and self.alive:
            self.invincible = not self.invincible
        jump_pressed = controls.take_press("jump")
        combat_pressed = controls.take_first_press(MOVES)
        if self.state in ("HIT", "DYING", "DEAD"):
            self.vx = 0.0
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

        if self.blocking and "combat_h" not in controls.held:
            self.vx = 0.0
            self.cancel_combat()
            self.animation.set_state("IDLE")
        if self.active_move is None:
            if "combat_h" in controls.held:
                self.start_move(MOVES["combat_h"], controls.direction)
            elif combat_pressed is not None and not MOVES[combat_pressed].blocking:
                self.start_move(MOVES[combat_pressed], controls.direction)
        if self.active_move is not None:
            if self.blocking:
                self.block_elapsed += dt
                proposed = self.x + self.vx * dt
                self.x = clamp(proposed, config.PLAYER_HALF_WIDTH,
                               config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)
                self.vx = (0.0 if proposed != self.x else
                           approach(self.vx, 0.0, config.BLOCK_KNOCKBACK_FRICTION * dt))
            else:
                self.vx = 0.0
            self.update_vertical(dt)
            self.animation.update(dt)
            if self.blocking:
                # Reach a readable guard pose, then hold it until H is released.
                self.animation.elapsed = min(self.animation.elapsed,
                                             config.BLOCK_HOLD_FRAME / config.BLOCK_FPS)
            elif self.animation.finished:
                self.cancel_combat()
                self.animation.set_state("IDLE")
            return

        if jump_pressed and self.jump_count < 2:
            if self.jump_count == 0:
                self.vy = config.JUMP_SPEED
            elif controls.running and controls.direction:
                self.vy = config.RUN_DOUBLE_JUMP_SPEED
            else:
                self.vy = config.DOUBLE_JUMP_SPEED
            self.jump_count += 1
            self.animation.set_state("JUMP")
            self.animation.elapsed = 0.0

        direction = controls.direction
        speed = config.RUN_SPEED if controls.running else config.WALK_SPEED
        target = direction * speed
        if direction and self.vx * direction < 0:
            # Brake to zero first; only the remaining time accelerates the turn.
            stop_time = abs(self.vx) / config.FRICTION
            self.vx = approach(self.vx, 0.0, config.FRICTION * dt)
            if stop_time < dt:
                self.vx = approach(0.0, target, config.ACCELERATION * (dt - stop_time))
        else:
            # Releasing Shift must use the same strong braking as releasing a key.
            slowing = not direction or abs(self.vx) > speed
            rate = config.FRICTION if slowing else config.ACCELERATION
            self.vx = approach(self.vx, target, rate * dt)
        self.x += self.vx * dt
        bounded = clamp(self.x, config.PLAYER_HALF_WIDTH,
                        config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)
        if bounded != self.x:
            self.vx = 0.0
            self.x = bounded
        if direction:
            self.facing = direction
        self.update_vertical(dt)

        state = "IDLE"
        if abs(self.vx) > 0.1:
            state = "RUN" if controls.running else "WALK"
        if not self.grounded:
            state = "JUMP"
        self.animation.set_state(state)
        self.animation.update(dt)
