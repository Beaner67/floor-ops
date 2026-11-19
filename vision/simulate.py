"""Restaurant simulator: drives the whole system without cameras.

Emits the same events the vision worker would (and POS order updates), with
realistic timing and deliberate imperfections: slow first visits, unanswered
raised hands, late kitchen orders, and the occasional sloppy cleaning, so every
alert and verification path shows up in a demo.

    python simulate.py                       # you play the counter staff in the UI
    python simulate.py --auto-staff          # fully autonomous demo
    python simulate.py --speed 2             # everything twice as fast

Standard library only.
"""
from __future__ import annotations

import argparse
import heapq
import itertools
import json
import random
import time
import urllib.error
import urllib.request

CAMS = ("cam-1", "cam-2")


class Api:
    def __init__(self, base: str, key: str):
        self.base, self.key = base.rstrip("/"), key

    def _req(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "X-Device-Key": self.key})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            if e.code != 409:  # 409 = a human already acted on it; fine
                print(f"  ! {method} {path}: {e.code} {e.read()[:200]!r}")
        except urllib.error.URLError as e:
            print(f"  ! backend unreachable: {e.reason}")
        return None

    def get(self, path):
        return self._req("GET", path)

    def post(self, path, body=None):
        return self._req("POST", path, body or {})


class Sim:
    def __init__(self, api: Api, speed: float, auto_staff: bool):
        self.api, self.speed, self.auto = api, speed, auto_staff
        self.q: list = []
        self.seq = itertools.count()
        self.tables: dict[str, dict] = {}          # label -> backend table
        self.cam_of: dict[str, str] = {}
        self.busy: set[str] = set()                # tables with a simulated party
        self.party: dict[str, int] = {}
        self.surface: dict[str, int] = {}
        self.handled: set[tuple[int, str]] = set()  # (task id, stage)
        self.order_no = itertools.count(1001)

    # ------------------------------------------------------------ plumbing
    def later(self, seconds: float, fn, *args, **kwargs):
        heapq.heappush(self.q, (time.monotonic() + seconds / self.speed, next(self.seq), fn, args, kwargs))

    def event(self, type_: str, table: str | None = None, **data):
        cam = self.cam_of.get(table, CAMS[0]) if table else CAMS[0]
        self.api.post("/api/events", {"type": type_, "table": table, "camera_id": cam, "data": data})
        if type_ not in ("table.surface", "people.count", "camera.heartbeat"):
            print(f"  cam  {type_:<20} table {table or '-'} {data or ''}")

    def pos(self, ref: str, label: str, status: str, **extra):
        if status == "placed":
            self.api.post("/api/pos/orders", {"pos_ref": ref, "table": label, "status": status, **extra})
        else:
            self.api.post(f"/api/pos/orders/{ref}/status", {"status": status})
        print(f"  pos  order {ref:<15} table {label} -> {status}")

    # ------------------------------------------------------------ a party's visit
    def seat(self, label: str):
        size = random.randint(1, min(4, self.tables[label]["capacity"]))
        self.busy.add(label)
        self.party[label] = size
        for _ in range(size):
            self.event("entrance.enter")
        self.later(6, self.event, "table.occupied", label, party_size=size)

        # first staff visit: usually prompt, sometimes forgotten (-> 'customers waiting' alert)
        first = random.uniform(15, 50) if random.random() < 0.7 else random.uniform(140, 200)
        self.later(6 + first, self.event, "table.attended", label)

        # order via POS right after the first visit; some kitchens run late
        ref = f"POS-{next(self.order_no)}"
        sla = 2
        prep = random.uniform(70, 110) if random.random() < 0.7 else random.uniform(150, 200)
        t_order = 6 + first + 5
        self.later(t_order, self.pos, ref, label, "placed", items=random.choice(MENU), sla_minutes=sla)
        self.later(t_order + 20, self.pos, ref, label, "preparing")
        self.later(t_order + prep, self.pos, ref, label, "ready")
        carry = random.uniform(15, 50) if random.random() < 0.75 else random.uniform(110, 150)
        self.later(t_order + prep + carry, self.serve, ref, label)

        # raised hand; staff usually respond, sometimes too slowly (-> high-priority alert)
        if random.random() < 0.5:
            t_hand = t_order + random.uniform(30, 90)
            self.later(t_hand, self.event, "service.hand_raised", label)
            reply = random.uniform(15, 45) if random.random() < 0.6 else random.uniform(80, 120)
            self.later(t_hand + reply, self.event, "table.attended", label)

        stay = t_order + prep + carry + random.uniform(90, 180)
        self.later(stay, self.leave, label)

    def serve(self, ref: str, label: str):
        self.event("table.attended", label)
        self.pos(ref, label, "delivered")
        self.surface[label] = self.party.get(label, 2) * 2 + 1

    def leave(self, label: str):
        for _ in range(self.party.pop(label, 1)):
            self.event("entrance.exit")
        self.event("table.vacated", label)
        self.surface.setdefault(label, 3)
        self.busy.discard(label)

    # ------------------------------------------------------------ the staff (physically)
    def staff_cleans(self, task_id: int, label: str):
        self.event("table.attended", label)
        sloppy = random.random() < 0.15
        self.surface[label] = 1 if sloppy else 0
        self.later(4, self.event, "table.surface", label, items=self.surface[label])
        if self.auto:
            self.later(8, self.api.post, f"/api/tasks/{task_id}/complete")

    def react_to_tasks(self, state: dict):
        staff = [s["id"] for s in state["staff"] if s["on_shift"]]
        for t in state["tasks"]:
            label = t["table_label"]
            tid, st = t["id"], t["status"]
            if self.auto and st == "pending" and staff and (tid, "assign") not in self.handled:
                self.handled.add((tid, "assign"))
                self.later(random.uniform(4, 12), self.api.post, f"/api/tasks/{tid}/assign",
                           {"staff_id": random.choice(staff)})
            if t["type"] == "clean_table" and st == "assigned" and (tid, f"clean{t['assigned_at']}") not in self.handled:
                self.handled.add((tid, f"clean{t['assigned_at']}"))
                self.later(random.uniform(10, 30), self.staff_cleans, tid, label)
            if self.auto and t["type"] in ("assist_customer", "attend_table") and st == "assigned" \
                    and (tid, "go") not in self.handled:
                self.handled.add((tid, "go"))
                self.later(random.uniform(5, 20), self.event, "table.attended", label)
            if self.auto and t["type"] in ("check_order", "general") and st == "assigned" \
                    and (tid, "done") not in self.handled:
                self.handled.add((tid, "done"))
                self.later(random.uniform(10, 25), self.api.post, f"/api/tasks/{tid}/complete")
            if self.auto and st in ("verification_failed", "verification_uncertain") \
                    and (tid, st) not in self.handled:
                self.handled.add((tid, st))
                decision = "redo" if st == "verification_failed" else "confirm"
                self.later(random.uniform(8, 15), self.api.post, f"/api/tasks/{tid}/review", {"decision": decision})

    # ------------------------------------------------------------ main loop
    def run(self):
        state = self.api.get("/api/state")
        if not state:
            raise SystemExit("Backend not reachable. Start it first: uvicorn app.main:app --port 8000")
        self.tables = {t["label"]: t for t in state["tables"]}
        self.cam_of = {t["label"]: t["camera_id"] or CAMS[0] for t in state["tables"]}
        print(f"Simulating {len(self.tables)} tables at {self.speed}x"
              f"{' with auto-staff' if self.auto else ' – you are the counter staff (assign & complete in the UI)'}")

        last = {"beat": 0.0, "poll": 0.0, "count": 0.0, "surface": 0.0, "arrive": 0.0}
        for i, label in enumerate(random.sample(list(self.tables), k=min(3, len(self.tables)))):
            self.later(2 + i * 4, self.seat, label)

        while True:
            now = time.monotonic()
            while self.q and self.q[0][0] <= now:
                _, _, fn, args, kwargs = heapq.heappop(self.q)
                fn(*args, **kwargs)

            if now - last["beat"] >= 10:
                last["beat"] = now
                for cam in CAMS:
                    self.api.post("/api/events", {"type": "camera.heartbeat", "camera_id": cam})
            if now - last["poll"] >= 2:
                last["poll"] = now
                state = self.api.get("/api/state")
                if state:
                    self.tables = {t["label"]: t for t in state["tables"]}
                    self.react_to_tasks(state)
            if now - last["count"] >= 15:
                last["count"] = now
                self.event("people.count", inside=sum(self.party.values()) + 3)
            if now - last["surface"] >= 10 / self.speed:
                last["surface"] = now
                for label, items in self.surface.items():
                    self.event("table.surface", label, items=items)
            if now - last["arrive"] >= 1:
                last["arrive"] = now
                free = [l for l, t in self.tables.items() if t["status"] == "vacant" and l not in self.busy]
                if free and random.random() < 0.035 * self.speed:
                    self.seat(random.choice(free))
            time.sleep(0.1)


MENU = ["2x Masala Dosa, 1x Filter Coffee", "1x Veg Biryani, 2x Lassi", "3x Paneer Tikka, 1x Naan basket",
        "2x Thali", "1x Butter Chicken, 2x Roti, 1x Lime Soda", "4x Idli, 2x Vada, 2x Tea"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--key", default="", help="device key (RI_DEVICE_KEY)")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--auto-staff", action="store_true", help="also simulate counter staff actions")
    ap.add_argument("--seed", type=int)
    args = ap.parse_args()
    if args.seed is not None:
        random.seed(args.seed)
    try:
        Sim(Api(args.url, args.key), args.speed, args.auto_staff).run()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
