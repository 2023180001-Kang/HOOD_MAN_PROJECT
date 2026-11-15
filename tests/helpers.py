def advance(world, seconds, fps=60):
    for _ in range(round(seconds * fps)):
        world.update(1 / fps)


def tap(controls, key):
    controls.release(key)
    controls.press(key)


def clear_encounters(world):
    """Remove automatic actors for isolated motion/transition test fixtures."""
    for stage in world.stages:
        stage.enemies.clear()
    return world
