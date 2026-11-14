"""Requested enemy batches at random map boundaries, independent of the camera."""

import random
from itertools import count

import config
from enemy import Enemy
from walkable import default_area


def attack_speed_for_spawn(index):
    """Binary radical-inverse order spreads unique rates across a bounded range."""
    ordinal = index + 1
    fraction, weight = 0.0, 0.5
    while ordinal:
        fraction += (ordinal & 1) * weight
        ordinal >>= 1
        weight *= 0.5
    low, high = config.ENEMY_ATTACK_SPEED_RANGE
    return low + (high - low) * fraction


class SpawnManager:
    def __init__(self, *, rng=None, walkable=None, attack_sequence=None, spawn_area=None):
        self.rng = random.Random() if rng is None else rng
        self.spawned_count = 0
        self.walkable = default_area() if walkable is None else walkable
        self.spawn_area = self.walkable if spawn_area is None else spawn_area
        self.attack_sequence = count() if attack_sequence is None else attack_sequence

    def spawn(self, count, elapsed):
        enemies = []
        for _ in range(count):
            side = self.rng.choice((-1, 1))
            x = (config.ENEMY_HALF_WIDTH if side < 0
                  else config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH)
            _, bottom, _, top = self.spawn_area.bounds
            ground_y = self.rng.uniform(bottom, top)
            x, ground_y = self.spawn_area.project(x, ground_y, config.ENEMY_BOUNDARY_PADDING)
            run_speed = config.ENEMY_RUN_SPEEDS[self.spawned_count % len(config.ENEMY_RUN_SPEEDS)]
            attack_speed = attack_speed_for_spawn(next(self.attack_sequence))
            enemy = Enemy(x, facing=-side, spawned_at=elapsed, run_speed=run_speed,
                          ground_y=ground_y, attack_speed=attack_speed)
            enemy.walkable = self.walkable
            enemies.append(enemy)
            self.spawned_count += 1
        return enemies
