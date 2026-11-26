import random
import unittest

import config
from collision import body_contact_time, same_floor, world_rect
from combat import MOVES, STRONG_MOVES
from enemy import Enemy
from rush import RushSequence
from tests.helpers import ArchivedTwoFloorTests, advance
from tests.test_two_floors import place
from world import World


def on_stairs(world, *, source_floor=0, progress=None):
    stair = world.stage.stairs[0]
    enemy = Enemy(0)
    place(world, enemy, source_floor, *stair.entrance(source_floor))
    world.enemies.append(enemy)
    stair.request(enemy)
    stair.start_next()
    stair.occupants[enemy] = stair.length - 75 if progress is None else progress
    stair.update(0)
    enemy.previous_x, enemy.previous_ground_y = enemy.x, enemy.ground_y
    enemy.previous_jump_height = enemy.jump_height
    return enemy


def attack(world, enemy, key="combat_s", *, floor=1, facing=1):
    ground_y = 452 if floor else 136
    place(world, world.player, floor, enemy.x - facing * 65, ground_y)
    move = STRONG_MOVES.get(key) or world.player.moves[key]
    world.player.start_move(move, facing)
    world.player.animation.elapsed = (min(move.active_frames) + 0.1) / move.fps
    return world.player.try_hit(enemy)


def upper_group(count=8, seed=41):
    world = World(rng=random.Random(seed))
    world.player.invincible = True
    for index in range(count):
        enemy = Enemy(1000 + index * 70, ground_y=476, rng=random.Random(index))
        place(world, enemy, 1, enemy.x, enemy.ground_y)
        world.enemies.append(enemy)
    return world


