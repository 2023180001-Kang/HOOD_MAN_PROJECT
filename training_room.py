"""Single-screen practice room with weapons placed on the supplied table."""

import config
from drop_items import DropItem
from stage import Stage
from walkable import WalkableArea


class TrainingRoom(Stage):
    image_name = config.TRAINING_ROOM_IMAGE
    width = config.SCREEN_WIDTH
    camera_y_bounds = (0, 0)
    arrow_sides = ()

    def __init__(self):
        approach = config.TRAINING_TABLE_APPROACH_Y
        items = [DropItem(kind, x, approach, support_height=config.TRAINING_TABLE_SURFACE_Y - approach)
                 for kind, x in config.TRAINING_TABLE_ITEMS]
        super().__init__(walkable=WalkableArea.rectangle(*config.TRAINING_FLOOR), drop_items=items)
