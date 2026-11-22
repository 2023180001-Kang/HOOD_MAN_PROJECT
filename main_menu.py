"""Screen-fixed menu layout and two-frame buttons, independent of SDL."""

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
        self.buttons = tuple(
            MenuButton(action, image, x,
                       top - height / 2 - index * (height + config.MAIN_MENU_BUTTON_GAP),
                       width, height)
            for index, (action, image) in enumerate(config.MAIN_MENU_BUTTONS)
        )
        self.hovered_button = None

    def move_pointer(self, x, y):
        self.hovered_button = next(
            (button for button in self.buttons if button.contains(x, y)), None,
        )

    def clear_hover(self):
        self.hovered_button = None

    def click(self, x, y):
        """Only the game-start button has an action; the others are placeholders."""
        self.move_pointer(x, y)
        return self.hovered_button is not None and self.hovered_button.action == "game_start"

    def draw(self, assets):
        assets.images[config.MAIN_MENU_IMAGE].draw(
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
