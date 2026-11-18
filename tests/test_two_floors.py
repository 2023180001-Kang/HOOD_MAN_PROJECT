import random
import unittest
from unittest.mock import Mock, patch

import config
from collision import bodies_overlap, body_contact_time, resolve_bodies, same_floor
from combat import MOVES, STRONG_MOVES
from counter import can_counter
from enemy import Enemy
from rush import RushSequence
from spawn_manager import SpawnManager
from tests.helpers import advance, tap
from ui import STAIR_BOUNDS_COLOR, UI
from world import World


def place(world, actor, floor, x, y):
    actor.floor = floor
    actor.x, actor.ground_y = x, y
    actor.previous_x, actor.previous_ground_y = x, y
    actor.vx = actor.ground_vy = actor.vy = actor.jump_height = 0.0
    world.stage.constrain_actor(actor)


def opened_world(seed=41):
    world = World(rng=random.Random(seed))
    world.stage.toggle_doors()
    world.stage.update_doors(1)
    return world


def begin_player_stairs(world, floor=0):
    stair = world.stage.stairs[0]
    place(world, world.player, floor, *stair.entrance(floor))
    world.controls.press("up" if floor == 0 else "down")
    world.step(config.FIXED_DT)
    world.controls.release("up" if floor == 0 else "down")
    return stair


class OpenDoorSpawnTests(unittest.TestCase):
    def test_only_fully_open_doors_are_eligible_and_closing_excludes_them_immediately(self):
        world = World()
        self.assertEqual(world.stage.open_door_spawns(), [])
        world.stage.doors[1].toggle()
        world.stage.update_doors(0.2)
        self.assertEqual(world.stage.open_door_spawns(), [])
        world.stage.update_doors(1)
        points = world.stage.open_door_spawns()
        self.assertEqual([(point.source, point.floor) for point in points],
                         [(("door", 1, 0), 1)])
        world.stage.doors[1].toggle()
        self.assertEqual(world.stage.open_door_spawns(), [])
        world.stage.update_doors(1)
        self.assertEqual(world.stage.open_door_spawns(), [])

    def test_all_in_world_door_instances_include_the_mirrored_upstairs_door_and_shutter(self):
        world = opened_world()
        points = world.stage.open_door_spawns()
        self.assertEqual({point.source for point in points},
                         {("door", index, 0) for index in range(4)}
                         | {("door", 2, 1), ("door", 3, 1)})
        by_source = {point.source: point for point in points}
        self.assertEqual(by_source[("door", 2, 1)].x, 3344 - 1408.5)
        self.assertEqual(by_source[("door", 3, 1)].x, 3344 - 1441)
        for point in points:
            self.assertTrue(point.walkable.contains(point.x, point.ground_y, 88))
            self.assertEqual(point.walkable, world.stage.floor_areas[point.floor])

    def test_random_source_pool_keeps_both_edges_and_every_open_door_with_exact_profiles(self):
        world = opened_world()
        spawned = world.spawner.spawn(160, 7)
        expected = {point.source for point in world.stage.open_door_spawns()} | {
            ("edge", -1), ("edge", 1)}
        self.assertEqual({enemy.spawn_source for enemy in spawned}, expected)
        self.assertEqual(world.spawner.spawned_count, 160)
        self.assertEqual(len({enemy.attack_speed for enemy in spawned}), 160)
        for index, enemy in enumerate(spawned):
            self.assertEqual(enemy.run_speed, config.ENEMY_RUN_SPEEDS[index % 4])
            self.assertEqual(enemy.spawned_at, 7)
            self.assertEqual(enemy.hp, 200)
            self.assertTrue(enemy.walkable.contains(enemy.x, enemy.ground_y, enemy.boundary_padding))
            self.assertIs(enemy.walkable, world.stage.floor_areas[enemy.floor])

    def test_closed_doors_do_not_change_the_original_random_boundary_sequence(self):
        world = World(rng=random.Random(71))
        original = SpawnManager(rng=random.Random(71))
        actual, expected = world.spawner.spawn(25, 3), original.spawn(25, 3)
        self.assertEqual([(e.x, e.ground_y, e.facing, e.attack_speed) for e in actual],
                         [(e.x, e.ground_y, e.facing, e.attack_speed) for e in expected])

    def test_number_presses_spawn_exact_counts_once_with_open_doors_and_no_auto_spawn(self):
        for count in config.SPAWN_COUNTS:
            with self.subTest(count=count):
                world = opened_world()
                world.player.invincible = True
                advance(world, 0.5)
                self.assertEqual(world.enemies, [])
                world.controls.press(f"spawn_{count}")
                world.step(config.FIXED_DT)
                self.assertEqual(len(world.enemies), count)
                world.controls.press(f"spawn_{count}")
                advance(world, 0.1)
                self.assertEqual(len(world.enemies), count)
                tap(world.controls, f"spawn_{count}")
                world.step(config.FIXED_DT)
                self.assertEqual(len(world.enemies), count * 2)
                self.assertEqual(world.spawner.spawned_count, count * 2)
                self.assertEqual(len(world.stage.drop_items), 15)

    def test_upstairs_spawns_remain_upstairs_during_ai_spacing_and_constraints(self):
        world = opened_world()
        place(world, world.player, 1, 1280, 476)
        enemies = [e for e in world.spawner.spawn(80, 0) if e.floor == 1][:5]
        self.assertEqual(len(enemies), 5)
        world.enemies = enemies
        for _ in range(60):
            world.step(config.FIXED_DT)
            for enemy in enemies:
                self.assertEqual(enemy.floor, 1)
                if enemy.staircase is None:
                    self.assertTrue(world.stage.upper_walkable.contains(enemy.x, enemy.ground_y, 88))

    def test_other_maps_never_inherit_first_map_door_sources(self):
        world = opened_world()
        for index in range(1, len(world.stages)):
            world.select_stage(index)
            self.assertEqual(world.stage.open_door_spawns(), ())
            self.assertTrue(all(e.floor == 0 and e.spawn_source[0] == "edge"
                                for e in world.spawner.spawn(5, 0)))


