"""Requested enemy batches at random map boundaries, independent of the camera."""

import random

import config
from enemy import Enemy
from walkable import default_area


class SpawnManager:
    def __init__(self, *, rng=None, walkable=None):
        self.rng = random.Random() if rng is None else rng
        self.spawned_count = 0
        self.walkable = default_area() if walkable is None else walkable

    def spawn(self, count, elapsed):
        enemies = []
        for _ in range(count):
            side = self.rng.choice((-1, 1))
            x = (config.ENEMY_HALF_WIDTH if side < 0
                  else config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH)
            _, bottom, _, top = self.walkable.bounds
            ground_y = self.rng.uniform(bottom, top)
            x, ground_y = self.walkable.project(x, ground_y, config.ENEMY_BOUNDARY_PADDING)
            run_speed = config.ENEMY_RUN_SPEEDS[self.spawned_count % len(config.ENEMY_RUN_SPEEDS)]
            enemy = Enemy(x, facing=-side, spawned_at=elapsed, run_speed=run_speed, ground_y=ground_y)
            enemy.walkable = self.walkable
            enemies.append(enemy)
            self.spawned_count += 1
        return enemies
