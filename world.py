"""Fixed-step simulation usable without pico2d or a display."""

import config
from camera import Camera
from collision import resolve_bodies
from controls import Controls
from player import Player
from spawn_manager import SpawnManager


class World:
    def __init__(self, *, spawn_schedule=None):
        self.controls = Controls()
        self.spawn_schedule = spawn_schedule
        self.reset()

    def reset(self):
        self.controls.reset_for_restart()
        self.player = Player()
        self.camera = Camera(self.player.x)
        self.enemies = []
        self.spawner = SpawnManager(self.spawn_schedule)
        self.death_handled = False
        self.elapsed = 0.0
        self.accumulator = 0.0

    def update(self, dt):
        if self.controls.take_press("restart"):
            self.reset()
            return
        self.accumulator += min(max(dt, 0.0), config.MAX_FRAME_DT)
        while self.accumulator + 1e-12 >= config.FIXED_DT:
            self.step(config.FIXED_DT)
            self.accumulator = max(0.0, self.accumulator - config.FIXED_DT)

    def step(self, dt):
        self.elapsed += dt
        if self.player.alive:
            self.enemies.extend(self.spawner.update(self.elapsed))
        self.player.update(dt, self.controls)
        self.handle_death()
        for enemy in self.enemies:
            enemy.update(dt, self.player)
        if self.player.alive:
            resolve_bodies(self.player, self.enemies)
            for enemy in self.enemies:
                if enemy.try_hit(self.player):
                    self.camera.shake()
                    if not self.player.alive:
                        self.handle_death()
                        break
        self.camera.update(dt, self.player.x)

    def handle_death(self):
        if not self.player.alive and not self.death_handled:
            self.death_handled = True
            for enemy in self.enemies:
                enemy.knockback(self.player.x)
