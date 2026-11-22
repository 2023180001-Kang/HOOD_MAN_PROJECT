"""Exercise real Escape -> main menu -> new game cycles and normal quit."""

from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch

from PIL import ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d

import config
from combat import MOVES, STRONG_MOVES
from game import Game
import main as entrypoint
from tools.check_main_menu import menu_image, push_click, push_mouse, push_quit
from tools.check_render import capture
from tools.check_runtime import push_key
from world import World


def snapshot(world):
    player = world.player
    return (world.elapsed, world.stage_index, world.pending_stage_index,
            world.stage_loading_remaining, player.hp, player.state, player.x, player.y,
            player.vx, player.vy, player.weapon, world.time_scale,
            tuple(world.enemies), tuple(world.projectiles))


def check_return_states(game):
    textures = dict(game.assets.images)
    push_mouse(10, 10)
    game.handle_events(menu_screen=True)
    original_menu = menu_image(game)
    for scenario in ("idle", "jump", "attack", "slow", "dying", "dead", "loading"):
        push_key(pico2d.SDLK_ESCAPE, down=False)
        game.handle_events()
        game.world = World()
        world = game.world
        world.select_stage(6)
        player = world.player
        player.hp = 200
        player.equip_weapon("combat_knife")
        world.enemies = world.spawner.spawn(1, world.elapsed)
        if scenario == "jump":
            world.controls.press("jump")
            world.controls.press("right")
            world.controls.press("left_shift")
            game.update(1 / 30)
            assert player.jump_count == 1
        elif scenario == "attack":
            player.start_move(MOVES["combat_a"], 1)
        elif scenario == "slow":
            player.start_move(STRONG_MOVES["combat_r"], 1)
            assert world.time_scale == config.R_RAISE_TIME_SCALE
        elif scenario in ("dying", "dead"):
            player.take_damage(500)
            if scenario == "dead":
                player.animation.set_state("DEAD")
        elif scenario == "loading":
            world.select_stage(1)
            world.stage.arrows_visible = True
            player.x, player.vx = config.WORLD_WIDTH - config.STAGE_EXIT_MARGIN, config.RUN_SPEED
            assert world.try_stage_transition() and world.stage_loading
        before = snapshot(world)
        draw = game.draw_main_menu
        show = game.show_main_menu
        shown_at = None
        phase = "wait"
        visits = 0

        def image_without_recursing(name):
            with patch.object(game, "draw_main_menu", draw):
                return menu_image(game, name)

        def start_click():
            push_key(pico2d.SDLK_RIGHT)
            push_key(pico2d.SDLK_9)
            push_click(game.menu.main_buttons[0])
            for key in (pico2d.SDLK_SPACE, pico2d.SDLK_u, pico2d.SDLK_F5):
                push_key(key)

        def draw_and_inject(present=True):
            nonlocal shown_at, phase
            draw(present)
            assert world.player is player and snapshot(world) == before
            assert not world.controls.held and not world.controls.pressed
            if phase == "wait":
                assert not game.menu.bag_open
                if shown_at is None:
                    shown_at = perf_counter()
                    restored = image_without_recursing(
                        "menu_escape_returned" if scenario == "idle" else None)
                    assert ImageChops.difference(original_menu, restored).getbbox() is None
                    for key in (pico2d.SDLK_ESCAPE, pico2d.SDLK_SPACE, pico2d.SDLK_9):
                        push_key(key, repeat=True)
                elif perf_counter() - shown_at >= 0.15:
                    if scenario == "idle":
                        push_click(game.menu.main_buttons[-1])
                        phase = "bag"
                    else:
                        start_click()
                        phase = "done"
            elif phase == "bag":
                assert game.menu.bag_open
                image_without_recursing("menu_escape_bag")
                push_click(game.menu.bag_back_button)
                phase = "back"
            elif phase == "back":
                assert not game.menu.bag_open
                start_click()
                phase = "done"
            assert perf_counter() - shown_at < 5, "Returned menu failed to accept a fresh click"

        def show_and_check():
            nonlocal visits
            visits += 1
            assert visits == 1, "Holding Escape bounced the new game back to the menu"
            show()
            assert (world.stage_index, world.player.hp, world.player.state) == (0, 500, "IDLE")
            assert world.time_scale == 1 and not world.stage_loading
            assert not world.controls.held and not world.controls.pressed
            # Both native repeat and duplicate KEYDOWN must remain ignored
            # while the Escape used to leave gameplay has not been released.
            push_key(pico2d.SDLK_ESCAPE, repeat=True)
            push_key(pico2d.SDLK_ESCAPE)

        push_key(pico2d.SDLK_RIGHT)
        push_key(pico2d.SDLK_ESCAPE)
        push_key(pico2d.SDLK_9)
        push_click(game.menu.main_buttons[0])  # Must not carry into the returned menu.
        with patch.object(game, "draw_main_menu", side_effect=draw_and_inject), \
                patch.object(game, "show_main_menu", side_effect=show_and_check), \
                patch.object(game, "update", wraps=game.update) as update, \
                patch.object(world, "reset", wraps=world.reset) as reset:
            assert game.run(max_frames=2) == 2
        assert phase == "done" and visits == 1
        assert update.call_count == 2 and update.call_args_list[0].args[0] < 0.05
        reset.assert_called_once_with()
        assert world.player is not player and world.player.jump_count == 0
        assert world.stage_index == 0 and world.player.hp == 500
        assert all(not stage.enemies and len(stage.drop_items) == 15 for stage in world.stages)
        assert game.ui.details_visible and not world.controls.held and not world.controls.pressed
        assert all(game.assets.images[name] is image for name, image in textures.items())
        if scenario == "idle":
            capture(game, "menu_escape_restarted")
    print("PASS: real SDL Escape returns from idle/jump/attack/slow/death/loading to an exact "
          "main-menu image, freezes the old world, discards same-batch inputs/clicks, "
          "keeps bag/back navigation, and fresh Start resets stage 1 with shared textures; "
          "held Escape does not bounce back and menu wait never becomes gameplay dt.")


