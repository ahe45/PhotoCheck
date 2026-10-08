"""Explicit developer diagnostic: verify bundled models and Qt without downloads."""
import json
import tempfile
from pathlib import Path


def run(report_path):
    report = {"ok": False}
    try:
        from PIL import Image
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtGui import QFontDatabase
        from PySide6.QtWidgets import QApplication
        from .domain import Check, Status
        from .ui import MainWindow
        from .theme import apply_light_theme
        app = QApplication.instance() or QApplication([])
        if app.platformName() == "offscreen":
            import os
            QFontDatabase.addApplicationFont(str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts" / "malgun.ttf"))
        apply_light_theme(app)
        window = MainWindow()
        window.show()
        app.processEvents()
        with tempfile.TemporaryDirectory(prefix="photocheck-검증-") as folder:
            root = Path(folder)
            path = root / "한글사진.png"
            Image.new("RGB", (300, 400), "white").save(path)
            (root / "빈파일.jpg").touch()
            window.folder.setText(str(root))
            window.start_scan()
            loop = QEventLoop()
            window.worker.finished.connect(loop.quit)
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            timer.start(30000)
            try:
                loop.exec()
                assert window.worker is None or not window.worker.isRunning(), "검사 완료 시간 초과"
                assert window.total == 2 and len(window.results) == 2
                result = next(r for r in window.results if r.path.name == path.name)
                assert result.file_check == Check.PASS
                assert result.status == Status.REVIEW
                assert result.model_version != "unavailable", result.reasons
                assert any(r.status == Status.ERROR for r in window.results)
                assert window.proxy.rowCount() == 2
                window.search.setText("한글사진")
                assert window.proxy.rowCount() == 1
                window.pool.waitForDone()
                app.processEvents()
                assert window.view.photo is not None
                # Exercise the real modal gear flow without touching normal
                # user preferences: redirect this diagnostic dialog to a fixture.
                from . import ui
                from .criteria import load_criteria
                dialog_class = ui.SettingsDialog
                fixture_settings = root / "검사 설정.json"
                ui.SettingsDialog = lambda c, parent: dialog_class(c, parent, path=fixture_settings)
                def edit_dialog():
                    dialog = app.activeModalWidget()
                    if not isinstance(dialog, dialog_class):
                        return
                    dialog.fields["roll_degrees"][0].setValue(8)
                    dialog.checks["check_recapture"].setChecked(False)
                    dialog.fields["text_confidence"][0].setValue(.75)
                    dialog.checks["check_text"].setChecked(False)
                    dialog.save()
                try:
                    QTimer.singleShot(50, edit_dialog)
                    window.settings.click()
                finally:
                    ui.SettingsDialog = dialog_class
                assert window.criteria.roll_degrees == 8 and not window.criteria.check_recapture
                assert window.criteria.text_confidence == .75 and not window.criteria.check_text
                assert load_criteria(fixture_settings)[0] == window.criteria
                assert result.criteria_settings["roll_degrees"] == 5
                assert result.criteria_settings["check_text"] and result.criteria_settings["text_confidence"] == .6
                report["settings_popup_save_and_result_snapshot"] = True
                # Check the floating control when scrollbars and viewport size change.
                for width, height in ((1100, 850), (1024, 1000)):
                    window.resize(width, height)
                    window.view.zoom(2)
                    app.processEvents()
                    button = window.view.fit_button
                    viewport = window.view.viewport()
                    assert button.text() == "" and not button.icon().isNull()
                    assert viewport.width() - button.geometry().right() - 1 == 12
                    assert viewport.height() - button.geometry().bottom() - 1 == 12
                    button.click()
                    app.processEvents()
                    assert window.view.fitted
                controls = (window.previous, window.mark_normal, window.next, window.overlay)
                assert len({control.geometry().y() for control in controls}) == 1
                assert [control.geometry().x() for control in controls] == sorted(control.geometry().x() for control in controls)
                assert window.preview_state.text() == path.name
                assert window.preview_state.geometry().y() > window.previous.geometry().bottom()
                window.overlay.click()
                assert window.overlay.isChecked()
                window.overlay.click()
                assert not window.overlay.isChecked()
                assert window.width() == 1024
                assert abs(window.table.width() - window.view.width()) <= 1
                assert window.settings.geometry().x() > window.cancel.geometry().right()
                assert window.settings.geometry().center().y() == window.cancel.geometry().center().y()
                report["photo_layout_resize_fit_and_controls"] = True
                window.grab().save(str(Path(report_path).with_suffix(".png")))
                # Use only generated fixtures for export, copying and reclassification.
                import shutil
                from zipfile import ZipFile
                from xml.etree import ElementTree as ET
                from PySide6.QtWidgets import QFileDialog, QMessageBox
                from .export import NS
                def workbook_rows(filename):
                    with ZipFile(filename) as archive:
                        sheet=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
                    return [[ ''.join(cell.itertext()) for cell in row]
                            for row in sheet.findall(f'{{{NS}}}sheetData/{{{NS}}}row')]
                export_path=root/'검사 결과.xlsx'
                original_save=QFileDialog.getSaveFileName
                original_directory=QFileDialog.getExistingDirectory
                QFileDialog.getSaveFileName=lambda *a:(str(export_path),'엑셀 파일 (*.xlsx)')
                copy_folder=root/'복사 결과'; copy_folder.mkdir()
                QFileDialog.getExistingDirectory=lambda *a:str(copy_folder)
                alerts = []
                alert_timer = QTimer()
                def accept_copy_alert():
                    message = app.activeModalWidget()
                    if isinstance(message, QMessageBox) and message.windowTitle() == '사진 복사 결과':
                        alerts.append(message.text())
                        message.grab().save(str(Path(report_path).with_name('copy-complete.png')))
                        message.accept()
                alert_timer.timeout.connect(accept_copy_alert)
                alert_timer.start(25)
                try:
                    window.export.click()
                    assert len(workbook_rows(export_path)) == 3
                    window.copy.click()
                    assert window.copy_progress.isVisible()
                    window.copy_progress.grab().save(str(Path(report_path).with_name('copy-progress.png')))
                    copy_loop=QEventLoop()
                    window.copy_worker.finished.connect(copy_loop.quit)
                    copy_timer=QTimer(); copy_timer.setSingleShot(True)
                    copy_timer.timeout.connect(copy_loop.quit); copy_timer.start(5000)
                    copy_loop.exec(); copy_timer.stop(); app.processEvents()
                    assert window.copy_worker is None, '사진 복사 시간 초과'
                    assert window.copy_progress is None and len(alerts) == 1 and '복사 1건' in alerts[0]
                    assert (copy_folder/path.name).read_bytes() == path.read_bytes()
                    assert not (copy_folder/'빈파일.jpg').exists()
                    assert window.mark_normal.isEnabled()
                    original_reasons=list(result.reasons)
                    window.mark_normal.click()
                    assert result.status == Status.NORMAL and result.automatic_status == Status.REVIEW
                    assert result.reasons == original_reasons and result.manual_normal
                    assert window.counts[Status.NORMAL] == 1 and window.counts[Status.ERROR] == 1
                    assert window.current is None and window.proxy.rowCount() == 0
                    window.search.clear()
                    assert window.proxy.rowCount() == 1
                    window.export.click()
                    exported=workbook_rows(export_path)
                    assert len(exported) == 2 and exported[1][0] == '빈파일.jpg'
                    assert exported[0] == ['파일명','판정사유'] and len(exported[1]) == 2
                    assert window.model.headers == ['파일명','주요 사유']
                    assert window.export.text() == '결과 저장' and window.copy.text() == '사진 복사'
                    report['review_workflow'] = {'excel_only_non_normal':True,
                        'photo_copy_filtered_snapshot':True,'photo_copy_original_unchanged':True,
                        'normal_reclassification_updates_list_and_counts':True,
                        'automatic_analysis_preserved':True,'two_list_columns':True,
                        'two_excel_columns':True,'copy_progress_and_completion_alert':True}
                    shutil.copyfile(export_path,Path(report_path).with_suffix('.xlsx'))
                finally:
                    alert_timer.stop()
                    QFileDialog.getSaveFileName=original_save
                    QFileDialog.getExistingDirectory=original_directory
                report.update(ok=True, model_version=result.model_version, result=result.status.value,
                              reasons=result.reasons, qt="window, scan thread, counters, search and preview verified", frozen=__import__("sys").frozen if hasattr(__import__("sys"), "frozen") else False)
            finally:
                timer.stop()
                if window.worker and window.worker.isRunning():
                    window.worker.cancel()
                    window.worker.wait()
                if window.copy_worker is not None:
                    window.copy_worker.cancel()
                    window.copy_worker.wait()
                    app.processEvents()
                window.close()
    except Exception as error:
        import traceback
        report.update(error=str(error), traceback=traceback.format_exc())
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
