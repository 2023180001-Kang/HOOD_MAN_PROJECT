def advance(world, seconds, fps=60):
    for _ in range(round(seconds * fps)):
        world.update(1 / fps)


def tap(controls, key):
    controls.release(key)
    controls.press(key)


def clear_encounters(world):
    """Clear explicitly arranged actors in motion/transition test fixtures."""
    for stage in world.stages:
        stage.enemies.clear()
    return world


def spawn_encounter(world, count=4):
    """Arrange combat actors explicitly; input tests exercise numeric presses."""
    enemies = world.spawner.spawn(count, world.elapsed)
    world.enemies.extend(enemies)
    return enemies
