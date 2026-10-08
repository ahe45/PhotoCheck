import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image
from PySide6.QtWidgets import QApplication

from photocheck.domain import Check, Result
from photocheck.workers import ScanWorker


def test_cancellation_retains_current_result_and_stops_next(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    for name in ("가.png", "나.png", "다.png"):
        Image.new("RGB", (10, 10)).save(tmp_path / name)
    worker = ScanWorker(tmp_path, True)
    closed = []
    class Model:
        def __init__(self, criteria=None):
            self.criteria = criteria
        def close(self):
            closed.append(True)
    monkeypatch.setattr("photocheck.workers.Analyzer", Model)
    def inspect(path, root, analyzer):
        worker.cancel()
        return Result(path, str(path.relative_to(root)), file_check=Check.PASS).finalize()
    monkeypatch.setattr("photocheck.workers.inspect", inspect)
    results, completions, collections = [], [], []
    worker.batch.connect(lambda batch: results.extend(batch))
    worker.completed.connect(lambda cancelled, error: completions.append((cancelled, error)))
    worker.collected.connect(collections.append)
    worker.run()
    assert len(collections[0].paths) == 3
    assert len(results) == 1 and completions == [(True, "")] and closed == [True]


def test_collection_exception_reported_as_failure(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    worker = ScanWorker(tmp_path, True)
    def broken(*args):
        raise RuntimeError("collection failed")
    monkeypatch.setattr("photocheck.workers.collect", broken)
    completion = []
    worker.completed.connect(lambda cancelled, error: completion.append((cancelled, error)))
    worker.run()
    assert completion and "collection failed" in completion[0][1]
