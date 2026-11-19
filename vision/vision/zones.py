"""Per-table scene logic: pure Python, no CV dependencies, unit-testable.

Turns noisy per-frame detections into a small number of stable, debounced
operational events. All coordinates are normalised (0-1) image coordinates.

Heuristics (documented limits, tuned per installation):
- A person is "at" a table when the centre of their box is inside the table polygon.
- Residents: people continuously *seated* at the table >= occupy_s. They make the
  table occupied; standing staff never do.
- Visitor: someone who arrives after the party was seated (or at an empty table)
  and stays >= visit_s while standing (tall box). Interpreted as a staff visit.
  A late-arriving diner can be mistaken for a visit; that is why the backend
  treats camera evidence as evidence, and humans review uncertain cases.
- Vacated: nobody at the table for vacate_s (tolerates brief occlusion / ID switches).
"""
from __future__ import annotations

from dataclasses import dataclass, field

Point = tuple[float, float]
Box = tuple[float, float, float, float]  # x1, y1, x2, y2


def point_in_polygon(p: Point, poly: list[Point]) -> bool:
    x, y = p
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def centre(box: Box) -> Point:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


@dataclass
class Person:
    track_id: int
    box: Box
    hand_raised: bool = False

    @property
    def standing(self) -> bool:
        w, h = self.box[2] - self.box[0], self.box[3] - self.box[1]
        return w > 0 and h / w >= 1.8


@dataclass
class _Track:
    first_seen: float
    last_seen: float
    joined_after_seating: bool
    seated_since: float | None = None
    visit_reported: bool = False
    hand_since: float | None = None


@dataclass
class TableMonitor:
    label: str
    polygon: list[Point]
    surface: list[Point] | None = None
    occupy_s: float = 8.0
    vacate_s: float = 20.0
    visit_s: float = 3.0
    track_grace_s: float = 1.5
    hand_hold_s: float = 1.0
    hand_cooldown_s: float = 30.0
    surface_heartbeat_s: float = 15.0

    occupied: bool = False
    _tracks: dict[int, _Track] = field(default_factory=dict)
    _empty_since: float | None = None
    _last_hand_event: float = -1e9
    _surface_reported: int | None = None
    _surface_reported_at: float = -1e9
    _surface_history: list[int] = field(default_factory=list)

    def people_here(self, persons: list[Person]) -> list[Person]:
        return [p for p in persons if point_in_polygon(centre(p.box), self.polygon)]

    def update(self, t: float, persons: list[Person], surface_items: int | None = None) -> list[dict]:
        events: list[dict] = []
        here = self.people_here(persons)
        now_ids = {p.track_id for p in here}

        for p in here:
            tr = self._tracks.get(p.track_id)
            if tr is None:
                tr = self._tracks[p.track_id] = _Track(t, t, joined_after_seating=self.occupied)
            tr.last_seen = t
            tr.seated_since = None if p.standing else (tr.seated_since if tr.seated_since is not None else t)
            tr.hand_since = (tr.hand_since or t) if p.hand_raised else None

        # forget tracks that have been gone longer than the grace period
        for tid in [tid for tid, tr in self._tracks.items() if t - tr.last_seen > self.track_grace_s]:
            del self._tracks[tid]

        # Residents are *seated* people who arrived before/with the party. Standing
        # people (staff clearing a table) never make a table occupied.
        residents = [tid for tid, tr in self._tracks.items()
                     if not tr.joined_after_seating and tr.seated_since is not None
                     and t - tr.seated_since >= self.occupy_s]

        # occupancy
        if not self.occupied and residents:
            self.occupied = True
            self._empty_since = None
            events.append({"type": "table.occupied", "data": {"party_size": len(residents)}})
        elif self.occupied:
            # Only the party keeps a table occupied; staff visitors do not.
            if any(not tr.joined_after_seating for tr in self._tracks.values()):
                self._empty_since = None
            else:
                self._empty_since = self._empty_since if self._empty_since is not None else t
                if t - self._empty_since >= self.vacate_s:
                    self.occupied = False
                    self._empty_since = None
                    events.append({"type": "table.vacated", "data": {}})

        # staff visits
        by_id = {p.track_id: p for p in here}
        for tid, tr in self._tracks.items():
            p = by_id.get(tid)
            visitor = tr.joined_after_seating or not self.occupied
            if (p and visitor and not tr.visit_reported and p.standing
                    and t - tr.first_seen >= self.visit_s):
                tr.visit_reported = True
                events.append({"type": "table.attended", "data": {}})

        # raised hand (held, from a seated resident, with cooldown)
        if self.occupied and t - self._last_hand_event >= self.hand_cooldown_s:
            for tid in residents:
                tr = self._tracks[tid]
                if tr.hand_since is not None and t - tr.hand_since >= self.hand_hold_s and tid in now_ids:
                    self._last_hand_event = t
                    events.append({"type": "service.hand_raised", "data": {}})
                    break

        # surface: report a stable count on change, plus a periodic heartbeat
        if surface_items is not None:
            self._surface_history = (self._surface_history + [surface_items])[-3:]
            stable = len(self._surface_history) == 3 and len(set(self._surface_history)) == 1
            if stable and (surface_items != self._surface_reported
                           or t - self._surface_reported_at >= self.surface_heartbeat_s):
                self._surface_reported, self._surface_reported_at = surface_items, t
                events.append({"type": "table.surface", "data": {"items": surface_items}})

        for e in events:
            e["table"] = self.label
        return events


@dataclass
class LineCounter:
    """Counts entrance crossings of a line segment. `inside` is the side named in config."""

    a: Point
    b: Point
    inside_sign: int = 1
    _last_side: dict[int, int] = field(default_factory=dict)

    def _side(self, p: Point) -> int:
        (ax, ay), (bx, by) = self.a, self.b
        v = (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)
        return 1 if v > 0 else -1

    def update(self, persons: list[Person]) -> list[dict]:
        events = []
        seen = set()
        for p in persons:
            foot = ((p.box[0] + p.box[2]) / 2, p.box[3])
            side = self._side(foot)
            prev = self._last_side.get(p.track_id)
            if prev is not None and prev != side:
                events.append({"type": "entrance.enter" if side == self.inside_sign else "entrance.exit", "data": {}})
            self._last_side[p.track_id] = side
            seen.add(p.track_id)
        for tid in list(self._last_side):
            if tid not in seen:
                del self._last_side[tid]
        return events
