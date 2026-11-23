"""Exercise actual SDL bag equipment, pistol clips/aim, seven shots and reload."""

from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch

from PIL import ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pico2d
from sdl2 import SDL_Event, SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST

import config
from axe_enemy import AxeEnemy
from game import Game
from projectiles import PlayerPistolBullet
from tools.check_main_menu import menu_image, push, push_click, push_mouse
from tools.check_render import capture, render_image
from tools.check_runtime import push_key, release, tick


def mouse_click():
    push_mouse(900, 360, kind=pico2d.SDL_MOUSEBUTTONDOWN)
    push_mouse(900, 360, kind=pico2d.SDL_MOUSEBUTTONUP)


def check_bag_equipment_and_start(game):
    menu, world = game.menu, game.world
    player = world.player
    textures = dict(game.assets.images)
    push_click(menu.main_buttons[-1])
    assert not game.handle_events(menu_screen=True) and menu.bag_open
    # Equip from a rearranged slot, not a hard-coded slot index.
    push_mouse(*menu.bag_slot_center(3), kind=pico2d.SDL_MOUSEBUTTONDOWN)
    push_mouse(*menu.bag_slot_center(0), kind=pico2d.SDL_MOUSEBUTTONUP)
    assert not game.handle_events(menu_screen=True)
    order = menu.bag_items[:]
    push_mouse(*menu.bag_slot_center(0), kind=pico2d.SDL_MOUSEBUTTONDOWN)
    push_mouse(640, 420)
    push_mouse(640, 420, kind=pico2d.SDL_MOUSEBUTTONUP)
    assert not game.handle_events(menu_screen=True)
    assert menu.equipped_weapon == "pistol" and menu.bag_items == order
    assert world.player is player and player.weapon is None and world.elapsed == 0
    with patch.object(game.assets, "draw_sprite", wraps=game.assets.draw_sprite) as draw:
        menu_image(game, "pistol_bag_equipped")
    draw.assert_called_once_with(config.PLAYER_PISTOL_IMAGE, 1, 0, 640, 320, scale=1.7)
    variants = set()
    for frame in range(8):
        menu.bag_player_animation.elapsed = (frame + 0.05) / 7
        image = menu_image(game)
        variants.add(image.crop(config.BAG_PLAYER_RECT).tobytes())
    assert len(variants) == 8
    push_click(menu.bag_back_button)
    assert not game.handle_events(menu_screen=True)
    push_click(menu.main_buttons[0])
    game.show_main_menu()
    assert (world.player.weapon, world.player.pistol_ammo, world.player.state) == ("pistol", 7, "IDLE")
    assert not world.controls.held and not world.controls.pressed and not world.projectiles
    assert all(game.assets.images[name] is image for name, image in textures.items())
    print("PASS: real bag swap -> pistol drop equips all eight IDLE preview frames; "
          "old gameplay stays frozen, Start applies pistol/7 rounds, and menu clicks never shoot.")


def check_source_rows(game):
    player = game.world.player
    texture = game.assets.images[config.PLAYER_PISTOL_IMAGE]
    for facing in (-1, 1):
        player.facing = facing
        for state in ("IDLE", "WALK", "RUN", "JUMP", "SHOOT", "RELOAD", "HIT", "DYING"):
            player.animation.set_state(state)
            row, fps, _ = config.PLAYER_PISTOL_ANIMATIONS[state]
            for frame in range(8):
                player.animation.elapsed = (frame + 0.05) / fps
                tile = game.assets.frames[config.PLAYER_PISTOL_IMAGE][row - 1][frame]
                left, bottom, width, height = tile["clip"]
                scale = config.SPRITE_SCALE
                with patch.object(texture, "clip_composite_draw",
                                  wraps=texture.clip_composite_draw) as draw:
                    game.draw(present=False)
                draw.assert_called_once_with(
                    left, bottom, width, height, 0, "h" if facing < 0 else "",
                    player.x - game.world.camera.render_x + tile["offset_x"] * scale * facing,
                    player.y - game.world.camera.render_y + height * scale / 2,
                    width * scale, height * scale,  # No jump offset added twice.
                )
    game.world.reset()
    print("PASS: all 64 source clips in both directions use the new sheet, correct rows, "
          "0.75 scale, mirrored offsets and fixed physical feet.")


