"""City dual-club enemy with one committed random attack per swing."""

from functools import lru_cache
import json

import config
from enemy import Enemy


@lru_cache(maxsize=1)
def jump_heights():
    with (config.ROOT / "assets" / "frames.json").open(encoding="utf-8") as file:
        row = config.ENEMY02_ATTACKS["slam"][0] - 1
        return tuple(frame["jump_height"] for frame in json.load(file)[config.ENEMY02_IMAGE][row])


class Enemy02(Enemy):
    image_name = config.ENEMY02_IMAGE
    animations = config.ENEMY02_ANIMATIONS
    boundary_padding = config.ENEMY02_BOUNDARY_PADDING

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attack_kind = "clubs"
        self.vy = 0.0
        # The supplied sheet has no separate counter/car-hit art. Keep this
        # enemy's identity using its own hit/fall rows for those reactions.
        for state in self.animation.definitions:
            if state.startswith(("SUBDUED_", "HELD_")):
                row = 7 if state.endswith(("_J", "_L")) else 6
                _, fps, loop = self.animation.definitions[state]
                self.animation.definitions[state] = (row, fps, loop)

    @property
    def sprite_image(self):
        return self.image_name

    @property
    def attack_damage(self):
        return config.ENEMY02_ATTACKS[self.attack_kind][1]

    @property
    def attack_active_frames(self):
        return config.ENEMY02_ATTACKS[self.attack_kind][2]

    def start_attack(self):
        self.attack_kind = self.rng.choice(tuple(config.ENEMY02_ATTACKS))
        row, _, _ = config.ENEMY02_ATTACKS[self.attack_kind]
        self.animation.definitions["ATTACK"] = (row, self.attack_fps, False)
        self.jump_height = self.vy = 0.0
        super().start_attack()

    def _update_ai(self, dt, player):
        super()._update_ai(dt, player)
        if self.car_hit or self.counter_move is not None:
            return
        if self.state == "ATTACK":
            self.jump_height = (jump_heights()[self.animation.frame] * config.SPRITE_SCALE
                                if self.attack_kind == "slam" else 0.0)
            self.vy = 0.0
        elif self.jump_height > 0:
            # An interrupted aerial attack still falls during HIT/knockback/death.
            self.vy -= config.GRAVITY * dt
            self.jump_height = max(0.0, self.jump_height + self.vy * dt)
            if self.jump_height == 0:
                self.vy = 0.0

    def finish_counter(self):
        if self.counter_move is None:
            return
        super().finish_counter()
        if not self.alive:
            self.counter_death = None
            self.animation.definitions["DEAD"] = self.animations["DEAD"]
            self.animation.elapsed = 8 / self.animation.definitions["DEAD"][1]

    def hit_by_car(self, direction):
        if not super().hit_by_car(direction):
            return False
        self.animation.definitions["DEAD"] = (7, config.CAR_HIT_FPS, False)
        return True
