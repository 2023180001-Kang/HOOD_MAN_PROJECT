"""Held keys and edge-triggered presses, independent of SDL key codes."""

from math import hypot

import config


class Controls:
    def __init__(self):
        self.held = set()
        self.pressed = []

    def press(self, key):
        if key not in self.held:
            # Preserve the sequence for combos, escape, and selecting then summoning a target.
            ordered = (key.startswith(("combat_", "spawn_")) or key == "training_target"
                       or key in config.CROWD_ESCAPE_KEYS)
            if not ordered and key in self.pressed:
                self.pressed.remove(key)
            self.pressed.append(key)
        self.held.add(key)

    def release(self, key):
        self.held.discard(key)

    def take_press(self, key):
        if key in self.pressed:
            self.pressed[:] = [press for press in self.pressed if press != key]
            return True
        return False

    def take_presses(self, keys):
        matches = [key for key in self.pressed if key in keys]
        if matches:
            self.pressed[:] = [key for key in self.pressed if key not in keys]
        return matches

    def take_latest_press(self, keys):
        matches = self.take_presses(keys)
        return matches[-1] if matches else None

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
