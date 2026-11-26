"""Sword fighter with a grounded slash and a leaping landing strike."""

import config
from enemy02 import Enemy02


class SwordEnemy(Enemy02):
    image_name = config.SWORD_ENEMY_IMAGE
    attacks = config.SWORD_ENEMY_ATTACKS
    basic_attack = "slash"
    airborne_frames = (2, 3, 4, 5)
    strikes_on_air_contact = False
    boundary_padding = 96.0  # Includes the blade at full extension.
    formation_ground_min = None
