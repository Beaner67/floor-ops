"""Draw table zones on a camera frame and print them as config YAML.

    python -m vision.calibrate --source rtsp://user:pass@cam/stream

Left-click: add polygon point. Right-click / Enter: finish current table.
'u': undo point. 'q': quit and print YAML.
"""
import argparse

import cv2
import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    args = ap.parse_args()
    src = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(src)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"could not read a frame from {args.source}")
    h, w = frame.shape[:2]
    tables: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []

    def on_mouse(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN:
            current.append((round(x / w, 3), round(y / h, 3)))
        elif event == cv2.EVENT_RBUTTONDOWN and len(current) >= 3:
            tables.append(current.copy())
            current.clear()

    cv2.namedWindow("calibrate")
    cv2.setMouseCallback("calibrate", on_mouse)
    while True:
        img = frame.copy()
        for i, poly in enumerate(tables):
            pts = np.array([(int(x * w), int(y * h)) for x, y in poly], dtype=np.int32)
            cv2.polylines(img, [pts], True, (0, 200, 0), 2)
            cv2.putText(img, f"table {i + 1}", tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 0), 2)
        for x, y in current:
            cv2.circle(img, (int(x * w), int(y * h)), 4, (0, 140, 255), -1)
        cv2.imshow("calibrate", img)
        key = cv2.waitKey(30) & 0xFF
        if key == ord("q"):
            break
        if key == 13 and len(current) >= 3:
            tables.append(current.copy())
            current.clear()
        if key == ord("u") and current:
            current.pop()
    cv2.destroyAllWindows()
    print("    tables:")
    for i, poly in enumerate(tables):
        print(f"      - label: \"{i + 1}\"\n        polygon: {[list(p) for p in poly]}")


if __name__ == "__main__":
    main()
