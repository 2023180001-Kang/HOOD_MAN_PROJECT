"""Time-based sprite playback, with no dependency on a graphics context."""


class Animation:
    def __init__(self, definitions, state="IDLE"):
        self.definitions = definitions
        self.state = state
        self.elapsed = 0.0

    def set_state(self, state):
        if state != self.state:
            self.state = state
            self.elapsed = 0.0

    def update(self, dt):
        self.elapsed += dt

    @property
    def row(self):
        return self.definitions[self.state][0]

    @property
    def frame(self):
        _, fps, loop = self.definitions[self.state]
        index = int(self.elapsed * fps)
        return index % 8 if loop else min(index, 7)

    @property
    def finished(self):
        _, fps, loop = self.definitions[self.state]
        return not loop and self.elapsed >= 8 / fps
