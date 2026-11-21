"""Loading-dock axe enemy; the sheet's last (stun) row stays unused."""

import config
from enemy import Enemy


class AxeEnemy(Enemy):
    death_drop_kind = None  # An axe wielder must not drop the street thug's club.
    max_hp = config.AXE_ENEMY_MAX_HP
    image_name = config.AXE_ENEMY_IMAGE
    animations = config.AXE_ENEMY_ANIMATIONS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # There is no axe-specific counter sheet. Reuse its own flinch/fall,
        # never the other enemy's appearance or the reserved row-7 stun.
        for state, (_, fps, loop) in self.animation.definitions.items():
            if state.startswith(("SUBDUED_", "HELD_")):
                row = self.animations["DYING" if state.endswith(("_J", "_L")) else "HIT"][0]
                self.animation.definitions[state] = (row, fps, loop)

    @property
    def sprite_image(self):
        return self.image_name

    @property
    def attack_damage(self):
        return config.AXE_ENEMY_DAMAGE

    def take_strong_hit(self, move, direction):
        if not super().take_strong_hit(move, direction):
            return False
        self.animation.definitions["STRONG_HIT"] = (
            self.animations["HIT"][0], config.STRONG_HIT_FPS, False)
        return True

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
        self.animation.definitions["DEAD"] = self.animations["CAR_HIT"]
        return True
