"""Fixed-step simulation usable without pico2d or a display."""

import config
from camera import Camera
from collision import resolve_bodies
from controls import Controls
from effects import DamageNumber, HitEffect
from enemy_spacing import prepare_enemy_spacing, resolve_enemy_spacing
from player import Player
from stage import Stage


class World:
    def __init__(self, *, rng=None):
        self.controls = Controls()
        self.spawn_rng = rng
        self.reset()

    def reset(self):
        self.controls.reset_for_restart()
        self.player = Player()
        self.camera = Camera(self.player.x)
        self.stages = [Stage(index, rng=self.spawn_rng) for index in range(len(config.STAGE_IMAGES))]
        self.stage_index = 0
        self.death_handled = False
        self.elapsed = 0.0
        self.accumulator = 0.0

    @property
    def stage(self):
        return self.stages[self.stage_index]

    @property
    def enemies(self):
        return self.stage.enemies

    @enemies.setter
    def enemies(self, enemies):
        self.stage.enemies = enemies

    @property
    def effects(self):
        return self.stage.effects

    @effects.setter
    def effects(self, effects):
        self.stage.effects = effects

    @property
    def damage_numbers(self):
        return self.stage.damage_numbers

    @damage_numbers.setter
    def damage_numbers(self, numbers):
        self.stage.damage_numbers = numbers

    @property
    def spawner(self):
        return self.stage.spawner

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
        if self.controls.take_press("stage_exits") and self.player.alive:
            self.stage.arrows_visible = True
        self.try_stage_transition()
        for effect in self.effects:
            effect.update(dt)
        self.effects = [effect for effect in self.effects if not effect.finished]
        for number in self.damage_numbers:
            number.update(dt)
        self.damage_numbers = [number for number in self.damage_numbers if not number.finished]
        for count in config.SPAWN_COUNTS:
            if self.controls.take_press(f"spawn_{count}") and self.player.alive:
                self.enemies.extend(self.spawner.spawn(count, self.elapsed))
        self.player.update(dt, self.controls)
        self.handle_death()
        prepare_enemy_spacing(self.player, self.enemies)
        for enemy in self.enemies:
            enemy.update(dt, self.player)
        if self.player.alive:
            resolve_bodies(self.player, self.enemies)
            resolve_enemy_spacing(self.player, self.enemies, dt)
            player_box = self.player.attack_box
            if player_box is not None:
                for enemy in self.enemies:
                    previous_hp = enemy.hp
                    if self.player.try_hit(enemy):
                        self.damage_numbers.append(
                            DamageNumber.above_body(enemy.body, previous_hp - enemy.hp,
                                                    depth=enemy.depth))
                        self.effects.append(HitEffect.at_contact(player_box, enemy.body,
                                                                 self.player.facing,
                                                                 depth=enemy.depth))
                        self.camera.shake()
            for enemy in self.enemies:
                enemy_box = enemy.attack_box
                if enemy_box is not None and enemy.try_hit(self.player):
                    self.effects.append(HitEffect.at_contact(enemy_box, self.player.body,
                                                             enemy.facing))
                    self.camera.shake()
                    if not self.player.alive:
                        self.handle_death()
                        break
        self.camera.update(dt, self.player.x)

    def try_stage_transition(self):
        player = self.player
        if (not player.alive or player.active_move is not None
                or player.state in ("HIT", "DYING", "DEAD")):
            return False
        for side in self.stage.arrow_sides:
            destination = self.stage.destination(side)
            at_exit = (player.x <= config.STAGE_EXIT_MARGIN if side < 0 else
                       player.x >= config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN)
            outward = (player.vx * side > 0 or
                       (player.vx == 0 and self.controls.direction == side))
            if destination is None or not at_exit or not outward:
                continue
            # Enter far enough inside the new scene to avoid an immediate return.
            # Keep the same player, physics, held input and animation clock.
            self.stage_index = destination
            player.x = (config.STAGE_ENTRY_MARGIN if side > 0 else
                        config.WORLD_WIDTH - config.STAGE_ENTRY_MARGIN)
            player.previous_x = player.x
            self.camera = Camera(player.x)
            return True
        return False

    def handle_death(self):
        if not self.player.alive and not self.death_handled:
            self.death_handled = True
            for enemy in self.enemies:
                if not enemy.alive:
                    continue
                dx = enemy.x - self.player.x
                dy = enemy.y - self.player.y
                if dx * dx + dy * dy <= config.KNOCKBACK_RADIUS ** 2:
                    enemy.knockback(self.player.x)
                else:
                    enemy.stop()