def check_bag_pistol_return(game):
    menu, world = game.menu, game.world
    player = world.player
    before = world.elapsed, player.hp, player.weapon, player.pistol_ammo
    push_click(menu.main_buttons[-1])
    assert not game.handle_events(menu_screen=True) and menu.bag_open
    left, top, right, bottom = config.BAG_EQUIPPED_PISTOL_RECT
    gun = (left + right) / 2, config.SCREEN_HEIGHT - (top + bottom) / 2
    original = menu.bag_items[:]
    push_mouse(*gun, kind=pico2d.SDL_MOUSEBUTTONDOWN)
    push_mouse(900, 350)
    assert not game.handle_events(menu_screen=True) and menu.dragged_from_player
    with patch.object(game.assets, "draw_sprite", wraps=game.assets.draw_sprite) as draw, \
            patch.object(game.assets.images[config.PISTOL_ITEM_IMAGE], "clip_draw",
                         wraps=game.assets.images[config.PISTOL_ITEM_IMAGE].clip_draw) as icon:
        menu_image(game, "pistol_bag_return_dragging")
    assert draw.call_args.args[0] == config.PLAYER_IMAGE
    icon.assert_called_once()
    push_mouse(10, 10, kind=pico2d.SDL_MOUSEBUTTONUP)
    assert not game.handle_events(menu_screen=True)
    assert menu.equipped_weapon == "pistol" and menu.bag_items == original

    for target in range(6):
        push_mouse(*gun, kind=pico2d.SDL_MOUSEBUTTONDOWN)
        push_mouse(*menu.bag_slot_center(target))
        push_mouse(*menu.bag_slot_center(target), kind=pico2d.SDL_MOUSEBUTTONUP)
        assert not game.handle_events(menu_screen=True)
        assert menu.equipped_weapon is None and menu.bag_items[target][0] == "pistol"
        assert sorted(menu.bag_items) == sorted(config.BAG_ITEM_SPECS)
        with patch.object(game.assets, "draw_sprite", wraps=game.assets.draw_sprite) as draw:
            menu_image(game, "pistol_bag_returned" if target == 0 else None)
        assert draw.call_args.args[0] == config.PLAYER_IMAGE
        push_mouse(*menu.bag_slot_center(target), kind=pico2d.SDL_MOUSEBUTTONDOWN)
        push_mouse(640, 420, kind=pico2d.SDL_MOUSEBUTTONUP)
        assert not game.handle_events(menu_screen=True) and menu.equipped_weapon == "pistol"
    assert before == (world.elapsed, player.hp, player.weapon, player.pistol_ammo)

    # Unequip again, and verify that Start/F5 use the NEW unarmed selection.
    push_mouse(*gun, kind=pico2d.SDL_MOUSEBUTTONDOWN)
    push_mouse(*menu.bag_slot_center(0), kind=pico2d.SDL_MOUSEBUTTONUP)
    assert not game.handle_events(menu_screen=True) and menu.equipped_weapon is None
    push_click(menu.bag_back_button)
    assert not game.handle_events(menu_screen=True)
    push_click(menu.main_buttons[0])
    game.show_main_menu()
    assert world.player.weapon is None and world.starting_weapon is None
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert world.player.weapon is None
    capture(game, "pistol_bag_return_unarmed_start")

    # Re-equip through the same public UI for the remaining shooting checks.
    push_click(menu.main_buttons[-1])
    assert not game.handle_events(menu_screen=True)
    slot = next(index for index, item in enumerate(menu.bag_items) if item[0] == "pistol")
    push_mouse(*menu.bag_slot_center(slot), kind=pico2d.SDL_MOUSEBUTTONDOWN)
    push_mouse(640, 420, kind=pico2d.SDL_MOUSEBUTTONUP)
    push_click(menu.bag_back_button)
    assert not game.handle_events(menu_screen=True)
    push_click(menu.main_buttons[0])
    game.show_main_menu()
    assert (world.player.weapon, world.player.pistol_ammo) == ("pistol", 7)
    print("PASS: real equipped-pistol drag shows one held icon and an unarmed preview; "
          "all six slots unequip/swap without duplication, outside drops restore equipment, "
          "old world stays frozen and unarmed Start/F5 follows the updated bag selection.")


def check_aim_and_ammo_pixels(game):
    world = game.world
    player = world.player
    for side in (-1, 1):
        player.facing = side
        with patch.object(game.assets, "draw_researcher_aim"):
            without = render_image(game).convert("RGB")
        normal = capture(game, f"pistol_aim_{side}").convert("RGB")
        changed = ImageChops.difference(without, normal).getbbox()
        assert changed is not None
        red_pixels = [(x, y) for y in range(changed[1], changed[3])
                      for x in range(changed[0], changed[2])
                      if normal.getpixel((x, y)) == config.RESEARCHER_AIM_COLOR]
        assert len(red_pixels) > 200, len(red_pixels)
        assert max(y for _, y in red_pixels) - min(y for _, y in red_pixels) <= 4
        assert changed[2] - changed[0] > 350
        x, y, _, _ = player.aim_line
        assert abs((min(y for _, y in red_pixels) + max(y for _, y in red_pixels)) / 2
                   - (config.SCREEN_HEIGHT - (y - world.camera.render_y))) <= 2
        game.ui.details_visible = False
        with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as draw:
            hidden = render_image(game).convert("RGB")
        assert any("권총 7 / 7" == call.args[2] for call in draw.call_args_list)
        assert all(hidden.getpixel(point) == config.RESEARCHER_AIM_COLOR for point in red_pixels)
        game.ui.details_visible = True
    print("PASS: real red dotted horizontal aiming matches researcher color/radius/spacing "
          "in both directions; the lane and current ammo stay visible with U details hidden.")


