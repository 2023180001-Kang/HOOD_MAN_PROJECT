"""Screen-fixed main menu/bag navigation and two-frame buttons, without SDL."""

from dataclasses import dataclass

import config


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
        self.bag_open = False
        self.hovered_button = None

    @property
    def buttons(self):
        return (self.bag_back_button,) if self.bag_open else self.main_buttons

    def show_main(self):
        self.bag_open = False
        self.clear_hover()

    def move_pointer(self, x, y):
        self.hovered_button = next(
            (button for button in self.buttons if button.contains(x, y)), None,
        )

    def clear_hover(self):
        self.hovered_button = None

    def click(self, x, y):
        """Navigate locally; only a game-start click requests gameplay."""
        self.move_pointer(x, y)
        if self.hovered_button is None:
            return False
        action = self.hovered_button.action
        if action == "game_start":
            return True
        if action == "backpack":
            self.bag_open = True
            self.clear_hover()
        elif action == "back":
            self.show_main()
        return False

    def draw(self, assets):
        background = config.BAG_UI_IMAGE if self.bag_open else config.MAIN_MENU_IMAGE
        assets.images[background].draw(
            config.SCREEN_WIDTH / 2, config.SCREEN_HEIGHT / 2,
            config.SCREEN_WIDTH, config.SCREEN_HEIGHT,
        )
        for button in self.buttons:
            image = assets.images[button.image_name]
            frame_width = image.w // 2
            # Left: original black button. Right: original gray hover button.
            left = frame_width if button is self.hovered_button else 0
            image.clip_draw(left, 0, frame_width, image.h,
                            button.x, button.y, button.width, button.height)
