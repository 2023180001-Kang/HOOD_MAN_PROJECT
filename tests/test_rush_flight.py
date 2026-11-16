import unittest
from unittest.mock import patch

import config
from collision import bodies_overlap
from enemy import Enemy
from enemy02 import Enemy02
from tests.helpers import advance, tap
from tests.test_strong_attacks import encounter
from traffic import Car, Traffic


def launch(world):
    tap(world.controls, "combat_w")
    for _ in range(60):
        world.step(config.FIXED_DT)
        if world.player.rush_phase == "FLY":
            return
    raise AssertionError("Held W never launched")


def capture_enemy(world, enemy):
    launch(world)
    for _ in range(120):
        world.step(config.FIXED_DT)
        if enemy.state == "RUSH_CARRIED":
            return
    raise AssertionError("W did not capture the contacted enemy")


class RushFlightTests(unittest.TestCase):
    def test_held_w_flies_with_the_contacted_enemy_and_deals_fifty_only_once(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for enemy_type in (Enemy, Enemy02):
                for side in (-1, 1):
                    world, enemy = encounter(enemy_type, side, weapon)
                    capture_enemy(world, enemy)
                    self.assertEqual(enemy.hp, 150)
                    self.assertEqual(enemy.sprite_image, config.STRONG_HIT_IMAGE)
                    self.assertEqual((world.player.animation.frame, enemy.animation.row,
                                      enemy.animation.frame), (4, 5, 4))
                    self.assertIsNone(enemy.attack_box)
                    self.assertFalse(bodies_overlap(world.player, enemy))
                    start = world.player.x
                    advance(world, 0.5)
                    self.assertAlmostEqual((world.player.x - start) * side, config.RUSH_SPEED * 0.5)
                    self.assertAlmostEqual(enemy.x - world.player.x, side * config.RUSH_CARRY_DISTANCE)
                    self.assertEqual((enemy.ground_y, enemy.jump_height),
                                     (world.player.ground_y, world.player.jump_height))
                    self.assertEqual((enemy.hp, enemy.state), (150, "RUSH_CARRIED"))
                    self.assertIsNone(world.player.attack_box)

    def test_keyup_stops_the_player_immediately_and_the_enemy_slides_a_short_distance(self):
        for enemy_type in (Enemy, Enemy02):
            for side in (-1, 1):
                world, enemy = encounter(enemy_type, side)
                capture_enemy(world, enemy)
                px, ex = world.player.x, enemy.x
                world.controls.release("combat_w")
                world.step(config.FIXED_DT)
                self.assertEqual((world.player.x, world.player.vx), (px, 0))
                self.assertEqual(world.player.rush_phase, "RECOVERY")
                self.assertIsNone(world.rush)
                self.assertEqual(enemy.state, "RUSH_RELEASED")
                self.assertGreater((enemy.x - ex) * side, 0)
                stopped = False
                for _ in range(100):
                    if enemy.state != "RUSH_RELEASED":
                        break
                    before = enemy.x
                    world.step(config.FIXED_DT)
                    if enemy.vx == 0:
                        stopped = True
                        self.assertAlmostEqual(enemy.x, before, delta=0.1)
                self.assertTrue(stopped)
                self.assertGreater((enemy.x - ex) * side, 50)
                self.assertLess((enemy.x - ex) * side, 90)
                self.assertEqual((enemy.hp, enemy.state, enemy.jump_height), (150, "IDLE", 0))
                self.assertIsNone(world.player.rush_phase)
                self.assertEqual(world.player.x, px)

    def test_releasing_during_windup_does_not_fly_or_hit(self):
        world, enemy = encounter()
        tap(world.controls, "combat_w")
        advance(world, 0.05)
        start = world.player.x
        world.controls.release("combat_w")
        advance(world, 0.5)
        self.assertEqual(world.player.x, start)
        self.assertEqual(enemy.hp, 200)
        self.assertIsNone(world.player.rush_phase)
        self.assertIsNone(world.rush)

    def test_w_uses_physical_front_contact_not_the_old_ranged_attack_box(self):
        world, enemy = encounter()
        enemy.x = world.player.x + 120
        launch(world)
        self.assertEqual(enemy.hp, 200)
        for _ in range(3):
            world.step(config.FIXED_DT)
            self.assertEqual(enemy.hp, 200)
        for reason in ("depth", "height", "behind"):
            world, enemy = encounter()
            if reason == "depth":
                enemy.ground_y += 20
            elif reason == "height":
                enemy.jump_height = 350
            else:
                enemy.x = world.player.x - 80
            launch(world)
            advance(world, 0.3)
            self.assertEqual(enemy.hp, 200)
            self.assertNotEqual(enemy.state, "RUSH_CARRIED")

    def test_swept_contact_catches_a_target_even_if_one_step_crosses_it_completely(self):
        world, enemy = encounter()
        enemy.x = world.player.x + 200
        launch(world)
        with patch.object(config, "RUSH_SPEED", 60000):
            world.step(config.FIXED_DT)
        self.assertEqual((enemy.hp, enemy.state), (150, "RUSH_CARRIED"))
        self.assertIn(enemy, world.rush.captives)

    def test_multiple_contacted_enemies_are_carried_and_each_hit_is_consumed_once(self):
        world, first = encounter()
        second = Enemy02(world.player.x + 130, -1)
        second.animation.set_state("HIT")
        second.cooldown = 100
        world.enemies.append(second)
        capture_enemy(world, first)
        advance(world, 0.3)
        self.assertEqual((first.hp, second.hp), (150, 150))
        self.assertEqual(set(world.rush.captives), {first, second})
        advance(world, 0.5)
        self.assertEqual((first.hp, second.hp), (150, 150))
        world.controls.release("combat_w")
        world.step(config.FIXED_DT)
        self.assertEqual((first.state, second.state), ("RUSH_RELEASED", "RUSH_RELEASED"))

    def test_both_feet_remain_inside_all_stage_edges_and_a_sloped_polygon(self):
        from walkable import WalkableArea

        for enemy_type in (Enemy, Enemy02):
            for index in range(len(config.STAGE_IMAGES)):
                for side in (-1, 1):
                    world, enemy = encounter(enemy_type, side)
                    world.select_stage(index)
                    world.stage.traffic = None
                    left, bottom, right, top = world.stage.walkable.bounds
                    enemy.x = left + enemy.boundary_padding + 20 if side < 0 else right - enemy.boundary_padding - 20
                    enemy.ground_y = bottom if side < 0 else top
                    world.player.x = enemy.x - side * 80
                    world.player.ground_y = enemy.ground_y
                    world.enemies = [enemy]
                    capture_enemy(world, enemy)
                    for _ in range(60):
                        world.step(config.FIXED_DT)
                        for actor in (world.player, enemy):
                            self.assertTrue(world.stage.walkable.contains(actor.x, actor.ground_y,
                                                                         actor.boundary_padding))
                    world.controls.release("combat_w")
                    advance(world, 0.5)
                    self.assertTrue(world.stage.walkable.contains(enemy.x, enemy.ground_y, enemy.boundary_padding))
        world, enemy = encounter()
        world.stage.walkable = WalkableArea(((0, 56), (1800, 56), (1600, 148), (0, 148)))
        capture_enemy(world, enemy)
        advance(world, 0.5)
        for actor in (world.player, enemy):
            self.assertTrue(world.stage.walkable.contains(actor.x, actor.ground_y, actor.boundary_padding))

    def test_player_interruptions_release_every_captive_and_reset_cleans_references(self):
        for cause in ("hit", "death", "car", "drop", "swap", "attack", "restart"):
            world, enemy = encounter(weapon="steel_pipe")
            capture_enemy(world, enemy)
            sequence = world.rush
            if cause in ("hit", "death"):
                world.player.invincible = False
                world.player.take_damage(20 if cause == "hit" else 500)
            elif cause == "car":
                world.player.hit_by_car(1)
            elif cause == "drop":
                tap(world.controls, "weapon_interact")
            elif cause == "swap":
                world.player.equip_weapon("combat_knife")
            elif cause == "attack":
                tap(world.controls, "combat_q")
            else:
                tap(world.controls, "restart")
            world.update(config.FIXED_DT)
            self.assertIsNone(world.rush)
            self.assertNotEqual(enemy.state, "RUSH_CARRIED")
            self.assertTrue(sequence.finished)
            self.assertFalse(sequence.captives)

    def test_captive_hit_car_or_removal_is_not_overwritten_and_interrupted_lift_falls(self):
        for enemy_type in (Enemy, Enemy02):
            for cause in ("hit", "car", "remove"):
                world, enemy = encounter(enemy_type)
                capture_enemy(world, enemy)
                if cause == "hit":
                    enemy.take_damage(10)
                elif cause == "car":
                    enemy.hit_by_car(1)
                else:
                    world.enemies.remove(enemy)
                world.step(config.FIXED_DT)
                self.assertNotIn(enemy, world.rush.captives)
                self.assertNotEqual(enemy.state, "RUSH_CARRIED")
                if cause != "remove":
                    world.controls.release("combat_w")
                    advance(world, 1)
                    self.assertEqual(enemy.jump_height, 0)

    def test_lethal_contact_keeps_the_captured_pose_until_release_then_dies_normally(self):
        for enemy_type in (Enemy, Enemy02):
            world, enemy = encounter(enemy_type)
            enemy.hp = 40
            capture_enemy(world, enemy)
            self.assertEqual(enemy.hp, 0)
            self.assertFalse(enemy.blocks_movement)
            advance(world, 0.5)
            self.assertEqual(enemy.state, "RUSH_CARRIED")
            world.controls.release("combat_w")
            advance(world, 1.5)
            self.assertEqual((enemy.state, enemy.sprite_image), ("DEAD", enemy.image_name))
            advance(world, 5)
            self.assertNotIn(enemy, world.enemies)

    def test_traffic_still_has_priority_and_loading_pauses_the_flying_pair(self):
        world, enemy = encounter()
        capture_enemy(world, enemy)
        before = (world.player.x, enemy.x, enemy.jump_height)
        world.pending_stage_index, world.stage_loading_remaining = 1, 2
        world.update(0.5)
        self.assertEqual((world.player.x, enemy.x, enemy.jump_height), before)
        world.pending_stage_index = None
        world.stage.traffic = Traffic()
        world.player.ground_y = enemy.ground_y = config.CAR_GROUND_Y
        world.stage.traffic.car = Car(world.player.x, 1, 1400)
        world.step(config.FIXED_DT)
        self.assertEqual((world.player.hp, enemy.hp), (0, 0))
        self.assertIsNone(world.rush)
        self.assertNotEqual(enemy.state, "RUSH_CARRIED")
        world, enemy = encounter()
        launch(world)
        enemy.x = world.player.x + config.RUSH_CARRY_DISTANCE
        world.player.ground_y = enemy.ground_y = config.CAR_GROUND_Y
        world.stage.traffic = Traffic()
        world.stage.traffic.car = Car(world.player.x, 1, 1400)
        world.step(config.FIXED_DT)
        self.assertEqual((world.player.hp, enemy.hp), (0, 0))
        self.assertEqual([number.damage for number in world.damage_numbers], [200])
        self.assertTrue(all(effect.image_name == config.CLUB_HIT_IMAGE for effect in world.effects))

    def test_flight_release_and_enemy_slide_are_render_rate_independent(self):
        results = []
        for fps in (30, 60, 120, 144):
            world, enemy = encounter(Enemy02)
            tap(world.controls, "combat_w")
            advance(world, 0.5, fps)
            captured = (world.player.x, enemy.x, enemy.hp, enemy.state)
            world.controls.release("combat_w")
            advance(world, 0.5, fps)
            results.append((captured, world.player.x, world.player.jump_height, world.player.state,
                            enemy.x, enemy.vx, enemy.jump_height, enemy.state))
        self.assertTrue(all(result == results[0] for result in results))

    def test_held_w_turns_without_a_captive_and_keeps_the_last_direction_when_neutral(self):
        for side in (-1, 1):
            world, _ = encounter(side=side)
            world.enemies.clear()
            launch(world)
            world.controls.press("left" if side > 0 else "right")
            before = world.player.x
            world.step(config.FIXED_DT)
            self.assertEqual(world.player.facing, -side)
            self.assertEqual(world.rush.direction, -side)
            self.assertAlmostEqual(world.player.x - before, -side * config.RUSH_SPEED * config.FIXED_DT)
            world.controls.press("right" if side > 0 else "left")
            world.step(config.FIXED_DT)
            self.assertEqual(world.player.facing, -side)
            world.controls.release("left")
            world.controls.release("right")
            world.step(config.FIXED_DT)
            self.assertEqual(world.player.vx, -side * config.RUSH_SPEED)
            self.assertIn("combat_w", world.controls.held)

    def test_turning_moves_captives_to_the_new_front_without_restarting_or_redamaging(self):
        for weapon in (None, *config.WEAPON_POSE_IMAGES):
            for enemy_type in (Enemy, Enemy02):
                for side in (-1, 1):
                    world, enemy = encounter(enemy_type, side, weapon)
                    capture_enemy(world, enemy)
                    sequence = world.rush
                    for direction in (-side, side, -side):
                        world.controls.release("left")
                        world.controls.release("right")
                        world.controls.press("right" if direction > 0 else "left")
                        before = world.player.x
                        world.step(config.FIXED_DT)
                        self.assertIs(world.rush, sequence)
                        self.assertEqual((world.player.rush_phase, world.player.facing), ("FLY", direction))
                        self.assertAlmostEqual(world.player.x - before,
                                               direction * config.RUSH_SPEED * config.FIXED_DT)
                        self.assertAlmostEqual(enemy.x - world.player.x, direction * config.RUSH_CARRY_DISTANCE)
                        self.assertEqual((enemy.facing, enemy.hp, enemy.state), (-direction, 150, "RUSH_CARRIED"))
                        self.assertEqual((world.player.animation.frame, enemy.animation.frame), (4, 4))
                        self.assertEqual(len(world.damage_numbers), 1)
                    world.controls.release("left")
                    world.controls.release("right")
                    world.controls.release("combat_w")
                    px, ex = world.player.x, enemy.x
                    world.step(config.FIXED_DT)
                    self.assertEqual((world.player.x, world.player.vx), (px, 0))
                    self.assertGreater((enemy.x - ex) * -side, 0)
                    self.assertEqual(enemy.state, "RUSH_RELEASED")

    def test_reversed_flight_captures_new_front_targets_without_hitting_the_same_enemy_again(self):
        world, first = encounter()
        second = Enemy02(world.player.x - 160, 1)
        second.animation.set_state("HIT")
        second.cooldown = 100
        world.enemies.append(second)
        capture_enemy(world, first)
        self.assertEqual((first.hp, second.hp), (150, 200))
        world.controls.press("left")
        advance(world, 0.25)
        self.assertEqual((first.hp, second.hp), (150, 150))
        self.assertEqual(set(world.rush.captives), {first, second})
        self.assertTrue(all(enemy.x < world.player.x for enemy in world.rush.captives))

    def test_reversing_at_every_stage_edge_keeps_the_flying_pair_inside(self):
        for enemy_type in (Enemy, Enemy02):
            for index in range(len(config.STAGE_IMAGES)):
                for side in (-1, 1):
                    world, enemy = encounter(enemy_type, side)
                    world.select_stage(index)
                    world.stage.traffic = None
                    left, bottom, right, top = world.stage.walkable.bounds
                    enemy.x = left + enemy.boundary_padding + 20 if side < 0 else right - enemy.boundary_padding - 20
                    enemy.ground_y = bottom if side < 0 else top
                    world.player.x = enemy.x - side * 80
                    world.player.ground_y = enemy.ground_y
                    world.enemies = [enemy]
                    capture_enemy(world, enemy)
                    advance(world, 0.5)
                    before = world.player.x
                    world.controls.press("left" if side > 0 else "right")
                    world.step(config.FIXED_DT)
                    self.assertAlmostEqual(world.player.x - before, -side * config.RUSH_SPEED * config.FIXED_DT)
                    for actor in (world.player, enemy):
                        self.assertTrue(world.stage.walkable.contains(actor.x, actor.ground_y,
                                                                     actor.boundary_padding))
                    self.assertAlmostEqual(enemy.x - world.player.x, -side * config.RUSH_CARRY_DISTANCE)

    def test_interruption_uses_the_last_flight_direction_instead_of_the_next_attacks_direction(self):
        world, enemy = encounter()
        capture_enemy(world, enemy)
        world.controls.press("left")
        world.step(config.FIXED_DT)
        world.controls.release("left")
        world.controls.press("right")
        tap(world.controls, "combat_q")
        before = enemy.x
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.facing, 1)
        self.assertIsNone(world.rush)
        self.assertEqual(enemy.state, "RUSH_RELEASED")
        self.assertLess(enemy.x, before)
        self.assertLess(enemy.vx, 0)

    def test_mirroring_a_captive_does_not_sweep_its_old_side_into_a_vehicle(self):
        world, enemy = encounter()
        capture_enemy(world, enemy)
        world.player.ground_y = enemy.ground_y = config.CAR_GROUND_Y
        world.stage.traffic = Traffic()
        world.stage.traffic.car = Car(world.player.x + config.CAR_HALF_WIDTH + config.PLAYER_HALF_WIDTH + 8,
                                      1, 1400)
        world.controls.press("left")
        world.step(config.FIXED_DT)
        self.assertEqual((world.player.hp, enemy.hp, enemy.state), (500, 150, "RUSH_CARRIED"))
        self.assertLess(enemy.x, world.player.x)


if __name__ == "__main__":
    unittest.main()
