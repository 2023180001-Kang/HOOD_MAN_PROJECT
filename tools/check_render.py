"""Capture actual SDL render targets for visual verification (needs Pillow)."""

import ctypes
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d
from pico2d import pico2d as backend
from sdl2 import SDL_PIXELFORMAT_RGBA32, SDL_RenderReadPixels

import config
from game import Game
from enemy import Enemy
from world import World


def capture(game, name):
    game.draw(present=False)
    pixels = (ctypes.c_ubyte * (config.SCREEN_WIDTH * config.SCREEN_HEIGHT * 4))()
    result = SDL_RenderReadPixels(backend.renderer, None, SDL_PIXELFORMAT_RGBA32,
                                  pixels, config.SCREEN_WIDTH * 4)
    if result != 0:
        raise RuntimeError("SDL_RenderReadPixels failed")
    image = Image.frombytes("RGBA", (config.SCREEN_WIDTH, config.SCREEN_HEIGHT), bytes(pixels))
    directory = ROOT / "artifacts"
    directory.mkdir(exist_ok=True)
    image.save(directory / f"{name}.png")
    pico2d.update_canvas()
    print(f"Captured artifacts/{name}.png")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.world = World(spawn_schedule=())
        capture(game, "idle")
        game.world.controls.press("right")
        game.world.controls.press("left_shift")
        for _ in range(30):
            game.update(1 / 60)
        capture(game, "run")
        game.world.controls.press("jump")
        for _ in range(12):
            game.update(1 / 60)
        capture(game, "jump")
        game.world = World(spawn_schedule=())
        game.world.enemies = [Enemy(config.START_X - 180),
                              Enemy(config.START_X + 180, facing=-1)]
        for _ in range(30):
            game.update(1 / 60)
        capture(game, "enemies")
        game.world.enemies = [Enemy(config.START_X - 80)]
        for _ in range(26):
            game.update(1 / 60)
        capture(game, "hit")
        game.world.enemies.clear()
        game.world.camera.update(1, game.world.player.x)
        for hp in (500, 480, 250, 0):
            game.world.player.hp = hp
            capture(game, f"hp_{hp}")
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
