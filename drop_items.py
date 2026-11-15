"""Stage-local floor props with independent random layouts and looping sprites."""

from dataclasses import dataclass
import random

import config


@dataclass
class DropItem:
    kind: str
    x: float
    ground_y: float
    facing: int = 1
    elapsed: float = 0.0

    @property
    def image_name(self):
        return config.DROP_ITEM_IMAGES[self.kind]

    @property
    def frame(self):
        return int(self.elapsed * config.DROP_ITEM_FPS + 1e-9) % config.DROP_ITEM_FRAMES

    def update(self, dt):
        self.elapsed += dt


def spawn_drop_items(walkable, *, rng=None):
    rng = random.Random() if rng is None else rng
    count = rng.randint(*config.DROP_ITEM_COUNT_RANGE)
    kinds = list(config.DROP_ITEM_IMAGES)
    choices = kinds + [rng.choice(kinds) for _ in range(count - len(kinds))]
    rng.shuffle(choices)
    left, bottom, right, top = walkable.bounds
    # Reserve both exits before N reveals them, including the arrow's full sway.
    exit_edge = (config.STAGE_EXIT_MARGIN + config.STAGE_ARROW_WIDTH / 2
                 + config.STAGE_ARROW_SWAY_AMPLITUDE + config.DROP_ITEM_EXIT_GAP)
    left, right = max(left, exit_edge), min(right, config.WORLD_WIDTH - exit_edge)
    # Randomize within separate strips so the visible weapons cannot pile up.
    strip_width = (right - left) / count
    items = []
    for index, kind in enumerate(choices):
        x = rng.uniform(left + index * strip_width + config.DROP_ITEM_HALF_WIDTH,
                        left + (index + 1) * strip_width - config.DROP_ITEM_HALF_WIDTH)
        ground_y = rng.uniform(bottom + config.DROP_ITEM_SHADOW_HALF_DEPTH,
                               top - config.DROP_ITEM_HEIGHT)
        items.append(DropItem(kind, x, ground_y, rng.choice((-1, 1)),
                              rng.random() * config.DROP_ITEM_FRAMES / config.DROP_ITEM_FPS))
    return items
