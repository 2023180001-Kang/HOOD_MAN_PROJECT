"""Screen-fixed menu navigation, item dragging and buttons, without SDL."""

from dataclasses import dataclass

import config
from animation import Animation


MENU_BACKGROUNDS = {
    "main": config.MAIN_MENU_IMAGE,
    "stage_progress": config.STAGE_PROGRESS_IMAGE,
    "backpack": config.BAG_UI_IMAGE,
}


@dataclass(frozen=True)
class MenuButton:
    action: str
    image_name: str
    x: float
    y: float
    width: float
    height: float

    def contains(self, x, y):
        return (self.x - self.width / 2 <= x < self.x + self.width / 2
                and self.y - self.height / 2 <= y < self.y + self.height / 2)


class MainMenu:
    def __init__(self):
        width, height = config.MAIN_MENU_BUTTON_SIZE
        x = config.SCREEN_WIDTH - config.MAIN_MENU_RIGHT_MARGIN - width / 2
        top = config.SCREEN_HEIGHT - config.MAIN_MENU_TOP_MARGIN
        self.main_buttons = tuple(
            MenuButton(action, image, x,
                       top - height / 2 - index * (height + config.MAIN_MENU_BUTTON_GAP),
                       width, height)
            for index, (action, image) in enumerate(config.MAIN_MENU_BUTTONS)
        )
        width, height = config.BAG_BACK_BUTTON_SIZE
        self.bag_back_button = MenuButton(
            "back", config.BAG_BUTTON_IMAGE,
            config.BAG_BACK_BUTTON_LEFT + width / 2,
            config.SCREEN_HEIGHT - config.BAG_BACK_BUTTON_TOP - height / 2,
            width, height,
        )
        self.screen = "main"
        self.bag_items = list(config.BAG_ITEM_SPECS)
        self.equipped_weapon = None
        self.cancel_drag()
        self.bag_player_animation = Animation({"IDLE": config.PLAYER_ANIMATIONS["IDLE"]})
        self.hovered_button = None

    @property
    def bag_open(self):
        return self.screen == "backpack"

    @property
    def buttons(self):
        return self.main_buttons if self.screen == "main" else (self.bag_back_button,)

    def show_main(self):
        self.screen = "main"
        self.cancel_drag()
        self.clear_hover()

    def move_pointer(self, x, y):
        if self.dragged_slot is not None:
            self.drag_position = (x + self.drag_offset[0], y + self.drag_offset[1])
            self.clear_hover()
            return
        self.hovered_button = next(
            (button for button in self.buttons if button.contains(x, y)), None,
        )

    def press_pointer(self, x, y):
        if self.dragged_slot is not None:
            return False
        slot = self.bag_slot_at(x, y)
        equipped_rect = config.BAG_EQUIPPED_RECTS.get(self.equipped_weapon)
        if self.bag_open and equipped_rect and self.rect_contains(equipped_rect, x, y):
            slot = next(index for index, item in enumerate(self.bag_items)
                        if item[0] == self.equipped_weapon)
            self.dragged_from_player = True
            left, top, right, bottom = equipped_rect
            center_x, center_y = (left + right) / 2, config.SCREEN_HEIGHT - (top + bottom) / 2
        elif slot is None:
            return self.click(x, y)
        else:
            center_x, center_y = self.bag_slot_center(slot)
        self.dragged_slot = slot
        # Keep the grabbed point under the mouse instead of snapping to center.
        self.drag_offset = (center_x - x, center_y - y)
        self.move_pointer(x, y)
        return False

    def release_pointer(self, x, y):
        if self.dragged_slot is None:
            return
        target = self.bag_slot_at(x, y)
        weapon = self.bag_items[self.dragged_slot][0]
        if self.dragged_from_player:
            if target is not None:
                source = self.dragged_slot
                self.bag_items[source], self.bag_items[target] = (
                    self.bag_items[target], self.bag_items[source],
                )
                self.equipped_weapon = None
                self.bag_player_animation.elapsed = 0.0
        elif weapon in config.PLAYER_EQUIPPED_SHEETS and self.bag_player_contains(x, y):
            self.equipped_weapon = weapon
            self.bag_player_animation.elapsed = 0.0
        elif target is not None:
            source = self.dragged_slot
            self.bag_items[source], self.bag_items[target] = (
                self.bag_items[target], self.bag_items[source],
            )
        self.cancel_drag()
        self.move_pointer(x, y)

    def cancel_drag(self):
        # The layout is committed only on a valid drop, so cancellation is lossless.
        self.dragged_slot = None
        self.dragged_from_player = False
        self.drag_position = None
        self.drag_offset = (0.0, 0.0)

    def bag_slot_at(self, x, y):
        if self.bag_open:
            for slot, (left, top, right, bottom) in enumerate(config.BAG_ITEM_SLOT_RECTS):
                if (left <= x < right
                        and config.SCREEN_HEIGHT - bottom <= y < config.SCREEN_HEIGHT - top):
                    return slot
        return None

    @staticmethod
    def bag_player_contains(x, y):
        return MainMenu.rect_contains(config.BAG_PLAYER_RECT, x, y)

    @staticmethod
    def rect_contains(rect, x, y):
        left, top, right, bottom = rect
        return (left <= x < right
                and config.SCREEN_HEIGHT - bottom <= y < config.SCREEN_HEIGHT - top)

    @staticmethod
    def bag_slot_center(slot):
        left, top, right, bottom = config.BAG_ITEM_SLOT_RECTS[slot]
        return (left + right) / 2, config.SCREEN_HEIGHT - (top + bottom) / 2

    def clear_hover(self):
        self.hovered_button = None

    def update(self, dt):
        # Only this UI clock runs in the bag; the gameplay world stays paused.
        if self.bag_open:
            self.bag_player_animation.update(max(0.0, dt))

    def click(self, x, y):
        """Navigate locally; only a game-start click requests gameplay."""
        self.move_pointer(x, y)
        if self.hovered_button is None:
            return False
        action = self.hovered_button.action
        if action == "game_start":
            return True
        if action in ("backpack", "stage_progress"):
            self.screen = action
            self.cancel_drag()
            if self.bag_open:
                self.bag_player_animation.elapsed = 0.0
            self.clear_hover()
        elif action == "back":
            self.show_main()
        return False

    def draw(self, assets):
        background = MENU_BACKGROUNDS[self.screen]
        assets.images[background].draw(
            config.SCREEN_WIDTH / 2, config.SCREEN_HEIGHT / 2,
            config.SCREEN_WIDTH, config.SCREEN_HEIGHT,
        )
        if self.bag_open:
            self.draw_bag_player(assets)
            self.draw_bag_items(assets)
        elif self.screen == "stage_progress":
            lock = assets.images[config.STAGE_LOCK_IMAGE]
            for x in config.STAGE_LOCK_CENTERS_X:
                lock.draw(x, config.STAGE_LOCK_Y)
        for button in self.buttons:
            image = assets.images[button.image_name]
            frame_width = image.w // 2
            # Left: original black button. Right: original gray hover button.
            left = frame_width if button is self.hovered_button else 0
            image.clip_draw(left, 0, frame_width, image.h,
                            button.x, button.y, button.width, button.height)

    def draw_bag_player(self, assets):
        animation = self.bag_player_animation
        weapon = None if self.dragged_from_player else self.equipped_weapon
        image = config.PLAYER_EQUIPPED_SHEETS.get(weapon, config.PLAYER_IMAGE)
        assets.draw_sprite(image, animation.row, animation.frame,
                           config.BAG_PLAYER_X, config.BAG_PLAYER_FEET_Y,
                           scale=config.BAG_PLAYER_SCALE)

    def draw_bag_items(self, assets):
        for slot in range(len(self.bag_items)):
            if slot != self.dragged_slot:
                self.draw_bag_item(assets, slot)
        if self.dragged_slot is not None:
            # Draw the held icon once, above all stationary items.
            self.draw_bag_item(assets, self.dragged_slot, self.drag_position)

    def draw_bag_item(self, assets, slot, position=None):
        padding = config.BAG_ITEM_SLOT_PADDING
        _, image_name, clip = self.bag_items[slot]
        left, top, right, bottom = config.BAG_ITEM_SLOT_RECTS[slot]
        width, height = clip[2:]
        scale = min((right - left - padding * 2) / width,
                    (bottom - top - padding * 2) / height)
        x, y = self.bag_slot_center(slot) if position is None else position
        assets.images[image_name].clip_draw(*clip, x, y, width * scale, height * scale)
