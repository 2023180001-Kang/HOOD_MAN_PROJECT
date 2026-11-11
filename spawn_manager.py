"""Requested enemy batches at random map boundaries, independent of the camera."""

import random

import config
from enemy import Enemy


class SpawnManager:
    def __init__(self, *, rng=None):
        self.rng = random.Random() if rng is None else rng
        self.spawned_count = 0

    def spawn(self, count, elapsed):
        enemies = []
        for _ in range(count):
            side = self.rng.choice((-1, 1))
            x = (config.ENEMY_HALF_WIDTH if side < 0
                 else config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH)
            run_speed = config.ENEMY_RUN_SPEEDS[self.spawned_count % len(config.ENEMY_RUN_SPEEDS)]
            enemies.append(Enemy(x, facing=-side, spawned_at=elapsed, run_speed=run_speed))
            self.spawned_count += 1
        return enemies
