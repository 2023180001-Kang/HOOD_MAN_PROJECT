import unittest

import pico2d

import config
from drop_items import DropItem
from enemy02 import leap_height
from final_boss import FinalBoss
from projectiles import EnemyKnifeProjectile, RifleBullet
from tests.helpers import ManualSpawnWorld, advance, tap
from tests.test_main_menu import process_menu_events
from tests.test_menu_return import key_event, scene


def arena(gap=300):
    world = ManualSpawnWorld()
    world.select_stage(config.STAGE_IMAGES.index(config.BOSS_STAGE_IMAGES[0]))
    world.stage.drop_items.clear()
    world.player.x = world.player.previous_x = 1200
    boss = FinalBoss(1200 - gap, 1 if gap >= 0 else -1, ground_y=world.player.ground_y)
    world.enemies.append(boss)
    return world, boss


class FinalBossTests(unittest.TestCase):
    def test_b_then_number_spawns_on_every_campaign_map_and_training_has_its_own_selection(self):
        game = scene()
        world = game.world

        def press(key):
            process_menu_events(game, key_event(key), key_event(key, down=False), menu_screen=False)
            world.step(config.FIXED_DT)

        for index, stage in enumerate(config.STAGE_IMAGES):
            world.reset(stage_index=index)
            for key, count in ((pico2d.SDLK_2, 2), (pico2d.SDLK_KP_3, 3)):
                with self.subTest(stage=stage, key=key):
                    before = len(world.enemies)
                    press(pico2d.SDLK_b)
                    press(key)
                    spawned = world.enemies[before:]
                    self.assertEqual([type(e) for e in spawned], [FinalBoss] * count)
                    self.assertTrue(all(e.hp == e.max_hp == 400 for e in spawned))
        world.training = True
        world.reset()
        press(pico2d.SDLK_KP_8)
        press(pico2d.SDLK_KP_PLUS)
        boss = world.stage.target
        self.assertIsInstance(boss, FinalBoss)
        self.assertEqual((boss.animation.row, boss.hp), (6, 400))
        advance(world, 7)
        self.assertEqual((world.player.hp, boss.ammo, boss.reserve_magazines), (100, 0, 0))

    def test_two_magazines_fire_in_locked_lanes_with_one_reload_then_melee(self):
        for facing in (-1, 1):
            world, boss = arena(360 * facing)
            player = world.player
            world.step(config.FIXED_DT)
            for magazine in range(2):
                if magazine:
                    # Let the second magazine acquire a target in the opposite direction.
                    player.x, player.ground_y = boss.x + 360 * -facing, boss.ground_y
                    for _ in range(121):
                        if boss.state != "RELOAD":
                            break
                        world.step(config.FIXED_DT)
                    self.assertEqual(boss.state, "IDLE")
                    world.step(config.FIXED_DT)
                line = boss.aim_line
                self.assertIsNotNone(line)
                direction = facing if magazine == 0 else -facing
                self.assertEqual((boss.animation.row, boss.ammo, boss.facing), (6, 20, direction))
                # Leave the depth lane and cross behind the shooter during the warning.
                player.ground_y -= 80
                player.x = boss.x - 300 * direction
                for tick in range(1, 120):
                    world.step(config.FIXED_DT)
                    self.assertEqual(boss.aim_line, line)
                    self.assertEqual(boss.ammo, 20)
                    if tick in (16, 31, 46, 119):
                        self.assertEqual(boss.animation.frame, min(3, tick // 15))
                for round_number in range(20):
                    world.step(config.FIXED_DT)
                    bullet = world.projectiles[-1]
                    self.assertIs(type(bullet), RifleBullet)
                    self.assertEqual((bullet.y, bullet.facing, bullet.damage, bullet.image_name),
                                     (line[1], direction, 10, config.RIFLE_BULLET_IMAGE))
                    self.assertEqual(bullet.x, line[0] + direction * bullet.half_width)
                    self.assertEqual(boss.ammo, 19 - round_number)
                    self.assertIsNone(boss.aim_line)
                    for _ in range(11):
                        world.step(config.FIXED_DT)
                        self.assertEqual(boss.ammo, 19 - round_number)
                world.step(config.FIXED_DT)
                self.assertEqual((boss.state, boss.animation.row),
                                 ("RELOAD", 7) if magazine == 0 else ("IDLE", 1))
            self.assertEqual((boss.reserve_magazines, player.hp), (0, config.MAX_HP))
            player.x, player.ground_y = boss.x + 85, boss.ground_y
            advance(world, 0.6)
            self.assertEqual((boss.animation.row, player.hp), (4, config.MAX_HP - 40))

    def test_hit_stun_resumes_the_single_reload_without_extra_ammo(self):
        world, boss = arena()
        advance(world, 3.5)
        self.assertEqual((boss.state, boss.ammo, boss.reserve_magazines), ("RELOAD", 0, 1))
        reload_frame = boss.animation.frame
        boss.take_damage(10)
        self.assertEqual((boss.animation.row, boss.hp), (11, 390))
        for _ in range(120):
            world.step(config.FIXED_DT)
            if boss.state == "RELOAD":
                break
        self.assertEqual((boss.state, boss.animation.frame), ("RELOAD", reload_frame))
        advance(world, 0.6)
        self.assertEqual((boss.state, boss.ammo, boss.reserve_magazines), ("AIM", 20, 0))
        boss.take_damage(400)
        advance(world, 1)
        self.assertEqual((boss.state, boss.animation.row, boss.ammo), ("DEAD", 12, 20))

    def test_fifth_throw_frame_emits_one_knife_that_hits_falls_and_can_be_reused(self):
        for direction, player_picks_up in ((1, True), (-1, False)):
            world, boss = arena(180 * direction)
            boss.ammo = boss.reserve_magazines = 0
            for _ in range(100):
                world.step(config.FIXED_DT)
                if world.projectiles:
                    break
                self.assertEqual(boss.animation.row, 9)
                self.assertLess(boss.animation.frame, 4)
            knife, = world.projectiles
            self.assertIsInstance(knife, EnemyKnifeProjectile)
            self.assertEqual((boss.animation.frame, knife.facing, knife.image_name),
                             (4, direction, config.KNIFE_PROJECTILE_IMAGE))
            self.assertFalse(boss.has_knife)
            self.assertIsNone(boss.take_projectile())
            advance(world, knife.straight_duration)
            self.assertEqual(world.player.hp, config.MAX_HP - 40)
            self.assertTrue(knife.falling)
            self.assertEqual(knife.height, knife.release_offset[1] * config.SPRITE_SCALE)
            advance(world, 0.5)
            item, = world.stage.drop_items
            self.assertTrue(item.grounded)
            self.assertEqual((item.kind, item.floor), ("combat_knife", boss.floor))
            if player_picks_up:
                world.player.x, world.player.ground_y = item.x, item.ground_y
                tap(world.controls, "weapon_interact")
                world.step(config.FIXED_DT)
                self.assertEqual(world.player.weapon, "combat_knife")
                self.assertFalse(boss.has_knife)
            else:
                world.player.x = boss.x - 800 * direction
                for _ in range(720):
                    world.step(config.FIXED_DT)
                    if boss.has_knife:
                        break
                self.assertTrue(boss.has_knife)
                self.assertEqual(boss.death_drop_kind, "combat_knife")
                rows = []
                for _ in range(4):
                    boss.start_attack()
                    rows.append(boss.animation.row)
                self.assertEqual(set(rows), {4, 5, 8, 9})
            self.assertNotIn(item, world.stage.drop_items)

    def test_unarmed_boss_stays_in_melee_even_with_a_knife_underfoot(self):
        world, boss = arena(90)
        world.player.invincible = True
        boss.ammo = boss.reserve_magazines = 0
        nearby_knife = DropItem("combat_knife", boss.x, boss.ground_y)
        world.stage.drop_items.append(nearby_knife)
        for _ in range(600):
            world.step(config.FIXED_DT)
            if not boss.has_knife:
                break
        self.assertFalse(boss.has_knife)
        self.assertEqual((boss.animation.row, boss.animation.frame), (9, 4))

        # Let the original throw finish, then observe complete unarmed attack cycles.
        advance(world, 0.4)
        rows = []
        for _ in range(1200):
            world.step(config.FIXED_DT)
            self.assertFalse(boss.has_knife)
            self.assertIn(nearby_knife, world.stage.drop_items)
            if boss.state == "ATTACK" and (not rows or rows[-1] != boss.animation.row):
                rows.append(boss.animation.row)
        self.assertEqual(set(rows), {4, 5, 10})
        self.assertGreaterEqual(rows.count(10), 2)

    def test_distant_bosses_split_pursuit_and_recovery_until_player_returns(self):
        splits = set()
        for seed in range(6):
            world, first = arena(800)
            world.stage.route_rng.seed(seed)
            for i in range(3):
                world.enemies.append(FinalBoss(first.x + (i + 1) * 32, ground_y=first.ground_y))
            for boss in world.enemies:
                boss.has_knife = False
                boss.ammo = boss.reserve_magazines = 0
                world.stage.drop_items.append(DropItem("combat_knife", boss.x - 220, boss.ground_y))
            origins = [boss.x for boss in world.enemies]
            world.step(config.FIXED_DT)
            seekers = tuple(i for i, boss in enumerate(world.enemies) if boss.x < origins[i])
            pursuers = [boss for i, boss in enumerate(world.enemies) if i not in seekers]
            self.assertTrue(seekers and pursuers)
            splits.add(seekers)
            goals = [world.enemies[i].navigation_target for i in seekers]
            self.assertEqual(len(set(goals)), len(goals))
            for _ in range(12):
                world.step(config.FIXED_DT)
                for i in seekers:
                    self.assertLess(world.enemies[i].vx, 0)
                for boss in pursuers:
                    self.assertGreater(boss.vx, 0)
                    self.assertIsNone(boss.navigation_target)
            seeker = world.enemies[seekers[0]]
            world.player.x, world.player.ground_y = seeker.x + 100, seeker.ground_y
            world.step(config.FIXED_DT)
            self.assertIsNone(seeker.navigation_target)
            self.assertFalse(seeker.has_knife)
        self.assertGreater(len(splits), 1)

    def test_melee_hits_once_per_move_and_slam_matches_double_jump_apex(self):
        world, boss = arena(90)
        boss.ammo = boss.reserve_magazines = 0
        player = world.player
        for row, damage in ((4, 40), (5, 50), (8, 30)):
            boss.start_attack()
            self.assertEqual((boss.animation.row, boss.attack_damage), (row, damage))
            boss.animation.elapsed = (4 + 0.1) / boss.attack_fps
            hp = player.hp
            self.assertTrue(boss.try_hit(player))
            self.assertFalse(boss.try_hit(player))
            self.assertEqual(player.hp, hp - damage)
        world, boss = arena(420)
        boss.ammo = boss.reserve_magazines = 0
        peak, active_rows = 0, set()
        for _ in range(240):
            world.step(config.FIXED_DT)
            if boss.state == "ATTACK":
                active_rows.add(boss.animation.row)
            peak = max(peak, boss.jump_height)
            if peak and boss.state == "IDLE":
                break
        self.assertEqual(active_rows, {10})
        self.assertAlmostEqual(peak, leap_height(), delta=0.1)
        self.assertEqual(world.player.hp, config.MAX_HP - 60)
