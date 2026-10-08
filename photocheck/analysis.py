"""CPU face inference with the user's height, direction and retained face rules."""
import hashlib
import json
import math
import sys
from decimal import Decimal
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from .domain import CRITERIA_VERSION, Check, Result
from .criteria import Criteria
from .recapture import detect_recapture
from .text_detection import TextDetector, MODEL_NAME, MODEL_HASH, REC_MODEL_NAME, DICT_NAME, location


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


class Analyzer:
    def __init__(self, criteria: Criteria | None = None):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self.mp, self.criteria = mp, criteria or Criteria()
        self.stack = ExitStack()
        folder = resource_root() / "models"
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        buffers = {}
        for item in manifest["models"]:
            data = (folder / item["filename"]).read_bytes()
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise RuntimeError(f"모델 무결성 확인 실패: {item['filename']}")
            buffers[item["filename"]] = data
        self.version = f"mediapipe-{mp.__version__}/" + manifest["version"] + "/face+text-ctc-runs-v1"

        def base(name):
            return BaseOptions(model_asset_buffer=buffers[name], delegate=BaseOptions.Delegate.CPU)

        try:
            self.text = None
            if self.criteria.check_text:
                text_bytes = buffers[MODEL_NAME]
                if hashlib.sha256(text_bytes).hexdigest() != MODEL_HASH:
                    raise RuntimeError("문자 검출 모델 무결성 확인 실패")
                self.text = TextDetector(text_bytes, buffers[REC_MODEL_NAME], buffers[DICT_NAME])
            self.detector = self.stack.enter_context(vision.FaceDetector.create_from_options(
                vision.FaceDetectorOptions(base_options=base("blaze_face_short_range.tflite"),
                                           min_detection_confidence=0.5)))
            self.face = self.stack.enter_context(vision.FaceLandmarker.create_from_options(
                vision.FaceLandmarkerOptions(base_options=base("face_landmarker.task"), num_faces=3,
                    min_face_detection_confidence=0.8, min_face_presence_confidence=0.9)))
        except Exception:
            self.close()
            raise

    def close(self):
        self.stack.close()

    def _image(self, pixels):
        return self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(pixels))

    def analyze(self, image, result: Result):
        c = self.criteria
        result.criteria_version, result.model_version = c.version, self.version
        result.criteria_settings = c.snapshot()
        result.criteria_id = c.identity
        rgb = np.asarray(image)
        height, width = rgb.shape[:2]
        # Original EXIF-normalized resolution survives thumbnail rounding and IPC.
        display_width = result.metrics.get("image_width", width)
        display_height = result.metrics.get("image_height", height)
        result.direction_check = result.framing_check = Check.PASS

        def review(message, tag, direction=False):
            result.reasons.append(message)
            result.tags.add(tag)
            if direction:
                result.direction_check = Check.REVIEW
            else:
                result.framing_check = Check.REVIEW

        # Text is independent of face detection: also check a photo with no face,
        # multiple faces, or failed facial landmarks before their early returns.
        if c.check_text:
            regions, metrics = self.text.detect(rgb, c)
            result.metrics.update(metrics)
            result.text_boxes.extend(box for box, _ in regions)
            if regions:
                places = list(dict.fromkeys(location(box) for box, _ in regions))
                review(f"글자 포함 의심 — {', '.join(places)} ({len(regions)}개 영역, 연속 {c.text_min_chars:g}글자 이상)", "글자 포함 의심")

        if c.check_landscape and display_width > display_height:
            review(f"가로가 세로보다 넓은 사진 ({display_width} × {display_height}px)", "회전·기울기", True)

        # Decimal cross-products preserve inclusive configured boundaries even
        # when the analysis thumbnail or a displayed metric has been rounded.
        if display_width <= 0 or display_height <= 0:
            raise ValueError("유효하지 않은 사진 가로·세로 크기")
        aspect = display_width / display_height
        normalized_height = c.aspect_width * display_height / display_width
        difference = normalized_height - c.aspect_width
        target_difference = c.aspect_height - c.aspect_width
        result.metrics.update(image_aspect_ratio=round(aspect, 6),
                              normalized_aspect_height=round(normalized_height, 6),
                              aspect_difference=round(difference, 6),
                              aspect_target_difference=round(target_difference, 6),
                              aspect_difference_error=round(abs(difference-target_difference), 6))
        if c.check_aspect:
            # Normalize the observed width to the configured width A. Then
            # |(H/W*A - A) - (B-A)| <= E. Cross-products avoid rounded limits.
            observed = Decimal(str(display_height)) * Decimal(str(c.aspect_width))
            expected = Decimal(str(display_width)) * Decimal(str(c.aspect_height))
            tolerance = Decimal(str(display_width)) * Decimal(str(c.aspect_tolerance))
            if abs(observed-expected) > tolerance:
                low, high = target_difference-c.aspect_tolerance, target_difference+c.aspect_tolerance
                review(f"증명사진 비율 확인 필요 ({display_width} × {display_height}px; "
                       f"가로 {c.aspect_width:g} 기준 환산 세로−가로 {difference:.4f}; "
                       f"기준 {c.aspect_width:g}:{c.aspect_height:g}, 허용 차이 {low:g}~{high:g})", "사진 비율")

        detections = self.detector.detect(self._image(rgb)).detections
        result.metrics["face_count"] = len(detections)
        for detection in detections:
            b = detection.bounding_box
            result.boxes.append((b.origin_x / width, b.origin_y / height,
                                 b.width / width, b.height / height))
        if not detections:
            # Exactly one fallback, only when the upright detector found no face.
            rotated = self.detector.detect(self._image(np.rot90(rgb, 2))).detections
            result.metrics["rotated_180_face_count"] = len(rotated)
            if rotated:
                review("정방향에서는 얼굴 미검출, 180° 회전 후 얼굴 검출", "회전·기울기", True)
            else:
                review("정방향·180° 회전 모두 얼굴 미검출; 방향 확인 필요", "회전·기울기", True)
            review("정방향 얼굴 미검출로 구도를 확인할 수 없음", "얼굴·신뢰도")
            return

        faces = self.face.detect(self._image(rgb)).face_landmarks
        if len(detections) != 1 or len(faces) != 1:
            review(f"얼굴 수 확인 필요: 검출 {len(detections)}명 / 특징점 {len(faces)}명", "얼굴·신뢰도")
            review("얼굴 검출 결과로 방향을 확정할 수 없음", "회전·기울기", True)
            return
        base_score = detections[0].categories[0].score
        if not math.isfinite(base_score):
            raise ValueError("얼굴 검출 신뢰도에 유효하지 않은 수치가 있음")
        result.metrics["face_confidence"] = round(base_score, 4)
        if c.check_confidence and base_score <= c.confidence:
            review(f"얼굴 검출 신뢰도 부족 또는 경계값 ({base_score:.2f})", "얼굴·신뢰도")
            review("얼굴 신뢰도가 낮아 방향 확인 필요", "회전·기울기", True)

        face = faces[0]
        selected = [33, 263, 1, 10, 152, 234, 454, 61, 291]
        if not all(math.isfinite(v) for p in face for v in (p.x, p.y, p.z)):
            raise ValueError("얼굴 특징점에 유효하지 않은 수치가 있음")
        result.points.extend((face[i].x, face[i].y) for i in selected)
        left, right = sorted((face[33], face[263]), key=lambda p: p.x)
        dx, dy = (right.x - left.x) * width, (right.y - left.y) * height
        roll = math.degrees(math.atan2(dy, dx))
        result.metrics["roll_degrees"] = round(roll, 2)
        if c.check_roll and (dx < width * c.eye_span_min or abs(roll) >= c.roll_degrees):
            review(f"얼굴 기울기 또는 눈 위치 확인 필요 ({roll:.1f}°)", "회전·기울기", True)

        b = detections[0].bounding_box
        if b.width <= 0 or b.height <= 0:
            raise ValueError("얼굴 검출 영역 크기가 유효하지 않음")
        visible_height = max(0, min(height, b.origin_y + b.height) - max(0, b.origin_y))
        height_ratio = visible_height / height
        result.metrics["face_height_ratio"] = round(height_ratio, 6)
        # Compare unrounded values: exactly the minimum is a review; no upper size gate.
        if c.check_height and height_ratio <= c.face_height_min:
            review(f"얼굴 높이 부족 (사진 높이의 {height_ratio:.1%}; 기준 {c.face_height_min:.0%} 초과)", "구도·위치")

        nose, forehead, chin = face[1], face[10], face[152]
        landmark_height = chin.y - forehead.y
        face_width = abs(face[454].x - face[234].x)
        center = (face[234].x + face[454].x) / 2
        result.metrics.update(landmark_face_height_ratio=round(landmark_height, 4),
                              face_center_x=round(center, 4),
                              forehead_y_ratio=round(forehead.y, 6),
                              chin_y_ratio=round(chin.y, 6),
                              face_width_ratio=round(face_width, 6))
        if c.check_center and abs(center - 0.5) >= c.center_offset:
            review("얼굴이 중앙 범위를 벗어나거나 경계에 있음", "구도·위치")
        # Review near-frame facial points, without imposing a fixed chin position
        # or a second face-size threshold. These points do not locate hair tips.
        lower, upper = c.boundary_margin, 1 - c.boundary_margin
        labels = {33: "눈", 263: "눈", 1: "코", 10: "이마", 152: "턱",
                  234: "볼", 454: "볼", 61: "입", 291: "입"}
        for i in selected:
            point = face[i]
            if c.check_boundary and (not lower < point.x < upper or not lower < point.y < upper):
                review(f"{labels[i]} 경계 근접 (가로 {point.x:.1%}, 세로 {point.y:.1%}; "
                       f"허용 범위 {lower:.1%}~{upper:.1%})", "머리·턱 여백")

        eye_span = max(right.x - left.x, 1e-6)
        yaw = abs(nose.x - (left.x + right.x) / 2) / eye_span
        depth_asymmetry = abs(left.z - right.z) / eye_span
        pitch_ratio = (nose.y - forehead.y) / max(landmark_height, 1e-6)
        result.metrics.update(front_symmetry=round(yaw, 3), depth_asymmetry=round(depth_asymmetry, 3),
                              nose_height_ratio=round(pitch_ratio, 3))
        if c.check_front and (yaw >= c.front_symmetry_max or depth_asymmetry >= c.depth_asymmetry_max or not c.nose_height_min < pitch_ratio < c.nose_height_max):
            review("정면 방향·얼굴 가림을 충분히 확인하지 못함", "정면·가림")
        if not b.origin_x / width < nose.x < (b.origin_x + b.width) / width or not b.origin_y / height < nose.y < (b.origin_y + b.height) / height:
            review("얼굴 검출과 특징점 위치가 충돌함", "얼굴·신뢰도")
        if c.check_recapture:
            paper = detect_recapture(rgb, result.metrics, c)
            result.metrics.update(paper)
            if paper["recapture_suspected"]:
                review("인화사진 재촬영 의심 — 얼굴 주변의 종이 테두리·외부 배경 확인", "재촬영 의심")
        result.reasons[:] = list(dict.fromkeys(result.reasons))
