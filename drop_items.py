"""Stage-local weapons and gravity-driven falling items."""

from dataclasses import dataclass
import random

import config


@dataclass
class DropItem:
    collectible = True
    frame_count = config.DROP_ITEM_FRAMES

    kind: str
    x: float
    ground_y: float
    facing: int = 1
    elapsed: float = 0.0
    jump_height: float = 0.0
    vy: float = 0.0
    floor: int = 0
    pistol_ammo: int | None = None
    support_height: float = 0.0
    rifle_ammo: int | None = None
    axe_owner: object | None = None
    spin_while_falling: bool = False

    @property
    def firearm_ammo(self):
        return self.rifle_ammo if self.kind == "ar_rifle" else self.pistol_ammo

    @property
    def surface_y(self):
        return self.ground_y + self.support_height

    @property
    def grounded(self):
        return self.jump_height <= 0 and self.vy == 0

    @property
    def image_name(self):
        if self.kind in config.THROWN_WEAPON_SPRITES:
            return config.THROWN_WEAPON_SPRITES[self.kind].image
        if self.kind in config.FIREARM_DROP_SPRITES:
            return config.FIREARM_DROP_SPRITES[self.kind][0]
        return config.DROP_ITEM_IMAGES[self.kind]

    @property
    def display_height(self):
        if self.kind in config.THROWN_WEAPON_SPRITES:
            return config.THROWN_WEAPON_SPRITES[self.kind].rest_height
        if self.kind in config.FIREARM_DROP_SPRITES:
            _, clip, scale = config.FIREARM_DROP_SPRITES[self.kind]
            return clip[3] * scale
        return config.DROP_ITEM_BODY_HEIGHTS[self.kind] * config.DROP_ITEM_SCALE

    @property
    def frame(self):
        if self.kind in config.FIREARM_DROP_SPRITES or self.kind in config.THROWN_WEAPON_SPRITES:
            return 0
        return int(self.elapsed * config.DROP_ITEM_FPS + 1e-9) % self.frame_count

    def update(self, dt):
        self.elapsed += dt
        if not self.grounded:
            self.vy -= config.GRAVITY * dt
            self.jump_height = max(0.0, self.jump_height + self.vy * dt)
            if self.jump_height == 0:
                self.vy = 0.0


def spawn_drop_items(walkable, *, rng=None, upper_walkable=None):
    """Share the stage's initial item total across its available floors."""
    rng = random.Random() if rng is None else rng
    count = rng.randint(*config.DROP_ITEM_COUNT_RANGE)
    kinds = list(config.DROP_ITEM_IMAGES)
    areas = (walkable,) if upper_walkable is None else (walkable, upper_walkable)
    per_floor, remainder = divmod(count, len(areas))
    # Reserve both exits before N reveals them, including the arrow's full sway.
    exit_edge = (config.STAGE_EXIT_MARGIN + config.STAGE_ARROW_WIDTH / 2
                 + config.STAGE_ARROW_SWAY_AMPLITUDE + config.DROP_ITEM_EXIT_GAP)
    items = []
    for floor, area in enumerate(areas):
        floor_count = per_floor + (floor < remainder)
        choices = kinds + [rng.choice(kinds) for _ in range(floor_count - len(kinds))]
        rng.shuffle(choices)
        left, bottom, right, top = area.bounds
        left, right = max(left, exit_edge), min(right, config.WORLD_WIDTH - exit_edge)
        # Separate strips on each floor keep weapons from piling up.
        strip_width = (right - left) / floor_count
        for index, kind in enumerate(choices):
            x = rng.uniform(left + index * strip_width + config.DROP_ITEM_HALF_WIDTH,
                            left + (index + 1) * strip_width - config.DROP_ITEM_HALF_WIDTH)
            ground_y = rng.uniform(bottom + config.DROP_ITEM_SHADOW_HALF_DEPTH,
                                   top - config.DROP_ITEM_HEIGHT)
            items.append(DropItem(kind, x, ground_y, rng.choice((-1, 1)),
                                  rng.random() * config.DROP_ITEM_FRAMES / config.DROP_ITEM_FPS,
                                  floor=floor))
    return items
