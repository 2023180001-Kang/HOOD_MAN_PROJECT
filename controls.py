"""Held keys and edge-triggered presses, independent of SDL key codes."""


class Controls:
    def __init__(self):
        self.held = set()
        self.pressed = set()

    def press(self, key):
        if key not in self.held:
            self.pressed.add(key)
        self.held.add(key)

    def release(self, key):
        self.held.discard(key)

    def take_press(self, key):
        if key in self.pressed:
            self.pressed.remove(key)
            return True
        return False

    def take_first_press(self, keys):
        selected = None
        for key in keys:
            if self.take_press(key) and selected is None:
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
    def running(self):
        return bool(self.held & {"left_shift", "right_shift"})
