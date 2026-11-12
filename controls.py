"""Held keys and edge-triggered presses, independent of SDL key codes."""

from math import hypot


class Controls:
    def __init__(self):
        self.held = set()
        self.pressed = {}  # Insertion order preserves the latest fresh input.

    def press(self, key):
        if key not in self.held:
            self.pressed.pop(key, None)
            self.pressed[key] = None
        self.held.add(key)

    def release(self, key):
        self.held.discard(key)

    def take_press(self, key):
        if key in self.pressed:
            del self.pressed[key]
            return True
        return False

    def take_latest_press(self, keys):
        """Consume matching presses and select the newest, without buffering."""
        selected = None
        for key in tuple(self.pressed):
            if key in keys:
                del self.pressed[key]
                selected = key
        return selected

    def reset_for_restart(self):
        # Keep restart latched until KEYUP to avoid repeated resets while held.
        self.held.intersection_update({"restart"})
        self.pressed.clear()

    @property
    def direction(self):
        return int("right" in self.held) - int("left" in self.held)

    @property
    def depth_direction(self):
        return int("up" in self.held) - int("down" in self.held)

    @property
    def movement(self):
        x, y = self.direction, self.depth_direction
        length = hypot(x, y)
        return (x / length, y / length) if length else (0.0, 0.0)

    @property
    def moving(self):
        return bool(self.direction or self.depth_direction)

    @property
    def running(self):
        return bool(self.held & {"left_shift", "right_shift"})