def check_closing_returned_menu(game):
    push_key(pico2d.SDLK_ESCAPE, down=False)
    game.handle_events()
    player = game.world.player
    before = snapshot(game.world)
    draw = game.draw_main_menu

    def draw_and_quit(present=True):
        draw(present)
        push_quit()

    push_key(pico2d.SDLK_ESCAPE)
    with patch.object(game, "draw_main_menu", side_effect=draw_and_quit), \
            patch.object(game, "update", wraps=game.update) as update, \
            patch.object(game.world, "reset", wraps=game.world.reset) as reset:
        assert game.run(max_frames=2) == 0
    assert not game.running
    assert game.world.player is player and snapshot(game.world) == before
    update.assert_not_called()
    reset.assert_not_called()
    print("PASS: closing the menu reached with Escape exits normally, without another "
          "gameplay frame or world reset.")


def check_entrypoint_cycles():
    seen = {"menus": 0, "draws": 0, "run_calls": 0}

    class LaunchGame(Game):
        def show_main_menu(self):
            seen["menus"] += 1
            assert seen["menus"] <= 3
            draw = self.draw_main_menu

            def draw_and_inject(present=True):
                draw(present)
                if seen["menus"] < 3:
                    push_click(self.menu.main_buttons[0])
                else:
                    push_quit()

            with patch.object(self, "draw_main_menu", side_effect=draw_and_inject):
                super().show_main_menu()

        def draw(self, present=True):
            super().draw(present)
            seen["draws"] += 1
            assert seen["draws"] <= 2
            push_key(pico2d.SDLK_ESCAPE, down=False)
            push_key(pico2d.SDLK_ESCAPE)

        def run(self, max_frames=None):
            seen["run_calls"] += 1
            seen["frames"] = super().run(max_frames)
            return seen["frames"]

        def close(self):
            super().close()
            seen["closed"] = True

    with patch.object(sys, "argv", ["main.py"]), patch("game.Game", LaunchGame):
        entrypoint.main()
    assert (seen["menus"], seen["run_calls"], seen["frames"], seen["draws"]) == (3, 1, 2, 2)
    assert seen["closed"]
    print("PASS: real main.py handles Start -> Escape -> Start -> Escape -> close "
          "in one game loop and releases resources normally.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events()
        check_return_states(game)
        check_closing_returned_menu(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()
    check_entrypoint_cycles()


if __name__ == "__main__":
    main()
