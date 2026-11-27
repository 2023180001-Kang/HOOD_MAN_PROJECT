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
        self.assertFalse(self.world.training)
        self.assertEqual(len(self.world.enemies), 4)
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
        player.x = target.x - 350
        advance(self.world, 3)
        self.assertEqual((target.x, target.y, target.state), (*position, "IDLE"))
        self.assertEqual(player.hp, config.MAX_HP)

    def test_number_then_plus_summons_the_matching_enemy_and_it_attacks_only_nearby(self):
        cases = (
            (config.ENEMY_IMAGE, 20, 200, 5), (config.ENEMY02_IMAGE, 30, 200, 6),
            (config.AXE_ENEMY_IMAGE, 40, 400, 5), (config.RESEARCHER_IMAGE, 30, 200, 6),
            (config.SHIELD_SOLDIER_IMAGE, 40, 400, 6), (config.AR_SOLDIER_IMAGE, 5, 300, 5),
            (config.SWORD_ENEMY_IMAGE, 30, 200, 6),
        )
        for number, (image, damage, hp, hit_row) in enumerate(cases, 1):
            with self.subTest(number=number):
                self.press("restart")
                player = self.world.player
                previous = self.world.stage.target
                prefix = "KP_" if number % 2 == 0 else ""
                key = getattr(pico2d, f"SDLK_{prefix}{number}")
                process_menu_events(self.game, key_event(key), key_event(key, down=False), menu_screen=False)
                self.world.update(config.FIXED_DT)
                self.assertIs(self.world.stage.target, previous)
                self.press("training_target")
                target, = self.world.enemies
                self.assertEqual((target.sprite_image, target.attack_damage, target.hp, target.max_hp),
                                 (image, damage, hp, hp))
                position = target.x, target.y
                player.x = target.x - 350
                advance(self.world, 3)
                self.assertEqual((target.x, target.y, target.state), (*position, "IDLE"))
                self.assertEqual(self.world.player.hp, config.MAX_HP)
                self.assertFalse(self.world.projectiles)
                player.x = target.x + 85
                player.ground_y = target.ground_y + 50
                advance(self.world, 1)
                self.assertEqual(player.hp, config.MAX_HP)
                player.ground_y = target.ground_y
                for _ in range(240):
                    self.world.step(config.FIXED_DT)
                    if player.hp < config.MAX_HP:
                        break
                self.assertEqual((player.hp, target.facing), (config.MAX_HP - damage, 1))
                self.assertEqual((target.x, target.y), position)
                number_hit, = self.world.damage_numbers
                self.assertTrue(number_hit.on_player)
                self.assertEqual((number_hit.damage, number_hit.x), (damage, player.x))
                player.x = target.x - 350
                bullet = PlayerPistolBullet(target.x, target.ground_y, 60, 1)
                self.world.projectiles.append(bullet)
                self.world.update_projectiles(0)
                self.assertEqual((self.world.damage_numbers[-1].damage, target.hp), (20, hp - 20))
                self.assertEqual((target.sprite_image, target.animation.row), (image, hit_row))
                target.take_damage(hp * 2)
                self.assertEqual((target.hp, target.last_hit_damage), (1, hp * 2))
                player.ground_y = target.ground_y - config.ATTACK_DEPTH_TOLERANCE - 1
                advance(self.world, 2)
                self.assertEqual(target.state, "IDLE")

    def test_practice_axe_throws_after_retreat_and_shows_unarmed_damage_until_recovery(self):
        self.press("spawn_3")
        self.press("training_target")
        enemy = self.world.stage.target
        player = self.world.player
        with patch.object(enemy.rng, "random", return_value=0):
            advance(self.world, 0.55)
            self.assertEqual(player.hp, 460)
            player.x = enemy.x - 350
            advance(self.world, 1.2)
            self.assertFalse(enemy.armed)
            assets = Mock()
            with patch("pico2d.draw_rectangle"):
                self.game.ui.draw(assets, self.world)
            labels = [call.args[2] for call in assets.font.draw.call_args_list]
            self.assertIn("공격력   주먹 15 / 발차기 20", labels)
            advance(self.world, 0.4)
            self.assertEqual(player.hp, 410)
            advance(self.world, 4)
        self.assertTrue(enemy.armed)
        self.assertEqual(enemy.sprite_image, config.AXE_ENEMY_IMAGE)
        self.assertFalse(any(item.axe_owner is enemy for item in self.world.stage.drop_items))

    def test_practice_player_survives_repeated_hits_and_guard_reduces_displayed_damage(self):
        player = self.world.player
        player.hp = 2
        player.equip_weapon("shield_item")
        self.press("combat_s")
        self.press("spawn_6")
        self.press("training_target")
        advance(self.world, 2)
        self.assertEqual((player.hp, player.state), (1, "GUARD"))
        hits = [n.damage for n in self.world.damage_numbers if n.on_player]
        self.assertGreater(len(hits), 1)
        self.assertTrue(all(damage == 2.5 for damage in hits))
        self.launch("game_start")
        self.assertTrue(self.world.player.take_damage(config.MAX_HP))
        self.assertEqual(self.world.player.state, "DYING")

    def test_selection_and_summon_follow_event_order_in_one_batch(self):
        for key in (pico2d.SDLK_2, pico2d.SDLK_PLUS, pico2d.SDLK_6, pico2d.SDLK_PLUS,
                    pico2d.SDLK_KP_7, pico2d.SDLK_KP_PLUS, pico2d.SDLK_2):
            process_menu_events(self.game, key_event(key), key_event(key, down=False), menu_screen=False)
        self.world.update(config.FIXED_DT)
        target, = self.world.enemies
        self.assertEqual(target.sprite_image, config.SWORD_ENEMY_IMAGE)
        self.press("training_target")
        self.assertEqual(self.world.stage.target.sprite_image, config.ENEMY02_IMAGE)
        self.press("restart")
        self.assertIsNone(self.world.stage.target)
        self.press("training_target")
        self.assertEqual(self.world.stage.target.sprite_image, config.ENEMY_IMAGE)

    def test_repeated_melee_and_projectile_hits_show_full_damage_and_never_kill(self):
        self.press("training_target")
        target, = self.world.enemies
        position = target.x, target.y
        for move in [MOVES["combat_f"]] * 5 + [STRONG_MOVES["combat_e"]]:
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
        self.assertEqual((target.hp, target.x, target.y), (1, *position))
        self.assertTrue(target.alive)

    def test_held_w_hits_once_without_carrying_or_displacing_the_target(self):
        self.press("training_target")
        target, = self.world.enemies
        position = target.x, target.y
        self.press("combat_w")
        advance(self.world, 0.4)
        self.assertEqual([n.damage for n in self.world.damage_numbers], [STRONG_MOVES["combat_w"].damage])
        advance(self.world, 0.8)
        self.assertEqual(self.world.player.air_kick_phase, "WAIT")
        self.assertEqual((target.x, target.y, target.jump_height), (*position, 0))

    def test_training_guide_hp_and_damage_stay_visible_with_campaign_details_hidden(self):
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
        for word in ("조작법 익히기", "1~7", "7  검병", "이단 점프", "G", "+", "Esc", "왼손 잽", "주인공 HP  500 / 500",
                     "소환된 적  ·  쇠몽둥이", "공격력   20", "현재 HP  180", "최대 HP  200", "-10", "+10",
                     "HP 전체 복구", "적용", "시작 HP  500 / 500"):
            self.assertIn(word, texts)

    def test_left_hp_controls_are_independent_and_full_restore_works_without_a_target(self):
        def click(x, button=pico2d.SDL_BUTTON_LEFT):
            event = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, x, 465, button)
            process_menu_events(self.game, event, menu_screen=False)

        player = self.world.player
        click(400)
        self.assertEqual((player.hp, player.max_hp), (490, 500))
        click(480)
        click(480)
        self.assertEqual((player.hp, player.max_hp), (510, 520))
        assets = Mock()
        with patch("pico2d.draw_rectangle"):
            self.game.ui.draw(assets, self.world)
        self.assertIn("주인공 HP  510 / 520", [call.args[2] for call in assets.font.draw.call_args_list])
        player.hp = 6
        click(400)
        self.assertEqual(player.hp, 1)
        click(480)
        self.assertEqual(player.hp, 11)
        click(600, SDL_BUTTON_RIGHT)
        self.assertEqual(player.hp, 11)
        click(600)
        self.assertEqual((player.hp, player.max_hp), (530, 530))
        self.press("training_target")
        enemy = self.world.stage.target
        enemy.take_damage(50)
        click(400)
        self.assertEqual((enemy.hp, enemy.max_hp, player.hp), (150, 200, 520))
        click(600)
        self.assertEqual((enemy.hp, player.hp), (150, 530))
        self.assertFalse(self.world.damage_numbers)
        self.press("restart")
        self.assertEqual((self.world.player.hp, self.world.player.max_hp), (500, 500))
        click(480)
        self.assertEqual((self.world.player.hp, self.world.player.max_hp), (510, 510))
        self.launch("game_start")
        self.assertEqual((self.world.player.hp, self.world.player.max_hp), (500, 500))

    def test_apply_sets_current_and_max_campaign_hp_until_applied_again(self):
        def click(x, button=pico2d.SDL_BUTTON_LEFT):
            event = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, x, 465, button)
            process_menu_events(self.game, event, menu_screen=False)

        click(480)
        click(480)
        click(400)
        click(726, SDL_BUTTON_RIGHT)
        self.assertEqual((self.world.starting_hp, self.world.starting_max_hp), (500, 500))
        click(726)
        click(480)
        assets = Mock()
        with patch("pico2d.draw_rectangle"):
            self.game.ui.draw(assets, self.world)
        labels = [call.args[2] for call in assets.font.draw.call_args_list]
        self.assertIn("주인공 HP  520 / 530", labels)
        self.assertIn("시작 HP  510 / 520", labels)

        self.launch("game_start")
        player = self.world.player
        self.assertEqual((player.hp, player.max_hp), (510, 520))
        self.assertTrue(player.take_damage(20))
        self.world.select_stage(1)
        self.assertEqual((player.hp, player.max_hp), (490, 520))
        self.press("restart")
        self.assertEqual((self.world.player.hp, self.world.player.max_hp), (510, 520))

        self.launch("controls")
        click(726)
        self.launch("game_start")
        self.assertEqual((self.world.player.hp, self.world.player.max_hp), (500, 500))

    def test_applied_enemy_hp_follows_each_type_through_campaign_spawns_and_restart(self):
        plus = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, 1190, 410)
        apply = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, 1190, 368)
        expected = []
        for number in range(1, 8):
            self.press(f"spawn_{number}")
            self.press("training_target")
            target = self.world.stage.target
            base = target.max_hp
            target.take_damage(number)
            self.press(f"spawn_{number % 7 + 1}")  # Only the next summon changes.
            process_menu_events(self.game, *([plus] * number), apply, plus, menu_screen=False)
            expected.append((base + 9 * number, base + 10 * number))

        self.launch("game_start")
        self.assertEqual((self.world.player.hp, self.world.player.max_hp), (500, 500))
        for index, hp_pair in enumerate(expected[:6]):
            self.world.select_stage(index * 2)
            advance(self.world, 1)
            self.press("spawn_2")
            self.assertEqual([(e.hp, e.max_hp) for e in self.world.enemies], [hp_pair] * 6)

        self.press("cycle_spawn_enemy")  # Summon the first map's thug on the AR map.
        self.press("spawn_1")
        thug = self.world.enemies[-1]
        self.assertEqual((thug.hp, thug.max_hp), expected[0])
        self.press("sword_spawn")
        self.press("spawn_2")
        self.assertEqual([(e.hp, e.max_hp) for e in self.world.enemies[-2:]], [expected[6]] * 2)
        thug.take_damage(30)
        self.press("restart")
        self.press("spawn_1")
        fresh = self.world.enemies[-1]
        self.assertEqual((fresh.hp, fresh.max_hp), expected[0])

    def test_enemy_hp_apply_is_explicit_and_restore_can_revert_the_campaign_setting(self):
        def click(x, y, button=pico2d.SDL_BUTTON_LEFT):
            event = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, x, y, button)
            process_menu_events(self.game, event, menu_screen=False)

        click(1190, 368)  # No summoned target.
        self.press("training_target")
        click(1100, 410)
        click(1190, 368, SDL_BUTTON_RIGHT)
        self.launch("game_start")
        self.press("spawn_1")
        self.assertEqual(self.world.enemies[0].hp, 200)

        self.launch("controls")
        self.press("training_target")
        click(1100, 410)
        self.world.stage.target.take_damage(25)
        click(1190, 368)
        click(1190, 410)
        assets = Mock()
        with patch("pico2d.draw_rectangle"):
            self.game.ui.draw(assets, self.world)
        labels = [call.args[2] for call in assets.font.draw.call_args_list]
        self.assertIn("적 시작 HP  165 / 190", labels)
        self.assertIn("현재 HP  175     최대 HP  200", labels)

        self.press("restart")
        self.press("training_target")
        target = self.world.stage.target
        self.assertEqual((target.hp, target.max_hp), (165, 190))
        click(1100, 368)
        click(1190, 368)
        self.launch("game_start")
        self.press("spawn_1")
        fresh = self.world.enemies[-1]
        self.assertEqual((fresh.hp, fresh.max_hp), (200, 200))

    def test_left_attack_values_follow_weapon_pickup_and_return(self):
        assets = Mock()
        player = self.world.player

        def attack_text():
            assets.font.draw.reset_mock()
            with patch("pico2d.draw_rectangle"):
                self.game.ui.draw(assets, self.world)
            return " ".join(call.args[2] for call in assets.font.draw.call_args_list
                            if call.args[0] < config.SCREEN_WIDTH / 2)

        self.assertIn("A  왼손 잽  10", attack_text())
        for item in list(self.world.stage.drop_items):
            with self.subTest(weapon=item.kind):
                player.x, player.ground_y = item.x, item.ground_y
                self.press("weapon_interact")
                text = attack_text()
                self.assertIn(f"주인공 공격력  ·  {config.WEAPON_NAMES[item.kind]}", text)
                if item.kind in config.FIREARM_MAGAZINE_SIZES:
                    self.assertIn("20 / 발", text)
                    self.assertIn("S 방향 고정", text)
                else:
                    for move in player.moves.values():
                        self.assertIn(f"{move.key.upper()}  {move.name}  {move.damage}", text)
                if item.kind == "axe":
                    self.assertIn("D 내려찍기  40", text)
                self.press("weapon_interact")
                self.assertIn("주인공 공격력  ·  맨손", attack_text())

    def test_incoming_damage_is_drawn_over_the_player_and_blocked_hits_show_no_number(self):
        player = self.world.player
        player.hp = 1
        player.invincible = True
        self.press("training_target")
        advance(self.world, 1)
        self.assertFalse(self.world.damage_numbers)
        player.invincible = False
        for _ in range(240):
            self.world.step(config.FIXED_DT)
            if self.world.damage_numbers:
                break
        assets = Mock()
        self.game.ui.draw_enemy_health(assets, self.world, 0, 0)
        x, y, label, color = assets.damage_font.draw.call_args.args
        self.assertEqual((label, color, player.hp), ("-20", (255, 143, 143), 1))
        self.assertLess(abs(x - player.x), 20)
        self.assertGreater(y, player.body.top)

    def test_restore_button_recovers_the_summoned_enemy_in_place(self):
        click = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, 1100, 368)
        process_menu_events(self.game, click, menu_screen=False)
        self.assertIsNone(self.world.stage.target)
        for number in range(1, 8):
            with self.subTest(number=number):
                self.press(f"spawn_{number}")
                self.press("training_target")
                target, = self.world.enemies
                original_hp = target.max_hp
                adjust_x = 1190 if number % 2 else 1100
                process_menu_events(self.game, mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, adjust_x, 410),
                                    menu_screen=False)
                self.assertNotEqual(target.max_hp, original_hp)
                target.take_damage(original_hp * 2)
                self.press(f"spawn_{number % 7 + 1}")
                process_menu_events(self.game, mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, 1100, 368, SDL_BUTTON_RIGHT),
                                    menu_screen=False)
                self.assertEqual(target.hp, 1)
                process_menu_events(self.game, click, click, menu_screen=False)
                self.assertEqual(self.world.enemies, [target])
                self.assertEqual((target.hp, target.max_hp), (original_hp, original_hp))

    def test_hp_buttons_adjust_only_the_displayed_target_and_never_kill(self):
        plus = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, 1190, 410)
        minus = mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, 1100, 410)
        process_menu_events(self.game, plus, menu_screen=False)
        self.assertIsNone(self.world.stage.target)
        self.press("spawn_2")
        self.press("training_target")
        target = self.world.stage.target
        target.take_damage(30)
        self.press("spawn_6")
        process_menu_events(self.game, plus, plus, minus, menu_screen=False)
        self.assertEqual((target.hp, target.max_hp), (180, 210))
        for event in (mouse_event(pico2d.SDL_MOUSEMOTION, 1190, 410),
                      mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, 1190, 410, SDL_BUTTON_RIGHT),
                      mouse_event(pico2d.SDL_MOUSEBUTTONDOWN, 1190, 450)):
            process_menu_events(self.game, event, menu_screen=False)
        self.assertEqual((target.hp, target.max_hp), (180, 210))
        assets = Mock()
        with patch("pico2d.draw_rectangle"):
            self.game.ui.draw(assets, self.world)
        texts = [call.args[2] for call in assets.font.draw.call_args_list]
        self.assertIn("소환된 적  ·  쌍몽둥이", texts)
        self.assertIn("공격력   타격 30   /   내려찍기 50", texts)
        self.assertIn("현재 HP  180     최대 HP  210", texts)
        process_menu_events(self.game, *([minus] * 25), menu_screen=False)
        self.assertEqual((target.hp, target.max_hp), (1, 1))
        projectile = SteelClubProjectile(target.x, target.ground_y, 60, 1)
        self.world.projectiles.append(projectile)
        self.world.update_projectiles(0)
        self.assertEqual((target.hp, self.world.damage_numbers[-1].damage), (1, 50))
        process_menu_events(self.game, plus, menu_screen=False)
        self.assertEqual((target.hp, target.max_hp), (11, 11))
        advance(self.world, 2)  # Let the piercing club fly past the summon point.
        self.press("training_target")
        target = self.world.stage.target
        self.assertEqual((target.opponent.name, target.hp, target.max_hp), ("AR 소총", 300, 300))
