"""Factory-exterior axe enemy using the replacement six-row sprite sheet."""

import config
from enemy import Enemy


class AxeEnemy(Enemy):
    max_hp = config.AXE_ENEMY_MAX_HP
    image_name = config.AXE_ENEMY_IMAGE
    animations = config.AXE_ENEMY_ANIMATIONS

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

    def hit_by_car(self, direction):
        if not super().hit_by_car(direction):
            return False
        self.animation.definitions["DEAD"] = self.animations["CAR_HIT"]
        return True