class StairCombatTests(ArchivedTwoFloorTests):
    def test_upstairs_player_can_hit_an_ascending_enemy_before_it_reaches_floor_two(self):
        world = World()
        enemy = on_stairs(world)
        feet = enemy.y
        self.assertTrue(attack(world, enemy))
        self.assertEqual((enemy.hp, enemy.state), (185, "HIT"))
        self.assertIsNotNone(enemy.staircase)
        self.assertEqual(enemy.y, feet)
        self.assertEqual(enemy.floor, 0)
        self.assertFalse(same_floor(world.player, enemy))

    def test_ground_player_can_hit_an_enemy_near_the_bottom_of_the_steps(self):
        world = World()
        enemy = on_stairs(world, progress=65)
        self.assertTrue(attack(world, enemy, floor=0))
        self.assertEqual(enemy.hp, 185)

    def test_descending_enemies_are_also_hittable_in_actual_height_range(self):
        world = World()
        enemy = on_stairs(world, source_floor=1, progress=25)
        self.assertTrue(attack(world, enemy))
        self.assertEqual(enemy.state, "HIT")

    def test_both_facings_and_all_normal_attacks_hit_once(self):
        for facing in (-1, 1):
            for key, move in MOVES.items():
                with self.subTest(facing=facing, key=key):
                    world = World()
                    enemy = on_stairs(world)
                    self.assertTrue(attack(world, enemy, key, facing=facing))
                    self.assertFalse(world.player.try_hit(enemy))
                    self.assertEqual(enemy.hp, config.ENEMY_MAX_HP - move.damage)

    def test_knife_and_pipe_attacks_hit_stair_enemies(self):
        for kind in ("combat_knife", "steel_pipe"):
            world = World()
            enemy = on_stairs(world)
            world.player.equip_weapon(kind)
            self.assertTrue(attack(world, enemy, "combat_a"))
            self.assertEqual(enemy.hp, config.ENEMY_MAX_HP - world.player.active_move.damage)

    def test_distant_heights_horizontal_range_and_wrong_facing_still_miss(self):
        world = World()
        enemy = on_stairs(world, progress=150)
        self.assertFalse(attack(world, enemy))
        world = World()
        enemy = on_stairs(world)
        attack(world, enemy)
        world.player.hit_enemies.clear()
        world.player.x = enemy.x - 400
        self.assertFalse(world.player.try_hit(enemy))
        world.player.x = enemy.x + 100
        self.assertFalse(world.player.try_hit(enemy))

    def test_separate_flat_floors_remain_isolated(self):
        world = World()
        enemy = Enemy(world.player.x + 65, -1, ground_y=world.player.ground_y)
        enemy.floor = 1
        world.player.start_move(MOVES["combat_s"], 1)
        world.player.animation.elapsed = 3 / MOVES["combat_s"].fps
        self.assertFalse(world.player.try_hit(enemy))
        self.assertEqual(enemy.hp, 200)

    def test_stair_hit_effect_and_damage_number_are_at_the_visible_contact_height(self):
        world = World()
        enemy = on_stairs(world)
        attack(world, enemy)
        # Start a distinct attack through the real World combat path.
        world.player.finish_move()
        world.player.start_move(MOVES["combat_s"], 1)
        world.player.animation.elapsed = 3 / MOVES["combat_s"].fps
        world.step(config.FIXED_DT)
        self.assertEqual(enemy.hp, 170)
        effect = world.effects[-1]
        box = world_rect(world.player.attack_box, world.player)
        body = world_rect(enemy.body, enemy)
        self.assertGreaterEqual(effect.y, max(box.bottom, body.bottom))
        self.assertLessEqual(effect.y, min(box.top, body.top))
        self.assertGreater(world.damage_numbers[-1].y, enemy.y + config.ENEMY_HEIGHT)

    def test_hit_pauses_the_column_without_overlap_and_then_everyone_resumes(self):
        world = World()
        place(world, world.player, 1, 1200, 476)
        stair = world.stage.stairs[0]
        enemies = [Enemy(238, ground_y=136) for _ in range(3)]
        world.enemies = enemies
        for enemy in enemies:
            stair.request(enemy)
        for _ in range(110):
            stair.start_next()
            stair.update(config.FIXED_DT)
        self.assertEqual(len(stair.occupants), 3)
        enemies[0].take_damage(10)
        before = dict(stair.occupants)
        advance(world, 0.25)
        self.assertEqual(stair.occupants, before)
        self.assertEqual(enemies[0].state, "HIT")
        for _ in range(600):
            world.step(config.FIXED_DT)
            progress = list(stair.occupants.values())
            self.assertTrue(all(a - b >= config.STAIR_FOLLOW_DISTANCE - 1e-8
                                for a, b in zip(progress, progress[1:])))
            if all(enemy.floor == 1 for enemy in enemies):
                break
        self.assertTrue(all(enemy.floor == 1 for enemy in enemies))

    def test_strong_hit_knocks_the_target_off_without_teleporting_its_feet(self):
        world = World()
        enemy = on_stairs(world)
        before = enemy.y
        self.assertTrue(attack(world, enemy, "combat_q"))
        self.assertEqual((enemy.hp, enemy.state), (150, "STRONG_HIT"))
        self.assertIsNone(enemy.staircase)
        self.assertTrue(enemy.falling_from_upper)
        self.assertEqual(enemy.y, before)
        self.assertNotIn(enemy, world.stage.stairs[0].occupants)
        advance(world, 1)
        self.assertEqual(enemy.jump_height, 0)
        self.assertFalse(enemy.falling_from_upper)

    def test_lethal_stair_hit_releases_occupancy_falls_and_eventually_fades(self):
        world = World()
        enemy = on_stairs(world)
        enemy.hp = MOVES["combat_s"].damage
        before = enemy.y
        self.assertTrue(attack(world, enemy))
        self.assertEqual(enemy.hp, 0)
        self.assertEqual(enemy.y, before)
        self.assertTrue(enemy.falling_from_upper)
        self.assertIsNone(enemy.staircase)
        advance(world, 5)
        self.assertNotIn(enemy, world.enemies)

    def test_rush_contact_can_capture_a_stair_enemy_without_cross_floor_projection(self):
        world = World()
        enemy = on_stairs(world, progress=220)
        place(world, world.player, 0, enemy.x - 40, 136)
        player = world.player
        player.jump_height = player.previous_jump_height = enemy.y - player.ground_y
        player.start_move(STRONG_MOVES["combat_w"], 1)
        player.rush_phase = "FLY"
        self.assertIsNone(body_contact_time(player, enemy))
        self.assertIsNotNone(body_contact_time(player, enemy, allow_transit=True))
        rush = RushSequence(player, world.stage.walkable)
        self.assertEqual(len(rush.update([enemy])), 1)
        self.assertIsNone(enemy.staircase)
        self.assertFalse(enemy.falling_from_upper)
        self.assertEqual(enemy.state, "RUSH_CARRIED")
        self.assertEqual(enemy.floor, player.floor)
        self.assertEqual(enemy.jump_height, player.jump_height)

    def test_falling_enemies_can_be_hit_from_the_upper_floor_at_matching_visible_height(self):
        world = World()
        enemy = Enemy(1000, ground_y=430)
        world.enemies = [enemy]
        enemy.begin_floor_fall(world.stage.walkable)
        self.assertTrue(attack(world, enemy))
        self.assertEqual(enemy.state, "HIT")
        before = enemy.y
        world.step(config.FIXED_DT)
        self.assertLess(enemy.y, before)


