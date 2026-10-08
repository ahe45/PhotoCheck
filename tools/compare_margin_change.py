"""Reproduce the historical 0.2.1-to-0.3 margin change comparison."""
import csv
import json
from collections import Counter
from pathlib import Path


root = Path(__file__).resolve().parent.parent


def read(name):
    with (root / "build" / name).open(encoding="utf-8-sig", newline="") as handle:
        return {row["상대 경로"]: row for row in csv.DictReader(handle)}


old = read("sample-frozen-criteria-0.2.1.csv")
new = read("sample-frozen-criteria-0.3.csv")
assert set(old) == set(new)
assert {row["검수 기준 버전"] for row in new.values()} == {"strict-0.3-margin-unvalidated"}
removed_reason = "머리·턱 여백 또는 얼굴 비율 확인 필요"
mismatches = []
regressions = []
promoted = 0
for name, previous in old.items():
    remaining = [r for r in previous["판정 사유"].split(" | ") if r and r != removed_reason]
    expected = "정상" if previous["파일 검사"] == "통과" and not remaining else previous["자동 분류"]
    actual = new[name]["자동 분류"]
    if actual != expected:
        mismatches.append(name)
    if previous["자동 분류"] == "정상" and actual != "정상":
        regressions.append(name)
    if previous["자동 분류"] == "확인 필요" and actual == "정상":
        promoted += 1
report = {"ok": not mismatches and not regressions, "total": len(new),
          "previous_counts": dict(Counter(row["자동 분류"] for row in old.values())),
          "current_counts": dict(Counter(row["자동 분류"] for row in new.values())),
          "review_to_normal": promoted, "normal_regressions": regressions,
          "policy_prediction_mismatches": mismatches,
          "example_statuses": {name: new[name]["자동 분류"] for name in
              ("120200002.jpg", "120801148.jpg", "127300486.jpg")},
          "accuracy_measured": False}
(root / "build" / "margin-change-comparison.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=True, indent=2))
assert report["ok"], report
