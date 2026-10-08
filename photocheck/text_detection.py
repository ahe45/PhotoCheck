"""Local candidate detection and CTC run counting; no transcription is retained."""
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import unicodedata

import cv2
import numpy as np


MODEL_NAME = "ppocrv3_det.onnx"
MODEL_HASH = "03f550c6b406fda8bf54bd8327815f6c7e2edd98cea02348c93d879254366587"
REC_MODEL_NAME = "korean_ppocrv5_rec.onnx"
REC_MODEL_HASH = "92f0b7785e64fc9090106a241cf4c1eb97472824558272751b88a2a4476d3a08"
DICT_NAME = "korean_rec_dict.json"
DICT_HASH = "8c89748b14e07b3332eb3fa569cf39eb78dbfc7ed2fe0f333f19f9574e94c6f3"


def count_ctc_run(probability, characters, min_confidence):
    """Collapse CTC repeats/blanks before counting consecutive trusted letters.

    Blank is alignment, not whitespace. A repeated letter separated by a blank
    is a second letter. Separators and uncertain tokens break runs, not vanish.
    Returns only the longest run and its weakest character confidence.
    """
    if (probability.ndim != 2 or not probability.size or
            probability.shape[1] != len(characters) or
            not np.isfinite(probability).all() or
            probability.min() < 0 or probability.max() > 1 or
            not np.allclose(probability.sum(axis=1), 1., atol=.001)):
        raise ValueError("문자 인식 모델 출력이 유효하지 않습니다.")
    ids = probability.argmax(axis=1)
    scores = probability.max(axis=1)
    best, best_score, run, run_score = 0, 0., 0, 1.
    for t, (index, score) in enumerate(zip(ids, scores)):
        if index == 0 or (t and index == ids[t-1]):
            continue
        char = characters[int(index)]
        if (len(char) == 1 and unicodedata.category(char)[0] in ('L', 'N')
                and score >= min_confidence):
            run += 1
            run_score = min(run_score, float(score))
            if run > best or (run == best and run_score > best_score):
                best, best_score = run, run_score
        else:
            run, run_score = 0, 1.
    return best, best_score


def regions_from_map(probability, confidence, min_height_ratio):
    """Score connected text masks, keeping boxes in normalized image coordinates."""
    if probability.ndim != 2 or not probability.size or not np.isfinite(probability).all():
        raise ValueError("문자 검출 결과가 유효하지 않습니다.")
    if probability.min() < 0 or probability.max() > 1:
        raise ValueError("문자 검출 점수 범위가 유효하지 않습니다.")
    height, width = probability.shape
    contours = cv2.findContours((probability > .3).astype(np.uint8),
                               cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
    # Work is bounded even for an adversarial or highly textured image. Larger
    # components take priority over tiny speckles; this is not a face/body mask.
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:1000]
    found = []
    for contour in contours:
        if cv2.contourArea(contour) < 6:
            continue
        rectangle = cv2.minAreaRect(contour)
        (_, _), sides, _ = rectangle
        if min(sides) < 3:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if h / height < min_height_ratio:
            continue
        # DB confidence averages the complete rotated text rectangle, including
        # gaps between strokes. Averaging only the thresholded contour inflated
        # isolated eyebrow/eyelash scores on otherwise text-free portraits.
        polygon = cv2.boxPoints(rectangle).astype(np.int32)
        px, py, pw, ph = cv2.boundingRect(polygon)
        sx, sy = max(0, px), max(0, py)
        ex, ey = min(width, px+pw), min(height, py+ph)
        mask = np.zeros((ey-sy, ex-sx), dtype=np.uint8)
        cv2.fillPoly(mask, [polygon - np.array([sx, sy])], 1)
        score = float(cv2.mean(probability[sy:ey, sx:ex], mask)[0])
        if score < confidence:
            continue
        # Expand only the visual indication: model masks lie inside characters.
        left, top = max(0, x-2), max(0, y-2)
        right, bottom = min(width, x+w+2), min(height, y+h+2)
        found.append(((left/width, top/height, (right-left)/width, (bottom-top)/height), score))
    return sorted(found, key=lambda region: (region[0][1], region[0][0]))


def location(box):
    x, y, w, h = box
    row = "상단" if y+h/2 < 1/3 else "하단" if y+h/2 > 2/3 else "중앙"
    column = "좌측" if x+w/2 < 1/3 else "우측" if x+w/2 > 2/3 else "중앙"
    return row if column == "중앙" else column if row == "중앙" else f"{column} {row}"


