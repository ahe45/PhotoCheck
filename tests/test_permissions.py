import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from photocheck.domain import Result, Status, Check
from photocheck.export import export_excel
from photocheck.files import load_image
from photocheck.ui import MainWindow


def test_no_read_permission_is_file_error(tmp_path):
    path = tmp_path / "사진.jpg"
    path.write_bytes(b"image")
    with patch("photocheck.files.Image.open", side_effect=PermissionError()):
        image, check, reasons = load_image(path)
    assert image is None and check == Check.ERROR and "권한" in reasons[0]


def test_failed_export_preserves_existing_file_and_cleans_temporary(tmp_path, monkeypatch):
    path = tmp_path / "기존.xlsx"
    path.write_bytes(b"keep existing data")
    def denied(*args):
        raise PermissionError("denied")
    monkeypatch.setattr("photocheck.export.os.replace", denied)
    with pytest.raises(PermissionError):
        export_excel(path, [Result(tmp_path / "photo.jpg", "photo.jpg")])
    assert path.read_bytes() == b"keep existing data"
    assert list(tmp_path.glob(".photocheck-*.tmp")) == []


def test_export_never_overwrites_original(tmp_path):
    path = tmp_path / "원본.jpg"
    path.write_bytes(b"original")
    with pytest.raises(ValueError):
        export_excel(path, [Result(path, path.name)])
    assert path.read_bytes() == b"original"


def test_ui_permission_denial_keeps_results(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    result = Result(tmp_path / "사진.jpg", "사진.jpg")
    window.results.append(result)
    window.model.add([result])
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, message: messages.append((title, message)))
    window.folder.setText(str(tmp_path))
    with patch("os.scandir", side_effect=PermissionError()):
        window.start_scan()
    assert "권한" in messages[-1][0] and window.results == [result] and window.worker is None
    window.update_counts()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(tmp_path / "result.xlsx"), ""))
    monkeypatch.setattr("photocheck.ui.export_excel", lambda *args: (_ for _ in ()).throw(PermissionError()))
    window.save_excel()
    assert "권한" in messages[-1][0] and window.results == [result]
    window.close()
