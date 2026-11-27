"""Player state, movement and animation; graphics stay in the renderer."""

from math import hypot

import config
from animation import Animation
from collision import Rect, attack_hits_body
from combat import (ALL_MOVES, COMBAT_INPUTS, AXE_THROW, DUAL_BATONS_THROW, KNIFE_THROW, PIPE_THROW, SHIELD_THROW,
                    STEEL_CLUB_THROW, STRONG_MOVES, CrowdEscape, moves_for_weapon)
from physics import approach_vector
from projectiles import (AxeProjectile, DualBatonProjectile, KnifeProjectile, PlayerPistolBullet, PlayerRifleBullet,
                         ShieldProjectile, SteelClubProjectile, SteelPipeProjectile)
from traffic import start_car_hit, update_car_hit
from walkable import default_area


THROW_PROJECTILES = {KNIFE_THROW: KnifeProjectile, PIPE_THROW: SteelPipeProjectile,
                     STEEL_CLUB_THROW: SteelClubProjectile, AXE_THROW: AxeProjectile,
                     DUAL_BATONS_THROW: DualBatonProjectile, SHIELD_THROW: ShieldProjectile}


class Player:
    stair_following = False
    boundary_padding = config.PLAYER_BOUNDARY_PADDING

    def __init__(self):
        self.x = config.START_X
        self.previous_x = self.x
        self.ground_y = config.GROUND_Y
        self.previous_ground_y = self.ground_y
        self.jump_height = 0.0
        self.previous_jump_height = 0.0
        self.ground_vy = 0.0
        self.walkable = default_area()
        self.floor = 0
        self.staircase = None
        self.stair_arrival = False
        self.stair_regrab_remaining = 0.0
        self.upper_landing_requested = False
        self.falling_from_upper = False
        self.navigation_target = None
        self.vx = 0.0
        self.vy = 0.0
        self.jump_count = 0
        self._facing = 1
        self.firearm_facing_locked = False
        self.max_hp = config.MAX_HP
        self.hp = self.max_hp
        self.last_hit_damage = 0
        self.invincible = False
        self.crowd_escape = CrowdEscape()
        self.car_hit = False
        self.weapon = None
        self.pistol_ammo = config.PLAYER_PISTOL_MAGAZINE_SIZE
        self.rifle_ammo = config.PLAYER_RIFLE_MAGAZINE_SIZE
        self.rifle_cooldown = 0.0
        self.rifle_trigger = False
        self.pistol_shot_pending = False
        self.firearm_gait = "IDLE"
        self.sword_parry_gait = "IDLE"
        self.pistol_reload_interrupted = False
        self.active_move = None
        self.weapon_leap_phase = None
        self.weapon_leap_direction = (1.0, 0.0)
        self.weapon_leap_velocity = (0.0, 0.0)
        self.air_kick_phase = None
        self.air_kick_strike_frame = config.AIR_KICK_STRIKE_FRAMES[0]
        self.air_kick_count = 0
        self.air_kicks_used = 0
        self.hit_enemies = set()
        definitions = dict(config.PLAYER_ANIMATIONS)
        definitions.update({move.state: (move.row, move.fps, False)
                            for move in ALL_MOVES.values()})
        self.animation = Animation(definitions)

    @property
    def state(self):
        return self.animation.state

    @property
    def alive(self):
        return self.hp > 0

    @property
    def facing(self):
        return self._facing

    @facing.setter
    def facing(self, direction):
        if not self.firearm_facing_locked:
            self._facing = direction

    @property
    def moves(self):
        double_jump = self.jump_count == 2 or self.weapon_leap_phase is not None
        return moves_for_weapon(self.weapon, double_jump=double_jump)

    @property
    def firearm_ammo(self):
        return self.rifle_ammo if self.weapon == "ar_rifle" else self.pistol_ammo

    @firearm_ammo.setter
    def firearm_ammo(self, rounds):
        if self.weapon == "ar_rifle":
            self.rifle_ammo = rounds
        else:
            self.pistol_ammo = rounds

    @property
    def time_scale(self):
        if self.alive and self.active_move is not None and self.air_kick_phase == "WAIT":
            return config.AIR_KICK_TIME_SCALE
        if self.alive and self.active_move is not None and self.active_move.jump_attack:
            if self.weapon_leap_phase == "AIM":
                return config.WEAPON_AIM_TIME_SCALE
            if self.weapon_leap_phase in ("DIVE", "LANDING"):
                return config.WEAPON_DIVE_TIME_SCALE
        return 1.0

    @property
    def y(self):
        """Projected feet; physics keeps ground_y and jump_height independent."""
        return self.ground_y + self.jump_height

    @y.setter
    def y(self, value):
        self.jump_height = max(0.0, value - self.ground_y)

    @property
    def sprite_image(self):
        if self.car_hit:
            return config.PLAYER_CAR_HIT_IMAGE
        if self.active_move is not None:
            return self.active_move.image_name
        if self.weapon in config.PLAYER_EQUIPPED_SHEETS:
            return config.PLAYER_EQUIPPED_SHEETS[self.weapon]
        if self.state in config.WEAPON_POSE_ROWS.get(self.weapon, {}):
            return config.WEAPON_POSE_IMAGES[self.weapon]
        return config.PLAYER_IMAGE

    @property
    def sprite_row(self):
        if self.active_move is not None:
            return self.active_move.row
        if self.state == "SWORD_PARRY":
            return config.SWORD_PARRY_MOVING_ROWS.get(self.sword_parry_gait, self.animation.row)
        if self.state in ("SHOOT", "RELOAD"):
            pose = self._firearm_pose_for_frame(self.animation.frame)
            return self.animation.definitions[pose][0]
        if self.sprite_image in config.WEAPON_POSE_IMAGES.values():
            return config.WEAPON_POSE_ROWS[self.weapon][self.state]
        return self.animation.row

    def cancel_combat(self):
        self.pistol_shot_pending = False
        self.rifle_trigger = False
        self.active_move = None
        self.hit_enemies.clear()
        self.weapon_leap_phase = None
        self.weapon_leap_direction = (float(self.facing), 0.0)
        self.weapon_leap_velocity = (0.0, 0.0)
        self.air_kick_phase = None
        self.air_kick_strike_frame = config.AIR_KICK_STRIKE_FRAMES[0]
        self.air_kick_count = 0

    def finish_move(self):
        self.cancel_combat()
        self.vx = self.ground_vy = 0.0
        self.animation.set_state("IDLE" if self.grounded else "JUMP")

    def equip_weapon(self, weapon):
        if weapon == self.weapon:
            return
        self.weapon = weapon
        self.firearm_facing_locked = False
        self.rifle_cooldown = 0.0
        self.pistol_reload_interrupted = False
        hit_fps = self.animation.definitions["HIT"][1]
        poses = config.EQUIPPED_ANIMATIONS.get(weapon, config.PLAYER_ANIMATIONS)
        self.animation.definitions.update(poses)
        if self.state == "HIT":
            # A mid-flinch G swap changes the sheet/row, not the chosen recovery speed.
            row, _, loop = poses["HIT"]
            self.animation.definitions["HIT"] = (row, hit_fps, loop)
        if self.active_move is not None or self.state in ("SHOOT", "RELOAD", "GUARD", "SWORD_PARRY"):
            # Dropping/swapping a weapon cannot leave its old strike pending.
            self.cancel_combat()
            self.animation.set_state("IDLE" if self.grounded else "JUMP")

    def _firearm_pose_for_frame(self, frame):
        if self.state in ("SHOOT", "RELOAD") and self.firearm_gait in ("WALK", "RUN"):
            # The moving shots flash again in column seven. Use the matching
            # non-firing stride there because one A press fires one round.
            if self.weapon == "pistol" and self.state == "SHOOT" and frame == 6:
                return self.firearm_gait
            return f"{self.firearm_gait}_{self.state}"
        return self.state

    def _pistol_muzzle_offset(self, frame):
        pose = self._firearm_pose_for_frame(frame)
        forward, height = config.PLAYER_PISTOL_MUZZLE_OFFSETS[pose][frame]
        return self.facing * forward * config.SPRITE_SCALE, height * config.SPRITE_SCALE

    @property
    def aim_line(self):
        if (self.weapon != "pistol" or not self.alive or self.staircase is not None
                or self.active_move is not None
                or self.state not in config.PLAYER_PISTOL_MUZZLE_OFFSETS):
            return None
        offset_x, offset_y = self._pistol_muzzle_offset(self.animation.frame)
        height = self.y + offset_y
        left, _, right, _ = self.walkable.bounds
        end = max(left, min(right, self.x + self.facing * config.PLAYER_PISTOL_RANGE))
        return self.x + offset_x, height, end, height

    def start_pistol_shot(self, direction=0):
        if (self.weapon != "pistol" or not self.alive or self.staircase is not None
                or self.active_move is not None
                or self.state not in ("IDLE", "WALK", "RUN", "JUMP")):
            return False
        if self.pistol_ammo <= 0:
            self.start_pistol_reload()
            return False
        if direction:
            self.facing = direction
        self.cancel_combat()
        self.firearm_gait = self.state if self.grounded else "JUMP"
        self.pistol_shot_pending = True
        self.animation.set_state("SHOOT")
        return True

    def start_pistol_reload(self):
        self.start_firearm_reload()

    def start_firearm_reload(self):
        if self.state in ("IDLE", "WALK", "RUN", "JUMP"):
            self.firearm_gait = self.state
        self.cancel_combat()
        self.animation.set_state("RELOAD")
        self.animation.elapsed = 0.0

    def take_projectile(self):
        if not self.alive or self.staircase is not None:
            return None
        if self.weapon == "ar_rifle" and self.state == "SHOOT":
            if not self.rifle_trigger or self.rifle_cooldown > 1e-9 or self.rifle_ammo == 0:
                return None
            # Alternate the sheet's two flash poses on successive rounds.
            flash = self.rifle_ammo % 2
            frame = (1, 4)[flash]
            self.animation.elapsed = (frame + 1e-9) / self.animation.definitions["SHOOT"][1]
            pose = self._firearm_pose_for_frame(frame)
            forward, height = config.PLAYER_RIFLE_FLASH_OFFSETS[pose][flash]
            self.rifle_ammo -= 1
            self.rifle_cooldown = config.PLAYER_RIFLE_FIRE_INTERVAL
            return PlayerRifleBullet(
                self.x + self.facing * (forward * config.SPRITE_SCALE + PlayerRifleBullet.half_width),
                self.ground_y, self.jump_height + height * config.SPRITE_SCALE, self.facing, self.floor)
        projectile_type = THROW_PROJECTILES.get(self.active_move)
        if projectile_type is not None and self.weapon == projectile_type.weapon_kind:
            release_time = projectile_type.release_frame / self.active_move.fps
            if self.animation.elapsed + 1e-9 < release_time:
                return None
            self.animation.elapsed = max(self.animation.elapsed, release_time)
            # The remaining throw cells already show empty hands. Finish this
            # motion, but relinquish the weapon now so it can be emitted only once.
            self.weapon = None
            self.animation.definitions.update(config.PLAYER_ANIMATIONS)
            forward, height = projectile_type.release_offset
            return projectile_type(self.x + self.facing * forward * config.SPRITE_SCALE,
                                   self.ground_y, self.jump_height + height * config.SPRITE_SCALE,
                                   self.facing, self.floor)
        if (self.weapon != "pistol" or self.state != "SHOOT"
                or not self.pistol_shot_pending or self.pistol_ammo <= 0
                or self.animation.finished):
            return None
        fps = self.animation.definitions["SHOOT"][1]
        flash_time = config.PLAYER_PISTOL_SHOOT_FRAME / fps
        if self.animation.elapsed + 1e-9 < flash_time:
            return None
        # Keep the emitted round and the first visible muzzle flash in one frame.
        self.animation.elapsed = max(self.animation.elapsed, flash_time + 1e-9 / fps)
        self.pistol_shot_pending = False
        self.pistol_ammo -= 1
        offset_x, offset_y = self._pistol_muzzle_offset(config.PLAYER_PISTOL_SHOOT_FRAME)
        return PlayerPistolBullet(
            self.x + offset_x + self.facing * PlayerPistolBullet.half_width,
            self.ground_y, self.jump_height + offset_y,
            self.facing, self.floor)

    def update_firearm(self, dt, controls):
        if self.grounded or self.weapon == "ar_rifle":
            speed = config.RUN_SPEED if controls.running else config.WALK_SPEED
            self.move_on_ground(dt, controls, speed)
        else:
            self.vx = self.ground_vy = 0.0
        self.update_vertical(dt)
        self.firearm_gait = self.movement_state(controls)
        self.animation.update(dt)
        if self.weapon == "ar_rifle" and self.state == "SHOOT":
            if not self.rifle_trigger and self.rifle_cooldown <= 1e-9:
                self.animation.set_state(self.firearm_gait)
            return
        if self.animation.elapsed + 1e-9 < 8 / self.animation.definitions[self.state][1]:
            return
        if self.state == "SHOOT" and self.pistol_ammo == 0:
            self.start_pistol_reload()
        else:
            if self.state == "RELOAD":
                self.firearm_ammo = config.FIREARM_MAGAZINE_SIZES[self.weapon]
                self.pistol_reload_interrupted = False
            self.pistol_shot_pending = False
            self.animation.set_state(self.firearm_gait)

    def start_move(self, move, direction):
        if move.jump_attack and (self.grounded or self.jump_count != 2):
            return
        if move is STRONG_MOVES["combat_w"]:
            if not self.grounded and self.air_kicks_used >= config.AIR_KICK_MAX_COUNT:
                return
            if self.grounded:
                self.air_kicks_used = 0
        velocity = self.vx, self.ground_vy
        self.cancel_combat()
        self.active_move = move
        self.vx = 0.0
        self.ground_vy = 0.0
        if direction:
            self.facing = direction
        self.animation.definitions[move.state] = (move.row, move.fps, False)
        self.animation.set_state(move.state)
        self.animation.elapsed = 0.0
        if move is STRONG_MOVES["combat_w"]:
            self.air_kick_phase = "KICK"
            self.air_kick_count = 1
            self.air_kicks_used += 1
        if move.jump_attack:
            self.weapon_leap_phase = "AIM"
            self.weapon_leap_direction = (float(self.facing), 0.0)
            self.vx, self.ground_vy = velocity
            self.animation.elapsed = 2.05 / move.fps

    def resume_air_kick(self):
        if (self.air_kick_count >= config.AIR_KICK_MAX_COUNT
                or self.air_kicks_used >= config.AIR_KICK_MAX_COUNT):
            return
        self.air_kick_count += 1
        self.air_kicks_used += 1
        self.air_kick_strike_frame = config.AIR_KICK_STRIKE_FRAMES[1]
        self.air_kick_phase = "KICK"
        self.hit_enemies.clear()
        self.animation.elapsed = (self.air_kick_strike_frame - 1) / self.active_move.fps

    def update_air_kick(self, dt, controls):
        self.vx = self.ground_vy = 0.0
        if controls.direction:
            self.facing = controls.direction
        self.update_vertical(dt)
        if self.air_kick_phase == "KICK":
            self.animation.update(dt)
            deadline = (self.air_kick_strike_frame + 1) / self.active_move.fps
            if self.animation.elapsed + 1e-9 >= deadline:
                if (self.air_kick_count >= config.AIR_KICK_MAX_COUNT
                        or self.air_kicks_used >= config.AIR_KICK_MAX_COUNT):
                    self.air_kick_phase = "RECOVERY"
                    self.animation.elapsed = deadline
                else:
                    self.air_kick_phase = "WAIT"
        elif self.air_kick_phase == "RECOVERY":
            self.animation.update(dt)
            if self.animation.finished:
                self.finish_move()
                return
        if self.air_kick_phase == "WAIT":
            # Retract the leg between fresh W presses; this pose never attacks.
            self.animation.elapsed = config.AIR_KICK_HOLD_FRAME / self.active_move.fps

    def start_weapon_dive(self, controls):
        direction = controls.movement if controls.moving else self.weapon_leap_direction
        if direction[0]:
            self.facing = 1 if direction[0] > 0 else -1
        self.weapon_leap_direction = direction
        self.weapon_leap_velocity = tuple(axis * config.WEAPON_DIVE_SPEED for axis in direction)
        self.vx, self.ground_vy = self.weapon_leap_velocity
        self.vy = -config.WEAPON_DIVE_FALL_SPEED
        self.weapon_leap_phase = "DIVE"
        self.animation.elapsed = 3.05 / self.active_move.fps

    def update_weapon_leap(self, dt, controls):
        move = self.active_move
        if self.weapon_leap_phase == "AIM":
            speed = config.RUN_SPEED if controls.running else config.WALK_SPEED
            self.move_on_ground(dt, controls, speed)
            if controls.moving:
                self.weapon_leap_direction = controls.movement
            self.update_vertical(dt)
            self.animation.elapsed = (2.05 if move.strike_during_dive or self.vy >= 0 else 3.05) / move.fps
            if self.grounded:
                # Waiting out the jump without a second D never releases a hit.
                self.cancel_combat()
                self.animation.set_state("IDLE")
            return
        if self.weapon_leap_phase == "DIVE":
            self.vx, self.ground_vy = self.weapon_leap_velocity
            self.x += self.vx * dt
            self.ground_y += self.ground_vy * dt
            self.walkable.constrain(self, config.PLAYER_HALF_WIDTH)
            self.update_vertical(dt)
            if move.strike_during_dive:
                self.animation.elapsed = min(self.animation.elapsed + dt, max(move.active_frames) / move.fps)
            if self.grounded:
                self.weapon_leap_phase = "LANDING"
                self.vx = self.ground_vy = 0.0
                self.animation.elapsed = max(self.animation.elapsed, 4 / move.fps)
            return
        self.vx = self.ground_vy = 0.0
        self.animation.update(dt)
        if self.animation.finished:
            self.cancel_combat()
            self.animation.set_state("IDLE")

    @property
    def grounded(self):
        return self.jump_height <= 0.0 and self.vy == 0

    @property
    def body(self):
        """x/height-plane AABB; ground-depth proximity is a separate condition."""
        base = config.GROUND_Y + self.jump_height
        return Rect(self.x - config.PLAYER_HALF_WIDTH, base,
                    self.x + config.PLAYER_HALF_WIDTH, base + config.PLAYER_HEIGHT)

    @property
    def attack_box(self):
        move = self.active_move
        if (not self.alive or move is None or self.state != move.state
                or self.animation.frame not in move.active_frames):
            return None
        if move.jump_attack:
            descending_strike = move.strike_during_dive and self.weapon_leap_phase == "DIVE"
            landing_strike = self.weapon_leap_phase == "LANDING" and self.grounded
            if not (descending_strike or landing_strike):
                return None
        if self.air_kick_phase is not None and (
                self.air_kick_phase != "KICK" or self.animation.frame != self.air_kick_strike_frame):
            return None
        near = self.x + self.facing * 10
        far = self.x + self.facing * move.reach
        base = config.GROUND_Y + self.jump_height
        return Rect(min(near, far), base + 20, max(near, far), base + move.height)

    def try_hit(self, enemy):
        box = self.attack_box
        if (not enemy.alive or enemy in self.hit_enemies or not attack_hits_body(self, enemy, box)):
            return False
        self.hit_enemies.add(enemy)
        if self.active_move.enemy_hit_row is not None:
            return enemy.take_strong_hit(self.active_move, self.facing)
        return enemy.take_damage(self.active_move.damage)

    def _apply_damage(self, damage):
        self.last_hit_damage = min(self.hp, damage)
        self.hp -= self.last_hit_damage

    def take_damage(self, damage, *, attacker=None, stagger=True):
        if not self.alive or self.invincible or self.crowd_escape.active:
            return False
        guarding = self.state == "GUARD"
        self._apply_damage(damage * 0.5 if guarding else damage)
        if attacker is not None and self.hp and self.last_hit_damage > 0:
            self.crowd_escape.record_hit(attacker)
        if self.alive and (guarding or not stagger):
            return True
        if self.weapon == "pistol" and self.state == "RELOAD" and self.hp:
            self.pistol_reload_interrupted = True
        self.vx = 0.0
        self.ground_vy = 0.0
        self.cancel_combat()
        if self.hp and self.state != "HIT":
            # Choose recovery speed once per reaction; further hits must not
            # restart or prolong it, even if equipment changes during HIT.
            poses = config.EQUIPPED_ANIMATIONS.get(self.weapon, config.PLAYER_ANIMATIONS)
            row, fps, loop = poses["HIT"]
            if self.weapon in config.WEAPON_POSE_IMAGES:
                fps = config.WEAPON_HIT_FPS
            self.animation.definitions["HIT"] = (row, fps, loop)
        # Every enemy swing applies damage. Re-entering HIT preserves the
        # current animation clock; a lethal hit always overrides it with DYING.
        self.animation.set_state("HIT" if self.hp else "DYING")
        return True

    def hit_by_car(self, direction):
        if not self.alive:
            return False
        self.cancel_combat()
        self.invincible = False
        self.firearm_facing_locked = False
        start_car_hit(self, direction)
        return True

    def update_vertical(self, dt):
        if not self.grounded:
            self.vy -= config.GRAVITY * dt
            self.jump_height += self.vy * dt
            if self.jump_height <= 0.0:
                self.jump_height = 0.0
                self.vy = 0.0
                self.jump_count = 0
                self.air_kicks_used = 0
                self.upper_landing_requested = False
                self.falling_from_upper = False

    def start_jump(self, controls):
        if self.jump_count >= 2:
            return
        if self.jump_count == 0:
            self.vy = config.JUMP_SPEED
            self.air_kicks_used = 0
        elif controls.running and controls.moving:
            self.vy = config.RUN_DOUBLE_JUMP_SPEED
        else:
            self.vy = config.DOUBLE_JUMP_SPEED
        self.jump_count += 1
        if self.weapon == "ar_rifle" and self.state in ("SHOOT", "RELOAD"):
            return
        self.animation.set_state("JUMP")
        self.animation.elapsed = 0.0

    def update(self, dt, controls, walkable=None, *, process_input=True):
        if walkable is not None:
            self.walkable = walkable
        self.walkable.constrain(self, config.PLAYER_HALF_WIDTH)
        self.previous_x = self.x
        self.previous_ground_y = self.ground_y
        self.previous_jump_height = self.jump_height
        if process_input:
            self.crowd_escape.advance(dt)
            self.handle_input(controls)
        self._update(dt, controls)
        self.walkable.constrain(self, config.PLAYER_HALF_WIDTH)

    def handle_input(self, controls):
        """Resolve fresh actions before World samples the simulation time scale."""
        if controls.take_press("invincibility") and self.alive:
            self.invincible = not self.invincible
        if self.weapon in config.FIREARM_MAGAZINE_SIZES:
            toggles = controls.take_presses(("combat_s",))
            if self.alive and len(toggles) % 2:
                self.firearm_facing_locked = not self.firearm_facing_locked
        escape = self.crowd_escape
        arrow_presses = controls.take_presses(config.CROWD_ESCAPE_KEYS)
        if self.alive and any(escape.press(key) for key in arrow_presses):
            self.finish_move()
            if self.pistol_ammo:
                self.pistol_reload_interrupted = False
        if self.weapon not in config.FIREARM_MAGAZINE_SIZES:
            controls.take_press("combat_r")
        combat_pressed = controls.take_latest_press(COMBAT_INPUTS)
        if self.state == "HIT" and self.pistol_reload_interrupted:
            # Leave one jump press in Controls until the hit reaction finishes.
            return
        jump_pressed = controls.take_press("jump")
        if self.staircase is not None or self.state in ("CAR_HIT", "HIT", "DYING", "DEAD"):
            return
        if self.active_move in THROW_PROJECTILES:
            return
        if self.weapon == "sword" and "combat_s" in controls.held and not escape.active:
            if self.state != "SWORD_PARRY":
                self.cancel_combat()
                self.sword_parry_gait = self.movement_state(controls)
                self.animation.set_state("SWORD_PARRY")
                self.animation.elapsed = 1 / config.SWORD_PARRY_FPS
            if controls.direction:
                self.facing = controls.direction
            return
        if self.state == "SWORD_PARRY":
            self.animation.set_state(self.movement_state(controls))
        if self.weapon == "shield_item" and self.active_move is None:
            if "combat_s" in controls.held and not escape.active:
                self.vx = self.ground_vy = 0.0
                self.animation.set_state("GUARD")
                return
            if self.state == "GUARD":
                self.animation.set_state("IDLE" if self.grounded else "JUMP")
        if self.weapon in config.FIREARM_MAGAZINE_SIZES and combat_pressed == "combat_r":
            combat_pressed = None
            can_reload = self.state in ("IDLE", "WALK", "RUN", "JUMP") or (
                self.weapon == "ar_rifle" and self.state == "SHOOT")
            if (self.active_move is None and can_reload
                    and self.firearm_ammo < config.FIREARM_MAGAZINE_SIZES[self.weapon]):
                if jump_pressed:
                    self.start_jump(controls)
                self.pistol_reload_interrupted = False
                self.start_firearm_reload()
                return
        if self.weapon == "ar_rifle" and self.active_move is None:
            firing = combat_pressed == "combat_a" or (combat_pressed is None and "combat_a" in controls.held)
            self.rifle_trigger = firing and self.rifle_ammo > 0
            if self.state in ("SHOOT", "RELOAD") or self.rifle_trigger:
                if jump_pressed:
                    self.start_jump(controls)
                if self.rifle_trigger and self.state != "RELOAD":
                    self.animation.set_state("SHOOT")
                return
        if self.weapon == "pistol" and self.active_move is None:
            if self.pistol_reload_interrupted and (controls.moving or jump_pressed or not self.grounded):
                if self.state == "RELOAD":
                    self.animation.set_state("IDLE" if self.grounded else "JUMP")
                combat_pressed = None  # Only movement and jumping can interrupt the reload.
            elif self.state in ("SHOOT", "RELOAD"):
                return
            elif self.pistol_ammo == 0:
                self.start_pistol_reload()
                return
            elif combat_pressed == "combat_a":
                self.start_pistol_shot(controls.direction)
                return
        # A second Space and D may arrive together, before start_jump increments jump_count.
        starting_second_jump = jump_pressed and self.active_move is None and self.jump_count == 1
        moves = moves_for_weapon(self.weapon, double_jump=True) if starting_second_jump else self.moves
        move = STRONG_MOVES.get(combat_pressed) or moves.get(combat_pressed)
        if jump_pressed and self.active_move is None and (move is None or move.jump_attack):
            self.start_jump(controls)
        if move is not None:
            if move == self.active_move:
                if move.jump_attack and self.weapon_leap_phase == "AIM":
                    self.start_weapon_dive(controls)
                elif self.air_kick_phase == "WAIT":
                    self.resume_air_kick()
            else:
                self.start_move(move, controls.direction)

    def _update(self, dt, controls):
        if self.rifle_cooldown > 0:
            self.rifle_cooldown = max(0.0, self.rifle_cooldown - dt)
        if self.state == "CAR_HIT":
            update_car_hit(self, dt)
            return
        if self.state in ("HIT", "DYING", "DEAD"):
            self.vx = 0.0
            self.ground_vy = 0.0
            self.update_vertical(dt)
            if self.state == "DEAD":
                return
            self.animation.update(dt)
            if self.animation.finished:
                if self.state == "DYING":
                    self.animation.set_state("DEAD")
                    self.animation.elapsed = 8 / config.PLAYER_ANIMATIONS["DEAD"][1]
                else:
                    if self.pistol_ammo > 0:
                        # An interrupted top-up leaves the remaining rounds usable.
                        self.pistol_reload_interrupted = False
                    self.animation.set_state("IDLE")
            return

        if self.state == "SWORD_PARRY":
            if self.grounded:
                speed = config.RUN_SPEED if controls.running else config.WALK_SPEED
                self.move_on_ground(dt, controls, speed)
            else:
                self.vx = self.ground_vy = 0.0
            self.update_vertical(dt)
            self.sword_parry_gait = self.movement_state(controls)
            if self.sword_parry_gait in config.SWORD_PARRY_MOVING_ROWS:
                self.animation.update(dt)
                return
            # The stationary spin loops only source cells 2 through 6.
            first = 1 / config.SWORD_PARRY_FPS
            duration = 5 / config.SWORD_PARRY_FPS
            self.animation.elapsed = first + (self.animation.elapsed - first + dt) % duration
            return

        if self.state == "GUARD":
            self.update_vertical(dt)
            hold_time = config.SHIELD_GUARD_HOLD_FRAME / self.animation.definitions["GUARD"][1]
            self.animation.elapsed = min(self.animation.elapsed + dt, hold_time)
            return

        if self.state in ("SHOOT", "RELOAD"):
            self.update_firearm(dt, controls)
            return

        if self.active_move is not None:
            if self.air_kick_phase is not None:
                self.update_air_kick(dt, controls)
                return
            if self.active_move.jump_attack:
                self.update_weapon_leap(dt, controls)
                return
            self.vx = 0.0
            self.ground_vy = 0.0
            self.update_vertical(dt)
            self.animation.update(dt)
            if self.animation.finished:
                self.cancel_combat()
                self.animation.set_state("IDLE")
            return

        speed = config.RUN_SPEED if controls.running else config.WALK_SPEED
        self.move_on_ground(dt, controls, speed)
        self.update_vertical(dt)

        self.animation.set_state(self.movement_state(controls))
        self.animation.update(dt)

    def movement_state(self, controls):
        if not self.grounded:
            return "JUMP"
        if hypot(self.vx, self.ground_vy) > 0.1:
            return "RUN" if controls.running else "WALK"
        return "IDLE"

    def move_on_ground(self, dt, controls, speed, *, turn=True):
        move_x, move_y = controls.movement
        target_x, target_y = move_x * speed, move_y * speed
        magnitude = hypot(self.vx, self.ground_vy)
        if controls.moving and self.vx * move_x + self.ground_vy * move_y < 0:
            # Brake to zero first; only the remaining time accelerates the turn.
            stop_time = magnitude / config.FRICTION
            self.vx, self.ground_vy = approach_vector(self.vx, self.ground_vy, 0.0, 0.0,
                                                     config.FRICTION * dt)
            if stop_time < dt:
                self.vx, self.ground_vy = approach_vector(0.0, 0.0, target_x, target_y,
                                                         config.ACCELERATION * (dt - stop_time))
        else:
            # Releasing Shift must use the same strong braking as releasing a key.
            slowing = not controls.moving or magnitude > speed
            rate = config.FRICTION if slowing else config.ACCELERATION
            self.vx, self.ground_vy = approach_vector(self.vx, self.ground_vy, target_x, target_y,
                                                     rate * dt)
        self.x += self.vx * dt
        self.ground_y += self.ground_vy * dt
        self.walkable.constrain(self, config.PLAYER_HALF_WIDTH)
        if turn and controls.direction:
            self.facing = controls.direction
