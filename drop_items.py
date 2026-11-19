"""Stage-local weapons, death-only props and gravity-driven falling items."""

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

    @property
    def grounded(self):
        return self.jump_height <= 0 and self.vy == 0

    @property
    def image_name(self):
        return config.DROP_ITEM_IMAGES[self.kind]

    @property
    def frame(self):
        return int(self.elapsed * config.DROP_ITEM_FPS + 1e-9) % self.frame_count

    def update(self, dt):
        self.elapsed += dt
        if not self.grounded:
            self.vy -= config.GRAVITY * dt
            self.jump_height = max(0.0, self.jump_height + self.vy * dt)
            if self.jump_height == 0:
                self.vy = 0.0


class MetalClubDrop(DropItem):
    """A single-club enemy's visual death drop, with no pickup/equipment path."""

    collectible = False
    frame_count = config.METAL_CLUB_ITEM_FRAMES

    def __init__(self, x, ground_y, facing=1, *, jump_height=0.0, floor=0):
        super().__init__("metal_club", x, ground_y, facing,
                         jump_height=jump_height, floor=floor)

    @property
    def image_name(self):
        return config.METAL_CLUB_ITEM_IMAGE

    @property
    def frame(self):
        # The source poses wobble; only animate them while the club is falling.
        return 0 if self.grounded else super().frame


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