class RandomDescentTests(ArchivedTwoFloorTests):
    def test_groups_are_split_into_a_random_nonempty_drop_and_stair_subset(self):
        for count in (2, 3, 5, 9):
            for seed in range(8):
                world = upper_group(count, seed)
                world.step(config.FIXED_DT)
                dropping = sum(enemy.descent_route == "DROP" for enemy in world.enemies)
                self.assertGreaterEqual(dropping, 1)
                self.assertLess(dropping, count)
                self.assertTrue(all(enemy.descent_route in ("DROP", "STAIRS")
                                    for enemy in world.enemies))

    def test_drop_counts_vary_across_seeds(self):
        counts = set()
        for seed in range(20):
            world = upper_group(seed=seed)
            world.step(config.FIXED_DT)
            counts.add(sum(enemy.descent_route == "DROP" for enemy in world.enemies))
        self.assertGreater(len(counts), 3)

    def test_route_choices_are_not_rerolled_every_frame(self):
        world = upper_group()
        stage = world.stage
        stage.update_navigation(config.FIXED_DT, world.player, world.controls)
        routes = [enemy.descent_route for enemy in world.enemies]
        rng_state = stage.route_rng.getstate()
        for _ in range(20):
            stage.update_navigation(config.FIXED_DT, world.player, world.controls)
        self.assertEqual([enemy.descent_route for enemy in world.enemies], routes)
        self.assertEqual(stage.route_rng.getstate(), rng_state)

    def test_navigation_randomness_does_not_change_later_spawn_locations_or_speeds(self):
        actual, reference = upper_group(), upper_group()
        actual.stage.assign_descent_routes(0)
        first = actual.spawner.spawn(30, 0)
        second = reference.spawner.spawn(30, 0)
        self.assertEqual([(e.x, e.ground_y, e.run_speed, e.attack_speed) for e in first],
                         [(e.x, e.ground_y, e.run_speed, e.attack_speed) for e in second])

    def test_combat_randomness_does_not_change_descent_choices(self):
        actual, reference = upper_group(), upper_group()
        for _ in range(100):
            actual.enemies[0].rng.random()
        for world in (actual, reference):
            world.stage.assign_descent_routes(0)
        self.assertEqual([(e.descent_route, e.descent_delay) for e in actual.enemies],
                         [(e.descent_route, e.descent_delay) for e in reference.enemies])

    def test_selected_enemies_walk_to_the_front_edge_and_fall_with_continuous_feet(self):
        world = upper_group()
        fell = []
        for _ in range(120):
            before = {enemy: enemy.y for enemy in world.enemies}
            world.step(config.FIXED_DT)
            for enemy in world.enemies:
                if enemy.falling_from_upper and enemy not in fell:
                    fell.append(enemy)
                    self.assertAlmostEqual(enemy.y, world.stage.upper_walkable.bounds[1])
                    self.assertLess(abs(before[enemy] - enemy.y), 6)
                    self.assertGreater(enemy.jump_height, 300)
                    self.assertEqual(enemy.hp, 200)
                    self.assertIsNone(enemy.staircase)
                    self.assertNotIn(enemy, world.stage.stairs[0].queue)
            if fell:
                break
        self.assertTrue(fell)

    def test_fractional_depths_reach_the_drop_edge_at_every_run_speed(self):
        for speed in config.ENEMY_RUN_SPEEDS:
            for ground_y in (452.5, 476.5, 501.25):
                with self.subTest(speed=speed, ground_y=ground_y):
                    world = upper_group(1)
                    enemy = world.enemies[0]
                    enemy.run_speed = speed
                    enemy.ground_y = enemy.previous_ground_y = ground_y
                    enemy.descent_route = "DROP"
                    for _ in range(120):
                        world.step(config.FIXED_DT)
                        if enemy.falling_from_upper:
                            break
                    self.assertTrue(enemy.falling_from_upper)
                    self.assertAlmostEqual(enemy.y, world.stage.upper_walkable.bounds[1])

    def test_dropping_enemies_follow_horizontally_and_resume_ground_pursuit(self):
        world = upper_group()
        saw_drop = saw_stair = False
        for _ in range(1200):
            target_x = world.player.x
            world.step(config.FIXED_DT)
            for enemy in world.enemies:
                if enemy.falling_from_upper:
                    saw_drop = True
                    self.assertIsNone(enemy.attack_box)
                    # Ground collisions can move the player after enemy AI.
                    # Check pursuit against the target used during this tick.
                    distance = target_x - enemy.previous_x
                    if enemy.vy < 0 and abs(distance) > 10:
                        self.assertGreater(enemy.vx * distance, 0)
                if enemy.staircase:
                    saw_stair = True
            if all(enemy.floor == 0 and not enemy.falling_from_upper and enemy.staircase is None
                   for enemy in world.enemies):
                break
        self.assertTrue(saw_drop and saw_stair)
        self.assertTrue(all(enemy.floor == 0 for enemy in world.enemies))
        self.assertEqual(world.player.hp, config.MAX_HP)
        advance(world, 3)
        self.assertTrue(any(enemy.state == "ATTACK" for enemy in world.enemies))

    def test_a_lone_enemy_still_uses_stairs_but_a_later_partner_can_form_a_split_group(self):
        world = upper_group(1)
        world.step(config.FIXED_DT)
        self.assertIsNone(world.enemies[0].descent_route)
        enemy = Enemy(1200, ground_y=476)
        place(world, enemy, 1, 1200, 476)
        world.enemies.append(enemy)
        world.step(config.FIXED_DT)
        self.assertEqual({e.descent_route for e in world.enemies}, {"DROP", "STAIRS"})

    def test_player_returning_upstairs_cancels_unstarted_drop_routes(self):
        world = upper_group()
        world.stage.assign_descent_routes(0)
        place(world, world.player, 1, 1280, 476)
        world.step(config.FIXED_DT)
        self.assertTrue(all(enemy.descent_route is None and not enemy.falling_from_upper
                            and enemy.floor == 1 for enemy in world.enemies))

    def test_dead_or_incapacitated_enemies_do_not_start_a_drop(self):
        world = upper_group(4)
        dead, hit = world.enemies[:2]
        dead.take_damage(200)
        hit.take_damage(10)
        world.step(config.FIXED_DT)
        self.assertFalse(dead.falling_from_upper)
        self.assertFalse(hit.falling_from_upper)
        self.assertIsNone(hit.descent_route)
        self.assertEqual({enemy.descent_route for enemy in world.enemies[2:]}, {"DROP", "STAIRS"})

    def test_inactive_stage_pauses_a_falling_enemy_and_resumes_gravity_on_return(self):
        world = upper_group()
        for _ in range(120):
            world.step(config.FIXED_DT)
            falling = next((enemy for enemy in world.enemies if enemy.falling_from_upper), None)
            if falling:
                break
        self.assertIsNotNone(falling)
        before = falling.y, falling.vy
        world.select_stage(1)
        advance(world, 1)
        self.assertEqual((falling.y, falling.vy), before)
        world.select_stage(0)
        world.step(config.FIXED_DT)
        self.assertLess(falling.y, before[0])
        self.assertLess(falling.vy, before[1])

    def test_f5_clears_falling_enemies_routes_and_stair_occupants(self):
        world = upper_group()
        advance(world, 0.4)
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertEqual(world.enemies, [])
        self.assertFalse(world.stage.stairs[0].occupants)
        self.assertEqual(len(world.stage.drop_items), 15)
        self.assertTrue(all(door.state == "CLOSED" for door in world.stage.doors))

    def test_random_split_and_falling_are_render_rate_independent(self):
        snapshots = []
        for fps in (30, 60, 120, 144):
            world = upper_group()
            advance(world, 0.5, fps)
            snapshots.append([(enemy.descent_route, enemy.floor, enemy.x, enemy.ground_y,
                               enemy.jump_height, enemy.vy) for enemy in world.enemies])
        self.assertTrue(all(snapshot == snapshots[0] for snapshot in snapshots))


if __name__ == "__main__":
    unittest.main()
