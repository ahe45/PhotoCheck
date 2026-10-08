import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThread, Signal
from PySide6.QtGui import QImage

from .process_analyzer import ProcessAnalyzer as Analyzer
from .domain import Check, Result
from .files import collect, inspect, load_image
from .criteria import Criteria
from .photo_copy import CopyReport, copy_photos


class CopyWorker(QThread):
    progress = Signal(int,int)
    completed = Signal(object)

    def __init__(self, results, destination, parent=None):
        super().__init__(parent)
        self.results, self.destination = list(results), destination
        self.stop = threading.Event()

    def cancel(self):
        self.stop.set()

    def run(self):
        last = time.monotonic()
        def update(done,total):
            nonlocal last
            now = time.monotonic()
            if now-last >= .1 or done == total:
                self.progress.emit(done,total)
                last = now
        try:
            report = copy_photos(self.results,self.destination,self.stop.is_set,update)
        except Exception as error:
            report = CopyReport(errors=[str(error)])
        self.completed.emit(report)


class ScanWorker(QThread):
    collected = Signal(object)
    batch = Signal(object)
    message = Signal(str)
    completed = Signal(bool, str)

    def __init__(self, root: Path, recursive: bool, parent=None, criteria=None):
        super().__init__(parent)
        self.root, self.recursive = root, recursive
        self.stop = threading.Event()
        self.criteria = criteria or Criteria()

    def cancel(self):
        self.stop.set()

    def run(self):
        analyzer = None
        pending = []
        fatal_error = ""
        try:
            self.message.emit("후보 파일 수집 중…")
            collection = collect(self.root, self.recursive, self.stop.is_set)
            self.collected.emit(collection)
            if self.stop.is_set():
                return
            self.message.emit("로컬 분석 모델 준비 중…")
            model_error = ""
            try:
                analyzer = Analyzer(criteria=self.criteria)
            except Exception as error:
                model_error = f"로컬 모델 준비 실패: {type(error).__name__}: {error}"
                self.message.emit(model_error)
            last = time.monotonic()
            for path in collection.paths:
                if self.stop.is_set():
                    break
                try:
                    result = inspect(path, self.root, analyzer)
                    if model_error and result.file_check != Check.ERROR:
                        result.reasons.append(model_error)
                except Exception as error:
                    result = Result(path, str(path.relative_to(self.root)), file_check=Check.ERROR,
                                    reasons=[f"파일 처리 실패: {error}"], tags={"파일"}).finalize()
                result.criteria_version = self.criteria.version
                result.criteria_settings = self.criteria.snapshot()
                result.criteria_id = self.criteria.identity
                pending.append(result)
                if len(pending) >= 20 or time.monotonic() - last > 0.15:
                    self.batch.emit(pending)
                    pending = []
                    last = time.monotonic()
        except Exception as error:
            fatal_error = f"검사 실행 오류: {error}"
            self.message.emit(fatal_error)
        finally:
            if pending:
                self.batch.emit(pending)
            if analyzer is not None:
                try:
                    analyzer.close()
                except Exception as error:
                    self.message.emit(f"모델 종료 오류: {error}")
            self.completed.emit(self.stop.is_set(), fatal_error)


class PreviewSignals(QObject):
    ready = Signal(int, object, str)


class PreviewWorker(QRunnable):
    def __init__(self, request_id: int, path: Path):
        super().__init__()
        self.request_id, self.path = request_id, path
        self.signals = PreviewSignals()

    def run(self):
        image, _, reasons = load_image(self.path, edge=2200)
        if image is None:
            self.signals.ready.emit(self.request_id, None, "\n".join(reasons))
            return
        try:
            raw = image.tobytes()
            qimage = QImage(raw, image.width, image.height, image.width * 3, QImage.Format.Format_RGB888).copy()
            self.signals.ready.emit(self.request_id, qimage, "")
        except Exception as error:
            self.signals.ready.emit(self.request_id, None, f"미리보기 실패: {error}")
        finally:
            image.close()
