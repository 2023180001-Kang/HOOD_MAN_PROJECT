"""Independent street scenes and world-space backgrounds/exit markers."""

from math import ceil, floor, sin, tau

import config
from drop_items import spawn_drop_items
from enemy import Enemy
from enemy02 import Enemy02
from spawn_manager import SpawnManager
from walkable import WalkableArea, for_stage


class Stage:
    def __init__(self, index=0, *, rng=None, attack_sequence=None, traffic_rng=None, item_rng=None):
        self.index = index
        self.arrows_visible = False
        self.enemies = []
        self.effects = []
        self.afterimages = []
        self.damage_numbers = []
        self.walkable = for_stage(index)
        drop_bounds = config.STAGE_DROP_ITEM_SPAWN_BOUNDS.get(self.image_name)
        self.drop_spawn_area = (WalkableArea.rectangle(*drop_bounds) if drop_bounds is not None
                                else self.walkable)
        self.drop_items = spawn_drop_items(self.drop_spawn_area, rng=item_rng)
        spawn_bounds = config.STAGE_ENEMY_SPAWN_BOUNDS.get(self.image_name)
        self.spawn_area = (WalkableArea.rectangle(*spawn_bounds) if spawn_bounds is not None
                           else self.walkable)
        self.spawner = SpawnManager(rng=rng, walkable=self.walkable, spawn_area=self.spawn_area,
                                    attack_sequence=attack_sequence,
                                    enemy_type=Enemy02 if self.image_name in config.ENEMY02_STAGE_IMAGES
                                    else Enemy)
        self.traffic = None  # Road traffic is retired; no stage creates cars.

    def constrain_actor(self, actor):
        actor.walkable = self.walkable
        half_width = (actor.body.right - actor.body.left) / 2
        self.walkable.constrain(actor, half_width)

    @property
    def image_name(self):
        return config.STAGE_IMAGES[self.index]

    @property
    def arrow_sides(self):
        if not self.arrows_visible:
            return ()
        return (1,) if self.index == 0 else (-1, 1)

    def destination(self, side):
        target = self.index + side
        if side in self.arrow_sides and 0 <= target < len(config.STAGE_IMAGES):
            return target
        return None

    def draw(self, assets, camera_x=0.0, camera_y=0.0, *, elapsed=0.0):
        # Keep the supplied character/building scale instead of enlarging the
        # artwork to the full world width. Mirrored tiles join without a cut.
        image = assets.images[self.image_name]
        scale = config.STAGE_SCALE
        width = image.w * scale
        height = image.h * scale
        anchor = config.STAGE_GROUND_ANCHORS.get(self.image_name, config.STAGE_GROUND_Y)
        bottom = config.GROUND_Y - anchor * scale - camera_y
        # Clamp vertical shake at image edges so backgrounds never expose a
        # blank strip above or below the viewport.
        bottom = min(0.0, max(config.SCREEN_HEIGHT - height, bottom))
        first = max(0, floor(camera_x / width))
        last = min(ceil(config.WORLD_WIDTH / width),
                   ceil((camera_x + config.SCREEN_WIDTH) / width))
        for index in range(first, last):
            image.composite_draw(
                0, "h" if index % 2 else "",
                index * width + width / 2 - camera_x,
                bottom + height / 2, width, height,
            )
        # Flat floor props stay underneath characters, vehicles and exit markers.
        for item in self.drop_items:
            if item.grounded:
                assets.draw_drop_item(item, camera_x, camera_y)
        sway = (sin(tau * elapsed / config.STAGE_ARROW_SWAY_PERIOD)
                * config.STAGE_ARROW_SWAY_AMPLITUDE)
        for side in self.arrow_sides:
            arrow = assets.images[config.STAGE_ARROW_IMAGES[side]]
            x = (config.STAGE_EXIT_MARGIN if side < 0 else
                 config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN)
            arrow.draw(x + side * sway - camera_x, config.STAGE_ARROW_Y - camera_y,
                       config.STAGE_ARROW_WIDTH, config.STAGE_ARROW_WIDTH * arrow.h / arrow.w)
