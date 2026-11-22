"""Verify bag navigation and native black/gray button pixels with real SDL."""

from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d
from sdl2 import (
    SDL_BUTTON_MIDDLE, SDL_BUTTON_RIGHT, SDL_Event,
    SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST, SDL_WINDOWEVENT_LEAVE,
)

import config
from game import Game, KEYS
import main as entrypoint
from tools.check_main_menu import menu_image, push, push_click, push_mouse, push_quit, screen_box
from tools.check_render import capture
from tools.check_runtime import push_key, release, tick
from world import World


def check_bag_pixels_and_navigation(game):
    push_mouse(10, 10)
    assert not game.handle_events(menu_screen=True)
    main_image = menu_image(game)
    menu = game.menu
    world, player = game.world, game.world.player
    textures = dict(game.assets.images)
    back, bag = menu.bag_back_button, menu.main_buttons[-1]
    with patch.object(world, "reset", wraps=world.reset) as reset, \
            patch.object(world, "update", wraps=world.update) as update:
        push_click(bag)
        assert not game.handle_events(menu_screen=True) and menu.bag_open
        assert menu.hovered_button is None
        arrow = game.assets.images[config.BAG_BUTTON_IMAGE]
        with patch.object(arrow, "clip_draw", wraps=arrow.clip_draw) as clip:
            normal = menu_image(game, "bag_ui_default")
        clip.assert_called_once_with(0, 0, 62, 58, 63, 667, 62, 58)
        with Image.open(ROOT / config.BAG_UI_IMAGE) as image:
            background = image.convert("RGB")
        with patch.object(menu, "draw_bag_items"):
            empty_slots = menu_image(game)
        box = screen_box(back)
        assert box == (32, 24, 94, 82)
        changed = ImageChops.difference(background, empty_slots).getbbox()
        assert changed is not None
        assert box[0] <= changed[0] < changed[2] <= box[2]
        assert box[1] <= changed[1] < changed[3] <= box[3]
        title = (130, 24, 270, 82)
        assert normal.crop(title).tobytes() == background.crop(title).tobytes()

        item_changes = ImageChops.difference(normal, empty_slots)
        padding = config.BAG_ITEM_SLOT_PADDING
        for (kind, name, _), (left, top, right, bottom) in zip(
                config.BAG_ITEM_SPECS, config.BAG_ITEM_SLOT_RECTS):
            # Remove each real texture independently: its pixels must occur
            # only in the assigned slot, not a neighboring slot or its border.
            with patch.object(game.assets.images[name], "clip_draw"):
                without_item = menu_image(game)
            bounds = ImageChops.difference(normal, without_item).getbbox()
            assert bounds is not None, f"{kind} did not appear in the bag"
            assert left + padding <= bounds[0] < bounds[2] <= right - padding, (kind, bounds)
            assert top + padding <= bounds[1] < bounds[3] <= bottom - padding, (kind, bounds)
            item_changes.paste((0, 0, 0), (left, top, right, bottom))
            x, y = (left + right) / 2, config.SCREEN_HEIGHT - (top + bottom) / 2
            push_mouse(x, y, kind=pico2d.SDL_MOUSEBUTTONDOWN)
            push_mouse(x, y, kind=pico2d.SDL_MOUSEBUTTONUP)
            assert not game.handle_events(menu_screen=True) and menu.bag_open
            assert menu.hovered_button is None
        assert item_changes.getbbox() is None, "Item pixels escaped the six slot frames"

        push_mouse(back.x, back.y)
        assert not game.handle_events(menu_screen=True)
        with patch.object(arrow, "clip_draw", wraps=arrow.clip_draw) as clip:
            hovered = menu_image(game, "bag_ui_hover_back")
        clip.assert_called_once_with(62, 0, 62, 58, 63, 667, 62, 58)
        changed = ImageChops.difference(normal, hovered).getbbox()
        assert changed is not None
        assert box[0] <= changed[0] < changed[2] <= box[2]
        assert box[1] <= changed[1] < changed[3] <= box[3]
        sample = (42, 32, 82, 40)
        assert (sum(ImageStat.Stat(hovered.crop(sample)).mean)
                > sum(ImageStat.Stat(normal.crop(sample)).mean) + 30)
        push_mouse(640, 360)
        assert not game.handle_events(menu_screen=True)
        assert ImageChops.difference(normal, menu_image(game)).getbbox() is None
        for kind in (SDL_WINDOWEVENT_LEAVE, SDL_WINDOWEVENT_FOCUS_LOST):
            push_mouse(back.x, back.y)
            assert not game.handle_events(menu_screen=True)
            event = SDL_Event()
            event.type, event.window.event = SDL_WINDOWEVENT, kind
            push(event)
            assert not game.handle_events(menu_screen=True)
            assert menu.bag_open and menu.hovered_button is None
            assert ImageChops.difference(normal, menu_image(game)).getbbox() is None

        for button in menu.main_buttons:
            push_click(button)
            assert not game.handle_events(menu_screen=True) and menu.bag_open
        for mouse_button in (SDL_BUTTON_RIGHT, SDL_BUTTON_MIDDLE):
            push_click(back, mouse_button)
            assert not game.handle_events(menu_screen=True) and menu.bag_open
        for key in (*KEYS, pico2d.SDLK_RETURN, pico2d.SDLK_ESCAPE):
            push_key(key)
            push_key(key, repeat=True)
            push_key(key, down=False)
        assert not game.handle_events(menu_screen=True) and menu.bag_open
        assert not world.controls.held and not world.controls.pressed
        assert ImageChops.difference(normal, menu_image(game)).getbbox() is None

        push_click(back)
        assert not game.handle_events(menu_screen=True) and not menu.bag_open
        assert menu.hovered_button is None
        returned = menu_image(game, "bag_ui_returned_menu")
        assert ImageChops.difference(main_image, returned).getbbox() is None
        for _ in range(20):
            push_click(bag)
            assert not game.handle_events(menu_screen=True) and menu.bag_open
            assert menu.hovered_button is None
            push_click(back)
            assert not game.handle_events(menu_screen=True) and not menu.bag_open
        assert ImageChops.difference(main_image, menu_image(game)).getbbox() is None
        reset.assert_not_called()
        update.assert_not_called()
    assert game.world is world and world.player is player
    assert (world.elapsed, world.stage_index, player.hp, player.state) == (0, 0, 500, "IDLE")
    assert all(game.assets.images[name] is image for name, image in textures.items())
    print("PASS: bag background is pixel-identical except the arrow and six ordered item icons; "
          "each icon stays in its padded slot, title is intact, item clicks have no action, "
          "black/gray arrow clips and hover-only pixel changes match, "
          "leave/focus restore black, hidden menu/buttons/keys do not activate, "
          "20 round trips reuse textures without advancing/resetting the world.")


