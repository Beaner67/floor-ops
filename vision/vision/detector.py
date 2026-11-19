"""YOLO + ByteTrack wrapper (ultralytics).

- Pose model tracks people (ByteTrack keeps IDs stable across frames) and gives
  keypoints for raised-hand detection.
- Detection model counts tableware/food on table surfaces (no tracking needed).

One Detector per camera: the tracker keeps per-stream state.
No face recognition or re-identification is performed; track IDs are
per-stream integers that are discarded when a person leaves view.
"""
from __future__ import annotations

import numpy as np

from .zones import Person

# COCO classes left on a table after a meal: bottle, wine glass, cup, fork, knife,
# spoon, bowl, and food items (banana … cake).
TABLEWARE_CLASSES = [39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55]

# COCO keypoint indices
NOSE, L_SHOULDER, R_SHOULDER, L_WRIST, R_WRIST = 0, 5, 6, 9, 10


def hand_raised(kpts: np.ndarray, conf: np.ndarray | None, box_h: float, min_conf: float = 0.5) -> bool:
    """A wrist clearly above both the shoulders and the nose."""
    def ok(i: int) -> bool:
        return conf is None or conf[i] >= min_conf

    ref = [kpts[i][1] for i in (NOSE, L_SHOULDER, R_SHOULDER) if ok(i)]
    if not ref:
        return False
    top = min(ref) - 0.08 * box_h
    return any(ok(w) and kpts[w][1] > 0 and kpts[w][1] < top for w in (L_WRIST, R_WRIST))


class Detector:
    def __init__(self, pose_model: str = "yolo11n-pose.pt", object_model: str = "yolo11n.pt",
                 conf: float = 0.4, device: str | None = None):
        from ultralytics import YOLO  # heavy import, keep lazy

        self.pose = YOLO(pose_model)
        self.objects = YOLO(object_model)
        self.conf = conf
        self.device = device

    def people(self, frame) -> list[Person]:
        h, w = frame.shape[:2]
        res = self.pose.track(frame, persist=True, tracker="bytetrack.yaml", conf=self.conf,
                              classes=[0], verbose=False, device=self.device)[0]
        if res.boxes is None or res.boxes.id is None:
            return []
        boxes = res.boxes.xyxyn.cpu().numpy()
        ids = res.boxes.id.int().cpu().tolist()
        kxy = res.keypoints.xyn.cpu().numpy() if res.keypoints is not None else None
        kconf = res.keypoints.conf.cpu().numpy() if res.keypoints is not None and res.keypoints.conf is not None else None
        out = []
        for i, (box, tid) in enumerate(zip(boxes, ids)):
            raised = False
            if kxy is not None:
                raised = hand_raised(kxy[i], kconf[i] if kconf is not None else None, box[3] - box[1])
            out.append(Person(track_id=tid, box=tuple(float(v) for v in box), hand_raised=raised))
        return out

    def tableware_centres(self, frame) -> list[tuple[float, float]]:
        res = self.objects.predict(frame, conf=0.3, classes=TABLEWARE_CLASSES, verbose=False, device=self.device)[0]
        if res.boxes is None:
            return []
        b = res.boxes.xyxyn.cpu().numpy()
        return [(float((x1 + x2) / 2), float((y1 + y2) / 2)) for x1, y1, x2, y2 in b]
