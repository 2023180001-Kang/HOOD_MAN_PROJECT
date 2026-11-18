"""Main game loop and shared-resource lifetime."""

import ctypes
from time import perf_counter, sleep

import pico2d
from pico2d import pico2d as backend
from sdl2 import SDL_Event, SDL_PollEvent, SDL_WINDOWEVENT, SDL_WINDOWEVENT_FOCUS_LOST

import config
from assets import Assets
from effects import SpriteAfterimage
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
    pico2d.SDLK_F4: "toggle_floor_bounds",
    pico2d.SDLK_u: "toggle_details",
    pico2d.SDLK_g: "weapon_interact",
}
KEYS.update({getattr(pico2d, f"SDLK_{key}"): f"combat_{key}"
             for key, *_ in config.COMBAT_MOVE_SPECS})
KEYS.update({getattr(pico2d, f"SDLK_{key}"): f"combat_{key}"
             for key, *_ in config.STRONG_MOVE_SPECS})
KEYS.update({getattr(pico2d, f"SDLK_{key}"): f"counter_{key}"
             for key, *_ in config.COUNTER_MOVE_SPECS})
KEYS.update({getattr(pico2d, f"SDLK_{prefix}{count}"): f"spawn_{count}"
             for count in config.SPAWN_COUNTS for prefix in ("", "KP_")})


class Game:
    def __init__(self):
        self.assets = Assets()
        self.ui = UI()
        self.world = World()
        self.running = True
        pico2d.SDL_SetWindowTitle(backend.window, b"HOOD_MAN_PROJECT")

    def handle_events(self, *, title_screen=False):
        # pico2d.get_events filters out focus events, so poll its SDL event queue
        # directly to prevent stuck keys after Alt+Tab or clicking another window.
        event = SDL_Event()
        while SDL_PollEvent(ctypes.byref(event)):
            if event.type == pico2d.SDL_QUIT:
                self.running = False
            elif event.type == SDL_WINDOWEVENT and event.window.event == SDL_WINDOWEVENT_FOCUS_LOST:
                self.world.controls.held.clear()
                self.world.controls.pressed.clear()
            elif not title_screen and event.type in (pico2d.SDL_KEYDOWN, pico2d.SDL_KEYUP):
                key = KEYS.get(event.key.keysym.sym)
                if key is not None:
                    if event.type == pico2d.SDL_KEYDOWN and not event.key.repeat:
                        self.world.controls.press(key)
                    elif event.type == pico2d.SDL_KEYUP:
                        self.world.controls.release(key)

    def draw_title_screen(self, present=True):
        pico2d.clear_canvas()
        self.assets.images[config.TITLE_IMAGE].draw(
            config.SCREEN_WIDTH / 2, config.SCREEN_HEIGHT / 2,
            config.SCREEN_WIDTH, config.SCREEN_HEIGHT,
        )
        if present:
            pico2d.update_canvas()

    def show_title_screen(self):
        if not self.running:
            return
        self.draw_title_screen()
        deadline = perf_counter() + config.TITLE_SCREEN_DURATION
        while self.running:
            # Consume title inputs without advancing gameplay or skipping the wait.
            self.handle_events(title_screen=True)
            remaining = deadline - perf_counter()
            if not self.running or remaining <= 0:
                break
            self.draw_title_screen()
            sleep(min(1 / config.TARGET_FPS, remaining))

    def update(self, dt):
        # Presentation remains toggleable while gameplay is loading or dead.
        if self.world.controls.take_press("toggle_details"):
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
        # Stable depth sorting puts older echoes behind newer ones and the
        # live actors on the same floor, without sorting by airborne height.
        sprites = [(image.ground_y, image, image.image_name, image.opacity)
                   for image in self.world.afterimages]
        sprites.extend((enemy.ground_y, enemy, enemy.sprite_image, enemy.opacity)
                       for enemy in self.world.enemies)
        sprites.append((player.ground_y, player, player.sprite_image, 1.0))
        sprites.extend((item.ground_y, item, item.image_name, 1.0)
                       for item in self.world.stage.drop_items if not item.grounded)
        traffic = self.world.stage.traffic
        if traffic is not None and traffic.car is not None:
            sprites.append((traffic.car.ground_y, traffic.car, config.CAR_IMAGE, 1.0))
        for _, actor, image, opacity in sorted(sprites, key=lambda entry: entry[0], reverse=True):
            if image == config.CAR_IMAGE:
                self.assets.draw_car(actor, camera_x, camera_y)
            elif image in config.DROP_ITEM_IMAGES.values():
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
        for effect in self.world.effects:
            self.assets.draw_hit_effect(effect, camera_x, camera_y)
        self.ui.draw_enemy_health(self.assets, self.world, camera_x, camera_y)
        self.ui.draw_pickup_prompt(self.assets, self.world, camera_x, camera_y)
        self.ui.draw(self.assets, self.world)
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
