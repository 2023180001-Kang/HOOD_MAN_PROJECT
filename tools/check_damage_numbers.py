"""Verify short damage text near enemy HP bars through SDL input and pixels."""

from pathlib import Path
import sys
from unittest.mock import patch

from PIL import ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from combat import MOVES
from enemy import Enemy
from game import Game
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, tick
from world import World


def attack(game, key, hp=200, side=1):
    game.world = World()
    enemy = Enemy(config.START_X + side * 80, -side)
    enemy.hp = hp
    enemy.cooldown = 100
    game.world.enemies = [enemy]
    direction = pico2d.SDLK_LEFT if side < 0 else pico2d.SDLK_RIGHT
    push_key(direction)
    push_key(getattr(pico2d, f"SDLK_{key}"))
    tick(game, 11)
    push_key(direction, down=False)
    push_key(getattr(pico2d, f"SDLK_{key}"), down=False)
    game.handle_events()
    # Isolate text motion from the already verified hit-camera shake.
    game.world.camera.update(config.SHAKE_DURATION, game.world.player.x)
    return enemy


def capture_number(game, name):
    number = game.world.damage_numbers[0]
    font = game.assets.damage_font
    with patch.object(font, "draw", wraps=font.draw) as draw:
        image = capture(game, name)
        assert any(call.args[2] == f"-{number.damage}" for call in draw.call_args_list)
    with patch.object(font, "draw"):
        clean = render_image(game)
    bounds = ImageChops.difference(image.convert("RGB"), clean.convert("RGB")).getbbox()
    assert bounds is not None, "Damage text must affect real rendered pixels"
    x = number.x - game.world.camera.render_x
    y = config.SCREEN_HEIGHT - number.display_y + game.world.camera.render_y
    assert x - 24 <= bounds[0] < bounds[2] <= x + 24, bounds
    assert y - 18 <= bounds[1] < bounds[3] <= y + 18, bounds
    assert number.y > game.world.enemies[0].body.top
    return bounds


def check_damage_numbers(game):
    font = game.assets.damage_font
    assert font is not None
    cases = [(key, 200) for key in "asdf"] + [("f", 10)]
    for index, (key, hp) in enumerate(cases):
        enemy = attack(game, key, hp, side=-1 if index % 2 else 1)
        expected = min(hp, MOVES[f"combat_{key}"].damage)
        assert enemy.hp == hp - expected
        assert [number.damage for number in game.world.damage_numbers] == [expected]
        label = key if hp == 200 else "lethal"
        bounds = capture_number(game, f"damage_number_{label}")
        if key == "a":
            tick(game, 6)
            later = capture_number(game, "damage_number_rising")
            assert later[1] <= bounds[1] - 3, (bounds, later)
        tick(game, 3)
        assert len(game.world.damage_numbers) == 1  # No repeat from active frames.
        tick(game, 30)
        assert not game.world.damage_numbers
        with patch.object(font, "draw", wraps=font.draw) as draw:
            render_image(game)
            assert not draw.called
    attack(game, "s")
    assert game.world.damage_numbers
    push_key(pico2d.SDLK_F5)
    tick(game)
    assert all(not stage.damage_numbers for stage in game.world.stages)
    assert game.assets.damage_font is font
    push_key(pico2d.SDLK_F5, down=False)
    game.handle_events()
    capture(game, "damage_number_restarted")
    print("PASS: SDL four basic attacks show exact HP loss near enemy bars; text rises, "
          "does not repeat per swing, expires quickly, survives the lethal hit, "
          "and F5 clears numbers while reusing the font.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_damage_numbers(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
