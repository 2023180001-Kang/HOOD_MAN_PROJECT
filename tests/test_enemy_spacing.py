import unittest
from math import hypot

import config
from collision import bodies_overlap, resolve_bodies
from enemy import Enemy
from enemy_spacing import prepare_enemy_spacing, resolve_enemy_spacing, sprite_extents
from tests.helpers import advance
from tests.helpers import ManualSpawnWorld as World


def crowd(count, side, *, distance=500, world=None):
    world = World() if world is None else world
    world.player.invincible = True
    enemies = [Enemy(world.player.x + side * distance, -side,
                     run_speed=config.ENEMY_RUN_SPEEDS[index % 4]) for index in range(count)]
    world.enemies.extend(enemies)
    return world, enemies


def ready_all(enemies):
    for enemy in enemies:
        enemy.animation.set_state("ATTACK")
        enemy.animation.elapsed = 4 / config.ENEMY_ANIMATIONS["ATTACK"][1]
        enemy.has_hit = False
        enemy.cooldown = config.ENEMY_ATTACK_INTERVAL


class EnemySpacingTests(unittest.TestCase):
    def assert_distinguishable(self, enemies):
        for index, first in enumerate(enemies):
            for second in enemies[index + 1:]:
                # Real depth must fit both the floor and the melee depth band.
                # Dense crowds compress instead of placing feet outside the map.
                self.assertTrue(abs(first.x - second.x) >= 50
                                or abs(first.ground_y - second.ground_y) >= 8,
                                (first.x, first.depth, second.x, second.depth))

    def test_one_sided_2_3_5_8_arrivals_spread_and_every_enemy_can_hit(self):
        for side in (-1, 1):
            for count in (2, 3, 5, 8):
                with self.subTest(side=side, count=count):
                    world, enemies = crowd(count, side)
                    landed = set()
                    peak_attackers = 0
                    for _ in range(8 * 120):
                        before = [(enemy.x, enemy.depth, enemy.state, enemy.has_hit)
                                  for enemy in enemies]
                        world.step(config.FIXED_DT)
                        attackers = sum(enemy.state == "ATTACK" for enemy in enemies)
                        peak_attackers = max(peak_attackers, attackers)
                        for enemy, (x, depth, state, has_hit) in zip(enemies, before):
                            if enemy.state == "ATTACK" and enemy.has_hit and not has_hit:
                                landed.add(enemy)
                            maximum = max(config.ENEMY_SPEED, enemy.run_speed) * config.FIXED_DT
                            if state == enemy.state == "ATTACK":
                                maximum = config.ENEMY_ATTACK_SEPARATION_SPEED * config.FIXED_DT
                            self.assertLessEqual(hypot(enemy.x - x, enemy.depth - depth), maximum + 1e-8)
                            self.assertGreaterEqual((enemy.x - world.player.x) * side, 61 - 1e-8)
                            self.assertFalse(bodies_overlap(enemy, world.player))
                            self.assertEqual(enemy.jump_height, 0.0)
                            self.assertTrue(world.stage.walkable.contains(enemy.x, enemy.ground_y,
                                                                         config.ENEMY_HALF_WIDTH))
                    self.assertEqual(landed, set(enemies))
                    self.assertGreaterEqual(peak_attackers, 2)
                    self.assert_distinguishable(enemies)
                    world.player.invincible = False
                    ready_all(enemies)
                    world.step(config.FIXED_DT)
                    self.assertEqual(world.player.hp, 500 - count * config.ENEMY_DAMAGE)
                    self.assertTrue(all(enemy.has_hit for enemy in enemies))
                    advance(world, 0.1)
                    self.assertEqual(world.player.hp, 500 - count * config.ENEMY_DAMAGE)

    def test_both_sides_eight_each_remain_separate_and_all_sixteen_hit_together(self):
        world, left = crowd(8, -1)
        _, right = crowd(8, 1, world=world)
        advance(world, 8)
        self.assert_distinguishable(left)
        self.assert_distinguishable(right)
        self.assertTrue(all(enemy.x < world.player.x for enemy in left))
        self.assertTrue(all(enemy.x > world.player.x for enemy in right))
        world.player.invincible = False
        ready_all(world.enemies)
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.hp, 180)
        self.assertEqual(len(world.effects), 16)
        self.assertTrue(all(enemy.has_hit for enemy in world.enemies))

    def test_stationary_formation_does_not_jitter_or_reshuffle_between_swings(self):
        world, enemies = crowd(8, -1)
        advance(world, 6)
        positions = [(enemy.x, enemy.depth, enemy.formation_slot) for enemy in enemies]
        for _ in range(4 * 120):
            world.step(config.FIXED_DT)
            self.assertEqual([(enemy.x, enemy.depth, enemy.formation_slot) for enemy in enemies],
                             positions)

    def test_preexisting_attack_overlap_is_relieved_gently_without_restarting_animation(self):
        world, enemies = crowd(8, 1, distance=80)
        for enemy in enemies:
            enemy.animation.set_state("ATTACK")
            enemy.animation.elapsed = 0.1
            enemy.cooldown = 1
        for _ in range(30):
            before = [(enemy.x, enemy.depth, enemy.animation.elapsed) for enemy in enemies]
            world.step(config.FIXED_DT)
            for enemy, (x, depth, elapsed) in zip(enemies, before):
                self.assertLessEqual(abs(enemy.x - x), 18 * config.FIXED_DT + 1e-8)
                self.assertLessEqual(hypot(enemy.x - x, enemy.depth - depth),
                                     18 * config.FIXED_DT + 1e-8)
                self.assertAlmostEqual(enemy.animation.elapsed, elapsed + config.FIXED_DT)
                self.assertEqual((enemy.state, enemy.facing), ("ATTACK", -1))
        advance(world, 4)
        self.assert_distinguishable(enemies)

    def test_even_the_shortest_player_attack_can_counter_every_settled_slot(self):
        for side in (-1, 1):
            with self.subTest(side=side):
                world, enemies = crowd(8, side)
                advance(world, 6)
                world.controls.press("left" if side < 0 else "right")
                world.controls.press("combat_a")
                advance(world, 0.175)
                self.assertEqual([enemy.hp for enemy in enemies], [190] * 8)
                self.assertEqual(len(world.damage_numbers), 8)
                for enemy, number in zip(enemies, world.damage_numbers):
                    self.assertEqual(number.damage, 10)
                    self.assertAlmostEqual(number.y - enemy.depth,
                                           enemy.body.top + config.ENEMY_HP_BAR_GAP
                                           + config.ENEMY_HP_BAR_HEIGHT + config.DAMAGE_NUMBER_GAP)

    def test_slots_survive_list_order_changes_and_a_neighbours_death(self):
        world, enemies = crowd(8, -1)
        advance(world, 6)
        slots = {enemy: (enemy.formation_slot, enemy.target_x, enemy.target_depth)
                 for enemy in enemies[1:]}
        freed_slot = enemies[0].formation_slot
        enemies[0].take_damage(200)
        world.enemies.reverse()
        advance(world, 0.1)
        for enemy, expected in slots.items():
            self.assertEqual((enemy.formation_slot, enemy.target_x, enemy.target_depth), expected)
        newcomer = Enemy(world.player.x - 200)
        world.enemies.append(newcomer)
        world.step(config.FIXED_DT)
        self.assertEqual(newcomer.formation_slot, freed_slot)

    def test_hit_death_and_knockback_keep_their_physical_movement_rules(self):
        world, enemies = crowd(5, -1)
        advance(world, 6)
        hit, dead, knocked = enemies[:3]
        hit.take_damage(20)
        dead.take_damage(200)
        knocked.knockback(world.player.x)
        hit_x, dead_position = hit.x, (dead.x, dead.depth)
        knocked_position, facing = knocked.x, knocked.facing
        world.step(config.FIXED_DT)
        self.assertEqual(hit.x, hit_x)
        self.assertEqual((dead.x, dead.depth), dead_position)
        self.assertAlmostEqual(knocked.x, knocked_position - config.KNOCKBACK_SPEED * config.FIXED_DT)
        self.assertEqual(knocked.facing, facing)
        self.assertIsNone(dead.formation_slot)
        self.assertIsNone(knocked.formation_slot)

    def test_wall_compaction_keeps_original_sides_and_reachable_attacks(self):
        for side in (-1, 1):
            with self.subTest(side=side):
                world = World()
                world.player.x = world.player.previous_x = (100 if side < 0 else 2460)
                world, enemies = crowd(8, side, distance=65, world=world)
                advance(world, 5)
                self.assertEqual(len({round(enemy.depth, 6) for enemy in enemies}), 8)
                self.assertTrue(all((enemy.x - world.player.x) * side >= 61 for enemy in enemies))
                self.assertTrue(all(32 <= enemy.x <= 2528 for enemy in enemies))
                self.assertTrue(all(world.stage.walkable.contains(enemy.x, enemy.ground_y, 32)
                                    for enemy in enemies))
                world.player.invincible = False
                ready_all(enemies)
                world.step(config.FIXED_DT)
                self.assertEqual(world.player.hp, 340)

    def test_crowded_wall_landing_does_not_flip_enemies_across_the_player(self):
        world = World()
        world.player.x = world.player.previous_x = 60
        left, right = Enemy(32), Enemy(70, -1)
        world.enemies = [left, right]
        resolve_bodies(world.player, world.enemies)
        self.assertLess(left.x, world.player.x)
        self.assertGreater(right.x, world.player.x)
        self.assertFalse(left.body.overlaps(world.player.body))
        self.assertFalse(right.body.overlaps(world.player.body))

    def test_floor_depth_is_separate_from_height_rectangles_and_attack_reach(self):
        world, enemies = crowd(8, 1)
        advance(world, 6)
        enemy = max(enemies, key=lambda actor: abs(actor.depth))
        ready_all([enemy])
        box = enemy.attack_box
        body = enemy.body
        enemy.ground_y = 56
        self.assertEqual(enemy.body, body)
        self.assertEqual(enemy.attack_box, box)
        self.assertFalse(enemy.try_hit(world.player))
        enemy.ground_y = world.player.ground_y
        world.player.y += config.ENEMY_HEIGHT + 1
        self.assertFalse(enemy.try_hit(world.player))
        world.player.y = config.GROUND_Y
        enemy.x = world.player.x + 200
        self.assertFalse(enemy.try_hit(world.player))

    def test_group_state_pauses_off_stage_and_restart_clears_both_stages(self):
        world, enemies = crowd(5, -1)
        advance(world, 4)
        snapshot = [(enemy.x, enemy.depth, enemy.formation_slot) for enemy in enemies]
        world.stage_index = 1
        advance(world, 1)
        self.assertEqual([(enemy.x, enemy.depth, enemy.formation_slot) for enemy in enemies], snapshot)
        crowd(3, 1, distance=200, world=world)
        advance(world, 1)
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertTrue(all(not stage.enemies for stage in world.stages))
        self.assertEqual(world.stage_index, 0)

    def test_group_results_are_independent_of_render_frame_rate(self):
        outcomes = []
        for fps in (30, 60, 120, 144):
            world, _ = crowd(8, -1)
            crowd(5, 1, world=world)
            advance(world, 6, fps)
            world.player.invincible = False
            ready_all(world.enemies)
            world.step(config.FIXED_DT)
            outcomes.append((world.player.hp, [(enemy.x, enemy.depth, enemy.state,
                                               enemy.animation.elapsed, enemy.has_hit)
                                              for enemy in world.enemies]))
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))

    def test_spacing_uses_scaled_occupied_sprite_width_including_frame_offsets(self):
        left, right = sprite_extents()
        # ATTACK frame 5 (zero-based) occupies source x=26..243 around x=128.
        self.assertLessEqual(left, (26 - 128) * config.SPRITE_SCALE)
        self.assertGreaterEqual(right, (243 - 128) * config.SPRITE_SCALE)
        self.assertGreater(right - left, config.ENEMY_HALF_WIDTH * 2)

    def test_attack_separation_moves_both_overlapped_enemies_in_opposite_directions(self):
        world, enemies = crowd(2, 1, distance=80)
        prepare_enemy_spacing(world.player, enemies)
        for enemy in enemies:
            enemy.animation.set_state("ATTACK")
        resolve_enemy_spacing(world.player, enemies, config.FIXED_DT)
        self.assertLess(enemies[0].x, config.START_X + 80)
        self.assertGreater(enemies[1].x, config.START_X + 80)
        self.assertLessEqual(abs(enemies[0].x - config.START_X - 80), 18 * config.FIXED_DT + 1e-8)

    def test_entry_exit_hysteresis_avoids_formation_churn_at_the_entry_distance(self):
        world, enemies = crowd(3, -1, distance=200)
        prepare_enemy_spacing(world.player, enemies)
        slots = [enemy.formation_slot for enemy in enemies]
        for enemy in enemies:
            enemy.x = world.player.x - 280
        prepare_enemy_spacing(world.player, enemies)
        self.assertEqual([enemy.formation_slot for enemy in enemies], slots)
        for enemy in enemies:
            enemy.x = world.player.x - 321
        prepare_enemy_spacing(world.player, enemies)
        self.assertTrue(all(enemy.formation_slot is None and enemy.target_x is None
                            for enemy in enemies))


if __name__ == "__main__":
    unittest.main()