def check_bag_wait_return_and_start(game):
    game.world = World()
    world = game.world
    world.select_stage(11)
    world.player.hp = 200
    player = world.player
    textures = dict(game.assets.images)
    draw = game.draw_main_menu
    menu = game.menu
    phase = "open"
    shown_at = None
    total_start = perf_counter()

    def draw_and_inject(present=True):
        nonlocal phase, shown_at
        draw(present)
        assert world.player is player and player.hp == 200
        assert world.stage_index == 11 and world.elapsed == 0
        assert not world.controls.held and not world.controls.pressed
        if phase == "open":
            assert not menu.bag_open
            push_click(menu.main_buttons[-1])
            phase = "wait"
        elif phase == "wait":
            assert menu.bag_open
            if shown_at is None:
                shown_at = perf_counter()
                for key in KEYS:
                    push_key(key)
                    push_key(key, repeat=True)
                    push_key(key, down=False)
                push_click(menu.main_buttons[0])  # Hidden start region stays inactive.
                push_click(menu.bag_back_button, SDL_BUTTON_RIGHT)
                push_mouse(640, 360)
            elif perf_counter() - shown_at >= 2.2:
                push_click(menu.bag_back_button)
                phase = "start"
        elif phase == "start":
            assert not menu.bag_open
            push_key(pico2d.SDLK_RIGHT)
            push_key(pico2d.SDLK_9)
            push_click(menu.main_buttons[0])
            push_key(pico2d.SDLK_SPACE)
            push_key(pico2d.SDLK_u)
            push_key(pico2d.SDLK_F5)
            phase = "done"
        assert perf_counter() - total_start < 5, "Bag navigation did not complete"

    with patch.object(game, "draw_main_menu", side_effect=draw_and_inject), \
            patch.object(world, "update", wraps=world.update) as update, \
            patch.object(world, "reset", wraps=world.reset) as reset:
        game.show_main_menu()
    seconds = perf_counter() - shown_at
    assert phase == "done" and seconds >= 2.2 and not menu.bag_open
    update.assert_not_called()
    reset.assert_called_once_with()
    assert world.player is not player
    assert (world.stage_index, world.player.hp, world.player.state, world.elapsed) == (0, 500, "IDLE", 0)
    assert all(not stage.enemies and len(stage.drop_items) == 15 for stage in world.stages)
    assert not world.controls.held and not world.controls.pressed and game.ui.details_visible
    capture(game, "bag_ui_started_after_return")
    push_key(pico2d.SDLK_SPACE)
    tick(game)
    assert world.player.jump_count == 1
    release(game, pico2d.SDLK_SPACE)
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert (world.stage_index, world.player.hp, world.player.state) == (0, 500, "IDLE")
    assert all(game.assets.images[name] is image for name, image in textures.items())
    print(f"PASS: actual bag/menu loop remained frozen for {seconds:.3f}s despite keys/invalid clicks; "
          "back returns to menu without starting, only a fresh start click resets stage 1, "
          "no queued gameplay input, fresh Space and F5 still work.")


