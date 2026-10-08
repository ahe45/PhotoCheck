from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

CRITERIA_VERSION = "strict-0.9-text-runs-unvalidated"

class Status(StrEnum):
    NORMAL = "정상"
    REVIEW = "확인 필요"
    ERROR = "파일 오류"


class Check(StrEnum):
    PASS = "통과"
    REVIEW = "확인 필요"
    ERROR = "오류"
    SKIP = "생략"


@dataclass
class Result:
    path: Path
    relative_path: str
    status: Status = Status.REVIEW
    file_check: Check = Check.SKIP
    direction_check: Check = Check.SKIP
    framing_check: Check = Check.SKIP
    reasons: list[str] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)
    metrics: dict[str, float] = field(default_factory=dict)
    # Normalized coordinates refer to the EXIF-normalized image, never a rotated probe.
    points: list[tuple[float, float]] = field(default_factory=list)
    boxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    text_boxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    checked_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
    criteria_version: str = CRITERIA_VERSION
    model_version: str = "unavailable"
    criteria_id: str = ""
    criteria_settings: dict = field(default_factory=dict)
    automatic_status: Status | None = None
    manual_normal: bool = False
    reviewed_at: str = ""

    def mark_normal(self):
        if not self.manual_normal:
            self.automatic_status = self.status
        self.manual_normal = True
        self.reviewed_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self.status = Status.NORMAL

    def finalize(self):
        if self.manual_normal:
            self.status = Status.NORMAL
            return self
        if self.file_check == Check.ERROR:
            self.status = Status.ERROR
        elif all(c == Check.PASS for c in (self.file_check, self.direction_check, self.framing_check)):
            self.status = Status.NORMAL
        else:
            self.status = Status.REVIEW
        return self
