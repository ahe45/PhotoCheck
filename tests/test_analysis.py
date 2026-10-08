from types import SimpleNamespace as NS
from pathlib import Path
import math

import numpy as np
from PIL import Image
import pytest

from photocheck.analysis import Analyzer, Criteria
from photocheck.domain import CRITERIA_VERSION, Check, Result, Status
from photocheck.files import load_image


def fixture_analyzer():
    analyzer = Analyzer.__new__(Analyzer)
    analyzer.criteria = Criteria()
    analyzer.version = "test-model"
    analyzer._image = lambda pixels: pixels
    analyzer.text = NS(detect=lambda *_: ([], {"text_region_count": 0}))
    points = [NS(x=0.5, y=0.4, z=0.0) for _ in range(478)]
    for i, x, y in [(33, .4, .36), (263, .6, .36), (1, .5, .44), (10, .5, .2),
                     (152, .5, .6), (234, .34, .43), (454, .66, .43), (61, .43, .54), (291, .57, .54)]:
        points[i] = NS(x=x, y=y, z=0.0)
    detection = NS(categories=[NS(score=.98)], bounding_box=NS(origin_x=90, origin_y=70, width=120, height=180))
    calls = []
    responses = [[detection]]
    def detect(pixels):
        calls.append(np.array(pixels))
        return NS(detections=responses[min(len(calls) - 1, len(responses) - 1)])
    analyzer.detector = NS(detect=detect)
    analyzer.face = NS(detect=lambda _: NS(face_landmarks=[points]))
    def forbidden_body_inference(_):
        raise AssertionError("Shoulders/chest must never be required")
    analyzer.pose = NS(detect=forbidden_body_inference)
    return analyzer, points, detection, calls, responses


def run(analyzer, size=(300, 400), metrics=None):
    result = Result(Path("test.png"), "test.png", file_check=Check.PASS, metrics=metrics or {})
    with Image.new("RGB", size, "white") as image:
        analyzer.analyze(image, result)
    return result.finalize()


def test_upright_face_passes_without_any_body_evidence_or_rotated_probes():
    analyzer, _, _, calls, _ = fixture_analyzer()
    result = run(analyzer)
    assert result.status == Status.NORMAL, result.reasons
    assert len(calls) == 1
    assert result.criteria_version == CRITERIA_VERSION


@pytest.mark.parametrize("height, expected", [(99, Status.REVIEW), (100, Status.REVIEW),
                                             (101, Status.NORMAL), (280, Status.NORMAL)])
def test_height_boundary_is_inclusive_and_has_no_upper_limit(height, expected):
    analyzer, _, detection, *_ = fixture_analyzer()
    detection.bounding_box.height = height
    detection.bounding_box.origin_y = 100
    result = run(analyzer)
    assert result.status == expected, result.reasons
    assert result.metrics["face_height_ratio"] == pytest.approx(height / 400)


def test_height_ratio_is_used_instead_of_area_ratio():
    analyzer, _, detection, *_ = fixture_analyzer()
    detection.bounding_box = NS(origin_x=120, origin_y=70, width=60, height=140)
    result = run(analyzer)
    assert result.status == Status.NORMAL, result.reasons
    assert result.metrics["face_height_ratio"] == .35


@pytest.mark.parametrize("angle, expected", [(-5.01, Check.REVIEW), (-5.0, Check.REVIEW),
                                           (-4.99, Check.PASS), (4.99, Check.PASS),
                                           (5.0, Check.REVIEW), (5.01, Check.REVIEW)])
def test_tilt_threshold_is_five_degrees_in_both_directions(angle, expected, monkeypatch):
    analyzer, points, _, *_ = fixture_analyzer()
    dx = (points[263].x - points[33].x) * 300
    points[263].y = points[33].y + dx * math.tan(math.radians(angle)) / 400
    if abs(angle) == 5:
        # Exercise exact decision boundaries without floating point geometry noise.
        monkeypatch.setattr("photocheck.analysis.math.degrees", lambda _: angle)
    result = run(analyzer)
    assert result.direction_check == expected, result.reasons
    assert result.metrics["roll_degrees"] == pytest.approx(angle)
    assert any("얼굴 기울기" in r for r in result.reasons) == (expected == Check.REVIEW)


@pytest.mark.parametrize("score, expected", [(.7999, Status.REVIEW), (.8, Status.REVIEW),
                                            (.80001, Status.NORMAL), (.85, Status.NORMAL),
                                            (.90, Status.NORMAL)])
def test_confidence_reviews_only_at_or_below_point_eight(score, expected):
    analyzer, _, detection, *_ = fixture_analyzer()
    detection.categories[0].score = score
    result = run(analyzer)
    assert result.status == expected, result.reasons
    assert any("신뢰도 부족" in r for r in result.reasons) == (score <= .8)


def test_margin_measurements_are_recorded_for_diagnosis():
    analyzer, *_ = fixture_analyzer()
    result = run(analyzer)
    assert result.metrics["forehead_y_ratio"] == .2
    assert result.metrics["chin_y_ratio"] == .6
    assert result.metrics["face_width_ratio"] == .32


@pytest.mark.parametrize("forehead, chin, face_width", [(.08, .6, .32), (.2, .77, .32),
                                                       (.2, .6, .14)])
def test_old_composition_limits_no_longer_block_an_uncropped_face(forehead, chin, face_width):
    analyzer, points, detection, *_ = fixture_analyzer()
    detection.bounding_box.height = 280
    points[10].y, points[152].y = forehead, chin
    points[1].y = forehead + .55 * (chin - forehead)
    points[234].x, points[454].x = .5 - face_width / 2, .5 + face_width / 2
    result = run(analyzer)
    assert result.status == Status.NORMAL, result.reasons


