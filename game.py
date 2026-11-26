"""Main game loop and shared-resource lifetime."""

import ctypes
from time import perf_counter, sleep

import pico2d
from pico2d import pico2d as backend
from sdl2 import (
    SDL_BUTTON_LEFT, SDL_Event, SDL_PollEvent,
    SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST, SDL_WINDOWEVENT_LEAVE,
)

import config
from assets import Assets
from drop_items import DropItem
from effects import SpriteAfterimage
from main_menu import MainMenu
from projectiles import ResearcherBullet
from researcher import Researcher
from sniper import Sniper
from ui import UI
from world import World


KEYS = {
    pico2d.SDLK_LEFT: "left",
    pico2d.SDLK_RIGHT: "right",
    pico2d.SDLK_UP: "up",
    pico2d.SDLK_DOWN: "down",
    pico2d.SDLK_LSHIFT: "left_shift",
    pico2d.SDLK_RSHIFT: "right_shift",
    pico2d.SDLK_SPACE: "jump",
    pico2d.SDLK_F5: "restart",
    pico2d.SDLK_n: "stage_exits",
    pico2d.SDLK_p: "invincibility",
    pico2d.SDLK_F3: "toggle_doors",
    pico2d.SDLK_F4: "toggle_floor_bounds",
    pico2d.SDLK_u: "toggle_details",
    pico2d.SDLK_g: "weapon_interact",
    pico2d.SDLK_r: "combat_r",
    pico2d.SDLK_m: "cycle_spawn_enemy",
    pico2d.SDLK_c: "sword_spawn",
    pico2d.SDLK_v: "sniper_spawn",
    pico2d.SDLK_PLUS: "training_target",
    pico2d.SDLK_KP_PLUS: "training_target",
}
KEYS.update({getattr(pico2d, f"SDLK_{key}"): f"combat_{key}"
             for key, *_ in config.COMBAT_MOVE_SPECS})
KEYS.update({getattr(pico2d, f"SDLK_{key}"): f"combat_{key}"
             for key, *_ in config.STRONG_MOVE_SPECS})
KEYS.update({getattr(pico2d, f"SDLK_{prefix}{count}"): f"spawn_{count}"
             for count in config.SPAWN_COUNTS for prefix in ("", "KP_")})


