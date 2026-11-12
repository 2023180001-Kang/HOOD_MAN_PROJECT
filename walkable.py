"""Convex world-space foot regions; camera and jump height never enter bounds."""

from dataclasses import dataclass
from functools import lru_cache

import config
from physics import clamp


@dataclass(frozen=True)
class WalkableArea:
    vertices: tuple

    def __post_init__(self):
        vertices = tuple((float(x), float(y)) for x, y in self.vertices)
        if len(vertices) < 3:
            raise ValueError("A walkable polygon needs at least three vertices")
        area = sum(x * vertices[(i + 1) % len(vertices)][1]
                   - y * vertices[(i + 1) % len(vertices)][0]
                   for i, (x, y) in enumerate(vertices))
        if area < 0:
            vertices = vertices[::-1]
        if abs(area) < 1e-9:
            raise ValueError("A walkable polygon must have positive area")
        for i, (x, y) in enumerate(vertices):
            bx, by = vertices[(i + 1) % len(vertices)]
            if (bx, by) == (x, y) or any(
                    (bx - x) * (cy - y) - (by - y) * (cx - x) < -1e-9
                    for cx, cy in vertices):
                raise ValueError("Walkable polygons must be convex with distinct adjacent vertices")
        object.__setattr__(self, "vertices", vertices)
        object.__setattr__(self, "_rectangle", len(vertices) == 4 and all(
            vertices[(i + 1) % 4][0] == x or vertices[(i + 1) % 4][1] == y
            for i, (x, y) in enumerate(vertices)))

    @classmethod
    def rectangle(cls, left, bottom, right, top):
        if right <= left or top <= bottom:
            raise ValueError("Invalid walkable rectangle")
        return cls(((left, bottom), (right, bottom), (right, top), (left, top)))

    @property
    @lru_cache(maxsize=64)
    def bounds(self):
        return (min(x for x, _ in self.vertices), min(y for _, y in self.vertices),
                max(x for x, _ in self.vertices), max(y for _, y in self.vertices))

    @lru_cache(maxsize=64)
    def inset(self, padding_x):
        """Inset by the actor's horizontal foot/body half-width, not sprite height."""
        if padding_x < 0:
            raise ValueError("Negative foot padding")
        polygon = self.vertices
        for index, (ax, ay) in enumerate(self.vertices):
            bx, by = self.vertices[(index + 1) % len(self.vertices)]
            nx, ny = ay - by, bx - ax
            limit = nx * ax + ny * ay + abs(nx) * padding_x
            clipped = []
            previous = polygon[-1]
            previous_distance = nx * previous[0] + ny * previous[1] - limit
            for current in polygon:
                distance = nx * current[0] + ny * current[1] - limit
                if (distance >= 0) != (previous_distance >= 0):
                    t = previous_distance / (previous_distance - distance)
                    clipped.append((previous[0] + t * (current[0] - previous[0]),
                                    previous[1] + t * (current[1] - previous[1])))
                if distance >= 0:
                    clipped.append(current)
                previous, previous_distance = current, distance
            if not clipped:
                raise ValueError("Actor footprint does not fit the walkable area")
            polygon = tuple(clipped)
        return polygon

    def contains(self, x, ground_y, padding_x=0.0):
        if self._rectangle:
            left, bottom, right, top = self.bounds
            return (left + padding_x - 1e-9 <= x <= right - padding_x + 1e-9
                    and bottom - 1e-9 <= ground_y <= top + 1e-9)
        polygon = self.inset(padding_x)
        return all((polygon[(i + 1) % len(polygon)][0] - ax) * (ground_y - ay)
                   - (polygon[(i + 1) % len(polygon)][1] - ay) * (x - ax) >= -1e-9
                   for i, (ax, ay) in enumerate(polygon))

    def project(self, x, ground_y, padding_x=0.0):
        if self._rectangle:
            left, bottom, right, top = self.bounds
            if padding_x < 0 or left + padding_x > right - padding_x:
                raise ValueError("Actor footprint does not fit the walkable area")
            return clamp(x, left + padding_x, right - padding_x), clamp(ground_y, bottom, top)
        if self.contains(x, ground_y, padding_x):
            return x, ground_y
        polygon = self.inset(padding_x)
        best, nearest = None, float("inf")
        for index, (ax, ay) in enumerate(polygon):
            bx, by = polygon[(index + 1) % len(polygon)]
            dx, dy = bx - ax, by - ay
            length_squared = dx * dx + dy * dy
            t = (clamp(((x - ax) * dx + (ground_y - ay) * dy) / length_squared, 0.0, 1.0)
                 if length_squared else 0.0)
            point = (ax + t * dx, ay + t * dy)
            distance = (point[0] - x) ** 2 + (point[1] - ground_y) ** 2
            if distance < nearest:
                best, nearest = point, distance
        return best

    def x_limits(self, ground_y, padding_x=0.0):
        if self._rectangle:
            left, bottom, right, top = self.bounds
            return (left + padding_x, right - padding_x) if bottom <= ground_y <= top else None
        intersections = []
        polygon = self.inset(padding_x)
        for index, (ax, ay) in enumerate(polygon):
            bx, by = polygon[(index + 1) % len(polygon)]
            if min(ay, by) - 1e-9 <= ground_y <= max(ay, by) + 1e-9:
                if abs(by - ay) < 1e-9:
                    intersections.extend((ax, bx))
                else:
                    intersections.append(ax + (bx - ax) * (ground_y - ay) / (by - ay))
        return (min(intersections), max(intersections)) if intersections else None

    def constrain(self, actor, padding_x):
        padding_x = max(padding_x, getattr(actor, "boundary_padding", padding_x))
        x, ground_y = self.project(actor.x, actor.ground_y, padding_x)
        if abs(x - actor.x) > 1e-9:
            actor.vx = 0.0
        if abs(ground_y - actor.ground_y) > 1e-9:
            actor.ground_vy = 0.0
        actor.x, actor.ground_y = x, ground_y


def for_stage(index):
    polygon = config.STAGE_WALKABLE_POLYGONS.get(index)
    return (WalkableArea(polygon) if polygon is not None else
            WalkableArea.rectangle(*config.STAGE_WALKABLE_BOUNDS[index]))


@lru_cache(maxsize=1)
def default_area():
    return for_stage(0)
