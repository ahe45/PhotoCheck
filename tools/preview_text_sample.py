"""Render the known signature's actual result and UI overlay offscreen."""
import os
from pathlib import Path
import sys
import json

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from PySide6.QtGui import QFontDatabase, QImage
from PySide6.QtWidgets import QApplication
from photocheck.analysis import Analyzer
from photocheck.criteria import Criteria
from photocheck.files import inspect, load_image
from photocheck.theme import apply_light_theme
from photocheck.ui import MainWindow

app = QApplication([])
QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot',r'C:\Windows'))/'Fonts/malgun.ttf'))
apply_light_theme(app)
paths = list((root/'sample').rglob('71W298095.jpg'))
assert len(paths) == 1
analyzer = Analyzer(Criteria())
try:
    result = inspect(paths[0], root/'sample', analyzer)
finally:
    analyzer.close()
assert '글자 포함 의심' in result.tags and len(result.text_boxes) == 1, result.reasons
window = MainWindow()
window.show()
window.results.append(result)
window.total = 1
window.counts[result.status.value] = 1
window.model.add([result])
window.overlay.setChecked(True)
window.table.selectRow(0)
window.pool.waitForDone()
app.processEvents()
window.grab().save(str(root/'build/text-sample-preview.png'))
window.close()
print(json.dumps({'status':result.status.value,'reasons':result.reasons,'boxes':result.text_boxes}))
