from vision.zones import LineCounter, Person, TableMonitor, point_in_polygon

SQUARE = [(0.2, 0.2), (0.6, 0.2), (0.6, 0.6), (0.2, 0.6)]
SEATED = (0.30, 0.30, 0.40, 0.45)      # wide-ish box (h/w = 1.5)
STANDING = (0.45, 0.10, 0.52, 0.55)    # tall box (h/w ~ 6.4)


def types(events):
    return [e["type"] for e in events]


def run(mon, start, end, persons, step=0.5, surface=None):
    out = []
    t = start
    while t <= end:
        out += mon.update(t, persons, surface)
        t += step
    return out


def test_point_in_polygon():
    assert point_in_polygon((0.4, 0.4), SQUARE)
    assert not point_in_polygon((0.7, 0.4), SQUARE)


def test_occupied_after_debounce_then_vacated():
    mon = TableMonitor("3", SQUARE, occupy_s=8, vacate_s=20)
    diners = [Person(1, SEATED), Person(2, SEATED)]
    assert run(mon, 0, 7.5, diners) == []
    ev = run(mon, 8, 9, diners)
    assert types(ev) == ["table.occupied"] and ev[0]["data"]["party_size"] == 2
    # brief occlusion (5s) must not vacate
    assert run(mon, 9.5, 14.5, []) == []
    assert run(mon, 15, 16, diners) == []
    assert "table.vacated" in types(run(mon, 16.5, 40, []))


def test_passer_by_does_not_occupy_but_counts_as_visit():
    # Someone standing at an empty table for >= visit_s (e.g. a busser cleaning)
    # is visit evidence for cleaning verification, but must not occupy the table.
    mon = TableMonitor("3", SQUARE, occupy_s=8, visit_s=3)
    assert types(run(mon, 0, 4, [Person(9, STANDING)])) == ["table.attended"]
    assert run(mon, 4.5, 20, []) == []
    assert not mon.occupied


def test_staff_visit_detected_once():
    mon = TableMonitor("3", SQUARE, occupy_s=8, visit_s=3)
    diners = [Person(1, SEATED)]
    run(mon, 0, 10, diners)
    ev = run(mon, 10.5, 20, diners + [Person(7, STANDING)])
    assert types(ev).count("table.attended") == 1


def test_hand_raise_needs_hold_and_has_cooldown():
    mon = TableMonitor("3", SQUARE, occupy_s=2, hand_hold_s=1, hand_cooldown_s=30)
    run(mon, 0, 3, [Person(1, SEATED)])
    assert run(mon, 3.5, 3.5, [Person(1, SEATED, hand_raised=True)]) == []      # flicker
    ev = run(mon, 4, 6, [Person(1, SEATED, hand_raised=True)])
    assert types(ev) == ["service.hand_raised"]
    assert run(mon, 6.5, 20, [Person(1, SEATED, hand_raised=True)]) == []      # cooldown


def test_surface_reports_only_stable_changes():
    mon = TableMonitor("3", SQUARE, surface_heartbeat_s=100)
    ev = []
    for t, n in enumerate([3, 3, 3, 3, 0, 3, 0, 0, 0]):
        ev += mon.update(float(t), [], n)
    assert [e["data"]["items"] for e in ev] == [3, 0]


def test_line_counter_direction():
    lc = LineCounter((0.0, 0.5), (1.0, 0.5), inside_sign=-1)
    assert lc.update([Person(1, (0.4, 0.3, 0.5, 0.6))]) == []      # feet below line
    assert types(lc.update([Person(1, (0.4, 0.1, 0.5, 0.4))])) == ["entrance.enter"]
    assert types(lc.update([Person(1, (0.4, 0.3, 0.5, 0.6))])) == ["entrance.exit"]


def test_busser_cleaning_empty_table_never_occupies_it():
    mon = TableMonitor("3", SQUARE, occupy_s=8, visit_s=3)
    ev = run(mon, 0, 60, [Person(5, STANDING)])
    assert types(ev) == ["table.attended"] and not mon.occupied


def test_staff_lingering_after_party_leaves_does_not_block_vacate():
    mon = TableMonitor("3", SQUARE, occupy_s=8, vacate_s=20, visit_s=3)
    run(mon, 0, 10, [Person(1, SEATED)])
    run(mon, 10.5, 15, [Person(1, SEATED), Person(7, STANDING)])
    ev = run(mon, 15.5, 40, [Person(7, STANDING)])   # diner gone, staff still there
    assert "table.vacated" in types(ev)
