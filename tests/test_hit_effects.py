import unittest

import config
from combat import MOVES
from effects import HitEffect
from enemy import Enemy
from enemy02 import Enemy02
from tests.helpers import advance
from tests.test_counters import attacker, follow_up
from tests.test_enemy02 import at_frame
from traffic import Car
from world import World


def striker(world, side=1):
    enemy = Enemy(world.player.x + side * 80, facing=-side)
    enemy.animation.set_state("ATTACK")
    enemy.animation.elapsed = 4 / config.ENEMY_ANIMATIONS["ATTACK"][1]
    enemy.cooldown = 1
    world.enemies.append(enemy)
    return enemy


class HitEffectTests(unittest.TestCase):
    def test_player_hits_spawn_at_contact_and_effects_follow_world_coordinates(self):
        for facing in (-1, 1):
            world = World()
            enemy = Enemy(config.START_X + facing * 80, -facing)
            enemy.cooldown = 100
            world.enemies = [enemy]
            world.controls.press("left" if facing < 0 else "right")
            world.controls.press("combat_a")
            advance(world, 0.2)
            self.assertEqual(enemy.hp, 190)
            self.assertEqual(len(world.effects), 1)
            self.assertGreater(world.camera.shake_remaining, 0)
            effect = world.effects[0]
            self.assertEqual(effect.image_name, config.PUNCH_KICK_HIT_IMAGE)
            self.assertEqual(effect.facing, facing)
            self.assertGreaterEqual(effect.x, enemy.body.left)
            self.assertLessEqual(effect.x, enemy.body.right)
            self.assertGreaterEqual(effect.y, enemy.body.bottom)
            self.assertLessEqual(effect.y, enemy.body.top)
            position = (effect.x, effect.y)
            world.camera.update(0.05, world.player.x)
            self.assertEqual((effect.x, effect.y), position)
            advance(world, 0.5)
            self.assertEqual(world.effects, [])

    def test_enemy_hit_spawns_one_effect_with_the_incoming_direction(self):
        for side in (-1, 1):
            world = World()
            striker(world, side)
            world.step(config.FIXED_DT)
            self.assertEqual(world.player.hp, 480)
            self.assertEqual(len(world.effects), 1)
            self.assertEqual(world.effects[0].facing, -side)
            self.assertEqual(world.effects[0].image_name, config.CLUB_HIT_IMAGE)
            advance(world, 0.1)
            self.assertEqual(len(world.effects), 1)

    def test_effect_plays_eight_frames_then_expires(self):
        for image_name in config.HIT_EFFECT_IMAGES:
            effect = HitEffect(100, 150, 1, image_name=image_name)
            frames = []
            for _ in range(8):
                frames.append(effect.frame)
                self.assertFalse(effect.finished)
                effect.update(1 / config.HIT_EFFECT_FPS)
            self.assertEqual(frames, list(range(8)))
            self.assertTrue(effect.finished)

    def test_simultaneous_player_and_other_enemy_hits_spawn_both_effects(self):
        world = World()
        victim = Enemy(config.START_X + 80, -1)
        victim.cooldown = 100
        world.enemies = [victim]
        striker(world, -1)
        world.player.start_move(MOVES["combat_a"], 1)
        world.player.animation.elapsed = 3 / MOVES["combat_a"].fps
        world.step(config.FIXED_DT)
        self.assertEqual((victim.hp, world.player.hp), (190, 480))
        self.assertEqual(len(world.effects), 2)
        self.assertEqual([effect.image_name for effect in world.effects],
                         [config.PUNCH_KICK_HIT_IMAGE, config.CLUB_HIT_IMAGE])
        self.assertNotEqual(world.effects[0].x, world.effects[1].x)

    def test_misses_and_dead_targets_never_spawn_hit_effects(self):
        for offset, defeated in ((-80, False), (80, True), (500, False)):
            world = World()
            enemy = Enemy(config.START_X + offset)
            enemy.cooldown = 100
            if defeated:
                enemy.take_damage(200)
            world.enemies = [enemy]
            world.controls.press("combat_a")
            advance(world, 0.3)
            self.assertEqual(world.effects, [])
            self.assertEqual(world.camera.shake_remaining, 0)

    def test_only_new_player_hits_restart_shake_and_it_expires(self):
        world = World()
        enemy = Enemy(config.START_X + 80, -1)
        enemy.cooldown = 100
        world.enemies = [enemy]
        world.controls.press("combat_a")
        advance(world, 0.175)
        remaining = world.camera.shake_remaining
        self.assertGreater(remaining, 0)
        advance(world, 0.05)
        self.assertLess(world.camera.shake_remaining, remaining)
        self.assertEqual(enemy.hp, 190)
        advance(world, 0.2)
        self.assertEqual(world.camera.shake_remaining, 0)
        self.assertEqual((world.camera.offset_x, world.camera.offset_y), (0, 0))

    def test_restart_clears_live_effects_and_combat(self):
        world = World()
        world.controls.press("combat_a")
        striker(world)
        world.step(config.FIXED_DT)
        world.effects.append(HitEffect(100, 150, 1))
        self.assertTrue(world.effects)
        world.controls.press("restart")
        world.update(1 / 60)
        self.assertEqual(world.effects, [])
        self.assertIsNone(world.player.active_move)
        self.assertEqual(world.player.hp, 500)
        self.assertEqual(world.player.vx, 0)
        self.assertEqual(world.player.x, config.START_X)
        self.assertEqual(world.enemies, [])

    def test_all_punches_and_kicks_use_the_new_sheet_against_both_enemy_types(self):
        for enemy_type in (Enemy, Enemy02):
            for facing in (-1, 1):
                for action, move in MOVES.items():
                    with self.subTest(enemy=enemy_type.__name__, facing=facing, action=action):
                        world = World()
                        enemy = enemy_type(config.START_X + facing * 80, -facing)
                        enemy.cooldown = 100
                        world.enemies = [enemy]
                        world.controls.press("left" if facing < 0 else "right")
                        world.controls.press(action)
                        advance(world, 4 / move.fps, fps=120)
                        self.assertEqual(enemy.hp, 200 - move.damage)
                        self.assertEqual(len(world.effects), 1)
                        self.assertEqual(world.effects[0].image_name, config.PUNCH_KICK_HIT_IMAGE)
                        self.assertEqual(world.effects[0].facing, facing)

    def test_new_enemy_club_swings_and_leap_landings_use_the_club_sheet(self):
        for side in (-1, 1):
            for kind, frame, hp in (("clubs", 2, 440), ("slam", 4, 420)):
                with self.subTest(side=side, kind=kind):
                    world = World()
                    world.stage_index = 3
                    _, enemy = at_frame(kind, frame, side=side)
                    world.enemies = [enemy]
                    advance(world, 0.12, fps=120)
                    self.assertEqual(world.player.hp, hp)
                    self.assertEqual(len(world.effects), 1)
                    self.assertEqual(world.effects[0].image_name, config.CLUB_HIT_IMAGE)
                    self.assertEqual(world.effects[0].facing, -side)

    def test_counter_followups_use_the_player_impact_instead_of_blood(self):
        for key in "hjkl":
            world = World()
            world.enemies.clear()
            enemy = attacker(world)
            world.controls.press(f"counter_{key}")
            world.step(config.FIXED_DT)
            follow_up(world)
            for _ in range(120):
                world.step(config.FIXED_DT)
                if world.effects:
                    break
            self.assertEqual(enemy.hp, 120)
            self.assertEqual(len(world.effects), 1)
            self.assertEqual(world.effects[0].image_name, config.PUNCH_KICK_HIT_IMAGE)

    def test_vehicle_impacts_use_the_club_impact_for_both_victims(self):
        world = World()
        world.stage_index = 2
        world.player.ground_y = config.CAR_GROUND_Y
        enemy = Enemy02(world.player.x, ground_y=config.CAR_GROUND_Y)
        world.enemies = [enemy]
        world.stage.traffic.car = Car(world.player.x, 1, 1400)
        world.step(config.FIXED_DT)
        self.assertEqual((world.player.hp, enemy.hp), (0, 0))
        self.assertEqual(len(world.effects), 2)
        self.assertTrue(all(effect.image_name == config.CLUB_HIT_IMAGE for effect in world.effects))

    def test_both_new_resources_are_transparent_four_by_two_sheets(self):
        from PIL import Image

        for name in config.HIT_EFFECT_IMAGES:
            with Image.open(config.ROOT / name) as image:
                self.assertEqual((image.size, image.mode), ((2048, 1024), "RGBA"))
                self.assertEqual(image.getchannel("A").getextrema(), (0, 255))
                for frame in range(8):
                    x, y = frame % 4 * 512, frame // 4 * 512
                    self.assertIsNotNone(image.crop((x, y, x + 512, y + 512)).getbbox())

    def test_mixed_effect_images_keep_their_clocks_when_the_scene_is_inactive(self):
        world = World()
        effects = [HitEffect(100, 150, 1, image_name=name) for name in config.HIT_EFFECT_IMAGES]
        world.effects.extend(effects)
        world.stage_index = 1
        advance(world, 0.2)
        self.assertTrue(all(effect.elapsed == 0 for effect in effects))
        world.stage_index = 0
        advance(world, 0.1)
        self.assertEqual([effect.image_name for effect in world.effects], list(config.HIT_EFFECT_IMAGES))
        self.assertTrue(all(effect.frame == 2 for effect in effects))
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertTrue(all(not stage.effects for stage in world.stages))

    def test_attack_and_effect_state_are_identical_across_render_rates(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world = World()
            enemy = Enemy(config.START_X + 80, -1)
            enemy.cooldown = 100
            world.enemies = [enemy]
            world.controls.press("combat_a")
            advance(world, 0.5, fps)
            outcomes.append((enemy.hp, world.player.state,
                              [(effect.x, effect.y, effect.frame, effect.image_name)
                               for effect in world.effects]))
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