class Game:
    def __init__(self):
        self.assets = Assets()
        self.ui = UI()
        self.world = World()
        self.menu = MainMenu()
        self.running = True
        self._menu_requested = False
        self._escape_held = False
        pico2d.SDL_SetWindowTitle(backend.window, b"HOOD_MAN_PROJECT")

    def request_main_menu(self):
        self._menu_requested = True
        self.world.controls.held.clear()
        self.world.controls.pressed.clear()

    def handle_events(self, *, menu_screen=False):
        # pico2d.get_events filters out focus events, so poll its SDL event queue
        # directly to prevent stuck keys after Alt+Tab or clicking another window.
        event = SDL_Event()
        start_requested = False
        while SDL_PollEvent(ctypes.byref(event)):
            if event.type == pico2d.SDL_QUIT:
                self.running = False
                self.menu.cancel_drag()
            elif event.type == SDL_WINDOWEVENT and event.window.event == SDL_WINDOWEVENT_FOCUS_LOST:
                self.world.controls.held.clear()
                self.world.controls.pressed.clear()
                self.menu.cancel_drag()
                self.menu.clear_hover()
                self._escape_held = False
                start_requested = False
            elif event.type == SDL_WINDOWEVENT and event.window.event == SDL_WINDOWEVENT_LEAVE:
                self.menu.cancel_drag()
                self.menu.clear_hover()
            elif (event.type in (pico2d.SDL_KEYDOWN, pico2d.SDL_KEYUP)
                  and event.key.keysym.sym == pico2d.SDLK_ESCAPE):
                if event.type == pico2d.SDL_KEYUP:
                    self._escape_held = False
                elif not event.key.repeat and not self._escape_held:
                    self._escape_held = True
                    if not menu_screen:
                        self.request_main_menu()
            elif menu_screen:
                if event.type == pico2d.SDL_MOUSEMOTION:
                    self.menu.move_pointer(
                        event.motion.x, config.SCREEN_HEIGHT - 1 - event.motion.y,
                    )
                elif event.type == pico2d.SDL_MOUSEBUTTONDOWN and event.button.button == SDL_BUTTON_LEFT:
                    previous_screen = self.menu.screen
                    start_requested |= self.menu.press_pointer(
                        event.button.x, config.SCREEN_HEIGHT - 1 - event.button.y,
                    )
                    if self.menu.screen != previous_screen:
                        # Navigation cancels an earlier start click in this batch.
                        start_requested = False
                elif event.type == pico2d.SDL_MOUSEBUTTONUP and event.button.button == SDL_BUTTON_LEFT:
                    self.menu.release_pointer(
                        event.button.x, config.SCREEN_HEIGHT - 1 - event.button.y,
                    )
            elif self.world.training and event.type in (pico2d.SDL_MOUSEMOTION, pico2d.SDL_MOUSEBUTTONDOWN):
                pointer = event.motion if event.type == pico2d.SDL_MOUSEMOTION else event.button
                back = self.menu.bag_back_button
                x, y = pointer.x, config.SCREEN_HEIGHT - 1 - pointer.y
                if back.contains(x, y):
                    self.menu.hovered_button = back
                    if event.type == pico2d.SDL_MOUSEBUTTONDOWN and event.button.button == SDL_BUTTON_LEFT:
                        self.request_main_menu()
                else:
                    self.menu.clear_hover()
                    if (not self._menu_requested and event.type == pico2d.SDL_MOUSEBUTTONDOWN
                            and event.button.button == SDL_BUTTON_LEFT):
                        self.ui.click_training_hp(self.world, x, y)
            elif not self._menu_requested and event.type in (pico2d.SDL_KEYDOWN, pico2d.SDL_KEYUP):
                key = KEYS.get(event.key.keysym.sym)
                if (event.key.keysym.sym == pico2d.SDLK_EQUALS
                        and (event.key.keysym.mod & pico2d.KMOD_SHIFT or event.type == pico2d.SDL_KEYUP)):
                    key = "training_target"
                if key is not None:
                    if event.type == pico2d.SDL_KEYDOWN and not event.key.repeat:
                        if key in ("sword_spawn", "sniper_spawn") and (
                                self.world.training or self.world.stage_loading or not self.world.player.alive):
                            continue
                        if key == "sniper_spawn" and not self.world.sniper_stage:
                            continue
                        self.world.controls.press(key)
                    elif event.type == pico2d.SDL_KEYUP:
                        self.world.controls.release(key)
        # Drain the entire menu batch so click/keyboard input cannot leak into play.
        # A quit in the same batch must win over a game-start click.
        return start_requested and self.running

    def draw_main_menu(self, present=True):
        pico2d.clear_canvas()
        self.menu.draw(self.assets)
        if present:
            pico2d.update_canvas()

    def show_main_menu(self):
        if not self.running:
            return
        self._menu_requested = False
        self.menu.show_main()
        self.world.controls.held.clear()
        self.world.controls.pressed.clear()
        self.draw_main_menu()
        previous = perf_counter()
        while self.running:
            now = perf_counter()
            self.menu.update(now - previous)
            previous = now
            if self.handle_events(menu_screen=True):
                self.world.training = self.menu.launch_action == "controls"
                self.world.starting_weapon = self.menu.equipped_weapon
                self.world.reset()
                self.ui.update(0, self.world.player)
                return
            if self.running:
                self.draw_main_menu()
                sleep(1 / config.TARGET_FPS)

    def update(self, dt):
        # Presentation remains toggleable while gameplay is loading or dead.
        if self.world.controls.take_press("toggle_details") and not self.world.training:
            self.ui.details_visible = not self.ui.details_visible
        if self.world.controls.take_press("toggle_floor_bounds"):
            self.ui.floor_bounds_visible = not self.ui.floor_bounds_visible
        # Snapshot HP before simulation so a first-frame hit also leaves a trail.
        self.ui.update(0, self.world.player)
        self.world.update(dt)
        self.ui.update(dt, self.world.player)

    def draw_stage_loading_screen(self, present=True):
        pico2d.clear_canvas()
        self.assets.images[config.STAGE_LOADING_IMAGE].draw(
            config.SCREEN_WIDTH / 2, config.SCREEN_HEIGHT / 2,
            config.SCREEN_WIDTH, config.SCREEN_HEIGHT,
        )
        if present:
            pico2d.update_canvas()

    def draw(self, present=True):
        if self.world.stage_loading:
            self.draw_stage_loading_screen(present)
            return
        pico2d.clear_canvas()
        camera_x = self.world.camera.render_x
        camera_y = self.world.camera.render_y
        self.world.stage.draw(self.assets, camera_x, camera_y, elapsed=self.world.elapsed)
        self.ui.draw_floor_bounds(self.world, camera_x, camera_y)
        player = self.world.player
        if player.weapon == "pistol":
            self.assets.draw_researcher_aim(player, camera_x, camera_y)
        for enemy in self.world.enemies:
            if isinstance(enemy, Researcher) and not isinstance(enemy, Sniper):
                self.assets.draw_researcher_aim(enemy, camera_x, camera_y)
        # Stable depth sorting puts older echoes behind newer ones and the
        # live actors on the same floor, without sorting by airborne height.
        sprites = [(image.ground_y, image, image.image_name, image.opacity)
                   for image in self.world.afterimages]
        sprites.extend((enemy.ground_y, enemy, enemy.sprite_image, enemy.opacity)
                       for enemy in self.world.enemies)
        sprites.append((player.ground_y, player, player.sprite_image, 1.0))
        sprites.extend((bullet.ground_y, bullet, bullet.image_name, 1.0)
                       for bullet in self.world.projectiles)
        sprites.extend((item.ground_y, item, item.image_name, 1.0)
                       for item in self.world.stage.drop_items if not item.grounded)
        traffic = self.world.stage.traffic
        if traffic is not None and traffic.car is not None:
            sprites.append((traffic.car.ground_y, traffic.car, config.CAR_IMAGE, 1.0))
        for _, actor, image, opacity in sorted(sprites, key=lambda entry: entry[0], reverse=True):
            if image == config.CAR_IMAGE:
                self.assets.draw_car(actor, camera_x, camera_y)
            elif isinstance(actor, ResearcherBullet):
                self.assets.draw_projectile(actor, camera_x, camera_y)
            elif isinstance(actor, DropItem):
                self.assets.draw_drop_item(actor, camera_x, camera_y)
            else:
                if isinstance(actor, SpriteAfterimage):
                    row, frame = actor.row, actor.frame
                else:
                    row = player.sprite_row if actor is player else actor.animation.row
                    frame = actor.animation.frame
                self.assets.draw_sprite(image, row, frame,
                                        actor.x - camera_x, actor.y - camera_y, actor.facing,
                                        opacity=opacity)
        for enemy in self.world.enemies:
            if isinstance(enemy, Sniper) and enemy.visible_target is not None:
                self.assets.draw_sniper_target(enemy, camera_x, camera_y)
        for effect in self.world.effects:
            self.assets.draw_hit_effect(effect, camera_x, camera_y)
        self.ui.draw_enemy_health(self.assets, self.world, camera_x, camera_y)
        self.ui.draw_pickup_prompt(self.assets, self.world, camera_x, camera_y)
        self.ui.draw(self.assets, self.world)
        if self.world.training:
            self.menu.draw_button(self.assets, self.menu.bag_back_button)
        if present:
            pico2d.update_canvas()

    def run(self, max_frames=None):
        previous = perf_counter()
        deadline = previous
        frames = 0
        while self.running and (max_frames is None or frames < max_frames):
            start = perf_counter()
            dt = start - previous
            previous = start
            self.handle_events()
            if not self.running:
                break
            if self._menu_requested:
                self._menu_requested = False
                self.show_main_menu()
                # Menu waiting must not become gameplay dt or a late FPS deadline.
                previous = deadline = perf_counter()
                continue
            was_loading = self.world.stage_loading
            self.update(dt)
            self.draw()
            if self.world.stage_loading and not was_loading:
                # Start the two-second wait after its first image is presented.
                previous = perf_counter()
            frames += 1
            # Absolute deadlines avoid accumulating Windows sleep overshoot.
            deadline += 1 / config.TARGET_FPS
            remaining = deadline - perf_counter()
            if remaining > 0:
                sleep(remaining)
            elif remaining < -config.MAX_FRAME_DT:
                deadline = perf_counter()
        return frames

    def close(self):
        self.assets.release()
