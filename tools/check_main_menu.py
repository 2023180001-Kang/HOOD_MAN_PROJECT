"""Check actual SDL menu pixels, mouse input, launch/start/restart and quit."""

import ctypes
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d
from pico2d import pico2d as backend
from sdl2 import (
    SDL_BUTTON_LEFT, SDL_BUTTON_MIDDLE, SDL_BUTTON_RIGHT, SDL_Event,
    SDL_PIXELFORMAT_RGBA32, SDL_PushEvent, SDL_RenderReadPixels,
    SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST, SDL_WINDOWEVENT_LEAVE,
)

import config
from game import Game, KEYS
import main as entrypoint
from tools.check_render import capture
from tools.check_runtime import push_key, release, tick
from world import World


def push(event):
    if SDL_PushEvent(ctypes.byref(event)) != 1:
        raise RuntimeError("SDL_PushEvent failed")


def push_mouse(x, y, *, kind=pico2d.SDL_MOUSEMOTION, button=SDL_BUTTON_LEFT):
    event = SDL_Event()
    event.type = kind
    target = event.motion if kind == pico2d.SDL_MOUSEMOTION else event.button
    target.x, target.y = int(x), config.SCREEN_HEIGHT - 1 - int(y)
    if kind != pico2d.SDL_MOUSEMOTION:
        target.button = button
    push(event)


def push_click(button, mouse_button=SDL_BUTTON_LEFT):
    push_mouse(button.x, button.y, kind=pico2d.SDL_MOUSEBUTTONDOWN, button=mouse_button)
    push_mouse(button.x, button.y, kind=pico2d.SDL_MOUSEBUTTONUP, button=mouse_button)


def push_quit():
    event = SDL_Event()
    event.type = pico2d.SDL_QUIT
    push(event)


def menu_image(game, name=None):
    game.draw_main_menu(present=False)
    pixels = (ctypes.c_ubyte * (config.SCREEN_WIDTH * config.SCREEN_HEIGHT * 4))()
    if SDL_RenderReadPixels(backend.renderer, None, SDL_PIXELFORMAT_RGBA32,
                            pixels, config.SCREEN_WIDTH * 4) != 0:
        raise RuntimeError("SDL_RenderReadPixels failed")
    image = Image.frombytes("RGBA", (config.SCREEN_WIDTH, config.SCREEN_HEIGHT),
                            bytes(pixels)).convert("RGB")
    if name is not None:
        directory = ROOT / "artifacts"
        directory.mkdir(exist_ok=True)
        image.save(directory / f"{name}.png")
        print(f"Captured artifacts/{name}.png")
    pico2d.update_canvas()
    return image


def screen_box(button):
    left = int(button.x - button.width / 2)
    top = int(config.SCREEN_HEIGHT - button.y - button.height / 2)
    return left, top, left + int(button.width), top + int(button.height)


def check_pixels_and_placeholders(game):
    push_mouse(10, 10)
    assert not game.handle_events(menu_screen=True)
    normal = menu_image(game, "main_menu_default")
    with Image.open(ROOT / config.MAIN_MENU_IMAGE) as source:
        background = source.convert("RGB")
    left_half = (0, 0, config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT)
    assert ImageChops.difference(normal.crop(left_half), background.crop(left_half)).getbbox() is None
    world, player = game.world, game.world.player
    for button in game.menu.buttons:
        push_mouse(button.x, button.y)
        assert not game.handle_events(menu_screen=True)
        assert game.menu.hovered_button is button
        hovered = menu_image(game, f"main_menu_hover_{button.action}")
        changed = ImageChops.difference(normal, hovered).getbbox()
        left, top, right, bottom = screen_box(button)
        assert changed is not None
        assert left <= changed[0] < changed[2] <= right
        assert top <= changed[1] < changed[3] <= bottom
        # A blank lower-right patch of the original panel is gray, not just a
        # changed label/border. The original black panel must be visibly darker.
        sample = (left + 490, top + 75, left + 510, top + 85)
        assert (sum(ImageStat.Stat(hovered.crop(sample)).mean)
                > sum(ImageStat.Stat(normal.crop(sample)).mean) + 30)
        for other in game.menu.buttons:
            if other is not button:
                box = screen_box(other)
                assert ImageChops.difference(normal.crop(box), hovered.crop(box)).getbbox() is None
        if button.action != "game_start":
            push_click(button)
            assert not game.handle_events(menu_screen=True)
            assert game.world is world and world.player is player and world.elapsed == 0
            assert ImageChops.difference(hovered, menu_image(game)).getbbox() is None
        push_mouse(10, 10)
        assert not game.handle_events(menu_screen=True)
        assert ImageChops.difference(normal, menu_image(game)).getbbox() is None
    for kind in (SDL_WINDOWEVENT_LEAVE, SDL_WINDOWEVENT_FOCUS_LOST):
        push_mouse(game.menu.buttons[0].x, game.menu.buttons[0].y)
        assert not game.handle_events(menu_screen=True)
        event = SDL_Event()
        event.type, event.window.event = SDL_WINDOWEVENT, kind
        push(event)
        assert not game.handle_events(menu_screen=True)
        assert ImageChops.difference(normal, menu_image(game)).getbbox() is None
    assert config.ARCHIVED_TITLE_IMAGE not in game.assets.images
    print("PASS: original background/left half, four right-side black/gray buttons, "
          "only the hovered rectangle changes, leave/focus restore pixels, "
          "all three placeholder clicks have no action; archived title is not loaded.")


