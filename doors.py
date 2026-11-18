"""Stage-local decorative doors with authored opening and closing sprite rows."""

import config
from animation import Animation


class StageDoor:
    def __init__(self, kind, source_rect):
        self.kind = kind
        self.source_rect = source_rect
        self.target_open = False
        self.moving = False
        self.animation = Animation({
            "OPENING": (1, config.DOOR_FPS, False),
            "CLOSING": (2, config.DOOR_FPS, False),
        }, "OPENING")

    @property
    def image_name(self):
        return config.DOOR_IMAGES[self.kind]

    @property
    def state(self):
        if self.moving:
            return "OPENING" if self.target_open else "CLOSING"
        return "OPEN" if self.target_open else "CLOSED"

    @property
    def row(self):
        return 1 if self.state == "CLOSED" else self.animation.row

    @property
    def frame(self):
        # Return to the same fully closed pose used at game start.
        return 0 if self.state == "CLOSED" else self.animation.frame

    def toggle(self):
        # A fresh press during motion reverses from the matching visible pose,
        # rather than jumping to a fully open/closed start frame.
        elapsed = ((config.DOOR_FRAMES - 1 - self.frame) / config.DOOR_FPS
                   if self.moving else 0.0)
        self.target_open = not self.target_open
        self.animation.set_state("OPENING" if self.target_open else "CLOSING")
        self.animation.elapsed = elapsed
        self.moving = True

    def update(self, dt):
        if not self.moving:
            return
        duration = config.DOOR_FRAMES / config.DOOR_FPS
        self.animation.elapsed = min(duration, self.animation.elapsed + max(0.0, dt))
        if self.animation.finished:
            self.moving = False
