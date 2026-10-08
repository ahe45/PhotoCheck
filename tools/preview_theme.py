"""Render the application's light theme after starting with a dark Qt palette."""
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication
from photocheck.domain import Check, Result
from photocheck.theme import apply_light_theme
from photocheck.ui import MainWindow

app = QApplication([])
for filename in ("malgun.ttf", "malgunbd.ttf", "segoeui.ttf", "seguisym.ttf"):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts" / filename))
app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
dark = QPalette()
for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
    dark.setColor(role, QColor("#2b2b2b"))
for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
    dark.setColor(role, QColor("#ffffff"))
app.setPalette(dark)
apply_light_theme(app)
preview_font = app.font()
preview_font.setFamilies(["Malgun Gothic", "Segoe UI", "Segoe UI Symbol"])
app.setFont(preview_font)
window = MainWindow()
window.show()
app.processEvents()
output = root / "build"
output.mkdir(exist_ok=True)
window.grab().save(str(output / "theme-idle.png"))

# Display fixtures exercise rows, selection, details, disabled controls and progress.
row = Result(root / "색상점검용_파일오류.jpg", "색상점검용_파일오류.jpg",
             file_check=Check.ERROR, reasons=["화면 색상 점검용 파일 오류 항목"], tags={"파일"}).finalize()
window.results.append(row)
window.model.add([row])
window.total = 2
window.counts[row.status.value] = 1
window.update_counts()
window.table.selectRow(0)
window.pool.waitForDone()
app.processEvents()
window.set_running(True)
window.progress.setRange(0, 100)
window.progress.setValue(45)
window.state.setText("화면 색상 점검 · 처리 중 표시")
window.grab().save(str(output / "theme-running.png"))
window.reason_filter.showPopup()
app.processEvents()
window.reason_filter.view().window().grab().save(str(output / "theme-dropdown.png"))
window.reason_filter.hidePopup()
window.set_running(False)
from photocheck.settings_dialog import SettingsDialog
dialog = SettingsDialog(window.criteria, window)
dialog.show()
app.processEvents()
for index, name in enumerate(('basic','front','recapture','text')):
    dialog.tabs.setCurrentIndex(index)
    app.processEvents()
    dialog.repaint()
    app.processEvents()
    dialog.grab().save(str(output / f'theme-settings-{name}.png'))
dialog.reject()
window.close()
print("Rendered light theme with a dark initial palette: build/theme-*.png")