def check_seven_shots_reload_and_hits(game):
    world = game.world
    for side in (-1, 1):
        world.reset()
        player = world.player
        player.facing = side
        enemy = AxeEnemy(player.x + side * 280, -side, ground_y=player.ground_y)
        world.enemies = [enemy]
        seen_reload = set()
        # Hold a target still to measure the player's real input/animation/rounds,
        # without an approaching target moving out of the reference shot lane.
        with patch.object(enemy, "update"):
            for shot in range(7):
                mouse_click()
                tick(game, 8)
                assert (player.state, player.sprite_row, player.animation.frame) == ("SHOOT", 5, 2)
                assert player.pistol_ammo == 6 - shot
                assert len([bullet for bullet in world.projectiles
                            if isinstance(bullet, PlayerPistolBullet)]) == 1
                if shot == 0:
                    capture(game, f"pistol_fire_{side}")
                tick(game, 17)
                assert enemy.hp == 400 - (shot + 1) * 20, (side, shot, enemy.hp)
                assert world.damage_numbers[-1].damage == 20
                assert player.hp == 500
                if shot == 0:
                    capture(game, f"pistol_hit_{side}")
                tick(game, 5)
                assert player.state == ("IDLE" if shot < 6 else "RELOAD")
            assert player.sprite_row == 6 and player.pistol_ammo == 0
            for index in range(60):
                seen_reload.add(player.animation.frame)
                if index in (0, 24, 56):
                    capture(game, f"pistol_reload_{side}_{player.animation.frame}")
                if index % 10 == 0:
                    mouse_click()
                tick(game)
                if index < 59:
                    assert player.state == "RELOAD" and player.pistol_ammo == 0
            assert seen_reload == set(range(8))
            assert (player.state, player.pistol_ammo, enemy.hp) == ("IDLE", 7, 260)
            tick(game, 30)
            assert player.pistol_ammo == 7 and not world.projectiles
    print("PASS: SDL clicks emit once at row-5 flash frame 2; seven real rounds deal 20 each "
          "on both sides (axe HP400 -> 260), then all eight row-6 frames play for 1s; "
          "early reload clicks never fire or queue a shot and completion restores seven rounds.")


def check_interrupt_restart_and_focus(game):
    world = game.world
    world.reset()
    player = world.player
    mouse_click()
    tick(game, 6)
    player.take_damage(20)
    assert player.sprite_row == 7
    tick(game, 60)
    assert player.pistol_ammo == 7 and not world.projectiles
    player.pistol_ammo = 0
    player.start_pistol_reload()
    tick(game, 20)
    player.take_damage(20)
    tick(game, 42)
    assert player.state == "RELOAD" and player.pistol_ammo == 0
    assert player.animation.elapsed < 0.1
    tick(game, 48)
    assert player.pistol_ammo == 0
    tick(game, 12)
    assert (player.state, player.pistol_ammo) == ("IDLE", 7)
    push_mouse(900, 360, kind=pico2d.SDL_MOUSEBUTTONDOWN)
    event = SDL_Event()
    event.type, event.window.event = SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST
    push(event)
    tick(game, 60)
    assert player.pistol_ammo == 7 and "shoot" not in world.controls.held
    mouse_click()
    tick(game, 10)
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert world.player is not player
    assert (world.player.weapon, world.player.pistol_ammo, world.player.state) == ("pistol", 7, "IDLE")
    assert all(not stage.projectiles for stage in world.stages)
    capture(game, "pistol_restarted")
    print("PASS: flinch cancels pre-flash shots without spending ammo, interrupted reload restarts "
          "after recovery without early refill, focus clears pending mouse input and F5 "
          "restores the selected pistol/7 rounds while clearing all rounds.")


