"""Vision worker: one thread per camera.

    python -m vision.run --config config.yaml [--show]

Each camera thread: read frame (RTSP / webcam index / video file) -> YOLO pose +
ByteTrack -> per-table zone logic -> debounced events -> backend.
Frames are processed in memory and never written to disk.
"""
from __future__ import annotations

import argparse
import logging
import threading
import time

import cv2
import numpy as np
import yaml

from .client import EventClient
from .detector import Detector
from .zones import LineCounter, TableMonitor, point_in_polygon

log = logging.getLogger("vision")


def _source(value):
    return int(value) if isinstance(value, int) or (isinstance(value, str) and value.isdigit()) else value


class CameraWorker(threading.Thread):
    def __init__(self, cam: dict, client: EventClient, models: dict, show: bool):
        super().__init__(daemon=True, name=cam["id"])
        self.cam, self.client, self.show = cam, client, show
        self.detector = Detector(models.get("pose", "yolo11n-pose.pt"), models.get("objects", "yolo11n.pt"),
                                 conf=models.get("conf", 0.4), device=models.get("device"))
        self.fps = cam.get("fps", 5)
        self.surface_every = cam.get("surface_every_s", 2.0)
        timing = cam.get("timing", {})
        self.tables = [TableMonitor(label=str(t["label"]), polygon=[tuple(p) for p in t["polygon"]],
                                    surface=[tuple(p) for p in t["surface"]] if t.get("surface") else None,
                                    **timing) for t in cam.get("tables", [])]
        line = cam.get("entrance_line")
        self.line = LineCounter(tuple(line["a"]), tuple(line["b"]), line.get("inside_sign", 1)) if line else None
        self.count_people = cam.get("count_people", False)

    def emit(self, events: list[dict]) -> None:
        for e in events:
            log.info("[%s] %s %s %s", self.cam["id"], e["type"], e.get("table", ""), e.get("data", ""))
            self.client.send(self.cam["id"], e)

    def run(self) -> None:
        src = _source(self.cam["source"])
        cap = None
        last_frame = last_beat = last_count = last_surface = 0.0
        surface_counts: dict[str, int] = {}
        while True:
            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(src)
                if not cap.isOpened():
                    log.warning("[%s] cannot open %s; retrying in 5s", self.cam["id"], src)
                    time.sleep(5)
                    continue
            ok, frame = cap.read()
            if not ok:
                cap.release()
                cap = None
                time.sleep(1)
                continue
            now = time.monotonic()
            if now - last_frame < 1 / self.fps:
                continue
            last_frame = now

            people = self.detector.people(frame)
            if now - last_surface >= self.surface_every:
                last_surface = now
                items = self.detector.tableware_centres(frame)
                surface_counts = {t.label: sum(point_in_polygon(c, t.surface or t.polygon) for c in items)
                                  for t in self.tables}
                fresh_surface = True
            else:
                fresh_surface = False

            for table in self.tables:
                self.emit(table.update(now, people, surface_counts.get(table.label) if fresh_surface else None))
            if self.line:
                self.emit(self.line.update(people))
            if self.count_people and now - last_count >= 15:
                last_count = now
                self.emit([{"type": "people.count", "data": {"inside": len(people)}}])
            if now - last_beat >= 10:
                last_beat = now
                self.client.send(self.cam["id"], {"type": "camera.heartbeat", "data": {}})

            if self.show:
                self._draw(frame, people)

    def _draw(self, frame, people) -> None:
        h, w = frame.shape[:2]
        for t in self.tables:
            pts = [(int(x * w), int(y * h)) for x, y in t.polygon]
            colour = (0, 140, 255) if t.occupied else (0, 200, 0)
            cv2.polylines(frame, [np.array(pts, dtype=np.int32)], True, colour, 2)
            cv2.putText(frame, f"T{t.label}", pts[0], cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2)
        for p in people:
            x1, y1, x2, y2 = (int(p.box[0] * w), int(p.box[1] * h), int(p.box[2] * w), int(p.box[3] * h))
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0) if not p.hand_raised else (0, 0, 255), 2)
            cv2.putText(frame, f"#{p.track_id}", (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
        cv2.imshow(self.cam["id"], frame)
        cv2.waitKey(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--show", action="store_true", help="display annotated video (demo/debug)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    client = EventClient(cfg["backend_url"], cfg.get("device_key", ""))
    workers = [CameraWorker(cam, client, cfg.get("models", {}), args.show) for cam in cfg["cameras"]]
    for w in workers:
        w.start()
    log.info("started %d camera worker(s)", len(workers))
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
