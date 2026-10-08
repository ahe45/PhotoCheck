import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QModelIndex

from photocheck.domain import Result, Status
from photocheck.ui import MainWindow, ResultFilter, ResultModel


def test_filter_navigation_and_preview_stale_guard(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    results = [Result(tmp_path / "첫째.png", "하위/첫째.png", tags={"파일"}),
               Result(tmp_path / "둘째.png", "둘째.png", tags={"회전·기울기"}),
               Result(tmp_path / "정상.png", "정상.png", status=Status.NORMAL)]
    window.results.extend(results)
    window.model.add(results)
    assert window.proxy.rowCount() == 2
    window.table.selectRow(0)
    window.move(1)
    assert window.current.path.name == "둘째.png"
    window.search.setText("첫째")
    assert window.proxy.rowCount() == 1
    assert window.current.path.name == "첫째.png"
    window.move(1)
    assert window.table.currentIndex().row() == 0
    window.preview_ready(window.preview_id - 1, None, "stale")
    assert "stale" not in window.preview_state.text()
    window.search.setText("없음")
    assert window.proxy.rowCount() == 0 and window.current is None
    assert window.position.text() == "0 / 0"
    window.close()

