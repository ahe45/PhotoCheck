"""Read-only contour feasibility probe, not an application classification rule."""
import csv
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


root = Path(__file__).resolve().parent.parent
with (root / "build" / "sample-frozen-criteria-0.3.csv").open(encoding="utf-8-sig", newline="") as handle:
    recorded = {r["상대 경로"]: json.loads(r["분석 수치"]) for r in csv.DictReader(handle)}
cases = []
for name in ("128100020.jpg", "120200002.jpg", "120801148.jpg", "127300486.jpg"):
    path = root / "sample" / name
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with Image.open(path) as original:
        with ImageOps.exif_transpose(original) as image:
            gray = np.asarray(image.convert("L"))
    height, width = gray.shape
    m = recorded[name]
    center = (m["face_center_x"] * width,
              (m["forehead_y_ratio"] + m["chin_y_ratio"]) * height / 2)
    blurred = cv2.GaussianBlur(gray, (3, 3), .8)
    # Supplementary straight-line evidence; open/weak paper edges may not form
    # a closed contour. Lines alone do not establish that a photo was recaptured.
    line_edges = cv2.Canny(gray, 5, 15)
    lines = cv2.HoughLinesP(line_edges, 1, np.pi / 180, 25,
                           minLineLength=max(20, round(width * .3)), maxLineGap=8)
    outer_lines = []
    face_left = (m["face_center_x"] - m["face_width_ratio"] / 2) * width
    face_right = (m["face_center_x"] + m["face_width_ratio"] / 2) * width
    for x1, y1, x2, y2 in ([] if lines is None else lines.reshape(-1, 4)):
        dx, dy = abs(int(x2) - int(x1)), abs(int(y2) - int(y1))
        horizontal = dx > 0 and dy / dx < .10
        vertical = dy > 0 and dx / dy < .10
        if (horizontal and (max(y1, y2) < m["forehead_y_ratio"] * height
                            or min(y1, y2) > m["chin_y_ratio"] * height)) or (
            vertical and (max(x1, x2) < face_left or min(x1, x2) > face_right)):
            outer_lines.append([int(v) for v in (x1, y1, x2, y2)])
    candidates = []
    for low, high in ((2, 6), (5, 15), (10, 30), (20, 60)):
        edges = cv2.Canny(blurred, low, high)
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            polygon = cv2.approxPolyDP(contour, .02 * cv2.arcLength(contour, True), True)
            area = cv2.contourArea(polygon)
            if len(polygon) != 4 or not cv2.isContourConvex(polygon) or not .15 < area / (width * height) < .9:
                continue
            points = polygon.reshape(-1, 2)
            if (points[:, 0].min() <= width * .015 or points[:, 0].max() >= width * .985
                or points[:, 1].min() <= height * .015 or points[:, 1].max() >= height * .985):
                continue
            if cv2.pointPolygonTest(polygon, center, False) < 0:
                continue
            x, y, w, h = cv2.boundingRect(polygon)
            if not .5 < w / h < 1 or area / (w * h) < .8:
                continue
            candidates.append({"canny_thresholds": [low, high], "corners": points.tolist(),
                               "area_ratio": round(area / (width * height), 4),
                               "bounding_rect": [x, y, w, h]})
    cases.append({"file": name, "size": [width, height], "candidates": candidates,
                  "outer_straight_line_evidence": outer_lines,
                  "original_unchanged": before == hashlib.sha256(path.read_bytes()).hexdigest()})
report = {"applied_to_application": False, "accuracy_measured": False,
          "note": "Exploratory contour candidates on four photos; not a validated recapture detector",
          "cases": cases}
(root / "build" / "recapture-probe.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=True, indent=2))
