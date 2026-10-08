"""Development-only local sample rotation checks; no downloads or original writes."""
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageOps

project = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project))
from photocheck.analysis import Analyzer
from photocheck.files import inspect
from photocheck.domain import Check, Status

source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else project / "sample" / "120200199.jpg"
before_source = hashlib.sha256(source.read_bytes()).hexdigest()
output = project / "build" / "integration-height"
output.mkdir(parents=True, exist_ok=True)
analyzer = Analyzer()
report = {"source": str(source), "model": analyzer.version, "cases": []}
try:
    with Image.open(source) as original, ImageOps.exif_transpose(original) as image:
        image.load()
        for angle in (0, 90, 180, 270):
            path = output / f"회전_{angle}.png"
            with image.rotate(angle, expand=True) as rotated:
                rotated.save(path)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            result = inspect(path, output, analyzer)
            assert before == hashlib.sha256(path.read_bytes()).hexdigest()
            assert not any("분석 실패" in reason for reason in result.reasons), result.reasons
            if angle == 0:
                assert result.status == Status.NORMAL, result.reasons
            else:
                assert result.status == Status.REVIEW, result.reasons
            if angle in (90, 270):
                assert result.direction_check == Check.REVIEW
                assert any("가로가 세로보다" in s for s in result.reasons)
            report["cases"].append({"angle": angle, "status": result.status.value,
                                    "reasons": result.reasons, "metrics": result.metrics})
finally:
    analyzer.close()
report["original_unchanged"] = before_source == hashlib.sha256(source.read_bytes()).hexdigest()
assert report["original_unchanged"]
(output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
