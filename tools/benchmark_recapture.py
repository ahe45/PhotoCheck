"""Time the exploratory edge/contour/line stage on decoded sample images.

This is not a complete recapture detector or an integrated app benchmark.
No application criteria or source photos are changed.
"""
import csv
import json
from pathlib import Path
import statistics
import sys
import time

import cv2
import numpy as np

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from photocheck.files import load_image

cv2.setNumThreads(1)
with (root / "build" / "sample-frozen.csv").open(encoding="utf-8-sig", newline="") as handle:
    rows = list(csv.DictReader(handle))


def probe(image, m):
    with image.convert("L") as converted:
        gray = np.asarray(converted)
    height, width = gray.shape
    center = (m.get("face_center_x", .5) * width,
              (m.get("forehead_y_ratio", .25) + m.get("chin_y_ratio", .75)) * height / 2)
    blurred = cv2.GaussianBlur(gray, (3, 3), .8)
    line_edges = cv2.Canny(gray, 5, 15)
    lines = cv2.HoughLinesP(line_edges, 1, np.pi / 180, 25,
                           minLineLength=max(20, round(width * .3)), maxLineGap=8)
    face_left = (m.get("face_center_x", .5) - m.get("face_width_ratio", .3) / 2) * width
    face_right = (m.get("face_center_x", .5) + m.get("face_width_ratio", .3) / 2) * width
    outer_lines = []
    for x1, y1, x2, y2 in ([] if lines is None else lines.reshape(-1, 4)):
        dx, dy = abs(int(x2) - int(x1)), abs(int(y2) - int(y1))
        if ((dx > 0 and dy / dx < .10) and (
            max(y1, y2) < m.get("forehead_y_ratio", .25) * height
            or min(y1, y2) > m.get("chin_y_ratio", .75) * height)) or (
            dy > 0 and dx / dy < .10 and (max(x1, x2) < face_left or min(x1, x2) > face_right)):
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
            candidates.append(points.tolist())
    return len(candidates), len(outer_lines)


durations = []
read_seconds = 0
errors = []
started = time.perf_counter()
for i, row in enumerate(rows, 1):
    before_read = time.perf_counter()
    image, _, reasons = load_image(Path(row["파일 경로"]))
    read_seconds += time.perf_counter() - before_read
    if image is None:
        errors.append(row["상대 경로"])
        continue
    metrics = json.loads(row["분석 수치"])
    try:
        start = time.perf_counter()
        probe(image, metrics)
        durations.append(time.perf_counter() - start)
    finally:
        image.close()
    if i % 3000 == 0:
        print(json.dumps({"processed": i, "compute_seconds": round(sum(durations), 3)}, ensure_ascii=True), flush=True)
baseline = json.loads((root / "build" / "sample-frozen.json").read_text(encoding="utf-8"))["elapsed_seconds"]
ordered = sorted(durations)
total = sum(durations)
report = {"photos": len(durations), "errors": errors, "opencv_threads": 1,
          "analysis_max_edge": 1280, "additional_compute_seconds": round(total, 3),
          "mean_ms": round(statistics.mean(durations) * 1000, 3),
          "median_ms": round(statistics.median(durations) * 1000, 3),
          "p95_ms": round(ordered[int((len(ordered) - 1) * .95)] * 1000, 3),
          "separate_decode_seconds": round(read_seconds, 3),
          "benchmark_wall_seconds": round(time.perf_counter() - started, 3),
          "current_app_baseline_seconds": baseline,
          "arithmetic_added_percent": round(total / baseline * 100, 2),
          "arithmetic_baseline_plus_compute_seconds": round(baseline + total, 3),
          "limitations": "Exploratory candidate stage only; background validation, paper model inference, IPC and integrated scheduling not measured; current sample resolutions only",
          "applied_to_application": False}
(root / "build" / "recapture-timing.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=True, indent=2), flush=True)
