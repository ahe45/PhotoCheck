"""Read-only heuristic probe using measurements from the archived baseline."""
import csv
import json
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from photocheck.criteria import Criteria
from photocheck.files import load_image
from photocheck.recapture import detect_recapture

root = Path(__file__).resolve().parent.parent
with (root/'build/sample-frozen-criteria-0.4.csv').open(encoding='utf-8-sig', newline='') as handle:
    rows = list(csv.DictReader(handle))
detector_seconds = 0
candidates, suspected = [], []
criteria = Criteria()
start = time.perf_counter()
for row in rows:
    measurements = json.loads(row['분석 수치'])
    if 'face_center_x' not in measurements:
        continue
    path = root/'sample'/row['상대 경로']
    if not path.exists():
        matches = list((root/'sample').rglob(Path(row['상대 경로']).name))
        if len(matches) != 1:
            raise RuntimeError(f"Archived sample location is missing or ambiguous: {row['상대 경로']}")
        path = matches[0]
    image, _, _ = load_image(path)
    if image is None:
        continue
    try:
        rgb = np.asarray(image)
        t = time.perf_counter()
        result = detect_recapture(rgb, measurements, criteria)
        detector_seconds += time.perf_counter()-t
        if result['recapture_candidate']:
            candidates.append(row['상대 경로'])
        if result['recapture_suspected']:
            suspected.append({'file':row['상대 경로'], 'metrics':result})
    finally:
        image.close()
report = {'total':len(rows), 'candidate_count':len(candidates), 'suspected_count':len(suspected),
          'detector_seconds':round(detector_seconds,3), 'wall_seconds':round(time.perf_counter()-start,3),
          'candidates':candidates, 'suspected':suspected, 'criteria':criteria.snapshot(), 'accuracy_measured':False}
(root/'build/recapture-fast-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:report[k] for k in ('total','candidate_count','suspected_count','detector_seconds','wall_seconds')},ensure_ascii=True))
print([r['file'] for r in suspected])
