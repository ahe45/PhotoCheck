"""Verify the 25%-height / 5-degree change against the preceding full scan."""
import csv
import json
from collections import Counter
from pathlib import Path


root = Path(__file__).resolve().parent.parent


def read(name):
    with (root / "build" / name).open(encoding="utf-8-sig", newline="") as handle:
        return {row["상대 경로"]: row for row in csv.DictReader(handle)}


old = read("sample-frozen-criteria-0.3.csv")
new = read("sample-frozen-criteria-0.4.csv")
assert set(old) == set(new)
assert {r["검수 기준 버전"] for r in new.values()} == {"strict-0.4-height25-roll5-unvalidated"}
regressions = [name for name, row in old.items() if row["자동 분류"] == "정상" and new[name]["자동 분류"] != "정상"]
promoted = sum(row["자동 분류"] == "확인 필요" and new[name]["자동 분류"] == "정상" for name, row in old.items())
example = new["128100020.jpg"]
report = {"ok": not regressions, "total": len(new),
          "previous_counts": dict(Counter(r["자동 분류"] for r in old.values())),
          "current_counts": dict(Counter(r["자동 분류"] for r in new.values())),
          "review_to_normal": promoted, "normal_regressions": regressions,
          "recapture_example": {"file": "128100020.jpg", "status": example["자동 분류"],
                               "reasons": example["판정 사유"], "metrics": json.loads(example["분석 수치"])},
          "recapture_detector_applied": False, "accuracy_measured": False}
(root / "build" / "threshold-change-comparison.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=True, indent=2))
assert report["ok"], report