def check_wait_start_and_restart(game):
    game.world = World()
    world = game.world
    world.select_stage(11)
    world.player.hp = 200
    old_player = world.player
    textures = dict(game.assets.images)
    draw = game.draw_main_menu
    shown_at = None
    clicked = False

    def draw_and_inject(present=True):
        nonlocal shown_at, clicked
        draw(present)
        assert world.player is old_player and world.player.hp == 200
        assert world.stage_index == 11 and world.elapsed == 0
        assert not world.controls.held and not world.controls.pressed
        if shown_at is None:
            shown_at = perf_counter()
            for key in (*KEYS, pico2d.SDLK_RETURN):
                push_key(key)
                push_key(key, repeat=True)
                push_key(key, down=False)
            for button in game.menu.buttons[1:]:
                push_click(button)
            for mouse_button in (SDL_BUTTON_RIGHT, SDL_BUTTON_MIDDLE):
                push_click(game.menu.buttons[0], mouse_button)
            push_mouse(10, 10, kind=pico2d.SDL_MOUSEBUTTONDOWN)
            push_mouse(10, 10)
        elif perf_counter() - shown_at >= 2.2 and not clicked:
            push_key(pico2d.SDLK_RIGHT)
            push_key(pico2d.SDLK_9)
            push_click(game.menu.buttons[0])
            push_key(pico2d.SDLK_SPACE)
            push_key(pico2d.SDLK_u)
            push_key(pico2d.SDLK_F5)
            clicked = True
        assert perf_counter() - shown_at < 5, "Menu did not accept the start click"

    with patch.object(game, "draw_main_menu", side_effect=draw_and_inject), \
            patch.object(world, "update", wraps=world.update) as update, \
            patch.object(world, "reset", wraps=world.reset) as reset:
        game.show_main_menu()
    waited = perf_counter() - shown_at
    assert clicked and waited >= 2.2
    update.assert_not_called()
    reset.assert_called_once_with()
    assert world.player is not old_player
    assert (world.stage_index, world.stage.image_name, world.player.hp, world.player.state) == (
        0, config.STAGE_IMAGE, 500, "IDLE",
    )
    assert not world.stage_loading and world.elapsed == 0
    assert not world.controls.held and not world.controls.pressed
    assert all(not stage.enemies and len(stage.drop_items) == 15 for stage in world.stages)
    assert game.ui.details_visible
    assert all(game.assets.images[name] is image for name, image in textures.items())
    capture(game, "main_menu_started")
    push_key(pico2d.SDLK_SPACE, repeat=True)
    tick(game)
    assert world.player.jump_count == 0
    release(game, pico2d.SDLK_SPACE)
    push_key(pico2d.SDLK_SPACE)
    tick(game)
    assert world.player.jump_count == 1
    release(game, pico2d.SDLK_SPACE)
    push_key(pico2d.SDLK_F5)
    tick(game)
    assert (world.stage_index, world.player.hp, world.player.state) == (0, 500, "IDLE")
    player = world.player
    push_key(pico2d.SDLK_F5, repeat=True)
    tick(game)
    assert world.player is player
    release(game, pico2d.SDLK_F5)
    assert all(game.assets.images[name] is image for name, image in textures.items())
    print(f"PASS: menu stayed frozen for {waited:.3f}s despite keys/placeholders/invalid clicks; "
          "left click resets to stage 1/HP500/IDLE/no enemies/15 items per map, "
          "same-batch keys never replay, fresh Space jumps and F5 restarts without the menu.")


def check_menu_quit(game):
    draw = game.draw_main_menu
    for click_first in (False, True):
        game.running = True
        before = game.world.player

        def draw_and_quit(present=True):
            draw(present)
            if click_first:
                push_click(game.menu.buttons[0])
            push_quit()

        with patch.object(game, "draw_main_menu", side_effect=draw_and_quit), \
                patch.object(game.world, "reset", wraps=game.world.reset) as reset:
            game.show_main_menu()
        reset.assert_not_called()
        assert not game.running and game.world.player is before
        assert game.run(max_frames=3) == 0
    print("PASS: closing the menu exits normally with zero gameplay frames, "
          "including when a start click is queued before SDL_QUIT.")


def check_entrypoint():
    for scenario in ("start", "quit", "smoke"):
        seen = {}

        class LaunchGame(Game):
            def show_main_menu(self):
                seen["menu"] = True
                draw = self.draw_main_menu

                def draw_and_inject(present=True):
                    draw(present)
                    if scenario == "start":
                        push_click(self.menu.buttons[0])
                    else:
                        push_quit()

                with patch.object(self, "draw_main_menu", side_effect=draw_and_inject):
                    super().show_main_menu()

            def run(self, max_frames=None):
                assert bool(seen.get("menu")) == (scenario != "smoke")
                assert self.world.stage_index == 0 and self.world.elapsed == 0
                seen["frames"] = super().run(3 if max_frames is None else max_frames)
                return seen["frames"]

            def close(self):
                super().close()
                seen["closed"] = True

        args = ["main.py", "--smoke-test", "3"] if scenario == "smoke" else ["main.py"]
        with patch.object(sys, "argv", args), patch("game.Game", LaunchGame):
            entrypoint.main()
        assert seen["frames"] == (0 if scenario == "quit" else 3)
        assert seen["closed"]
    print("PASS: real main.py entrypoint presents the menu before play, "
          "handles click/quit and releases resources; --smoke-test still bypasses menu waiting.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events(menu_screen=True)
        check_pixels_and_placeholders(game)
        check_wait_start_and_restart(game)
        check_menu_quit(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()
    check_entrypoint()


if __name__ == "__main__":
    main()
