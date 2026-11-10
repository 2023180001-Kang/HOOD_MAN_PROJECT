"""A finite, reproducible schedule at map boundaries, not camera boundaries."""

import config
from enemy import Enemy


class SpawnManager:
    def __init__(self, schedule=None):
        self.schedule = config.SPAWN_SCHEDULE if schedule is None else tuple(schedule)
        self.spawned_count = 0

    def update(self, elapsed):
        enemies = []
        while self.spawned_count < len(self.schedule):
            at, side = self.schedule[self.spawned_count]
            if elapsed + 1e-9 < at:
                break
            x = (config.ENEMY_HALF_WIDTH if side < 0
                 else config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH)
            enemies.append(Enemy(x, facing=-side, spawned_at=at))
            self.spawned_count += 1
        return enemies
