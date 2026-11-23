"""Verify bag navigation, item drag/swaps and original pixels with real SDL."""

from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch

from PIL import ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d
from sdl2 import (
    SDL_BUTTON_MIDDLE, SDL_BUTTON_RIGHT, SDL_Event,
    SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST, SDL_WINDOWEVENT_LEAVE,
)

import config
from combat import STRONG_MOVES
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
        assert (game.assets.images[config.BAG_UI_IMAGE].w,
                game.assets.images[config.BAG_UI_IMAGE].h) == (1672, 941)
        assert config.ARCHIVED_BAG_UI_IMAGE not in game.assets.images
        with patch.object(menu, "draw_bag_items"):
            empty_slots = menu_image(game)
        # Use SDL's scaled background as the reference, rather than a separate
        # Pillow resampler for the new 1672x941 -> 1280x720 presentation.
        with patch.object(menu, "draw_bag_items"), patch.object(menu, "draw_bag_player"):
            without_content = menu_image(game)
            with patch.object(arrow, "clip_draw"):
                background = menu_image(game)
        box = screen_box(back)
        assert box == (32, 24, 94, 82)
        changed = ImageChops.difference(background, without_content).getbbox()
        assert changed is not None
        assert box[0] <= changed[0] < changed[2] <= box[2]
        assert box[1] <= changed[1] < changed[3] <= box[3]
        title = (130, 24, 270, 82)
        assert normal.crop(title).tobytes() == background.crop(title).tobytes()
        with patch.object(menu, "draw_bag_player"):
            without_player = menu_image(game)
        player_bounds = ImageChops.difference(normal, without_player).getbbox()
        assert player_bounds is not None
        assert 528 <= player_bounds[0] < player_bounds[2] <= 752
        assert 24 <= player_bounds[1] < player_bounds[3] <= 410

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
    print("PASS: new bag background is pixel-identical except the idle preview, arrow and six item icons; "
          "old background is not loaded, each icon stays in its padded slot, "
          "title is intact, clicks within one slot do not reorder or navigate, "
          "black/gray arrow clips and hover-only pixel changes match, "
          "leave/focus restore black, hidden menu/buttons/keys do not activate, "
          "20 round trips reuse textures without advancing/resetting the world.")


def check_idle_preview(game):
    menu, world = game.menu, game.world
    player = world.player
    player.hp = 200
    player.equip_weapon("steel_pipe")
    player.start_move(STRONG_MOVES["combat_r"], 1)
    before = (player.hp, player.state, player.weapon, player.animation.elapsed,
              world.elapsed, world.time_scale)
    push_click(menu.main_buttons[-1])
    assert not game.handle_events(menu_screen=True) and menu.bag_open
    fps = config.PLAYER_ANIMATIONS["IDLE"][1]
    menu.update(0.1 / fps)
    reference = None
    variants = set()
    image = game.assets.images[config.PLAYER_IMAGE]
    preview_box = (528, 24, 752, 410)
    with patch.object(world, "update", wraps=world.update) as update, \
            patch.object(world, "reset", wraps=world.reset) as reset:
        for index in range(16):
            frame = index % 8
            assert menu.bag_player_animation.frame == frame
            tile = game.assets.frames[config.PLAYER_IMAGE][0][frame]
            left, bottom, width, height = tile["clip"]
            scale = config.BAG_PLAYER_SCALE
            with patch.object(image, "clip_composite_draw", wraps=image.clip_composite_draw) as draw:
                rendered = menu_image(game, f"bag_idle_{frame}" if index < 8 else None)
            draw.assert_called_once_with(
                left, bottom, width, height, 0, "",
                config.BAG_PLAYER_X + tile["offset_x"] * scale,
                config.BAG_PLAYER_FEET_Y + (height / 2 + tile.get("offset_y", 0)) * scale,
                width * scale, height * scale,
            )
            variants.add(rendered.crop(preview_box).tobytes())
            if reference is None:
                reference = rendered
            else:
                changed = ImageChops.difference(reference, rendered)
                changed.paste((0, 0, 0), preview_box)
                assert changed.getbbox() is None, "Animation changed the background, slots or button"
                if frame == 0:
                    assert ImageChops.difference(reference, rendered).getbbox() is None
            assert before == (player.hp, player.state, player.weapon, player.animation.elapsed,
                              world.elapsed, world.time_scale)
            menu.update(1 / fps)
        assert len(variants) == 8
        update.assert_not_called()
        reset.assert_not_called()
    menu.show_main()
    elapsed = menu.bag_player_animation.elapsed
    menu.update(10)
    assert menu.bag_player_animation.elapsed == elapsed
    push_click(menu.main_buttons[-1])
    assert not game.handle_events(menu_screen=True)
    assert menu.bag_player_animation.frame == 0 and menu.bag_player_animation.elapsed == 0
    push_click(menu.bag_back_button)
    assert not game.handle_events(menu_screen=True) and not menu.bag_open
    print("PASS: basic HoodMan IDLE shows all eight distinct source frames at 7 FPS/1.7 scale, "
          "loops twice with fixed feet, changes only the preview region, and is independent of "
          "the armed/slow gameplay player; hidden preview stops and reopening restarts frame 0.")