@pytest.mark.parametrize("index, axis, value, expected, label", [
    (10, "y", .02499, Check.REVIEW, "이마"), (10, "y", .025, Check.REVIEW, "이마"),
    (10, "y", .02501, Check.PASS, "이마"),
    (152, "y", .97499, Check.PASS, "턱"), (152, "y", .975, Check.REVIEW, "턱"),
    (152, "y", .97501, Check.REVIEW, "턱"),
    (61, "x", .02499, Check.REVIEW, "입"), (61, "x", .025, Check.REVIEW, "입"),
    (61, "x", .02501, Check.PASS, "입"),
    (291, "x", .97499, Check.PASS, "입"), (291, "x", .975, Check.REVIEW, "입"),
    (291, "x", .97501, Check.REVIEW, "입"),
])
def test_near_frame_boundaries_are_inclusive_and_have_specific_reasons(index, axis, value, expected, label):
    analyzer, points, detection, *_ = fixture_analyzer()
    detection.bounding_box.height = 280
    setattr(points[index], axis, value)
    points[1].y = points[10].y + .55 * (points[152].y - points[10].y)
    result = run(analyzer)
    assert result.framing_check == expected, result.reasons
    boundary_reasons = [r for r in result.reasons if "경계 근접" in r]
    assert bool(boundary_reasons) == (expected == Check.REVIEW)
    if boundary_reasons:
        assert any(r.startswith(label + " 경계 근접") and "2.5%~97.5%" in r for r in boundary_reasons)
        assert "머리·턱 여백" in result.tags


def test_insufficient_face_height_has_its_own_measured_reason():
    analyzer, _, detection, *_ = fixture_analyzer()
    detection.bounding_box.height = 100
    detection.bounding_box.origin_y = 100
    result = run(analyzer)
    assert result.status == Status.REVIEW
    assert any(r.startswith("얼굴 높이 부족") and "25.0%" in r for r in result.reasons)
    assert "머리·턱 여백" not in result.tags


@pytest.mark.parametrize("size, expected", [((400, 300), Check.REVIEW),
                                           ((300, 300), Check.PASS), ((300, 400), Check.PASS)])
def test_landscape_requires_review_but_square_is_not_landscape(size, expected):
    analyzer, *_ = fixture_analyzer()
    result = run(analyzer, size)
    assert result.direction_check == expected
    assert any("가로가 세로" in r for r in result.reasons) == (expected == Check.REVIEW)


def test_original_display_resolution_is_used_after_thumbnail_rounding(tmp_path):
    path = tmp_path / "slight-landscape.png"
    Image.new("RGB", (321, 320)).save(path)
    thumbnail, _, _ = load_image(path, edge=10)
    assert thumbnail.size == (10, 10)
    assert thumbnail.info["photocheck_display_size"] == (321, 320)
    thumbnail.close()
    analyzer, *_ = fixture_analyzer()
    result = run(analyzer, (300, 300), {"image_width": 321, "image_height": 320})
    assert result.direction_check == Check.REVIEW


@pytest.mark.parametrize("upside_down_found", [True, False])
def test_180_fallback_only_after_missing_upright_face(upside_down_found):
    analyzer, _, detection, calls, responses = fixture_analyzer()
    responses[:] = [[], [detection] if upside_down_found else []]
    result = Result(Path("test.png"), "test.png", file_check=Check.PASS)
    pixels = np.arange(300 * 400 * 3, dtype=np.uint8).reshape(400, 300, 3)
    with Image.fromarray(pixels) as image:
        analyzer.analyze(image, result)
    result.finalize()
    assert result.status == Status.REVIEW
    assert len(calls) == 2
    assert np.array_equal(calls[1], np.rot90(calls[0], 2))
    assert result.metrics["rotated_180_face_count"] == int(upside_down_found)
    assert any("180° 회전 후 얼굴 검출" in r for r in result.reasons) == upside_down_found


def test_landmark_failure_does_not_trigger_rotation_when_face_was_detected():
    analyzer, _, _, calls, _ = fixture_analyzer()
    analyzer.face.detect = lambda _: NS(face_landmarks=[])
    result = run(analyzer)
    assert result.status == Status.REVIEW
    assert len(calls) == 1


@pytest.mark.parametrize("problem, phrase", [("roll", "얼굴 기울기"), ("center", "중앙 범위"),
    ("head_margin", "이마 경계 근접"), ("confidence", "신뢰도 부족"),
    ("profile", "정면 방향"), ("multiple", "얼굴 수 확인"), ("boundary", "입 경계 근접")])
def test_retained_face_rules_still_require_review(problem, phrase):
    analyzer, points, detection, *_ = fixture_analyzer()
    if problem == "roll":
        points[263].y += .04
    elif problem == "center":
        points[234].x += .2
        points[454].x += .2
    elif problem == "head_margin":
        points[10].y = .02
    elif problem == "confidence":
        detection.categories[0].score = Criteria().confidence
    elif problem == "profile":
        points[1].x = .56
    elif problem == "multiple":
        analyzer.face.detect = lambda _: NS(face_landmarks=[points, points])
    elif problem == "boundary":
        points[61].x = .02
    result = run(analyzer)
    assert result.status == Status.REVIEW
    assert any(phrase in reason for reason in result.reasons), result.reasons