def check_bag_entrypoint():
    for scenario in ("start", "quit"):
        seen = {}

        class LaunchGame(Game):
            def show_main_menu(self):
                draw = self.draw_main_menu
                phase = "open"

                def draw_and_inject(present=True):
                    nonlocal phase
                    draw(present)
                    seen["draws"] = seen.get("draws", 0) + 1
                    assert seen["draws"] < 30, "Bag launch sequence did not complete"
                    if phase == "open":
                        push_click(self.menu.main_buttons[-1])
                        phase = "bag"
                    elif phase == "bag":
                        assert self.menu.bag_open
                        seen["bag"] = True
                        if scenario == "quit":
                            push_quit()
                        else:
                            push_click(self.menu.bag_back_button)
                            phase = "start"
                    elif phase == "start":
                        assert not self.menu.bag_open
                        push_click(self.menu.main_buttons[0])

                with patch.object(self, "draw_main_menu", side_effect=draw_and_inject):
                    super().show_main_menu()

            def run(self, max_frames=None):
                assert seen.get("bag")
                assert self.world.stage_index == 0 and self.world.elapsed == 0
                seen["frames"] = super().run(3)
                return seen["frames"]

            def close(self):
                super().close()
                seen["closed"] = True

        with patch.object(sys, "argv", ["main.py"]), patch("game.Game", LaunchGame):
            entrypoint.main()
        assert seen["frames"] == (3 if scenario == "start" else 0)
        assert seen["closed"]
    print("PASS: real main.py entrypoint supports menu -> bag -> back -> start; "
          "closing the bag exits with zero gameplay frames and releases resources.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events(menu_screen=True)
        check_bag_pixels_and_navigation(game)
        check_bag_wait_return_and_start(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()
    check_bag_entrypoint()


if __name__ == "__main__":
    main()