def check_item_drag_and_swap(game):
    menu, world = game.menu, game.world
    player = world.player
    before_world = (world.elapsed, world.stage_index, player.hp, player.weapon,
                    player.state, player.animation.elapsed, world.time_scale)
    textures = dict(game.assets.images)
    push_click(menu.main_buttons[-1])
    assert not game.handle_events(menu_screen=True) and menu.bag_open
    original = menu.bag_items[:]
    normal = menu_image(game)
    with patch.object(menu, "draw_bag_items"):
        empty = menu_image(game)

    def point(slot):
        left, top, right, bottom = config.BAG_ITEM_SLOT_RECTS[slot]
        return (left + right) / 2, config.SCREEN_HEIGHT - (top + bottom) / 2

    def drag(source, target):
        before = menu.bag_items[:]
        push_mouse(*point(source), kind=pico2d.SDL_MOUSEBUTTONDOWN)
        assert not game.handle_events(menu_screen=True)
        assert menu.dragged_slot == source
        push_mouse(*point(target))
        assert not game.handle_events(menu_screen=True)
        assert menu.bag_items == before
        push_mouse(*point(target), kind=pico2d.SDL_MOUSEBUTTONUP)
        assert not game.handle_events(menu_screen=True)
        before[source], before[target] = before[target], before[source]
        assert menu.bag_items == before and menu.dragged_slot is None

    with patch.object(world, "update", wraps=world.update) as update, \
            patch.object(world, "reset", wraps=world.reset) as reset:
        push_mouse(*point(0), kind=pico2d.SDL_MOUSEBUTTONDOWN)
        assert not game.handle_events(menu_screen=True)
        push_mouse(950, 370)
        assert not game.handle_events(menu_screen=True)
        assert menu.dragged_slot == 0 and menu.drag_position == (950.5, 370)
        held = menu_image(game, "bag_item_dragging")
        source_box = config.BAG_ITEM_SLOT_RECTS[0]
        assert held.crop(source_box).tobytes() == empty.crop(source_box).tobytes()
        # Remove the real dragged texture to find only its floating pixels.
        with patch.object(game.assets.images[original[0][1]], "clip_draw"):
            without_held = menu_image(game)
        held_bounds = ImageChops.difference(held, without_held).getbbox()
        assert held_bounds is not None
        assert 870 <= held_bounds[0] < held_bounds[2] <= 1030
        assert 310 <= held_bounds[1] < held_bounds[3] <= 390
        assert menu.bag_items == original

        push_mouse(*point(5), kind=pico2d.SDL_MOUSEBUTTONUP)
        assert not game.handle_events(menu_screen=True)
        assert menu.bag_items[0] == original[5] and menu.bag_items[5] == original[0]
        swapped_order = menu.bag_items[:]
        swapped = menu_image(game, "bag_items_swapped")
        changed = ImageChops.difference(normal, swapped)
        assert changed.getbbox() is not None
        for slot in (0, 5):
            changed.paste((0, 0, 0), config.BAG_ITEM_SLOT_RECTS[slot])
        assert changed.getbbox() is None, "Swap changed pixels outside the two slots"
        padding = config.BAG_ITEM_SLOT_PADDING
        for (_, name, _), (left, top, right, bottom) in zip(
                menu.bag_items, config.BAG_ITEM_SLOT_RECTS):
            with patch.object(game.assets.images[name], "clip_draw"):
                without_item = menu_image(game)
            bounds = ImageChops.difference(swapped, without_item).getbbox()
            assert bounds is not None
            assert left + padding <= bounds[0] < bounds[2] <= right - padding
            assert top + padding <= bounds[1] < bounds[3] <= bottom - padding

        push_click(menu.bag_back_button)
        push_click(menu.main_buttons[-1])
        assert not game.handle_events(menu_screen=True) and menu.bag_open
        assert menu.bag_items == swapped_order
        assert ImageChops.difference(swapped, menu_image(game)).getbbox() is None

        for source in range(6):
            for target in range(6):
                drag(source, target)

        back = menu.bag_back_button
        for target in ((640, 350), (267, 148), (back.x, back.y)):
            before = menu.bag_items[:]
            push_mouse(*point(0), kind=pico2d.SDL_MOUSEBUTTONDOWN)
            push_mouse(*target)
            push_mouse(*target, kind=pico2d.SDL_MOUSEBUTTONUP)
            assert not game.handle_events(menu_screen=True)
            assert menu.bag_items == before and menu.bag_open and menu.dragged_slot is None
        for kind in (SDL_WINDOWEVENT_LEAVE, SDL_WINDOWEVENT_FOCUS_LOST):
            before = menu.bag_items[:]
            push_mouse(*point(0), kind=pico2d.SDL_MOUSEBUTTONDOWN)
            push_mouse(*point(5))
            assert not game.handle_events(menu_screen=True)
            event = SDL_Event()
            event.type, event.window.event = SDL_WINDOWEVENT, kind
            push(event)
            push_mouse(*point(5), kind=pico2d.SDL_MOUSEBUTTONUP)
            assert not game.handle_events(menu_screen=True)
            assert menu.bag_items == before and menu.dragged_slot is None

        # Restore via real input, not by resetting the layout behind the UI.
        for slot, item in enumerate(original):
            current = menu.bag_items.index(item)
            if current != slot:
                drag(current, slot)
        push_mouse(640, 350)
        assert not game.handle_events(menu_screen=True)
        assert ImageChops.difference(normal, menu_image(game, "bag_drag_restored")).getbbox() is None
        push_click(menu.bag_back_button)
        assert not game.handle_events(menu_screen=True) and not menu.bag_open
        update.assert_not_called()
        reset.assert_not_called()
    assert before_world == (world.elapsed, world.stage_index, player.hp, player.weapon,
                            player.state, player.animation.elapsed, world.time_scale)
    assert all(game.assets.images[name] is image for name, image in textures.items())
    print("PASS: real SDL drag follows the grabbed point, leaves the source empty, "
          "and draws once above other items; all 36 source/target pairs swap on release, "
          "swapped textures fit destination padding, reopening preserves order, "
          "outside/back drops and leave/focus cancel safely; world and shared textures stay unchanged.")


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
    seen_idle_frames = set()
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
            seen_idle_frames.add(menu.bag_player_animation.frame)
            if shown_at is None:
                shown_at = perf_counter()
                assert menu.bag_player_animation.frame == 0
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
    assert seen_idle_frames == set(range(8)), "Live bag loop did not animate all idle frames"
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
    print(f"PASS: actual world stayed frozen while all eight idle frames animated for {seconds:.3f}s; "
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
        check_idle_preview(game)
        check_item_drag_and_swap(game)
        check_bag_wait_return_and_start(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()
    check_bag_entrypoint()


if __name__ == "__main__":
    main()
