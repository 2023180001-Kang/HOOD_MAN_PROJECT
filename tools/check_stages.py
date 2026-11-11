"""Verify stage markers, travel and state continuity through actual SDL input."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from game import Game
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, tick
from world import World


def view_edge(game, side):
    game.world.player.x = (config.STAGE_ENTRY_MARGIN if side < 0 else
                           config.WORLD_WIDTH - config.STAGE_ENTRY_MARGIN)
    game.world.camera.update(0, game.world.player.x)


def check_markers(game):
    textures = dict(game.assets.images)
    backgrounds = []
    for index in range(2):
        game.world = World()
        game.world.stage_index = index
        baseline = {}
        for side in (-1, 1):
            view_edge(game, side)
            baseline[side] = render_image(game)
        backgrounds.append(baseline[1])
        push_key(pico2d.SDLK_n)
        tick(game)
        assert game.world.stage.arrow_sides == ((1,) if index == 0 else (-1, 1))
        for side in (-1, 1):
            view_edge(game, side)
            image = capture(game, f"stage_{index + 1}_{'left' if side < 0 else 'right'}_markers")
            region = (0, 340, 190, 470) if side < 0 else (1090, 340, 1280, 470)
            before = baseline[side].crop(region)
            after = image.crop(region)
            if index == 0 and side < 0:
                assert after.tobytes() == before.tobytes()
            else:
                gold = lambda pixels: sum(r > 120 and g > 80 and r > b * 1.5
                                          for r, g, b, _ in pixels)
                assert gold(after.get_flattened_data()) > gold(before.get_flattened_data()) + 50
        push_key(pico2d.SDLK_n, repeat=True)
        tick(game)
        assert game.world.stage.arrows_visible
        push_key(pico2d.SDLK_n, down=False)
        game.handle_events()
    assert backgrounds[0].crop((250, 200, 1000, 500)).tobytes() != backgrounds[1].crop(
        (250, 200, 1000, 500)).tobytes()
    push_key(pico2d.SDLK_F5)
    tick(game)
    assert game.world.stage_index == 0
    assert all(not stage.arrows_visible for stage in game.world.stages)
    assert all(game.assets.images[name] is image for name, image in textures.items())
    push_key(pico2d.SDLK_F5, down=False)
    game.handle_events()
    print("PASS: SDL N reveals stage 1 right / stage 2 left+right yellow arrows; "
          "distinct backgrounds, unavailable next-stage marker and shared textures verified.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_markers(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
