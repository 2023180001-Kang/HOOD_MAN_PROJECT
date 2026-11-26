"""Ranged rounds with continuous collision and per-weapon flight/render profiles."""

from dataclasses import dataclass, field
from math import cos, radians, sin, sqrt
from operator import itemgetter

import config
from collision import same_floor


@dataclass
class ResearcherBullet:
    x: float
    ground_y: float
    height: float
    facing: int
    floor: int = 0
    elapsed: float = 0.0
    spent: bool = False
    shooter: object = field(default=None, kw_only=True, repr=False, compare=False)
    impact_target: object = field(default=None, init=False, repr=False)
    impact_damage: int = field(default=0, init=False)
    deflected: bool = field(default=False, init=False)

    image_name = config.RESEARCHER_BULLET_IMAGE
    damage = config.RESEARCHER_DAMAGE
    half_width = config.RESEARCHER_BULLET_HALF_WIDTH
    half_height = config.RESEARCHER_BULLET_HALF_HEIGHT
    speed = config.RESEARCHER_BULLET_SPEED
    fps = config.RESEARCHER_BULLET_FPS
    straight_range = config.RESEARCHER_BULLET_STRAIGHT_RANGE
    gravity = config.RESEARCHER_BULLET_GRAVITY
    scale = config.RESEARCHER_BULLET_SCALE
    anchor_y = config.RESEARCHER_BULLET_ANCHOR_Y
    range_limited = False
    world_width = config.WORLD_WIDTH
    hit_targets = None  # Piercing projectiles keep a set for the lifetime of the throw.
    deflectable = True
    ricochet_angle = radians(-35)

    @property
    def y(self):
        return self.ground_y + self.height

    @property
    def frame(self):
        return int(self.elapsed * self.fps + 1e-9) % 8

    @property
    def impact_x(self):
        return self.x + self.facing * self.half_width

    @property
    def straight_duration(self):
        return self.straight_range / self.speed

    @property
    def falling(self):
        return self.deflected or (not self.range_limited and self.elapsed + 1e-12 >= self.straight_duration)

    @property
    def horizontal_speed(self):
        return self.speed * cos(self.ricochet_angle) if self.deflected else self.speed

    @property
    def vy(self):
        if self.deflected:
            return self.speed * sin(self.ricochet_angle) - self.gravity * self.elapsed
        return -self.gravity * max(0.0, self.elapsed - self.straight_duration) if self.falling else 0.0

    @property
    def horizontal_limits(self):
        return -self.half_width, self.world_width + self.half_width

    @property
    def finished(self):
        left, right = self.horizontal_limits
        return (self.spent or self.height <= self.half_height
                or self.x < left or self.x > right
                or (self.range_limited and not self.deflected and self.elapsed + 1e-12 >= self.straight_duration))

    def update(self, dt, targets, *, on_impact=None):
        if self.finished:
            return False
        dt = max(0.0, dt)
        offset = 0.0
        dealt_damage = False
        while True:
            gravity = self.gravity if self.falling else 0.0
            vy = self.vy
            step = dt - offset
            range_time = float("inf")
            if not self.falling:
                # Split exactly at the range boundary, including a large update.
                step = min(step, self.straight_duration - self.elapsed)
                if self.range_limited:
                    range_time = self.straight_duration - self.elapsed
            ground_time = float("inf")
            if gravity:
                clearance = self.height - self.half_height
                ground_time = 2 * clearance / (sqrt(vy * vy + 2 * gravity * clearance) - vy)
                step = min(step, ground_time)
            left, right = self.horizontal_limits
            edge_gap = right - self.x if self.facing > 0 else self.x - left
            speed_x = self.facing * self.horizontal_speed
            edge_time = edge_gap / abs(speed_x)
            step = min(step, edge_time)
            terminal = min(ground_time, edge_time, range_time) <= step + 1e-12
            travel = step
            parried = False
            for contact, target in self._contacts(targets, step, offset, dt, gravity):
                # Ground/world contact wins a simultaneous tie.
                if terminal and contact >= step - 1e-12:
                    break
                if self.deflectable and target.state == "SWORD_PARRY":
                    travel = contact
                    parried = True
                    break
                if self._apply_hit(target):
                    dealt_damage = True
                    if on_impact is not None:
                        x = self.impact_x + speed_x * contact
                        y = self.y + vy * contact - gravity * contact * contact / 2
                        on_impact(self, x, y)
                if self.spent:
                    travel = contact
                    break
            self.x += speed_x * travel
            self.height += vy * travel - gravity * travel * travel / 2
            if parried:
                self.facing *= -1
                self.deflected = True
                self.elapsed = 0.0
                offset += travel
                continue
            self.elapsed += travel
            if self.spent:
                return dealt_damage
            if terminal:
                if ground_time <= step + 1e-12:
                    self.height = self.half_height
                self.spent = True
                return dealt_damage
            offset += step
            if offset >= dt:
                return dealt_damage

    def _apply_hit(self, target):
        if self.hit_targets is None:
            self.spent = True
        else:
            self.hit_targets.add(target)
        applied = self._deal_damage(target)
        self.impact_target = target
        self.impact_damage = target.last_hit_damage if applied else 0
        return applied

    def _deal_damage(self, player):
        return player.take_damage(self.damage, attacker=self.shooter, stagger=False)

    def _contacts(self, target, duration, offset, tick_duration, gravity):
        if self.deflected or (self.hit_targets is not None and target in self.hit_targets):
            return ()
        contact = self._contact_time(target, duration, offset, tick_duration, gravity)
        return () if contact is None else ((contact, target),)

    def _contact_time(self, player, duration, offset, tick_duration, gravity):
        if not player.alive or not same_floor(self, player):
            return None
        # A just-emitted bullet exists at the end of this simulation tick only.
        # Never sweep the player through a projectile that did not exist yet.
        if tick_duration == 0:
            px, py, height = player.x, player.ground_y, player.jump_height
            vx = ground_vy = jump_vy = 0.0
        else:
            vx = (player.x - player.previous_x) / tick_duration
            ground_vy = (player.ground_y - player.previous_ground_y) / tick_duration
            jump_vy = (player.jump_height - player.previous_jump_height) / tick_duration
            px = player.previous_x + vx * offset
            py = player.previous_ground_y + ground_vy * offset
            height = player.previous_jump_height + jump_vy * offset
        half_width = (player.body.right - player.body.left) / 2 + self.half_width
        half_height = self.half_height
        axes = (
            (self.x - px, self.facing * self.speed - vx, -half_width, half_width),
            (self.ground_y - py, -ground_vy,
              -config.ATTACK_DEPTH_TOLERANCE, config.ATTACK_DEPTH_TOLERANCE),
        )
        enter, leave = 0.0, duration
        for start, velocity, low, high in axes:
            if abs(velocity) < 1e-12:
                if not low <= start <= high:
                    return None
                continue
            first, last = sorted(((low - start) / velocity, (high - start) / velocity))
            enter, leave = max(enter, first), min(leave, last)
            if enter > leave:
                return None
        # Height is quadratic during the fall. A straight endpoint sweep could
        # miss a real mid-arc hit or report contact on the chord, off the arc.
        relative_height, relative_vy = self.height - height, self.vy - jump_vy
        low, high = -half_height, player.body.top - player.body.bottom + half_height
        candidates = [enter]
        for boundary in (low, high):
            difference = relative_height - boundary
            if gravity == 0:
                if abs(relative_vy) > 1e-12:
                    candidates.append(-difference / relative_vy)
            else:
                discriminant = relative_vy * relative_vy + 2 * gravity * difference
                if discriminant >= -1e-12:
                    root = sqrt(max(0.0, discriminant))
                    candidates.extend(((relative_vy - root) / gravity,
                                       (relative_vy + root) / gravity))
        for candidate in sorted(candidates):
            if enter - 1e-12 <= candidate <= leave + 1e-12:
                time = min(leave, max(enter, candidate))
                value = relative_height + relative_vy * time - gravity * time * time / 2
                if low - 1e-9 <= value <= high + 1e-9:
                    return time
        return None


