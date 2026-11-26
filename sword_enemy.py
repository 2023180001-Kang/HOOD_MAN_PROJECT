"""Sword fighter that slashes on midair contact or strikes on landing."""

import config
from enemy02 import Enemy02


class SwordEnemy(Enemy02):
    image_name = config.SWORD_ENEMY_IMAGE
    attacks = config.SWORD_ENEMY_ATTACKS
    basic_attack = "slash"
    airborne_frames = (2, 3, 4, 5)
    boundary_padding = 96.0  # Includes the blade at full extension.
    formation_ground_min = None
