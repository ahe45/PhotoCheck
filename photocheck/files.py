import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .domain import Check, Result


SUPPORTED = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG"}
CANDIDATES = frozenset((*SUPPORTED, ".jfif", ".jpe", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic", ".heif", ".avif", ".ico", ".svg", ".raw", ".cr2", ".nef", ".dng", ".apng"))
MAX_PIXELS = 40_000_000  # Resource guard, not a submission size rule.
ANALYSIS_EDGE = 1280


@dataclass
class Collection:
    paths: list[Path] = field(default_factory=list)
    excluded: int = 0
    issues: list[str] = field(default_factory=list)
    cancelled: bool = False


def collect(root: Path, recursive: bool, cancelled=lambda: False) -> Collection:
    found = Collection()

    def on_error(error):
        found.issues.append(f"폴더 접근 실패: {error.filename}: {error.strerror}")

    for directory, dirs, filenames in os.walk(root, onerror=on_error, followlinks=False):
        if cancelled():
            found.cancelled = True
            break
        dirs[:] = sorted(d for d in dirs if not Path(directory, d).is_symlink()) if recursive else []
        for filename in sorted(filenames, key=str.casefold):
            if cancelled():
                found.cancelled = True
                return found
            path = Path(directory, filename)
            if path.suffix.lower() in CANDIDATES:
                found.paths.append(path)
            else:
                found.excluded += 1
    return found


def load_image(path: Path, edge: int = ANALYSIS_EDGE) -> tuple[Image.Image | None, Check, list[str]]:
    """Verify and fully decode before making a bounded, EXIF-normalized RGB copy."""
    try:
        if path.stat().st_size == 0:
            return None, Check.ERROR, ["빈 파일 (0바이트)"]
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as source:
                fmt, frames, size = source.format, getattr(source, "n_frames", 1), source.size
                if fmt not in {"JPEG", "PNG"}:
                    return None, Check.ERROR, [f"지원하지 않는 실제 이미지 형식: {fmt}"]
                if min(size) <= 0:
                    return None, Check.ERROR, ["유효하지 않은 픽셀 크기"]
                if size[0] * size[1] > MAX_PIXELS:
                    return None, Check.REVIEW, ["안전한 분석 메모리 범위 초과 (4천만 픽셀); 별도 확인 필요"]
                source.verify()
            reasons = []
            if SUPPORTED.get(path.suffix.lower()) != fmt:
                reasons.append(f"확장자와 실제 형식 불일치: {path.suffix} / {fmt}")
            if frames != 1:
                reasons.append(f"다중 프레임·애니메이션 이미지 ({frames} 프레임)")
            with Image.open(path) as source:
                # First frame is displayed, but never automatically passes animated files.
                source.seek(0)
                source.load()
                exif_direction = source.getexif().get(274, 1)
                if exif_direction not in range(1, 9):
                    reasons.append("EXIF 방향 정보가 유효하지 않음")
                normalized = ImageOps.exif_transpose(source)
                try:
                    display_size = normalized.size
                    normalized.thumbnail((edge, edge), Image.Resampling.LANCZOS)
                    if "A" in normalized.getbands() or "transparency" in normalized.info:
                        reasons.append("투명 영역이 있는 이미지; 표시·구도 확인 필요")
                        rgba = normalized.convert("RGBA")
                        canvas = Image.new("RGBA", rgba.size, "white")
                        canvas.alpha_composite(rgba)
                        image = canvas.convert("RGB")
                        rgba.close()
                        canvas.close()
                    else:
                        image = normalized.convert("RGB")
                    image.info["photocheck_display_size"] = display_size
                finally:
                    normalized.close()
            return image, Check.REVIEW if reasons else Check.PASS, reasons
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        return None, Check.REVIEW, ["초대형 이미지로 안전한 디코딩 불가; 별도 확인 필요"]
    except PermissionError:
        return None, Check.ERROR, ["파일을 읽을 권한이 없거나 다른 프로그램에서 잠겨 있음; 접근 가능한 사본 또는 권한 확인 필요"]
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError) as error:
        return None, Check.ERROR, [f"파일 접근·디코딩 실패: {error}"]
    except Exception as error:
        return None, Check.ERROR, [f"파일 해석 실패: {type(error).__name__}: {error}"]


def inspect(path: Path, root: Path, analyzer=None) -> Result:
    result = Result(path, str(path.relative_to(root)))
    image, result.file_check, reasons = load_image(path)
    result.reasons.extend(reasons)
    if reasons:
        result.tags.add("파일")
    if image is None or result.file_check == Check.ERROR:
        return result.finalize()
    try:
        if analyzer is None:
            result.direction_check = result.framing_check = Check.REVIEW
            result.reasons.append("분석 모델을 사용할 수 없음")
            result.tags.add("모델·분석")
        else:
            display_width, display_height = image.info.get("photocheck_display_size", image.size)
            result.metrics.update(image_width=display_width, image_height=display_height)
            analyzer.analyze(image, result)
    except Exception as error:
        result.direction_check = result.framing_check = Check.REVIEW
        result.reasons.append(f"분석 실패: {type(error).__name__}: {error}")
        result.tags.add("모델·분석")
    finally:
        image.close()
    return result.finalize()