class PlayerProjectile(ResearcherBullet):
    """Resolve eligible enemy contacts in flight order, including coincident hits."""

    deflectable = False

    def _deal_damage(self, enemy):
        return enemy.take_damage(self.damage)

    def _contacts(self, enemies, duration, offset, tick_duration, gravity):
        contacts = []
        for enemy in enemies:
            if self.hit_targets is not None and enemy in self.hit_targets:
                continue
            contact = self._contact_time(enemy, duration, offset, tick_duration, gravity)
            if contact is not None:
                contacts.append((contact, enemy))
        contacts.sort(key=itemgetter(0))
        return contacts


class PlayerPistolBullet(PlayerProjectile):
    damage = config.PLAYER_PISTOL_DAMAGE


@dataclass
class ThrownWeaponProjectile(ResearcherBullet):
    """A thrown weapon that drops in its own lane when flight ends."""

    deflectable = False

    hit_targets: set = field(default_factory=set, init=False, repr=False, compare=False)

    speed = 840.0
    release_frame = config.THROWN_WEAPON_RELEASE_FRAME
    straight_range = 720.0
    gravity = 1200.0
    half_width = half_height = 20.0

    @property
    def horizontal_limits(self):
        return config.DROP_ITEM_HALF_WIDTH, self.world_width - config.DROP_ITEM_HALF_WIDTH


