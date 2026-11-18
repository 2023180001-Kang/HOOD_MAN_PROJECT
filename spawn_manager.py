"""Requested enemy batches at map edges/open doors, independent of the camera."""

import random
from dataclasses import dataclass
from itertools import count

import config
from enemy import Enemy
from walkable import WalkableArea, default_area


@dataclass(frozen=True)
class SpawnPoint:
    x: float
    ground_y: float
    floor: int
    walkable: WalkableArea
    source: tuple


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
    def __init__(self, *, rng=None, walkable=None, attack_sequence=None, spawn_area=None,
                 enemy_type=Enemy, extra_sources=None):
        self.rng = random.Random() if rng is None else rng
        self.spawned_count = 0
        self.walkable = default_area() if walkable is None else walkable
        self.spawn_area = self.walkable if spawn_area is None else spawn_area
        self.attack_sequence = count() if attack_sequence is None else attack_sequence
        self.enemy_type = enemy_type
        self.extra_sources = extra_sources

    def spawn(self, count, elapsed):
        enemies = []
        sources = tuple(self.extra_sources()) if self.extra_sources is not None else ()
        for _ in range(count):
            # Two edge entries plus each fully opened, in-world door instance.
            # With no open doors keep the original RNG sequence exactly.
            point = self.rng.choice((None, None, *sources)) if sources else None
            if point is None:
                side = self.rng.choice((-1, 1))
                x = (config.ENEMY_HALF_WIDTH if side < 0
                     else config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH)
                _, bottom, _, top = self.spawn_area.bounds
                ground_y = self.rng.uniform(bottom, top)
                x, ground_y = self.spawn_area.project(x, ground_y, self.enemy_type.boundary_padding)
                floor, area, source = 0, self.walkable, ("edge", side)
                facing = -side
            else:
                x, ground_y = point.walkable.project(point.x, point.ground_y,
                                                     self.enemy_type.boundary_padding)
                floor, area, source = point.floor, point.walkable, point.source
                facing = 1 if x < config.WORLD_WIDTH / 2 else -1
            run_speed = config.ENEMY_RUN_SPEEDS[self.spawned_count % len(config.ENEMY_RUN_SPEEDS)]
            attack_speed = attack_speed_for_spawn(next(self.attack_sequence))
            # Copy, rather than share or advance, the spawn RNG. Combat draws
            # must not change later spawn sides/depths or another enemy's moves.
            enemy_rng = random.Random()
            enemy_rng.setstate(self.rng.getstate())
            enemy = self.enemy_type(x, facing=facing, spawned_at=elapsed, run_speed=run_speed,
                                   ground_y=ground_y, attack_speed=attack_speed, rng=enemy_rng)
            enemy.floor, enemy.walkable, enemy.spawn_source = floor, area, source
            enemies.append(enemy)
            self.spawned_count += 1
        return enemies
