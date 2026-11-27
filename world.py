"""Fixed-step simulation usable without pico2d or a display."""

from itertools import count

import config
from axe_collisions import axe_clash_times
from camera import Camera
from collision import resolve_bodies, same_floor, transit_target, world_rect
from controls import Controls
from drop_items import DropItem
from effects import DamageNumber, HitEffect, SpriteAfterimage
from enemy_spacing import place_ranged_spawns, prepare_enemy_spacing, resolve_enemy_spacing
from physics import clamp
from player import Player
from projectiles import EnemyAxeProjectile, PlayerProjectile, ThrownWeaponProjectile
from stage import Stage, enemy_type_for_stage
from sword_enemy import SwordEnemy
from sniper import Sniper
from training_room import TrainingPlayer, TrainingRoom


SPAWN_REQUESTS = {f"spawn_{n}": (n, None) for n in config.SPAWN_COUNTS}
SPAWN_REQUESTS.update({f"spawn_sword_{n}": (n, SwordEnemy) for n in config.SPAWN_COUNTS})
SPAWN_REQUESTS.update({f"spawn_sniper_{n}": (n, Sniper) for n in config.SPAWN_COUNTS})


class World:
    def __init__(self, *, rng=None, traffic_rng=None, item_rng=None):
        self.controls = Controls()
        self.spawn_rng = rng
        self.traffic_rng = traffic_rng
        self.item_rng = item_rng
        self.starting_weapon = None
        self.starting_hp = self.starting_max_hp = config.MAX_HP
        self.enemy_starting_hp = {}
        self.cleared_stages = set()  # Campaign record for this session, including across F5.
        self.training = False
        self.reset()

    def reset(self, *, stage_index=0):
        for stage in getattr(self, "stages", ()):
            for stair in stage.stairs:
                for actor in tuple(stair.occupants):
                    stair.release(actor)
                stair.queue.clear()
        if self.training:
            self.stages = [TrainingRoom(enemy_starting_hp=self.enemy_starting_hp)]
        else:
            attack_sequence = count()
            self.stages = [self._new_stage(index, attack_sequence) for index in range(len(config.STAGE_IMAGES))]
        self._map_clears_pending_heal = set()
        self.elapsed = 0.0
        self._start_attempt(stage_index)

    def _new_stage(self, index, attack_sequence):
        return Stage(index, rng=self.spawn_rng, attack_sequence=attack_sequence,
                     traffic_rng=self.traffic_rng, item_rng=self.item_rng,
                     enemy_starting_hp=self.enemy_starting_hp)

    def retry_current_map(self):
        if self.training:
            self.reset()
            return
        self.stage.release_actor(self.player)
        self.stages[self.stage_index] = self._new_stage(self.stage_index, self.spawner.attack_sequence)
        self._map_clears_pending_heal.discard(self.stage_index)
        self._start_attempt(self.stage_index)

    def _start_attempt(self, stage_index):
        self.stage_index = stage_index
        self.controls.reset_for_restart()
        if self.training:
            self.player = TrainingPlayer(self.stage)
            self.player.x = self.player.previous_x = config.SCREEN_WIDTH / 2
        else:
            self.player = Player()
            self.player.hp = self.starting_hp
            self.player.max_hp = self.starting_max_hp
            self.player.equip_weapon(self.starting_weapon)
        self.stage.constrain_actor(self.player)
        self.camera = Camera(self.player.x, self.stage.width)
        self.pending_stage_index = None
        self.stage_loading_remaining = 0.0
        self.death_handled = False
        self.accumulator = 0.0
        self._dive_afterimage_remaining = 0.0
        self._encounter_delay_remaining = 0.0
        self.start_stage_encounter()
        self.update_camera(0)

    def start_stage_encounter(self):
        if self.training or self.stage.encounter_started:
            return
        total = config.STAGE_ENCOUNTER_SIZE
        sword_count = total // 2 if self.stage.image_name in config.CITY_STAGE_IMAGES else 0
        self.spawn_enemies(total - sword_count, enemy_type_for_stage(self.stage_index))
        if sword_count:
            self.spawn_enemies(sword_count, SwordEnemy)
        self.stage.encounter_started = True

    def spawn_enemies(self, count, enemy_type=None):
        spawned = self.spawner.spawn(count, self.elapsed, enemy_type=enemy_type)
        place_ranged_spawns(self.player, self.enemies, spawned)
        self.enemies.extend(spawned)

    def update_camera(self, dt):
        self.camera.update(dt, self.player.x, player_y=self.player.y,
                           vertical_bounds=self.stage.camera_y_bounds)

    @property
    def stage(self):
        return self.stages[self.stage_index]

    @property
    def sniper_stage(self):
        return not self.training and self.stage.image_name not in config.BOSS_STAGE_IMAGES[:-1]

    @property
    def stage_loading(self):
        return self.pending_stage_index is not None

    @property
    def opening_factory_exit(self):
        gate = self.stage.factory_gate
        return gate is not None and gate.state == "OPENING" and not gate.finished

    @property
    def entering_factory_gate(self):
        return (self.stage.factory_gate is not None
                and self.pending_stage_index == self.stage_index + 1)

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
    def projectiles(self):
        return self.stage.projectiles

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
        if self.stage_loading or player.staircase is not None or not player.alive or not player.grounded:
            return None
        candidates = [item for item in self.stage.drop_items if item.collectible and item.grounded
                      and item.floor == player.floor
                      and abs(item.x - player.x) <= config.WEAPON_PICKUP_RANGE
                      and abs(item.ground_y - player.ground_y) <= config.WEAPON_PICKUP_DEPTH]
        return min(candidates, key=lambda item: (item.x - player.x) ** 2
                   + (item.ground_y - player.ground_y) ** 2, default=None)

    def drop_weapon(self, kind):
        player = self.player
        pistol_ammo = player.pistol_ammo if kind == "pistol" else None
        rifle_ammo = player.rifle_ammo if kind == "ar_rifle" else None
        if self.training and self.stage.can_return_to_table(player, kind):
            return self.stage.place_on_table(kind, pistol_ammo=pistol_ammo, rifle_ammo=rifle_ammo)
        area = (self.stage.drop_spawn_area if player.floor == 0 else self.stage.area_for(player))
        left, bottom, right, top = area.bounds
        half_width, height = config.DROP_ITEM_HALF_WIDTH, config.DROP_ITEM_HEIGHT
        if kind in config.STATIC_DROP_SPRITES:
            width, height = config.STATIC_DROP_SPRITES[kind].display_size(grounded=True)
            half_width = max(half_width, width / 2)
        else:
            bottom += config.DROP_ITEM_SHADOW_HALF_DEPTH
            if kind in config.THROWN_WEAPON_SPRITES:
                height = max(height, config.THROWN_WEAPON_SPRITES[kind].rest_height)
        x, ground_y = area.project(player.x, player.ground_y, half_width)
        exit_edge = (config.STAGE_EXIT_MARGIN + config.STAGE_ARROW_WIDTH / 2
                     + config.STAGE_ARROW_SWAY_AMPLITUDE + config.DROP_ITEM_EXIT_GAP)
        if not self.training:
            x = clamp(x, max(left, exit_edge) + half_width,
                      min(right, self.stage.width - exit_edge) - half_width)
        item = DropItem(kind, x, ground_y, player.facing, floor=player.floor, pistol_ammo=pistol_ammo,
                        rifle_ammo=rifle_ammo)
        # A tall rifle may overhang the narrow city sidewalk. Its base stays on it.
        item.ground_y = clamp(ground_y, bottom, max(bottom, top - height))
        item.jump_height = max(0.0, player.y + config.WEAPON_DROP_HAND_HEIGHT - item.ground_y)
        self.stage.drop_items.append(item)
        return item

    def drop_enemy_weapon(self, enemy):
        kind = enemy.death_drop_kind
        if kind is None:
            return
        area = self.stage.area_for(enemy)
        x, ground_y = area.project(enemy.x, enemy.ground_y, config.DROP_ITEM_HALF_WIDTH)
        self.stage.drop_items.append(DropItem(
            kind, x, ground_y, enemy.facing, floor=enemy.floor,
            jump_height=max(0.0, enemy.y + config.WEAPON_DROP_HAND_HEIGHT - ground_y),
            pistol_ammo=enemy.ammo if kind == "pistol" else None,
            rifle_ammo=enemy.ammo if kind == "ar_rifle" else None,
        ))

    def interact_weapon(self):
        player = self.player
        if self.stage_loading or player.staircase is not None or not player.alive:
            return False
        item = self.pickup_item
        if item is not None:
            if player.weapon is not None:
                self.drop_weapon(player.weapon)
            self.stage.drop_items.remove(item)
            if item.axe_owner is not None:
                item.axe_owner.abandon_axe_recovery()
            if item.kind in config.FIREARM_MAGAZINE_SIZES and item.kind == player.weapon:
                # Two guns of the same kind still have separate magazines and actions.
                player.equip_weapon(None)
            player.equip_weapon(item.kind)
            if item.kind in config.FIREARM_MAGAZINE_SIZES:
                player.firearm_ammo = (config.FIREARM_MAGAZINE_SIZES[item.kind]
                                       if item.firearm_ammo is None else item.firearm_ammo)
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
            dt = max(0.0, dt)
            fading = self.entering_factory_gate and self.stage_loading_remaining > 0
            self.stage_loading_remaining = max(0.0, self.stage_loading_remaining - dt)
            if fading:
                # Draw the fully black exterior once before entering the dock.
                return
            if self.stage_loading_remaining <= 1e-9:
                self._finish_stage_exit(self.pending_stage_index)
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
        self.player.stair_regrab_remaining = max(0.0, self.player.stair_regrab_remaining - dt)
        self.stage.exit_player_stairs(self.player, self.controls)
        if self.controls.take_press("stage_exits") and self.player.alive and not self.training:
            self.stage.arrows_visible = True
        if self.controls.take_press("toggle_doors"):
            self.stage.toggle_doors()
        self.stage.constrain_actor(self.player)
        if self.controls.take_press("weapon_interact"):
            self.interact_weapon()
        entered_stage = self.try_stage_transition()
        if self.stage_loading:
            self.elapsed += dt
            return
        previous_jump_count = self.player.jump_count
        self.player.crowd_escape.advance(dt)
        self.player.handle_input(self.controls)
        if previous_jump_count == 1 and self.player.jump_count == 2:
            self.stage.prepare_player_double_jump(self.player)
        # Stage entry uses real play time even while combat is in slow motion.
        real_dt = dt
        dt *= self.time_scale
        self.elapsed += dt
        if self._encounter_delay_remaining > 0 and not entered_stage:
            self._encounter_delay_remaining -= real_dt
            if self._encounter_delay_remaining <= 1e-9:
                self._encounter_delay_remaining = 0.0
                self.start_stage_encounter()
        self.stage.update_doors(dt)
        self.update_combat_effects(dt)
        self.spawn_dive_afterimage(dt)
        for item in self.stage.drop_items:
            item.update(dt)
        if self.training:
            self.stage.handle_target_input(self.controls, self.player)
        else:
            self.controls.take_press("training_target")
        if self.controls.take_press("cycle_spawn_enemy") and self.player.alive and not self.training:
            self.stage.cycle_spawn_enemy_type()
        for request in self.controls.take_presses(SPAWN_REQUESTS):
            if self.player.alive and not self.training:
                count, enemy_type = SPAWN_REQUESTS[request]
                if enemy_type is Sniper and not self.sniper_stage:
                    continue
                if enemy_type is None and self.stage.mixes_lab_summons:
                    for _ in range(count):
                        self.spawn_enemies(1, next(self.stage.lab_summons))
                else:
                    self.spawn_enemies(count, enemy_type)
        for enemy in self.enemies:
            self.stage.constrain_actor(enemy)
        stair_moved = self.stage.update_navigation(dt, self.player, self.controls)
        if self.player not in stair_moved:
            self.player.update(dt, self.controls, self.stage.area_for(self.player), process_input=False)
            self.stage.try_player_stair_catch(self.player)
            self.stage.resolve_player_platforms(self.player, self.controls)
        self.handle_death()
        for item in self.stage.drop_items[:]:
            owner = item.axe_owner
            if owner is None:
                continue
            if not owner.alive or owner not in self.enemies:
                item.axe_owner = None
            elif owner.seek_axe(item, self.player):
                self.stage.drop_items.remove(item)
        prepare_enemy_spacing(self.player, self.enemies, self.stage.area_for(self.player))
        for enemy in self.enemies:
            if enemy not in stair_moved:
                enemy.update(dt, self.player, self.stage.area_for(enemy))
                self.stage.resolve_enemy_drop(enemy, self.player)
        self.enemies[:] = [enemy for enemy in self.enemies if not enemy.faded_out]
        if self.player.alive:
            area = self.stage.area_for(self.player)
            resolve_bodies(self.player, self.enemies, area)
            resolve_enemy_spacing(self.player, self.enemies, dt, area)
        self.update_traffic(dt)
        self.handle_death()
        if self.player.alive:
            player_box = self.player.attack_box
            if player_box is not None:
                for enemy in self.enemies:
                    transit = transit_target(enemy)
                    if self.player.try_hit(enemy):
                        self.damage_numbers.append(
                            DamageNumber.above_body(enemy.body, enemy.last_hit_damage,
                                                     depth=enemy.ground_y - config.GROUND_Y))
                        contact_box = world_rect(player_box, self.player) if transit else player_box
                        contact_body = world_rect(enemy.body, enemy) if transit else enemy.body
                        contact_depth = 0.0 if transit else enemy.ground_y - config.GROUND_Y
                        self.effects.append(HitEffect.at_contact(contact_box, contact_body,
                                                                 self.player.facing,
                                                                 depth=contact_depth,
                                                                 image_name=self.player.active_move.hit_image))
                        strength = (config.WEAPON_DIVE_SHAKE_STRENGTH
                                    if self.player.active_move.jump_attack else config.SHAKE_STRENGTH)
                        self.camera.shake(strength=strength)
            for enemy in self.enemies:
                enemy_box = enemy.attack_box
                if enemy_box is not None and enemy.try_hit(self.player):
                    self.effects.append(HitEffect.at_contact(enemy_box, self.player.body,
                                                             enemy.facing,
                                                             depth=self.player.ground_y - config.GROUND_Y,
                                                             image_name=config.CLUB_HIT_IMAGE))
                    self.camera.shake(strength=config.PLAYER_HIT_SHAKE_STRENGTH)
                    if not self.player.alive:
                        self.handle_death()
                        break
        self.update_projectiles(dt)
        self.handle_death()
        self.stage.constrain_actor(self.player)
        for enemy in self.enemies:
            self.stage.constrain_actor(enemy)
            if not enemy.alive and not enemy.defeat_counted:
                enemy.defeat_counted = True
                self.drop_enemy_weapon(enemy)
                self.stage.defeated_count += 1
                if self.stage.factory_gate is None and self.stage.defeated_count == config.STAGE_ENCOUNTER_SIZE:
                    self.stage.arrows_visible = True
                    if not self.training:
                        self._record_map_clear()
        if (self.stage.factory_gate is not None and self.stage.factory_gate.state == "CLOSED"
                and self.stage.encounter_started and self.stage.defeated_count > 0 and self.player.alive
                and not any(enemy.alive for enemy in self.enemies)):
            self._record_map_clear()
            self.stage.arrows_visible = False
            self.stage.opening_gate_x, _ = self.stage.factory_doorway(self.player.x)
            self.stage.factory_gate.set_state("OPENING")
        elif self.opening_factory_exit:
            self.stage.factory_gate.update(real_dt)
            if self.stage.factory_gate.finished:
                self.stage.arrows_visible = True
        self.update_camera(dt)

    def advance_projectiles(self, projectiles, dt):
        axes = [shot for shot in projectiles if isinstance(shot, EnemyAxeProjectile) and not shot.finished]
        stops = axe_clash_times(axes, dt, self.player)
        for shot in projectiles:
            targets = self.enemies if isinstance(shot, PlayerProjectile) else self.player
            shot.update(dt, targets, return_targets=self.enemies, on_impact=self.projectile_impact,
                        stop_at=stops.get(id(shot), float("inf")))

    def update_projectiles(self, dt):
        # Existing rounds survive their shooter's death. New shots are emitted
        # only after the player's strikes have had a chance to interrupt them.
        self.advance_projectiles(self.projectiles, dt)
        if self.player.alive:
            bullet = self.player.take_projectile()
            if bullet is not None:
                bullet.world_width = self.stage.width
                self.projectiles.append(bullet)
                bullet.update(0, self.enemies, on_impact=self.projectile_impact)
            for enemy in self.enemies:
                bullet = enemy.take_projectile()
                if bullet is None:
                    continue
                bullet.world_width = self.stage.width
                self.projectiles.append(bullet)
                if isinstance(bullet, EnemyAxeProjectile):
                    self.advance_projectiles([axe for axe in self.projectiles
                                              if isinstance(axe, EnemyAxeProjectile)], 0)
                else:
                    bullet.update(0, self.player, return_targets=self.enemies, on_impact=self.projectile_impact)
                if not self.player.alive:
                    break
        for bullet in self.projectiles:
            if isinstance(bullet, ThrownWeaponProjectile) and bullet.finished:
                # Land in the impact lane, even when the city's random loot spawns only on the sidewalk.
                x, ground_y = self.stage.area_for(bullet).project(bullet.x, bullet.ground_y,
                                                                  config.DROP_ITEM_HALF_WIDTH)
                item = DropItem(bullet.weapon_kind, x, ground_y, bullet.facing,
                                elapsed=bullet.elapsed, floor=bullet.floor, was_thrown=True)
                if isinstance(bullet, EnemyAxeProjectile):
                    item.axe_owner = bullet.shooter
                if bullet.height > bullet.half_height:
                    # At the map edge or the end of a parried axe's flight, drop in place.
                    item.jump_height = bullet.height - item.display_height / 2
                    item.vy = bullet.vy
                self.stage.drop_items.append(item)
        self.projectiles[:] = [bullet for bullet in self.projectiles if not bullet.finished]

    def projectile_impact(self, bullet, x, y):
        self.effects.append(HitEffect(x, y, bullet.facing,
                                      image_name=config.CLUB_HIT_IMAGE))
        if bullet.impact_target is not self.player:
            enemy = bullet.impact_target
            self.damage_numbers.append(DamageNumber.above_body(
                enemy.body, bullet.impact_damage, depth=enemy.ground_y - config.GROUND_Y))
            self.camera.shake()
        else:
            self.camera.shake(strength=config.PLAYER_HIT_SHAKE_STRENGTH)

    def update_combat_effects(self, dt):
        for group in (self.effects, self.damage_numbers, self.afterimages):
            for effect in group:
                effect.update(dt)
            group[:] = [effect for effect in group if not effect.finished]

    def spawn_dive_afterimage(self, dt):
        if self.player.weapon_leap_phase != "DIVE" or not self.player.alive:
            self._dive_afterimage_remaining = 0.0
            return
        self._dive_afterimage_remaining -= dt
        if self._dive_afterimage_remaining <= 1e-9:
            # Capture before movement: even the release tick leaves a pose
            # behind the player. Snapshots never follow later equipment/poses.
            self.afterimages.append(SpriteAfterimage.from_player(self.player))
            self._dive_afterimage_remaining += config.WEAPON_DIVE_AFTERIMAGE_INTERVAL

    def update_traffic(self, dt):
        if self.stage.traffic is None:
            return
        car = self.stage.traffic.update(dt)
        if car is None:
            return
        hit_player = car.hits(self.player)
        hit_enemies = [enemy for enemy in self.enemies if car.hits(enemy)]
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

    def try_stage_transition(self):
        player = self.player
        if (self.stage_loading or player.floor != 0 or player.staircase is not None
                or not player.alive or player.active_move is not None
                or player.state in ("SHOOT", "RELOAD", "HIT", "DYING", "DEAD")):
            return False
        if self.stage.at_open_factory_gate(player):
            self.pending_stage_index = self.stage_index + 1
            self.stage_loading_remaining = config.FACTORY_FADE_DURATION
            self.controls.pressed.clear()
            return True
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
                self._finish_stage_exit(destination)
            return True
        return False

    def _record_map_clear(self):
        self.cleared_stages.add(self.stage_index)
        self._map_clears_pending_heal.add(self.stage_index)

    def _finish_stage_exit(self, destination):
        if destination == self.stage_index + 1 and destination in config.STAGE_PROGRESS_PANELS:
            region_maps = (self.stage_index - 1, self.stage_index)
            if self._map_clears_pending_heal.issuperset(region_maps):
                self.player.hp = self.player.max_hp
                self._map_clears_pending_heal.difference_update(region_maps)
        self._enter_stage(destination)

    def select_stage(self, destination):
        """Enter a scene for tooling while preserving its actors and player HP."""
        if not self.player.alive or not 0 <= destination < len(self.stages):
            return False
        self.pending_stage_index = None
        self.stage_loading_remaining = 0.0
        self.accumulator = 0.0
        self.controls.pressed.clear()
        self._enter_stage(destination, entry_x=config.START_X)
        resolve_bodies(self.player, self.enemies, self.stage.area_for(self.player))
        self.player.previous_x = self.player.x
        self.player.previous_ground_y = self.player.ground_y
        self.camera = Camera(self.player.x, self.stage.width)
        self.update_camera(0)
        return True

    def _enter_stage(self, destination, *, entry_x=None):
        # Keep the same player, physics, held input and animation clock, and
        # enter far enough inside the next scene to avoid an immediate return.
        side = 1 if destination > self.stage_index else -1
        self._dive_afterimage_remaining = 0.0
        self.stage.release_actor(self.player)
        self.controls.take_press("sniper_spawn")
        self.controls.held.discard("sniper_spawn")
        self.stage_index = destination
        player = self.player
        player.floor = 0
        player.crowd_escape.clear_encounter()
        player.stair_arrival = False
        player.stair_regrab_remaining = 0.0
        player.upper_landing_requested = False
        player.falling_from_upper = False
        player.x = (entry_x if entry_x is not None else
                    config.STAGE_ENTRY_MARGIN if side > 0 else
                    config.WORLD_WIDTH - config.STAGE_ENTRY_MARGIN)
        self.stage.constrain_actor(player)
        player.previous_x = player.x
        player.previous_ground_y = player.ground_y
        self._encounter_delay_remaining = (0.0 if self.stage.encounter_started
                                           else config.STAGE_ENCOUNTER_DELAY)
        self.camera = Camera(player.x, self.stage.width)
        self.update_camera(0)

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
