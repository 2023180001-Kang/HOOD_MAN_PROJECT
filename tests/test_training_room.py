import unittest
from unittest.mock import Mock, patch

import pico2d
from sdl2 import SDL_BUTTON_RIGHT

import config
from combat import MOVES, STRONG_MOVES
from enemy import Enemy
from projectiles import PlayerPistolBullet, SteelClubProjectile
from tests.helpers import advance, tap
from tests.test_main_menu import mouse_event, process_menu_events
from tests.test_menu_return import click_event, key_event, scene


class TrainingRoomTests(unittest.TestCase):
    def setUp(self):
        self.game = scene()
        self.world = self.game.world
        self.launch("controls")

    def launch(self, action):
        button = next(b for b in self.game.menu.main_buttons if b.action == action)
        with patch.object(self.game, "draw_main_menu"), patch.object(
            self.game, "handle_events", side_effect=lambda **kw: process_menu_events(self.game, click_event(button))
        ):
            self.game.show_main_menu()

    def press(self, key):
        tap(self.world.controls, key)
        self.world.update(config.FIXED_DT)

    def test_back_arrow_requests_menu_only_on_left_click_in_training(self):
        back = self.game.menu.bag_back_button
        move = mouse_event(pico2d.SDL_MOUSEMOTION, back.x, back.y)
        right_click = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, back.x, back.y, SDL_BUTTON_RIGHT)
        outside = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, back.x + back.width, back.y)
        process_menu_events(self.game, move, right_click, menu_screen=False)
        self.assertIs(self.game.menu.hovered_button, back)
        process_menu_events(self.game, outside, menu_screen=False)
        self.assertIsNone(self.game.menu.hovered_button)
        self.assertFalse(self.game._menu_requested)
        self.world.controls.press("right")
        process_menu_events(self.game, click_event(back), key_event(pico2d.SDLK_a), menu_screen=False)
        self.assertTrue(self.game._menu_requested)
        self.assertFalse(self.world.controls.held or self.world.controls.pressed)
        self.launch("game_start")
        process_menu_events(self.game, click_event(back), menu_screen=False)
        self.assertFalse(self.game._menu_requested)

    def test_whole_floor_in_fixed_view_and_campaign_starts_separately(self):
        stage, player = self.world.stage, self.world.player
        self.assertEqual(stage.image_name, config.TRAINING_ROOM_IMAGE)
        self.assertEqual(stage.walkable.bounds, (0, 0, 1280, 300))
        for x in (-300, 1800):
            for y in (-100, 450):
                player.x, player.ground_y = x, y
                self.world.update(config.FIXED_DT)
                self.assertEqual(player.ground_y, 0 if y < 0 else 300)
                self.assertEqual(player.x, player.boundary_padding if x < 0 else 1280 - player.boundary_padding)
                self.assertEqual((self.world.camera.render_x, self.world.camera.render_y), (0, 0))
        for key in ("stage_exits", "cycle_spawn_enemy", "spawn_9"):
            self.press(key)
        self.assertFalse(stage.arrow_sides or stage.enemies)
        self.press("restart")
        self.assertTrue(self.world.training)
        self.assertEqual(len(self.world.stage.drop_items), 6)
        process_menu_events(self.game, key_event(), menu_screen=False)
        self.assertTrue(self.game._menu_requested)
        self.launch("game_start")
        self.press("training_target")
        self.assertFalse(self.world.training or self.world.enemies)
        self.assertEqual(self.world.stage.image_name, config.STAGE_IMAGE)
        self.assertEqual(len(self.world.stages), len(config.STAGE_IMAGES))

    def test_table_items_are_visible_at_table_height_and_reachable_from_the_floor(self):
        items = list(self.world.stage.drop_items)
        self.assertCountEqual([i.kind for i in items],
                              ["steel_pipe", "combat_knife", "steel_club", "axe", "pistol", "ar_rifle"])
        for item in items:
            self.assertTrue(item.grounded)
            self.assertLess(376, item.surface_y)
            self.assertLess(item.surface_y, 399)
            self.world.player.x, self.world.player.ground_y = item.x, item.ground_y - 10
            self.assertIs(self.world.pickup_item, item)
            self.press("weapon_interact")
            self.assertEqual(self.world.player.weapon, item.kind)
            self.assertNotIn(item, self.world.stage.drop_items)
        self.assertEqual({item.kind: (item.x, item.surface_y) for item in self.world.stage.drop_items},
                         {item.kind: (item.x, item.surface_y) for item in items[:-1]})

    def test_g_returns_each_weapon_to_its_display_slot_and_can_pick_it_up_again(self):
        player = self.world.player
        for item in list(self.world.stage.drop_items):
            with self.subTest(kind=item.kind):
                player.x, player.ground_y = item.x + config.WEAPON_PICKUP_RANGE, item.ground_y - 10
                self.press("weapon_interact")
                self.assertEqual(player.weapon, item.kind)
                if item.kind in config.FIREARM_MAGAZINE_SIZES:
                    self.assertEqual(player.firearm_ammo, config.FIREARM_MAGAZINE_SIZES[item.kind])
                    self.press("combat_a")
                    self.world.controls.release("combat_a")
                    advance(self.world, 0.5)
                self.press("weapon_interact")
                self.assertIsNone(player.weapon)
                returned = self.world.pickup_item
                self.assertIsNotNone(returned)
                self.assertEqual((returned.kind, returned.x, returned.ground_y, returned.surface_y),
                                 (item.kind, item.x, item.ground_y, item.surface_y))
                self.press("weapon_interact")
                self.assertEqual(player.weapon, item.kind)
                if item.kind in config.FIREARM_MAGAZINE_SIZES:
                    self.assertEqual(player.firearm_ammo, config.FIREARM_MAGAZINE_SIZES[item.kind] - 1)
                self.press("weapon_interact")
                self.assertEqual(len(self.world.stage.drop_items), 6)

    def test_g_away_from_the_table_still_drops_the_weapon_onto_the_floor(self):
        for kind, x, y in (("steel_pipe", 200, 135), ("axe", 606, 135),
                           ("ar_rifle", 1120, config.TRAINING_TABLE_APPROACH_Y)):
            with self.subTest(kind=kind, x=x, y=y):
                self.press("restart")
                player = self.world.player
                item = next(drop for drop in self.world.stage.drop_items if drop.kind == kind)
                player.x, player.ground_y = item.x, item.ground_y
                self.press("weapon_interact")
                player.x, player.ground_y = x, y
                self.press("weapon_interact")
                dropped, = [drop for drop in self.world.stage.drop_items if drop.kind == item.kind]
                self.assertIsNone(player.weapon)
                self.assertEqual((dropped.x, dropped.support_height), (x, 0))
                self.assertFalse(dropped.grounded)
                advance(self.world, 1)
                self.assertTrue(dropped.grounded)
                self.press("weapon_interact")
                self.assertEqual(player.weapon, kind)

    def test_main_keyboard_and_keypad_plus_summon_one_nearby_thug(self):
        player = self.world.player
        for key, modifier, x, facing in ((pico2d.SDLK_EQUALS, 0, 300, 1),
                                         (pico2d.SDLK_EQUALS, pico2d.KMOD_SHIFT, 1200, 1),
                                         (pico2d.SDLK_KP_PLUS, 0, 70, -1),
                                         (pico2d.SDLK_PLUS, 0, 640, -1)):
            player.x, player.facing = x, facing
            event = key_event(key)
            event.key.keysym.mod = modifier
            process_menu_events(self.game, event, key_event(key, down=False), menu_screen=False)
            self.world.update(config.FIXED_DT)
            if key == pico2d.SDLK_EQUALS and not modifier:
                self.assertFalse(self.world.enemies)
                continue
            target, = self.world.enemies
            self.assertIsInstance(target, Enemy)
            self.assertEqual(target.sprite_image, config.ENEMY_IMAGE)
            self.assertAlmostEqual(abs(target.x - x), 92)
            self.assertEqual(target.ground_y, player.ground_y)
        position = target.x, target.y
        advance(self.world, 3)
        self.assertEqual((target.x, target.y, target.state), (*position, "IDLE"))
        self.assertEqual(player.hp, config.MAX_HP)

    def test_repeated_melee_and_projectile_hits_show_full_damage_and_never_kill(self):
        self.press("training_target")
        target, = self.world.enemies
        position = target.x, target.y
        for move in [MOVES["combat_f"]] * 5 + [STRONG_MOVES["combat_t"]]:
            self.world.player.start_move(move, 1)
            self.world.player.animation.elapsed = min(move.active_frames) / move.fps
            self.world.update(config.FIXED_DT)
            self.assertEqual(self.world.damage_numbers[-1].damage, move.damage)
            self.assertEqual((target.state, target.sprite_image), ("HIT", config.ENEMY_IMAGE))
            advance(self.world, 0.8)
        for projectile, damage in ((PlayerPistolBullet, 20), (SteelClubProjectile, 50)):
            bullet = projectile(target.x, target.ground_y, 60, 1)
            self.world.projectiles.append(bullet)
            self.world.update_projectiles(0)
            self.assertEqual(self.world.damage_numbers[-1].damage, damage)
            self.assertEqual(target.state, "HIT")
        self.assertEqual((target.hp, target.x, target.y), (target.max_hp, *position))
        self.assertTrue(target.alive)

    def test_held_w_hits_once_without_carrying_or_displacing_the_target(self):
        self.press("training_target")
        target, = self.world.enemies
        position = target.x, target.y
        self.press("combat_w")
        advance(self.world, 0.4)
        self.assertEqual([n.damage for n in self.world.damage_numbers], [STRONG_MOVES["combat_w"].damage])
        advance(self.world, 0.8)
        self.assertFalse(self.world.rush.captives)
        self.assertEqual((target.x, target.y, target.jump_height), (*position, 0))

    def test_guide_and_damage_stay_visible_without_drawing_hp(self):
        self.game.ui.details_visible = False
        assets = Mock()
        assets.images = {}  # Accessing the campaign HP texture would fail.
        self.press("training_target")
        self.world.projectiles.append(PlayerPistolBullet(self.world.enemies[0].x,
                                                        self.world.player.ground_y, 60, 1))
        self.world.update_projectiles(0)
        with patch("pico2d.draw_rectangle"):
            self.game.ui.draw_enemy_health(assets, self.world, 0, 0)
            self.game.ui.draw(assets, self.world)
        self.assertEqual(assets.damage_font.draw.call_args.args[2], "-20")
        texts = " ".join(call.args[2] for call in assets.font.draw.call_args_list)
        for word in ("조작법 익히기", "이단 점프", "G", "+", "Esc", "왼손 잽"):
            self.assertIn(word, texts)
