"""Held-W flight contacts, captured enemies and joint floor constraints."""

import config
from collision import body_contact_time
from combat import STRONG_MOVES
from walkable import WalkableArea


class RushSequence:
    def __init__(self, player, walkable):
        self.player = player
        self.walkable = walkable
        self.direction = player.facing
        self.captives = []
        self.finished = False

    @property
    def valid(self):
        return (not self.finished and self.player.alive and self.player.rush_phase == "FLY"
                and self.player.active_move is STRONG_MOVES["combat_w"])

    def prune(self, enemies):
        for enemy in self.captives:
            if enemy not in enemies:
                enemy.release_rush(self.direction)
        self.captives[:] = [enemy for enemy in self.captives
                            if enemy in enemies and enemy.state == "RUSH_CARRIED"]

    def update(self, enemies):
        self.prune(enemies)
        player = self.player
        contacts = []
        for enemy in enemies:
            if (not enemy.alive or enemy in player.hit_enemies or enemy.counter_linked):
                continue
            contact = body_contact_time(player, enemy)
            if contact is None:
                continue
            px = player.previous_x + (player.x - player.previous_x) * contact
            ex = enemy.previous_x + (enemy.x - enemy.previous_x) * contact
            if (ex - px) * self.direction >= -1e-9:
                contacts.append((contact, enemy))
        impacts = []
        for _, enemy in sorted(contacts, key=lambda entry: entry[0]):
            hp = enemy.hp
            if enemy.start_rush_carry(STRONG_MOVES["combat_w"], self.direction):
                player.hit_enemies.add(enemy)
                self.captives.append(enemy)
                impacts.append((enemy, hp - enemy.hp))
        if not self.sync_pair():
            player.release_rush()
            self.finish()
        return impacts

    def sync_pair(self):
        if not self.captives:
            return True
        player = self.player
        distance = self.direction * config.RUSH_CARRY_DISTANCE
        padding = max(enemy.boundary_padding for enemy in self.captives)
        left = min(-player.boundary_padding, distance - padding)
        right = max(player.boundary_padding, distance + padding)
        center = (left + right) / 2
        try:
            area = WalkableArea(tuple((x - center, y) for x, y in
                                      self.walkable.inset((right - left) / 2)))
            x, y = area.project(player.x, player.ground_y)
        except ValueError:
            return False
        if abs(x - player.x) > 1e-9:
            player.vx = 0.0
        if abs(y - player.ground_y) > 1e-9:
            player.ground_vy = 0.0
        player.x, player.ground_y = x, y
        player.facing = self.direction
        for enemy in self.captives:
            enemy.x, enemy.ground_y = x + distance, y
            enemy.jump_height = player.jump_height
            enemy.vx, enemy.ground_vy, enemy.vy = player.vx, player.ground_vy, 0.0
            enemy.facing = -self.direction
        return True

    def finish(self):
        if self.finished:
            return
        self.finished = True
        for enemy in self.captives:
            enemy.release_rush(self.direction)
        self.captives.clear()