class TextDetector:
    def __init__(self, model_bytes, recognition_bytes=None, dictionary_bytes=None):
        folder = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))/'models'
        self.recognition_bytes = recognition_bytes if recognition_bytes is not None else (folder/REC_MODEL_NAME).read_bytes()
        dictionary_bytes = dictionary_bytes if dictionary_bytes is not None else (folder/DICT_NAME).read_bytes()
        for data, digest in ((self.recognition_bytes, REC_MODEL_HASH), (dictionary_bytes, DICT_HASH)):
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError("문자 인식 모델·사전 무결성 확인 실패")
        self.characters = [''] + json.loads(dictionary_bytes) + [' ']
        self.recognition = None
        self.net = cv2.dnn.readNetFromONNX(np.frombuffer(model_bytes, dtype=np.uint8))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        cv2.setNumThreads(4)
        self.mean = np.array([.485, .456, .406], dtype=np.float32)
        self.std = np.array([.229, .224, .225], dtype=np.float32)

    def recognize_run(self, rgb, box, min_confidence):
        # Initialize only when a candidate exists. CPU only, one bounded crop at
        # a time; there is no full-photo OCR or network request.
        if self.recognition is None:
            import onnxruntime as ort
            ort.disable_telemetry_events()
            options = ort.SessionOptions()
            options.log_severity_level = 3
            options.intra_op_num_threads = 4
            options.inter_op_num_threads = 1
            self.recognition = ort.InferenceSession(self.recognition_bytes, options,
                                                   providers=['CPUExecutionProvider'])
        height, width = rgb.shape[:2]
        x, y, w, h = box
        x, y, w, h = x*width, y*height, w*width, h*height
        # DB masks lie within strokes. Modest crop padding preserves the ends
        # without joining unrelated lines or distant regions.
        crop = rgb[max(0, int(y-h*.25)):min(height, math.ceil(y+h*1.25)),
                   max(0, int(x-h*.3)):min(width, math.ceil(x+w+h*.3)), ::-1]
        if not crop.size:
            raise ValueError("문자 인식 영역이 유효하지 않습니다.")
        hh, ww = crop.shape[:2]
        resized_width = min(640, max(32, math.ceil(48*ww/hh)))
        tensor = (cv2.resize(crop, (resized_width, 48)).astype(np.float32)/127.5-1)
        output = self.recognition.run(None, {'x':np.ascontiguousarray(tensor.transpose(2,0,1)[None])})[0]
        if output.ndim != 3 or output.shape[0] != 1:
            raise ValueError("문자 인식 모델 출력 형식이 유효하지 않습니다.")
        return count_ctc_run(output[0], self.characters, min_confidence)

    def detect(self, rgb, criteria):
        start = time.perf_counter()
        height, width = rgb.shape[:2]
        scale = min(1., criteria.text_edge / max(height, width))
        target = tuple(max(32, round(side*scale/32)*32) for side in (width, height))
        bgr = cv2.resize(rgb[:, :, ::-1], target, interpolation=cv2.INTER_LINEAR)
        tensor = (bgr.astype(np.float32)/255-self.mean)/self.std
        self.net.setInput(np.ascontiguousarray(tensor.transpose(2,0,1)[None]))
        output = self.net.forward()
        if output.ndim != 2:
            raise ValueError("문자 검출 모델 출력 형식이 유효하지 않습니다.")
        candidates = regions_from_map(output, criteria.text_confidence, criteria.text_height_min)
        if len(candidates) > 64:
            # Do not automatically pass an image whose check was truncated.
            raise ValueError("문자 후보 영역이 너무 많아 직접 확인이 필요합니다.")
        regions, longest, recognition_score = [], 0, 0.
        for box, score in candidates:
            length, rec_score = self.recognize_run(rgb, box, criteria.text_rec_confidence)
            longest = max(longest, length)
            if length >= criteria.text_min_chars:
                regions.append((box, score))
                recognition_score = max(recognition_score, rec_score)
        metrics = {"text_region_count": len(regions),
                   "text_candidate_count": len(candidates), "text_run_max": longest,
                   "text_rec_score_max": round(recognition_score, 6),
                   "text_score_max": round(max((score for _, score in regions), default=0.), 6),
                   "text_input_width": target[0], "text_input_height": target[1],
                   "text_elapsed_ms": round((time.perf_counter()-start)*1000, 3)}
        if not all(math.isfinite(v) for v in metrics.values()):
            raise ValueError("문자 검출 수치가 유효하지 않습니다.")
        return regions, metrics
