"""Single-screen practice room with weapons placed on the supplied table."""

import config
from drop_items import DropItem
from enemy import Enemy
from stage import Stage
from walkable import WalkableArea


class TrainingTarget(Enemy):
    """Use the first stage thug's hit animation at a fixed practice position."""

    uses_melee_slots = False
    blocks_movement = False

    def take_damage(self, damage):
        self.last_hit_damage = damage
        self.animation.set_state("HIT")
        self.animation.elapsed = 0.0
        return True

    def take_strong_hit(self, move, direction):
        return self.take_damage(move.damage)

    def start_rush_carry(self, move, direction):
        return self.take_damage(move.damage)

    def _update_ai(self, dt, player):
        self.animation.update(dt)
        if self.state == "HIT" and self.animation.finished:
            self.animation.set_state("IDLE")


class TrainingRoom(Stage):
    image_name = config.TRAINING_ROOM_IMAGE
    width = config.SCREEN_WIDTH
    camera_y_bounds = (0, 0)
    arrow_sides = ()
    table_slots = dict(config.TRAINING_TABLE_ITEMS)

    def __init__(self):
        super().__init__(walkable=WalkableArea.rectangle(*config.TRAINING_FLOOR), drop_items=[])
        for kind in self.table_slots:
            self.place_on_table(kind)

    def can_return_to_table(self, player, kind):
        left, right = config.TRAINING_TABLE_X_BOUNDS
        return (kind in self.table_slots and player.grounded and left <= player.x <= right
                and abs(player.ground_y - config.TRAINING_TABLE_APPROACH_Y) <= config.WEAPON_PICKUP_DEPTH)

    def place_on_table(self, kind, pistol_ammo=None):
        approach = config.TRAINING_TABLE_APPROACH_Y
        item = DropItem(kind, self.table_slots[kind], approach, pistol_ammo=pistol_ammo,
                        support_height=config.TRAINING_TABLE_SURFACE_Y - approach)
        self.drop_items.append(item)
        return item

    def summon_target(self, player):
        # Leave room for a jab, including when the player faces the nearest wall.
        facing = player.facing
        distance = 92
        left, right = self.walkable.x_limits(player.ground_y, TrainingTarget.boundary_padding)
        if not left <= player.x + facing * distance <= right:
            facing = -facing
        x, y = self.walkable.project(player.x + facing * distance, player.ground_y,
                                     TrainingTarget.boundary_padding)
        self.enemies[:] = [TrainingTarget(x, -facing, ground_y=y)]
