"""Capture, carry and A-triggered follow-ups using the matching counter rows."""

from dataclasses import dataclass

import config
from physics import clamp
from walkable import WalkableArea


@dataclass(frozen=True)
class CounterMove:
    key: str
    name: str
    row: int
    damage: int
    fps: float
    enemy_fps: float
    impact_frame: int

    @property
    def state(self):
        return f"COUNTER_{self.key.upper()}"

    @property
    def enemy_state(self):
        return f"SUBDUED_{self.key.upper()}"

    @property
    def hold_state(self):
        return f"HOLD_{self.key.upper()}"

    @property
    def enemy_hold_state(self):
        return f"HELD_{self.key.upper()}"

    @property
    def hold_times(self):
        player_frame, enemy_frame = config.COUNTER_HOLD_FRAMES[self.key]
        return player_frame / self.fps, enemy_frame / self.enemy_fps

    @property
    def duration(self):
        return 8 / self.fps

    @property
    def enemy_duration(self):
        return 8 / self.enemy_fps


COUNTERS = {
    f"counter_{key}": CounterMove(key, name, row, config.COUNTER_DAMAGE,
                                 config.COUNTER_FPS, config.COUNTER_ENEMY_FPS, impact_frame)
    for key, name, row, impact_frame in config.COUNTER_MOVE_SPECS
}


def can_counter(player, enemy):
    return (enemy.alive and enemy.counter_move is None and not enemy.knockback_started
            and enemy.state == "ATTACK" and not enemy.has_hit
            and enemy.animation.frame in config.COUNTER_TRIGGER_FRAMES
            and enemy.jump_height == 0 and not enemy.leaping
            and abs(enemy.x - player.x) <= config.COUNTER_RANGE
            and abs(enemy.ground_y - player.ground_y) <= config.COUNTER_DEPTH_TOLERANCE
            and (player.x - enemy.x) * enemy.facing >= 0)


class CounterSequence:
    """Pause before the strike until A; constrain both feet as one carried pair."""

    @classmethod
    def start(cls, player, enemy, move, walkable):
        side = (1 if enemy.x > player.x else -1) if enemy.x != player.x else -enemy.facing
        player_padding = max(player.boundary_padding, config.COUNTER_BOUNDARY_PADDING)
        enemy_padding = max(enemy.boundary_padding, config.COUNTER_BOUNDARY_PADDING)
        distance = config.COUNTER_PAIR_DISTANCE * side
        # On a convex floor the pair's horizontal envelope is one footprint.
        # Inset about its center, then translate back to player coordinates.
        left = min(-player_padding, distance - enemy_padding)
        right = max(player_padding, distance + enemy_padding)
        center = (left + right) / 2
        try:
            carry_area = WalkableArea(tuple((x - center, y) for x, y in
                                           walkable.inset((right - left) / 2)))
        except ValueError:
            return None
        limits = carry_area.x_limits(player.ground_y)
        if limits is None:
            return None
        player_x = clamp(player.x, *limits)
        return cls(player, enemy, move, side, player_x, player_x + distance, carry_area)

    def __init__(self, player, enemy, move, side, player_x, enemy_x, carry_area):
        self.player, self.enemy, self.move = player, enemy, move
        self.side = side
        self.carry_area = carry_area
        self.phase = "CAPTURE"
        self.capture_elapsed = 0.0
        self.elapsed = 0.0
        self.enemy_elapsed = 0.0
        self.damage_applied = False
        self.finished = False
        self.player_padding = player.boundary_padding
        player.boundary_padding = max(self.player_padding, config.COUNTER_BOUNDARY_PADDING)
        player.x = player.previous_x = player_x
        enemy.x = enemy.previous_x = enemy_x
        enemy.ground_y = enemy.previous_ground_y = player.ground_y
        player.previous_ground_y = player.ground_y
        player.start_counter(move, side)
        enemy.start_counter(move, -side)

    @property
    def valid(self):
        return (self.player.alive and self.player.counter_move is self.move
                and self.player.state in (self.move.state, self.move.hold_state)
                and self.enemy.counter_move is self.move
                and (self.phase == "FOLLOW_UP" or self.enemy.alive))

    @property
    def holding(self):
        return self.phase == "HOLD" and not self.finished

    def sync_pair(self):
        player, enemy = self.player, self.enemy
        x, y = self.carry_area.project(player.x, player.ground_y)
        if abs(x - player.x) > 1e-9:
            player.vx = 0.0
        if abs(y - player.ground_y) > 1e-9:
            player.ground_vy = 0.0
        player.x, player.ground_y = x, y
        player.facing = self.side
        enemy.x = player.x + self.side * config.COUNTER_PAIR_DISTANCE
        enemy.ground_y = player.ground_y
        enemy.facing = -self.side
        enemy.jump_height = config.COUNTER_CARRY_HEIGHT if self.holding else 0.0

    def start_follow_up(self):
        if not self.holding:
            return False
        self.phase = "FOLLOW_UP"
        self.player.vx = self.player.ground_vy = 0.0
        self.player.animation.set_state(self.move.state)
        self.enemy.animation.set_state(self.move.enemy_state)
        self.player.animation.elapsed = self.elapsed
        self.enemy.animation.elapsed = self.enemy_elapsed
        self.enemy.jump_height = 0.0
        return True

    def update(self, dt):
        if self.phase == "CAPTURE":
            self.capture_elapsed += dt
            player_time, enemy_time = self.move.hold_times
            self.elapsed = min(player_time, self.capture_elapsed)
            self.enemy_elapsed = min(enemy_time, self.capture_elapsed)
            if self.capture_elapsed + 1e-9 >= max(player_time, enemy_time):
                self.elapsed, self.enemy_elapsed = player_time, enemy_time
                self.phase = "HOLD"
                self.player.animation.set_state(self.move.hold_state)
                self.enemy.animation.set_state(self.move.enemy_hold_state)
                self.player.vx = self.player.ground_vy = 0.0
                self.sync_pair()
            self.player.animation.elapsed = self.elapsed
            self.enemy.animation.elapsed = self.enemy_elapsed
            return 0
        if self.holding:
            return 0
        self.elapsed = min(self.move.duration, self.elapsed + dt)
        self.enemy_elapsed = min(self.move.enemy_duration, self.enemy_elapsed + dt)
        if self.elapsed + 1e-9 >= self.move.duration:
            self.elapsed = self.move.duration
        self.player.animation.elapsed = self.elapsed
        self.enemy.animation.elapsed = self.enemy_elapsed
        damage = 0
        if not self.damage_applied and self.elapsed + 1e-9 >= self.move.impact_frame / self.move.fps:
            previous_hp = self.enemy.hp
            self.enemy.take_damage(self.move.damage)
            damage = previous_hp - self.enemy.hp
            self.damage_applied = True
        if self.elapsed + 1e-9 >= self.move.duration:
            self.finished = True
            self._release_player()
            self.enemy.release_counter()
        return damage

    def _release_player(self):
        if self.player.counter_move is self.move:
            self.player.counter_move = None
            self.player.boundary_padding = self.player_padding
            self.player.vx = self.player.ground_vy = 0.0
            if self.player.state in (self.move.state, self.move.hold_state):
                self.player.animation.set_state("IDLE" if self.player.alive else "DYING")

    def finish(self):
        """Cancel an interrupted pair, including a restart before player recovery."""
        if self.finished:
            return
        self.finished = True
        self._release_player()
        if self.enemy.counter_move is self.move:
            self.enemy.jump_height = 0.0
            self.enemy.finish_counter()
