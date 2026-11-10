def advance(world, seconds, fps=60):
    for _ in range(round(seconds * fps)):
        world.update(1 / fps)


def tap(controls, key):
    controls.release(key)
    controls.press(key)