class KnifeProjectile(ThrownWeaponProjectile, PlayerProjectile):
    weapon_kind = "combat_knife"
    image_name = config.KNIFE_PROJECTILE_IMAGE
    damage = config.KNIFE_THROW_DAMAGE
    speed = 1200.0
    release_offset = (90, 118)
    half_width = config.KNIFE_PROJECTILE_CLIP[2] * config.KNIFE_PROJECTILE_SCALE / 2
    half_height = config.DROP_ITEM_BODY_HEIGHTS[weapon_kind] * config.DROP_ITEM_SCALE / 2


class SteelPipeProjectile(ThrownWeaponProjectile, PlayerProjectile):
    weapon_kind = "steel_pipe"
    image_name = config.PIPE_PROJECTILE_IMAGE
    damage = config.PIPE_THROW_DAMAGE
    release_offset = (108, 104)  # Grip at the outstretched hand in row six, cell five.
    half_width = config.PIPE_PROJECTILE_CLIP[2] * config.PIPE_PROJECTILE_SCALE / 2
    half_height = config.DROP_ITEM_BODY_HEIGHTS[weapon_kind] * config.DROP_ITEM_SCALE / 2


class SteelClubProjectile(ThrownWeaponProjectile, PlayerProjectile):
    weapon_kind = "steel_club"
    image_name = config.STEEL_CLUB_PROJECTILE_IMAGE
    damage = config.STEEL_CLUB_THROW_DAMAGE
    release_offset = (76, 103)


class DualBatonProjectile(ThrownWeaponProjectile, PlayerProjectile):
    weapon_kind = "dual_black_batons"
    image_name = config.DUAL_BATON_PROJECTILE_IMAGE
    damage = config.DUAL_BATONS_THROW_DAMAGE
    release_offset = (54, 87)  # Center of the two batons leaving the hands in cell five.
    half_width = 60 * config.SPRITE_SCALE
    half_height = config.THROWN_WEAPON_SPRITES[weapon_kind].rest_height / 2


class ShieldProjectile(ThrownWeaponProjectile, PlayerProjectile):
    weapon_kind = "shield_item"
    image_name = config.SHIELD_PROJECTILE_IMAGE
    damage = config.SHIELD_THROW_DAMAGE
    release_frame = 5  # First empty-handed cell in row seven.
    release_offset = (90, 112)
    half_width = 65 * config.SPRITE_SCALE
    half_height = config.THROWN_WEAPON_SPRITES[weapon_kind].rest_height / 2


class ThrownAxe(ThrownWeaponProjectile):
    weapon_kind = "axe"
    image_name = config.AXE_PROJECTILE_IMAGE
    half_height = config.THROWN_WEAPON_SPRITES["axe"].rest_height / 2


class AxeProjectile(ThrownAxe, PlayerProjectile):
    damage = config.AXE_THROW_DAMAGE
    release_offset = (56, 133)  # Put the grip at the extended hand in row 6, cell 5.


class EnemyAxeProjectile(ThrownAxe):
    damage = config.AXE_ENEMY_THROW_DAMAGE
    release_offset = (108, 123)  # Extended hand in row seven, cell five.

    def _deal_damage(self, player):
        return player.take_damage(self.damage, attacker=self.shooter)


class RifleBullet(ResearcherBullet):
    """AR round: level, range-limited flight; shared swept collision, no floor drop."""

    image_name = config.RIFLE_BULLET_IMAGE
    damage = config.AR_SOLDIER_DAMAGE
    half_width = config.RIFLE_BULLET_HALF_WIDTH
    half_height = config.RIFLE_BULLET_HALF_HEIGHT
    speed = config.RIFLE_BULLET_SPEED
    fps = config.RIFLE_BULLET_FPS
    straight_range = config.RIFLE_BULLET_RANGE
    scale = config.RIFLE_BULLET_SCALE
    anchor_y = config.RIFLE_BULLET_ANCHOR_Y
    range_limited = True


class PlayerRifleBullet(PlayerProjectile, RifleBullet):
    damage = config.PLAYER_RIFLE_DAMAGE