class StairAndFloorTests(unittest.TestCase):
    def assert_on_floor_or_stairs(self, world, actor):
        if actor.staircase is None:
            self.assertTrue(world.stage.area_for(actor).contains(
                actor.x, actor.ground_y, actor.boundary_padding))
        else:
            self.assertIn(actor, actor.staircase.occupants)
            self.assertEqual(actor.jump_height, 0)

    def test_upper_floor_matches_art_and_only_first_stage_has_a_staircase(self):
        world = World()
        self.assertEqual(world.stage.upper_walkable.bounds, (0, 452, config.WORLD_WIDTH, 502))
        self.assertEqual(len(world.stage.stairs), 1)
        stair = world.stage.stairs[0]
        for floor in (0, 1):
            self.assertTrue(world.stage.floor_areas[floor].contains(*stair.entrance(floor), 88))
        self.assertTrue(all(len(stage.floor_areas) == 1 and not stage.stairs
                            for stage in world.stages[1:]))

    def test_up_and_down_follow_steps_continuously_instead_of_teleporting(self):
        world = World()
        for floor in (0, 1):
            stair = begin_player_stairs(world, floor)
            self.assertIs(stair.occupant, world.player)
            previous = world.player.x, world.player.ground_y
            for _ in range(300):
                world.step(config.FIXED_DT)
                actor = world.player
                distance = ((actor.x - previous[0]) ** 2 + (actor.ground_y - previous[1]) ** 2) ** 0.5
                self.assertLessEqual(distance, config.STAIR_SPEED * config.FIXED_DT + 1e-8)
                self.assert_on_floor_or_stairs(world, actor)
                previous = actor.x, actor.ground_y
                if stair.occupant is None:
                    break
            self.assertEqual(world.player.floor, 1 - floor)
            self.assertEqual((world.player.x, world.player.ground_y), stair.entrance(1 - floor))
            self.assertTrue(world.player.grounded)
            self.assertIsNone(world.player.active_move)

    def test_walking_along_the_boundary_jump_or_attacking_cannot_accidentally_change_floors(self):
        for action in ("right", "jump", "combat_a", None):
            with self.subTest(action=action):
                world = World()
                place(world, world.player, 0, 238, 136)
                if action:
                    world.controls.press(action)
                    world.controls.press("up")
                world.step(config.FIXED_DT)
                self.assertIsNone(world.player.staircase)
                self.assertEqual(world.player.floor, 0)
        world = World()
        world.controls.press("up")
        advance(world, 1)
        self.assertEqual((world.player.floor, world.player.ground_y), (0, 136))

    def test_second_floor_supports_four_directions_and_its_front_edge_allows_a_drop(self):
        for horizontal in ("left", "right"):
            for vertical in ("up", "down"):
                world = World()
                place(world, world.player, 1, 1280, 476)
                for key in (horizontal, vertical, "left_shift"):
                    world.controls.press(key)
                advance(world, 5)
                self.assertEqual(world.player.floor, 1 if vertical == "up" else 0)
                self.assertEqual(world.player.x, 68 if horizontal == "left" else 2492)
                self.assertEqual(world.player.ground_y, 502 if vertical == "up" else 56)
                self.assertEqual(world.player.jump_height, 0)
        for key in ("up", "down"):
            world = World()
            place(world, world.player, 1, 1280, 476)
            world.controls.press(key)
            advance(world, 0.08)
            self.assertGreater(world.player.ground_y, 452)
            self.assertLess(world.player.ground_y, 502)
            self.assertGreater((world.player.ground_y - 476) * (1 if key == "up" else -1), 0)
            self.assertEqual(world.player.floor, 1)

    def test_jump_stays_relative_to_the_second_floor(self):
        world = World()
        place(world, world.player, 1, 1100, 476)
        world.controls.press("jump")
        world.controls.press("right")
        advance(world, 0.1)
        self.assertGreater(world.player.jump_height, 0)
        self.assertEqual(world.player.ground_y, 476)
        self.assertEqual(world.player.y, 476 + world.player.jump_height)
        advance(world, 2)
        self.assertTrue(world.player.grounded)
        self.assertEqual((world.player.floor, world.player.ground_y), (1, 476))

    def test_stair_movement_consumes_attack_jump_counter_and_weapon_input_without_buffering(self):
        world = World()
        begin_player_stairs(world)
        world.player.equip_weapon("steel_pipe")
        for key in ("jump", "combat_a", "counter_h", "weapon_interact", "invincibility"):
            world.controls.press(key)
        world.step(config.FIXED_DT)
        self.assertEqual(world.player.weapon, "steel_pipe")
        self.assertTrue(world.player.invincible)
        self.assertEqual(world.player.jump_height, 0)
        self.assertIsNone(world.player.active_move)
        self.assertIsNone(world.counter)
        for key in ("jump", "combat_a", "counter_h", "weapon_interact", "invincibility"):
            self.assertNotIn(key, world.controls.pressed)
        advance(world, 3)
        self.assertEqual(world.player.floor, 1)
        self.assertIsNone(world.player.active_move)
        self.assertTrue(world.player.grounded)

    def test_enemies_chase_upstairs_in_a_spaced_column_and_resume_combat_on_arrival(self):
        world = World()
        world.player.invincible = True
        place(world, world.player, 1, 1000, 476)
        world.enemies = [Enemy(238 + index * 100, ground_y=136) for index in range(4)]
        entered, landed, maximum = [], [], 0
        for _ in range(2400):
            world.step(config.FIXED_DT)
            active = [enemy for enemy in world.enemies if enemy.staircase is not None]
            maximum = max(maximum, len(active))
            progress = list(world.stage.stairs[0].occupants.values())
            self.assertTrue(all(a - b >= config.STAIR_FOLLOW_DISTANCE - 1e-8
                                for a, b in zip(progress, progress[1:])))
            for enemy in world.enemies:
                self.assert_on_floor_or_stairs(world, enemy)
                if enemy.staircase and enemy not in entered:
                    entered.append(enemy)
                if enemy.floor == 1 and enemy not in landed:
                    landed.append(enemy)
            if len(landed) == 4:
                break
        self.assertEqual(entered, world.enemies)
        self.assertEqual(landed, world.enemies)
        self.assertGreater(maximum, 1)
        advance(world, 5)
        self.assertTrue(any(enemy.state == "ATTACK" for enemy in world.enemies))
        self.assertTrue(all(enemy.navigation_target is None for enemy in world.enemies))

    def test_player_waits_for_a_descending_enemy_instead_of_sharing_the_steps(self):
        world = World()
        stair = world.stage.stairs[0]
        enemy = Enemy(500, ground_y=476)
        place(world, enemy, 1, 500, 476)
        world.enemies = [enemy]
        world.step(config.FIXED_DT)
        self.assertIs(stair.occupant, enemy)
        place(world, world.player, 0, 238, 136)
        world.controls.press("up")
        world.step(config.FIXED_DT)
        self.assertIs(stair.occupant, enemy)
        self.assertIsNone(world.player.staircase)
        self.assertIn(world.player, stair.queue)
        for _ in range(400):
            world.step(config.FIXED_DT)
            self.assertFalse(enemy.staircase and world.player.staircase)
            if world.player.staircase:
                break
        self.assertIs(stair.occupant, world.player)
        self.assertEqual(enemy.floor, 0)

    def test_releasing_up_while_waiting_cancels_the_players_queue_request(self):
        world = World()
        stair = world.stage.stairs[0]
        enemy = Enemy(500, ground_y=476)
        place(world, enemy, 1, 500, 476)
        world.enemies = [enemy]
        world.step(config.FIXED_DT)
        place(world, world.player, 0, 238, 136)
        world.controls.press("up")
        world.step(config.FIXED_DT)
        self.assertIn(world.player, stair.queue)
        world.controls.release("up")
        world.step(config.FIXED_DT)
        self.assertNotIn(world.player, stair.queue)

    def test_long_queue_keeps_arrival_order_even_when_waiting_slots_extend_beyond_entry_radius(self):
        world = World()
        place(world, world.player, 1, 1800, 476)
        world.player.invincible = True
        world.enemies = [Enemy(238 + index * 15, ground_y=112) for index in range(7)]
        expected = list(world.enemies)
        entered = []
        for _ in range(2400):
            world.step(config.FIXED_DT)
            stair = world.stage.stairs[0]
            for actor in stair.occupants:
                if actor not in entered:
                    entered.append(actor)
            if len(entered) == len(expected):
                break
        self.assertEqual(entered, expected)

    def test_player_death_clears_stair_occupancy_and_all_waiting_requests(self):
        world = World()
        stair = begin_player_stairs(world)
        world.enemies = [Enemy(238, ground_y=136), Enemy(338, ground_y=112)]
        world.step(config.FIXED_DT)
        self.assertTrue(stair.queue)
        world.player.take_damage(config.MAX_HP)
        world.step(config.FIXED_DT)
        self.assertIsNone(stair.occupant)
        self.assertFalse(stair.queue)
        self.assertIsNone(world.player.staircase)
        self.assertTrue(all(enemy.staircase is None and enemy.navigation_target is None
                            for enemy in world.enemies))

    def test_door_spawn_positions_do_not_depend_on_the_camera_or_player_floor(self):
        snapshots = []
        for camera, floor in ((0, 0), (1280, 1)):
            world = opened_world()
            world.camera.x = camera
            place(world, world.player, floor, 1280, 100 if floor == 0 else 476)
            snapshots.append([(e.spawn_source, e.floor, e.x, e.ground_y)
                              for e in world.spawner.spawn(40, 0)])
        self.assertEqual(snapshots[0], snapshots[1])

    def test_upstairs_rush_carries_only_upstairs_enemies_without_projecting_either_actor_down(self):
        world = World()
        world.player.invincible = True
        place(world, world.player, 1, 1000, 476)
        upstairs = Enemy(1200, -1, ground_y=476)
        place(world, upstairs, 1, 1200, 476)
        downstairs = Enemy(1200, -1, ground_y=100)
        world.enemies = [upstairs, downstairs]
        world.controls.press("combat_w")
        advance(world, 0.7)
        self.assertIsNotNone(world.rush)
        self.assertIn(upstairs, world.rush.captives)
        self.assertNotIn(downstairs, world.rush.captives)
        self.assertEqual((world.player.floor, upstairs.floor, downstairs.floor), (1, 1, 0))
        self.assertEqual((world.player.ground_y, upstairs.ground_y), (476, 476))
        world.controls.release("combat_w")
        advance(world, 2)
        self.assert_on_floor_or_stairs(world, world.player)
        self.assert_on_floor_or_stairs(world, upstairs)

    def test_removed_or_dead_occupants_release_the_lock_and_waiting_enemies_continue(self):
        for removed in (False, True):
            with self.subTest(removed=removed):
                world = World()
                place(world, world.player, 1, 1000, 476)
                enemies = [Enemy(238, ground_y=136), Enemy(338, ground_y=112)]
                world.enemies = list(enemies)
                world.step(config.FIXED_DT)
                self.assertIs(world.stage.stairs[0].occupant, enemies[0])
                if removed:
                    world.enemies.remove(enemies[0])
                else:
                    enemies[0].take_damage(200)
                advance(world, 4)
                self.assertIsNone(enemies[0].staircase)
                self.assertEqual(enemies[1].floor, 1)
                self.assertIsNone(world.stage.stairs[0].occupant)

    def test_f5_clears_transit_queues_upstairs_enemies_and_open_doors(self):
        world = opened_world()
        stair = begin_player_stairs(world)
        self.assertIsNotNone(stair.occupant)
        player = world.player
        world.controls.press("restart")
        world.update(config.FIXED_DT)
        self.assertIsNone(player.staircase)
        self.assertIsNone(stair.occupant)
        self.assertFalse(stair.queue)
        self.assertEqual(world.player.floor, 0)
        self.assertIsNone(world.player.staircase)
        self.assertTrue(all(door.state == "CLOSED" for door in world.stage.doors))
        self.assertEqual(world.enemies, [])
        self.assertEqual(len(world.stage.drop_items), 15)

    def test_leaving_a_stage_during_transit_releases_player_but_preserves_other_floor_state(self):
        world = opened_world()
        enemy = Enemy(1500, ground_y=476)
        place(world, enemy, 1, 1500, 476)
        world.enemies = [enemy]
        stair = begin_player_stairs(world)
        world.select_stage(1)
        self.assertIsNone(stair.occupant)
        self.assertEqual(world.player.floor, 0)
        self.assertIsNone(world.player.staircase)
        world.select_stage(0)
        self.assertEqual(enemy.floor, 1)
        self.assertEqual(enemy.ground_y, 476)
        self.assertTrue(all(door.state == "OPEN" for door in world.stage.doors))
        self.assertEqual(world.player.floor, 0)

    def test_inactive_stages_pause_enemy_stair_progress_and_resume_without_losing_occupancy(self):
        world = World()
        place(world, world.player, 1, 1000, 476)
        enemy = Enemy(238, ground_y=136)
        world.enemies = [enemy]
        world.step(config.FIXED_DT)
        stair = world.stage.stairs[0]
        progress = stair.progress
        world.select_stage(1)
        advance(world, 2)
        self.assertEqual(stair.progress, progress)
        self.assertIs(stair.occupant, enemy)
        world.select_stage(0)
        for _ in range(300):
            world.step(config.FIXED_DT)
            if enemy.staircase is None:
                break
        self.assertIsNone(enemy.staircase)
        self.assertEqual(enemy.floor, 1)

    def test_upstairs_and_transit_cannot_use_ground_floor_stage_exits(self):
        world = World()
        world.stage.arrows_visible = True
        place(world, world.player, 1, 2492, 476)
        world.controls.press("right")
        world.player.vx = 720
        self.assertFalse(world.try_stage_transition())
        world.controls.release("right")
        begin_player_stairs(world, 1)
        self.assertFalse(world.try_stage_transition())
        advance(world, 3)
        place(world, world.player, 0, 2492, 100)
        world.player.vx = 720
        self.assertTrue(world.try_stage_transition())
        self.assertEqual((world.stage_index, world.player.floor), (1, 0))

    def test_floor_aware_hits_counters_and_swept_body_contacts_cannot_cross_floors(self):
        world = World()
        player = world.player
        enemy = Enemy(player.x + 80, -1, ground_y=100)
        enemy.floor = 1  # Equal y deliberately proves floor IDs, not just distance filtering.
        player.start_move(MOVES["combat_a"], 1)
        player.animation.elapsed = 3 / MOVES["combat_a"].fps
        enemy.start_attack()
        enemy.animation.elapsed = 3 / enemy.attack_fps
        self.assertFalse(player.try_hit(enemy))
        self.assertFalse(enemy.try_hit(player))
        self.assertFalse(can_counter(player, enemy))
        self.assertIsNone(body_contact_time(player, enemy))
        self.assertFalse(bodies_overlap(player, enemy))
        self.assertFalse(same_floor(player, enemy))
        enemy.floor = 0
        self.assertTrue(player.try_hit(enemy))

    def test_ground_floor_rush_never_captures_upstairs_enemies(self):
        world = World()
        player = world.player
        player.start_move(STRONG_MOVES["combat_w"], 1)
        player.rush_phase = "FLY"
        enemy = Enemy(player.x + 10, -1, ground_y=player.ground_y)
        enemy.floor = 1
        rush = RushSequence(player, world.stage.walkable)
        self.assertEqual(rush.update([enemy]), [])
        self.assertEqual(rush.captives, [])
        self.assertEqual(enemy.hp, 200)

    def test_upstairs_body_resolution_never_projects_ground_floor_enemies_upstairs(self):
        world = World()
        place(world, world.player, 1, 1000, 476)
        enemy = Enemy(1000, ground_y=100)
        before = enemy.x, enemy.ground_y
        resolve_bodies(world.player, [enemy], world.stage.upper_walkable)
        self.assertEqual((enemy.x, enemy.ground_y), before)
        self.assertEqual(world.player.ground_y, 476)

    def test_upstairs_combat_counter_and_strong_hit_keep_both_actors_on_the_upper_floor(self):
        world = World()
        place(world, world.player, 1, 1000, 476)
        enemy = Enemy(1080, -1, ground_y=476)
        place(world, enemy, 1, 1080, 476)
        world.enemies = [enemy]
        world.player.start_move(STRONG_MOVES["combat_q"], 1)
        world.player.animation.elapsed = 3 / STRONG_MOVES["combat_q"].fps
        self.assertTrue(world.player.try_hit(enemy))
        advance(world, 1)
        self.assertEqual(enemy.floor, 1)
        self.assert_on_floor_or_stairs(world, enemy)
        world.player.finish_move()
        place(world, enemy, 1, world.player.x + 80, world.player.ground_y)
        enemy.start_attack()
        enemy.animation.elapsed = min(config.COUNTER_TRIGGER_FRAMES) / enemy.attack_fps
        self.assertTrue(world.try_start_counter("counter_h"))
        advance(world, 0.5)
        self.assertTrue(world.counter.holding)
        world.controls.press("combat_a")
        advance(world, 2)
        self.assertIsNone(world.counter)
        self.assertEqual(world.player.floor, 1)
        self.assertEqual(enemy.floor, 1)
        self.assert_on_floor_or_stairs(world, enemy)

    def test_weapon_drop_and_pickup_stay_on_the_second_floor(self):
        world = World()
        place(world, world.player, 1, 1280, 476)
        world.player.equip_weapon("steel_pipe")
        self.assertTrue(world.interact_weapon())
        item = world.stage.drop_items[-1]
        self.assertEqual(item.floor, 1)
        self.assertTrue(world.stage.upper_walkable.contains(item.x, item.ground_y))
        advance(world, 2)
        self.assertIs(world.pickup_item, item)
        self.assertTrue(world.interact_weapon())
        self.assertEqual(world.player.weapon, "steel_pipe")
        self.assertNotIn(item, world.stage.drop_items)
        self.assertEqual(len(world.stage.drop_items), 15)

    def test_f4_includes_the_stair_path_and_both_floors_without_changing_gameplay(self):
        world = World()
        ui = UI()
        ui.floor_bounds_visible = True
        before = world.player.x, world.player.ground_y, world.player.floor
        with patch("pico2d.draw_line") as draw:
            ui.draw_floor_bounds(world, 120, -4)
        lines = [call.args for call in draw.call_args_list if call.args[4:] == STAIR_BOUNDS_COLOR]
        path = world.stage.stairs[0].path
        self.assertEqual([line[:4] for line in lines],
                         [(ax - 120, ay + 4, bx - 120, by + 4)
                          for (ax, ay), (bx, by) in zip(path, path[1:])])
        self.assertEqual((world.player.x, world.player.ground_y, world.player.floor), before)

    def test_floor_help_and_a_damaged_hp_bar_render_together(self):
        world = World()
        ui = UI()
        assets = Mock(images={config.HP_IMAGE: Mock(w=700, h=80)})
        for floor in (0, 1):
            place(world, world.player, floor, 1280, 100 if floor == 0 else 476)
            world.player.hp = 480
            ui.update(0, world.player)
            with patch("pico2d.draw_rectangle") as draw:
                ui.draw(assets, world)
            self.assertTrue(draw.called)
            self.assertTrue(any(f"{floor + 1}층" in call.args[2]
                                for call in assets.font.draw.call_args_list))

    def test_stairs_are_render_rate_independent(self):
        snapshots = []
        for fps in (30, 60, 120, 144):
            world = World()
            begin_player_stairs(world)
            advance(world, 0.5, fps)
            snapshots.append((world.player.x, world.player.ground_y, world.stage.stairs[0].progress))
        self.assertTrue(all(snapshot == snapshots[0] for snapshot in snapshots))


if __name__ == "__main__":
    unittest.main()
