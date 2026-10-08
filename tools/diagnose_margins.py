"""Explain the previous margin triggers using the preserved 0.2.1 results.

The alternative is a counterfactual only; it never changes application criteria,
sample images or recorded classifications.
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path


root = Path(__file__).resolve().parent.parent
source = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "build" / "sample-frozen-criteria-0.2.1.csv"
with source.open(encoding="utf-8-sig", newline="") as handle:
    rows = list(csv.DictReader(handle))
margin_reason = "머리·턱 여백 또는 얼굴 비율 확인 필요"
causes = Counter()
examples = []
margin_only = 0
proposed_normals = 0
for row in rows:
    metrics = json.loads(row["분석 수치"])
    reasons = row["판정 사유"].split(" | ") if row["판정 사유"] else []
    if margin_reason in reasons:
        assert all(key in metrics for key in ("forehead_y_ratio", "chin_y_ratio", "face_width_ratio")), "Re-run the current executable first to record margin measurements"
        causes["combined_margin_flag"] += 1
        causes["forehead_at_or_above_top_10_percent"] += metrics.get("forehead_y_ratio", 1) <= .10
        causes["chin_at_or_below_67_percent"] += metrics.get("chin_y_ratio", 0) >= .67
        causes["face_width_at_or_below_15_percent"] += metrics.get("face_width_ratio", 1) <= .15
        if reasons == [margin_reason]:
            margin_only += 1
        if row["상대 경로"] in {"120200002.jpg", "120801148.jpg", "127300486.jpg"}:
            examples.append({"file": row["상대 경로"], "metrics": metrics, "reasons": reasons})
    # Keep the existing independent 2.5%-97.5% landmark boundary check,
    # 30% height, centering, orientation, confidence and all other checks.
    remaining = [reason for reason in reasons if reason != margin_reason]
    if row["파일 검사"] == "통과" and not remaining:
        proposed_normals += 1

report = {
    "source_file": str(source.resolve()),
    "total": len(rows),
    "criteria_versions": sorted({row["검수 기준 버전"] for row in rows}),
    "actual_counts": dict(Counter(row["자동 분류"] for row in rows)),
    "margin_subcauses": dict(causes),
    "margin_only": margin_only,
    "examples": examples,
    "proposal": {
        "applied_to_application": False,
        "description": "Remove the combined 10% forehead / 67% chin / 15% width gate; keep independent landmark boundary and all other checks",
        "normal": proposed_normals,
        "remaining_non_normal": len(rows) - proposed_normals,
        "accuracy_measured": False,
        "note": "No ground truth labels. Coordinates in CSV are rounded diagnostic measurements.",
    },
}
output = source.with_suffix(".margin-diagnosis.json")
output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=True, indent=2))