def check_live_performance(game):
    world = game.world
    world.reset()
    player = world.player
    player.invincible = True
    player.pistol_ammo = 3  # Include firing AND a full reload within three seconds.
    world.enemies = [AxeEnemy(player.x + 260 + index * 60, -1,
                             ground_y=player.ground_y) for index in range(4)]
    handle_events = game.handle_events
    frames = 0
    states = set()

    def inject_clicks(*, menu_screen=False):
        nonlocal frames
        result = handle_events(menu_screen=menu_screen)
        states.add(player.state)
        if frames % 36 == 0:
            world.controls.release("shoot")
            world.controls.press("shoot")
            world.controls.release("shoot")
        frames += 1
        return result

    start = perf_counter()
    with patch.object(game, "handle_events", side_effect=inject_clicks):
        assert game.run(max_frames=180) == 180
    seconds = perf_counter() - start
    assert {"SHOOT", "RELOAD"} <= states
    capture(game, "pistol_live_combat")
    print(f"BENCHMARK: pistol + 4 enemies + aim/shots/reload/HP/UI: "
          f"180 frames / {seconds:.3f}s = {180 / seconds:.2f} FPS.")


def check_g_pistol_drop_and_pickup(game):
    world = game.world
    world.reset()
    player = world.player
    world.stage.drop_items.clear()
    player.pistol_ammo = 4
    textures = dict(game.assets.images)
    push_key(pico2d.SDLK_g)
    tick(game)
    release(game, pico2d.SDLK_g)
    assert player.weapon is None and len(world.stage.drop_items) == 1
    item = world.stage.drop_items[0]
    assert (item.kind, item.pistol_ammo, item.frame) == ("pistol", 4, 0)
    assert not item.grounded and world.pickup_item is None
    capture(game, "pistol_g_falling")
    tick(game, 30)
    assert item.grounded and world.pickup_item is item
    # Leave a little room to see the floor icon rather than hiding it under the feet.
    player.x = player.previous_x = item.x - 60
    world.update_camera(0)
    with patch.object(game.assets.font, "draw", wraps=game.assets.font.draw) as font:
        normal = capture(game, "pistol_g_ground").convert("RGB")
    assert any(call.args[2] == "G" for call in font.call_args_list)
    with patch.object(game.assets.images[config.PISTOL_ITEM_IMAGE], "clip_composite_draw"):
        without = render_image(game).convert("RGB")
    bounds = ImageChops.difference(normal, without).getbbox()
    assert bounds is not None, "The dropped pistol must be visible, not an empty sprite-strip cell"
    assert bounds[2] - bounds[0] <= 39 and bounds[3] - bounds[1] <= 30
    crop = normal.crop(bounds).tobytes()
    tick(game, 30)
    assert render_image(game).convert("RGB").crop(bounds).tobytes() == crop

    push_key(pico2d.SDLK_g)
    tick(game)
    release(game, pico2d.SDLK_g)
    assert (player.weapon, player.pistol_ammo, player.sprite_image) == (
        "pistol", 4, config.PLAYER_PISTOL_IMAGE)
    assert item not in world.stage.drop_items and not world.stage.drop_items
    mouse_click()
    tick(game, 8)
    assert player.pistol_ammo == 3
    capture(game, "pistol_g_picked_up_firing")
    tick(game, 30)

    # Empty magazines cannot be refilled by dropping and immediately re-equipping.
    player.pistol_ammo = 0
    player.start_pistol_reload()
    tick(game, 10)
    push_key(pico2d.SDLK_g)
    tick(game)
    release(game, pico2d.SDLK_g)
    item = world.stage.drop_items[0]
    assert player.weapon is None and item.pistol_ammo == 0
    tick(game, 30)
    push_key(pico2d.SDLK_g)
    tick(game)
    release(game, pico2d.SDLK_g)
    assert (player.state, player.pistol_ammo) == ("RELOAD", 0)
    tick(game, 58)
    assert player.pistol_ammo == 0
    tick(game)
    assert (player.state, player.pistol_ammo) == ("IDLE", 7)
    push_key(pico2d.SDLK_F5)
    tick(game)
    release(game, pico2d.SDLK_F5)
    assert all(len(stage.drop_items) == 15 and
               all(drop.kind in ("combat_knife", "steel_pipe") for drop in stage.drop_items)
               for stage in world.stages)
    assert all(game.assets.images[name] is image for name, image in textures.items())
    print("PASS: real G drops a falling collectible pistol, a static complete icon/G prompt "
          "appears after landing, and a fresh G re-equips with the SAME ammo and can fire; "
          "empty guns keep zero/restart full reload, F5 clears drops, initial 15 melee items/textures stay unchanged.")


def main():
    pico2d.open_canvas(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    pico2d.hide_lattice()
    game = None
    try:
        game = Game()
        game.handle_events(menu_screen=True)
        check_bag_equipment_and_start(game)
        check_bag_pistol_return(game)
        check_source_rows(game)
        check_aim_and_ammo_pixels(game)
        check_seven_shots_reload_and_hits(game)
        check_interrupt_restart_and_focus(game)
        check_g_pistol_drop_and_pickup(game)
        check_live_performance(game)
    finally:
        if game is not None:
            game.close()
        pico2d.close_canvas()


if __name__ == "__main__":
    main()
