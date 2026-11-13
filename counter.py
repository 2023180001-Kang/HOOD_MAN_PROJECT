"""Matching player/enemy counter rows and their shared playback timing."""

from dataclasses import dataclass

import config
from physics import clamp


@dataclass(frozen=True)
class CounterMove:
    key: str
    name: str
    row: int
    damage: int
    fps: float
    impact_frame: int

    @property
    def state(self):
        return f"COUNTER_{self.key.upper()}"

    @property
    def enemy_state(self):
        return f"SUBDUED_{self.key.upper()}"

    @property
    def duration(self):
        return 8 / self.fps


COUNTERS = {
    f"counter_{key}": CounterMove(key, name, row, config.COUNTER_DAMAGE,
                                 config.COUNTER_FPS, impact_frame)
    for key, name, row, impact_frame in config.COUNTER_MOVE_SPECS
}


def can_counter(player, enemy):
    return (enemy.alive and enemy.counter_move is None and not enemy.knockback_started
            and enemy.state == "ATTACK" and not enemy.has_hit
            and enemy.animation.frame in config.COUNTER_TRIGGER_FRAMES
            and enemy.jump_height == 0
            and abs(enemy.x - player.x) <= config.COUNTER_RANGE
            and abs(enemy.ground_y - player.ground_y) <= config.COUNTER_DEPTH_TOLERANCE
            and (player.x - enemy.x) * enemy.facing >= 0)


class CounterSequence:
    """One shared clock keeps the selected attacker and player in the same pose."""

    @classmethod
    def start(cls, player, enemy, move, walkable):
        side = (1 if enemy.x > player.x else -1) if enemy.x != player.x else -enemy.facing
        player_padding = max(player.boundary_padding, config.COUNTER_BOUNDARY_PADDING)
        enemy_padding = max(enemy.boundary_padding, config.COUNTER_BOUNDARY_PADDING)
        player_limits = walkable.x_limits(player.ground_y, player_padding)
        enemy_limits = walkable.x_limits(player.ground_y, enemy_padding)
        if player_limits is None or enemy_limits is None:
            return None
        distance = config.COUNTER_PAIR_DISTANCE * side
        low = max(player_limits[0], enemy_limits[0] - distance)
        high = min(player_limits[1], enemy_limits[1] - distance)
        if low > high:
            return None
        player_x = clamp(player.x, low, high)
        return cls(player, enemy, move, side, player_x, player_x + distance)

    def __init__(self, player, enemy, move, side, player_x, enemy_x):
        self.player, self.enemy, self.move = player, enemy, move
        self.elapsed = 0.0
        self.damage_applied = False
        self.finished = False
        self.player_padding = player.boundary_padding
        self.enemy_padding = enemy.boundary_padding
        player.boundary_padding = max(self.player_padding, config.COUNTER_BOUNDARY_PADDING)
        enemy.boundary_padding = max(self.enemy_padding, config.COUNTER_BOUNDARY_PADDING)
        player.x = player.previous_x = player_x
        enemy.x = enemy.previous_x = enemy_x
        enemy.ground_y = enemy.previous_ground_y = player.ground_y
        player.previous_ground_y = player.ground_y
        player.start_counter(move, side)
        enemy.start_counter(move, -side)

    @property
    def valid(self):
        return (self.player.alive and self.player.counter_move is self.move
                and self.enemy.counter_move is self.move)

    def update(self, dt):
        self.elapsed = min(self.move.duration, self.elapsed + dt)
        self.player.animation.elapsed = self.enemy.animation.elapsed = self.elapsed
        damage = 0
        if not self.damage_applied and self.elapsed + 1e-9 >= self.move.impact_frame / self.move.fps:
            previous_hp = self.enemy.hp
            self.enemy.take_damage(self.move.damage)
            damage = previous_hp - self.enemy.hp
            self.damage_applied = True
        if self.elapsed + 1e-9 >= self.move.duration:
            self.finish()
        return damage

    def finish(self):
        if self.finished:
            return
        self.finished = True
        if self.player.counter_move is self.move:
            self.player.counter_move = None
            self.player.boundary_padding = self.player_padding
            if self.player.state == self.move.state:
                self.player.animation.set_state("IDLE" if self.player.alive else "DYING")
        if self.enemy.counter_move is self.move:
            self.enemy.finish_counter()
            if self.enemy.alive:
                self.enemy.boundary_padding = self.enemy_padding
