"""Immutable, validated inspection settings shared by UI and inference process."""
from dataclasses import asdict, dataclass, fields
import hashlib
import json
import math
import os
from pathlib import Path
import uuid

from .domain import CRITERIA_VERSION


@dataclass(frozen=True)
class Criteria:
    version: str = CRITERIA_VERSION
    check_landscape: bool = True
    check_aspect: bool = True
    check_confidence: bool = True
    check_roll: bool = True
    check_height: bool = True
    check_center: bool = True
    check_boundary: bool = True
    check_front: bool = True
    check_recapture: bool = True
    check_text: bool = True
    text_confidence: float = .60
    text_height_min: float = .008
    text_edge: float = 512
    text_min_chars: float = 3
    text_rec_confidence: float = .60
    confidence: float = .80
    aspect_width: float = 3.0
    aspect_height: float = 4.0
    aspect_tolerance: float = .5
    roll_degrees: float = 5.0
    eye_span_min: float = .10
    center_offset: float = .07
    face_height_min: float = .25
    boundary_margin: float = .025
    front_symmetry_max: float = .12
    depth_asymmetry_max: float = .18
    nose_height_min: float = .40
    nose_height_max: float = .66
    paper_area_min: float = .15
    paper_area_max: float = .85
    paper_edge_min: float = .25
    paper_contrast_min: float = 3.0
    paper_background_min: float = 12.0

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name.startswith("check_"):
                if type(value) is not bool:
                    raise ValueError(f"잘못된 검사 항목: {f.name}")
            elif f.name != "version":
                low, high = RANGES[f.name]
                if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                    raise ValueError(f"기준값 범위 오류: {f.name}")
        if self.nose_height_min >= self.nose_height_max or self.paper_area_min >= self.paper_area_max:
            raise ValueError("최솟값은 최댓값보다 작아야 합니다.")
        if self.version != CRITERIA_VERSION:
            raise ValueError("지원하지 않는 검사 기준 버전입니다.")
        if self.text_min_chars != int(self.text_min_chars):
            raise ValueError("최소 연속 글자 수는 정수여야 합니다.")

    def snapshot(self):
        return asdict(self)

    @property
    def identity(self):
        return hashlib.sha256(json.dumps(self.snapshot(), sort_keys=True).encode()).hexdigest()[:12]


RANGES = {
    "text_confidence": (.1, 1), "text_height_min": (0, .2), "text_edge": (128, 1280),
    "text_min_chars": (3, 30), "text_rec_confidence": (.1, 1),
    "aspect_width": (.1, 100), "aspect_height": (.1, 100), "aspect_tolerance": (0, 100),
    "confidence": (0, 1), "roll_degrees": (.1, 90), "eye_span_min": (0, .5),
    "center_offset": (.001, .5), "face_height_min": (0, .99), "boundary_margin": (0, .2),
    "front_symmetry_max": (.001, 2), "depth_asymmetry_max": (.001, 2),
    "nose_height_min": (0, 1), "nose_height_max": (0, 1),
    "paper_area_min": (.01, .98), "paper_area_max": (.02, .99),
    "paper_edge_min": (.1, .6), "paper_contrast_min": (1, 100),
    "paper_background_min": (1, 100),
}


def settings_path():
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return base / "PhotoCheck" / "settings.json"


def load_criteria(path=None):
    path = Path(path) if path is not None else settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("criteria"), dict):
            raise ValueError("설정 파일 형식을 확인하세요.")
        values = dict(data["criteria"])
        # Upgrade the preceding saved preferences without changing its file or
        # resetting the user's other thresholds. New fields take their defaults.
        if values.get("version") in ("strict-0.5-settings-recapture-unvalidated", "strict-0.6-aspect-ratio-unvalidated"):
            # Percentage tolerance cannot be reinterpreted as a ratio-unit
            # tolerance. Adopt .5 for the new rule and keep other preferences.
            values.pop("aspect_tolerance_pct", None)
            values["aspect_tolerance"] = .5
            values["version"] = CRITERIA_VERSION
        if values.get("version") in ("strict-0.7-aspect-difference-unvalidated", "strict-0.8-text-presence-unvalidated"):
            values["version"] = CRITERIA_VERSION
        return Criteria(**values), ""
    except FileNotFoundError:
        return Criteria(), ""
    except (OSError, ValueError, TypeError) as error:
        return Criteria(), f"저장된 설정을 읽지 못해 기본값을 적용했습니다: {error}"


def save_criteria(criteria, path=None):
    path = Path(path) if path is not None else settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".settings-{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump({"schema": 1, "criteria": criteria.snapshot()}, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
