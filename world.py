"""Fixed-step simulation usable without pico2d or a display."""

from itertools import count

import config
from camera import Camera
from collision import resolve_bodies, same_floor, transit_target, world_rect
from controls import Controls
from counter import COUNTERS, CounterSequence, can_counter
from drop_items import DropItem
from effects import DamageNumber, HitEffect, SpriteAfterimage
from enemy_spacing import prepare_enemy_spacing, resolve_enemy_spacing
from physics import clamp
from player import Player
from rush import RushSequence
from stage import Stage


class World:
    def __init__(self, *, rng=None, traffic_rng=None, item_rng=None):
        self.controls = Controls()
        self.spawn_rng = rng
        self.traffic_rng = traffic_rng
        self.item_rng = item_rng
        self.reset()

    def reset(self):
        if getattr(self, "rush", None) is not None:
            self.rush.finish()
        if getattr(self, "counter", None) is not None:
            self.counter.finish()
        for stage in getattr(self, "stages", ()):
            for stair in stage.stairs:
                for actor in tuple(stair.occupants):
                    stair.release(actor)
                stair.queue.clear()
            for enemy in stage.enemies:
                if enemy.counter_move is not None:
                    enemy.finish_counter()
        self.controls.reset_for_restart()
        self.counter = None
        self.rush = None
        self.player = Player()
        self.camera = Camera(self.player.x)
        attack_sequence = count()
        self.stages = [Stage(index, rng=self.spawn_rng, attack_sequence=attack_sequence,
                             traffic_rng=self.traffic_rng, item_rng=self.item_rng)
                       for index in range(len(config.STAGE_IMAGES))]
        self.stage_index = 0
        self.pending_stage_index = None
        self.stage_loading_remaining = 0.0
        self.death_handled = False
        self.elapsed = 0.0
        self.accumulator = 0.0
        self._dive_afterimage_remaining = 0.0

    @property
    def stage(self):
        return self.stages[self.stage_index]

    @property
    def stage_loading(self):
        return self.pending_stage_index is not None

    @property
    def time_scale(self):
        return self.player.time_scale

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
    def afterimages(self):
        return self.stage.afterimages

    @property
    def damage_numbers(self):
        return self.stage.damage_numbers

    @damage_numbers.setter
    def damage_numbers(self, numbers):
        self.stage.damage_numbers = numbers

    @property
    def spawner(self):
        return self.stage.spawner

    @property
    def pickup_item(self):
        player = self.player
        if (self.stage_loading or player.staircase is not None or not player.alive or not player.grounded
                or player.counter_move is not None):
            return None
        candidates = [item for item in self.stage.drop_items if item.grounded
                      and item.floor == player.floor
                      and abs(item.x - player.x) <= config.WEAPON_PICKUP_RANGE
                      and abs(item.ground_y - player.ground_y) <= config.WEAPON_PICKUP_DEPTH]
        return min(candidates, key=lambda item: (item.x - player.x) ** 2
                   + (item.ground_y - player.ground_y) ** 2, default=None)

    def drop_weapon(self, kind):
        player = self.player
        area = (self.stage.drop_spawn_area if player.floor == 0 else self.stage.area_for(player))
        x, ground_y = area.project(player.x, player.ground_y, config.DROP_ITEM_HALF_WIDTH)
        left, bottom, right, top = area.bounds
        exit_edge = (config.STAGE_EXIT_MARGIN + config.STAGE_ARROW_WIDTH / 2
                     + config.STAGE_ARROW_SWAY_AMPLITUDE + config.DROP_ITEM_EXIT_GAP)
        x = clamp(x, max(left, exit_edge) + config.DROP_ITEM_HALF_WIDTH,
                  min(right, config.WORLD_WIDTH - exit_edge) - config.DROP_ITEM_HALF_WIDTH)
        ground_y = clamp(ground_y, bottom + config.DROP_ITEM_SHADOW_HALF_DEPTH,
                         top - config.DROP_ITEM_HEIGHT)
        item = DropItem(kind, x, ground_y, player.facing,
                        jump_height=max(0.0, player.y + config.WEAPON_DROP_HAND_HEIGHT - ground_y),
                        floor=player.floor)
        self.stage.drop_items.append(item)
        return item

    def interact_weapon(self):
        player = self.player
        if (self.stage_loading or player.staircase is not None
                or not player.alive or player.counter_move is not None):
            return False
        item = self.pickup_item
        if item is not None:
            if player.weapon is not None:
                self.drop_weapon(player.weapon)
            self.stage.drop_items.remove(item)
            player.equip_weapon(item.kind)
            return True
        if player.weapon is not None:
            self.drop_weapon(player.weapon)
            player.equip_weapon(None)
            return True
        return False

    def update(self, dt):
        if self.controls.take_press("restart"):
            self.reset()
            return
        if self.stage_loading:
            # Loading uses real elapsed time, independent of the physics dt cap.
            self.controls.pressed.clear()
            self.stage_loading_remaining = max(0.0, self.stage_loading_remaining - max(0.0, dt))
            if self.stage_loading_remaining <= 1e-9:
                self._enter_stage(self.pending_stage_index)
                self.pending_stage_index = None
                self.stage_loading_remaining = 0.0
            return
        self.accumulator += min(max(dt, 0.0), config.MAX_FRAME_DT)
        while self.accumulator + 1e-12 >= config.FIXED_DT:
            self.step(config.FIXED_DT)
            self.accumulator = max(0.0, self.accumulator - config.FIXED_DT)
            if self.stage_loading:
                self.accumulator = 0.0
                break

    def step(self, dt):
        if self.stage_loading:
            self.controls.pressed.clear()
            return
        for actor in [self.player, *self.enemies]:
            actor.stair_arrival = False
        self.cancel_invalid_counter()
        counter_pressed = self.controls.take_latest_press(COUNTERS)
        if counter_pressed is not None:
            self.try_start_counter(counter_pressed)
        if (self.counter is not None and self.counter.holding
                and self.controls.take_press("combat_a")):
            self.counter.start_follow_up()
        if self.controls.take_press("stage_exits") and self.player.alive:
            self.stage.arrows_visible = True
        if self.controls.take_press("toggle_doors"):
            self.stage.toggle_doors()
        self.stage.constrain_actor(self.player)
        if self.controls.take_press("weapon_interact"):
            self.interact_weapon()
        self.try_stage_transition()
        if self.stage_loading:
            self.elapsed += dt
            return
        previous_jump_count = self.player.jump_count
        self.player.handle_input(self.controls)
        if previous_jump_count == 1 and self.player.jump_count == 2:
            self.stage.prepare_player_double_jump(self.player)
        self.cancel_invalid_rush()
        # Input stays on the real fixed-step clock, so D can enter/leave slow
        # motion immediately. Every gameplay clock advances by the same dt.
        dt *= self.time_scale
        self.elapsed += dt
        self.stage.update_doors(dt)
        self.update_afterimages(dt)
        for item in self.stage.drop_items:
            item.update(dt)
        for effect in self.effects:
            effect.update(dt)
        self.effects = [effect for effect in self.effects if not effect.finished]
        for number in self.damage_numbers:
            number.update(dt)
        self.damage_numbers = [number for number in self.damage_numbers if not number.finished]
        for count in config.SPAWN_COUNTS:
            if self.controls.take_press(f"spawn_{count}") and self.player.alive:
                self.enemies.extend(self.spawner.spawn(count, self.elapsed))
        for enemy in self.enemies:
            self.stage.constrain_actor(enemy)
        stair_moved = self.stage.update_navigation(dt, self.player, self.controls)
        if self.player not in stair_moved:
            self.player.update(dt, self.controls, self.stage.area_for(self.player), process_input=False)
            self.stage.resolve_player_platforms(self.player, self.controls)
        self.cancel_invalid_counter()
        self.cancel_invalid_rush()
        if self.player.rush_phase == "FLY" and self.rush is None:
            self.rush = RushSequence(self.player, self.stage.area_for(self.player))
        self.handle_death()
        prepare_enemy_spacing(self.player, self.enemies, self.stage.area_for(self.player))
        for enemy in self.enemies:
            if enemy not in stair_moved:
                enemy.update(dt, self.player, self.stage.area_for(enemy))
                self.stage.resolve_enemy_drop(enemy, self.player)
        if self.counter is not None:
            self.counter.sync_pair()
        traffic_updated = self.rush is not None
        if traffic_updated:
            # Move existing captives before swept car checks, but let fatal
            # traffic cancel the flight before applying any new W contact hit.
            if not self.rush.sync_pair():
                self.player.release_rush()
            self.update_traffic(dt)
            self.handle_death()
            self.cancel_invalid_rush()
        if self.rush is not None:
            for enemy, damage in self.rush.update(self.enemies):
                self.damage_numbers.append(DamageNumber.above_body(
                    enemy.body, damage, depth=enemy.ground_y - config.GROUND_Y))
                self.effects.append(HitEffect(enemy.x, enemy.y + config.ENEMY_HEIGHT * 0.6,
                                              self.player.facing,
                                              image_name=config.PUNCH_KICK_HIT_IMAGE))
                self.camera.shake()
        self.enemies[:] = [enemy for enemy in self.enemies if not enemy.faded_out]
        if self.player.alive:
            area = self.stage.area_for(self.player)
            resolve_bodies(self.player, self.enemies, area)
            resolve_enemy_spacing(self.player, self.enemies, dt, area)
        if not traffic_updated:
            self.update_traffic(dt)
        self.handle_death()
        if self.player.alive:
            if self.counter is not None:
                sequence = self.counter
                damage = sequence.update(dt)
                if damage:
                    enemy = sequence.enemy
                    self.damage_numbers.append(DamageNumber.above_body(
                        enemy.body, damage, depth=enemy.ground_y - config.GROUND_Y))
                    self.effects.append(HitEffect(enemy.x, enemy.y + config.ENEMY_HEIGHT * 0.6,
                                                  self.player.facing,
                                                  image_name=config.PUNCH_KICK_HIT_IMAGE))
                    self.camera.shake()
                if sequence.finished:
                    self.counter = None
            player_box = self.player.attack_box
            if player_box is not None:
                for enemy in self.enemies:
                    previous_hp = enemy.hp
                    transit = transit_target(enemy)
                    if self.player.try_hit(enemy):
                        self.damage_numbers.append(
                            DamageNumber.above_body(enemy.body, previous_hp - enemy.hp,
                                                     depth=enemy.ground_y - config.GROUND_Y))
                        contact_box = world_rect(player_box, self.player) if transit else player_box
                        contact_body = world_rect(enemy.body, enemy) if transit else enemy.body
                        contact_depth = 0.0 if transit else enemy.ground_y - config.GROUND_Y
                        self.effects.append(HitEffect.at_contact(contact_box, contact_body,
                                                                 self.player.facing,
                                                                 depth=contact_depth,
                                                                 image_name=self.player.active_move.hit_image))
                        self.camera.shake()
            for enemy in self.enemies:
                enemy_box = enemy.attack_box
                if enemy_box is not None and enemy.try_hit(self.player):
                    self.cancel_invalid_counter()
                    self.effects.append(HitEffect.at_contact(enemy_box, self.player.body,
                                                             enemy.facing,
                                                             depth=self.player.ground_y - config.GROUND_Y,
                                                             image_name=config.CLUB_HIT_IMAGE))
                    self.camera.shake(strength=config.PLAYER_HIT_SHAKE_STRENGTH)
                    if not self.player.alive:
                        self.handle_death()
                        break
        self.cancel_invalid_rush()
        self.stage.constrain_actor(self.player)
        for enemy in self.enemies:
            self.stage.constrain_actor(enemy)
        self.camera.update(dt, self.player.x)

    def update_afterimages(self, dt):
        for afterimage in self.afterimages:
            afterimage.update(dt)
        self.afterimages[:] = [image for image in self.afterimages if not image.finished]
        if self.player.weapon_leap_phase != "DIVE" or not self.player.alive:
            self._dive_afterimage_remaining = 0.0
            return
        self._dive_afterimage_remaining -= dt
        if self._dive_afterimage_remaining <= 1e-9:
            # Capture before movement: even the release tick leaves a pose
            # behind the player. Snapshots never follow later equipment/poses.
            self.afterimages.append(SpriteAfterimage.from_player(self.player))
            self._dive_afterimage_remaining += config.WEAPON_DIVE_AFTERIMAGE_INTERVAL

    def cancel_invalid_counter(self):
        if self.counter is not None and (not self.counter.valid or self.counter.enemy not in self.enemies):
            self.counter.finish()
            self.counter = None

    def cancel_invalid_rush(self):
        if self.rush is not None:
            self.rush.prune(self.enemies)
            if not self.rush.valid:
                self.rush.finish()
                self.rush = None

    def update_traffic(self, dt):
        if self.stage.traffic is None:
            return
        car = self.stage.traffic.update(dt)
        if car is None:
            return
        hit_player = car.hits(self.player)
        hit_enemies = [enemy for enemy in self.enemies if car.hits(enemy)]
        if self.counter is not None and (hit_player or self.counter.enemy in hit_enemies):
            self.counter.finish()
            self.counter = None
        for enemy in hit_enemies:
            previous_hp = enemy.hp
            enemy.hit_by_car(car.facing)
            self.damage_numbers.append(DamageNumber.above_body(
                enemy.body, previous_hp, depth=enemy.ground_y - config.GROUND_Y))
            self.effects.append(HitEffect(enemy.x, enemy.y + config.ENEMY_HEIGHT * 0.5, car.facing,
                                         image_name=config.CLUB_HIT_IMAGE))
        if hit_player:
            self.player.hit_by_car(car.facing)
            self.effects.append(HitEffect(self.player.x, self.player.y + config.PLAYER_HEIGHT * 0.5,
                                          car.facing, image_name=config.CLUB_HIT_IMAGE))
        if hit_player or hit_enemies:
            self.camera.shake(strength=config.PLAYER_HIT_SHAKE_STRENGTH)

    def try_start_counter(self, action):
        player = self.player
        if (self.counter is not None or self.stage_loading or player.staircase is not None
                or not player.alive or not player.grounded
                or player.state in ("HIT", "DYING", "DEAD")):
            return False
        candidates = [enemy for enemy in self.enemies if can_counter(player, enemy)]
        candidates.sort(key=lambda enemy: (abs(enemy.x - player.x),
                                           abs(enemy.ground_y - player.ground_y)))
        for enemy in candidates:
            sequence = CounterSequence.start(player, enemy, COUNTERS[action], self.stage.area_for(player))
            if sequence is not None:
                self.counter = sequence
                return True
        return False

    def try_stage_transition(self):
        player = self.player
        if (self.stage_loading or player.floor != 0 or player.staircase is not None
                or not player.alive or player.active_move is not None
                or player.counter_move is not None
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
            if (self.stage_index, destination) in config.STAGE_LOADING_TRANSITIONS:
                self.pending_stage_index = destination
                self.stage_loading_remaining = config.STAGE_LOADING_DURATION
                self.controls.pressed.clear()
            else:
                self._enter_stage(destination)
            return True
        return False

    def select_stage(self, destination):
        """Enter a scene for tooling while preserving its actors and player HP."""
        if not self.player.alive or not 0 <= destination < len(self.stages):
            return False
        if self.counter is not None:
            self.counter.finish()
            self.counter = None
        self.pending_stage_index = None
        self.stage_loading_remaining = 0.0
        self.accumulator = 0.0
        self.controls.pressed.clear()
        self._enter_stage(destination, entry_x=config.START_X)
        resolve_bodies(self.player, self.enemies, self.stage.area_for(self.player))
        self.player.previous_x = self.player.x
        self.player.previous_ground_y = self.player.ground_y
        self.camera = Camera(self.player.x)
        return True

    def _enter_stage(self, destination, *, entry_x=None):
        if self.rush is not None:
            self.rush.finish()
            self.rush = None
        if self.player.rush_phase is not None:
            self.player.finish_move()
        # Keep the same player, physics, held input and animation clock, and
        # enter far enough inside the next scene to avoid an immediate return.
        side = 1 if destination > self.stage_index else -1
        self._dive_afterimage_remaining = 0.0
        self.stage.release_actor(self.player)
        self.stage_index = destination
        player = self.player
        player.floor = 0
        player.stair_arrival = False
        player.upper_landing_requested = False
        player.falling_from_upper = False
        player.x = (entry_x if entry_x is not None else
                    config.STAGE_ENTRY_MARGIN if side > 0 else
                    config.WORLD_WIDTH - config.STAGE_ENTRY_MARGIN)
        self.stage.constrain_actor(player)
        player.previous_x = player.x
        player.previous_ground_y = player.ground_y
        self.camera = Camera(player.x)

    def handle_death(self):
        if not self.player.alive and not self.death_handled:
            self.death_handled = True
            for enemy in self.enemies:
                if not enemy.alive:
                    continue
                dx = enemy.x - self.player.x
                dy = enemy.ground_y - self.player.ground_y
                height = enemy.jump_height - self.player.jump_height
                if (same_floor(self.player, enemy)
                        and dx * dx + dy * dy + height * height <= config.KNOCKBACK_RADIUS ** 2):
                    enemy.knockback(self.player.x, self.player.ground_y)
                else:
                    enemy.stop()
