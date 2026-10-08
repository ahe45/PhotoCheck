from collections import Counter
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QRectF, QSortFilterProxyModel, Qt, QThreadPool, QSize
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog,
    QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QProgressDialog, QPushButton, QSplitter, QTableView, QTextBrowser, QVBoxLayout, QWidget)

from .domain import Status
from .export import export_excel
from .workers import CopyWorker, PreviewWorker, ScanWorker
from .criteria import load_criteria
from .settings_dialog import SettingsDialog, gear_icon


class ResultModel(QAbstractTableModel):
    headers = ["파일명", "주요 사유"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r = self.rows[index.row()]
        values = [r.path.name, r.reasons[0] if r.reasons else ""]
        if role == Qt.ItemDataRole.DisplayRole:
            return values[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return str(r.path) + "\n" + "\n".join(r.reasons)
        if role == Qt.ItemDataRole.ForegroundRole and r.status == Status.ERROR:
            return QColor("#b42318")

    def remove(self, result):
        row = next(i for i,r in enumerate(self.rows) if r is result)
        self.beginRemoveRows(QModelIndex(),row,row)
        del self.rows[row]
        self.endRemoveRows()

    def add(self, results):
        rows = [r for r in results if r.status != Status.NORMAL]
        if not rows:
            return
        start = len(self.rows)
        self.beginInsertRows(QModelIndex(), start, start + len(rows) - 1)
        self.rows.extend(rows)
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self.rows.clear()
        self.endResetModel()


class ResultFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.query = ""
        self.tag = "모든 사유"

    def filterAcceptsRow(self, row, parent):
        r = self.sourceModel().rows[row]
        return (self.query in r.relative_path.casefold() and
                (self.tag == "모든 사유" or self.tag in r.tags))

    def update_filter(self, query, tag):
        self.beginFilterChange()
        self.query, self.tag = query.casefold().strip(), tag
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)


def fit_icon():
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#475569"), 3))
    for x, y, dx, dy in ((8, 8, 1, 1), (40, 8, -1, 1),
                          (8, 40, 1, -1), (40, 40, -1, -1)):
        painter.drawLine(x, y, x + dx * 10, y)
        painter.drawLine(x, y, x, y + dy * 10)
    painter.drawRect(18, 14, 12, 20)
    painter.end()
    return QIcon(pixmap)


class PhotoView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QColor("#e9edf3"))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.fitted = True
        self.photo = None
        self.overlay = []
        self.fit_button = QPushButton(self.viewport())
        self.fit_button.setIcon(fit_icon())
        self.fit_button.setIconSize(QSize(24, 24))
        self.fit_button.setFixedSize(38, 38)
        self.fit_button.setToolTip("화면 맞춤")
        self.fit_button.setAccessibleName("화면 맞춤")
        self.fit_button.setEnabled(False)
        self.fit_button.clicked.connect(self.fit)
        self.viewport().installEventFilter(self)
        self.position_fit_button()

    def position_fit_button(self):
        self.fit_button.move(max(0, self.viewport().width() - self.fit_button.width() - 12),
                             max(0, self.viewport().height() - self.fit_button.height() - 12))
        self.fit_button.raise_()

    def eventFilter(self, watched, event):
        if watched is self.viewport() and event.type() == QEvent.Type.Resize:
            self.position_fit_button()
        return super().eventFilter(watched, event)

    def clear(self):
        self.scene().clear()
        self.photo, self.overlay = None, []
        self.resetTransform()
        self.fit_button.setEnabled(False)

    def display(self, image, result, show_overlay):
        self.clear()
        self.photo = self.scene().addPixmap(QPixmap.fromImage(image))
        self.fit_button.setEnabled(True)
        w, h = image.width(), image.height()
        for x, y, bw, bh in result.boxes:
            item = self.scene().addRect(QRectF(x * w, y * h, bw * w, bh * h), QPen(QColor("#16a34a"), 2))
            self.overlay.append(item)
        for x, y, bw, bh in result.text_boxes:
            item = self.scene().addRect(QRectF(x * w, y * h, bw * w, bh * h), QPen(QColor("#f59e0b"), 3))
            self.overlay.append(item)
        for x, y in result.points:
            item = self.scene().addEllipse(x * w - 3, y * h - 3, 6, 6, QPen(QColor("#2563eb")), QColor("#2563eb"))
            self.overlay.append(item)
        self.scene().setSceneRect(QRectF(0, 0, w, h))
        self.set_overlay(show_overlay)
        self.fit()

    def set_overlay(self, visible):
        for item in self.overlay:
            item.setVisible(visible)

    def fit(self):
        self.fitted = True
        if self.photo:
            self.fitInView(self.photo, Qt.AspectRatioMode.KeepAspectRatio)

    def zoom(self, factor):
        scale = self.transform().m11() * factor
        if self.photo and 0.03 <= scale <= 20:
            self.fitted = False
            self.scale(factor, factor)

    def wheelEvent(self, event):
        self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fitted:
            self.fit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PhotoCheck · 수험생 사진 검수")
        self.resize(1024, 1000)
        self.results = []
        self.counts = Counter()
        self.total = self.excluded = self.preview_id = 0
        self.worker = None
        self.copy_worker = None
        self.copy_progress = None
        self.scanning = False
        self.current = None
        self.closing = False
        self.criteria, settings_error = load_criteria()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.discovery_issues = []
        self.discovery_cancelled = False
        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(22, 18, 22, 18)
        title = QLabel("수험생 사진 검수")
        title.setStyleSheet("font-size:24px; font-weight:700;")
        title_row = QHBoxLayout()
        title_row.addWidget(title)
        title_row.addStretch()
        self.settings = QPushButton()
        self.settings.setIcon(gear_icon())
        self.settings.setIconSize(QSize(24, 24))
        self.settings.setFixedSize(40, 36)
        self.settings.setAccessibleName("검사 기준 설정")
        self.settings.setToolTip("검사 항목·기준값 설정")
        self.settings.clicked.connect(self.open_settings)
        layout.addLayout(title_row)
        row = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("검사할 사진 폴더를 선택하세요")
        self.pick = QPushButton("폴더 선택")
        self.pick.clicked.connect(self.choose_folder)
        self.recursive = QCheckBox("하위 폴더 포함")
        self.recursive.setChecked(True)
        self.start = QPushButton("검사 시작")
        self.start.setObjectName("primary")
        self.start.clicked.connect(self.start_scan)
        self.cancel = QPushButton("취소")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.cancel_scan)
        for widget in (self.folder, self.pick, self.recursive, self.start, self.cancel, self.settings):
            row.addWidget(widget)
        layout.addLayout(row)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.state = QLabel(settings_error or "검사 대기", self)
        self.state.setWordWrap(True)
        self.state.hide()
        splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 10, 0)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("파일명·상대 경로 검색")
        self.reason_filter = QComboBox()
        self.reason_filter.addItems(["모든 사유", "파일", "회전·기울기", "사진 비율", "얼굴·신뢰도", "구도·위치", "머리·턱 여백", "정면·가림", "재촬영 의심", "글자 포함 의심", "모델·분석"])
        search_row.addWidget(self.search)
        search_row.addWidget(self.reason_filter)
        left_layout.addLayout(search_row)
        self.model = ResultModel(self)
        self.proxy = ResultFilter(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 149)
        self.table.selectionModel().currentRowChanged.connect(self.selected)
        left_layout.addWidget(self.table)
        self.search.textChanged.connect(self.filter_changed)
        self.reason_filter.currentTextChanged.connect(self.filter_changed)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 0, 0, 0)
        self.view = PhotoView()
        right_layout.addWidget(self.view, 1)
        nav = QHBoxLayout()
        self.previous = QPushButton("← 이전")
        self.next = QPushButton("다음 →")
        self.previous.clicked.connect(lambda: self.move(-1))
        self.next.clicked.connect(lambda: self.move(1))
        self.mark_normal = QPushButton("정상으로 분류")
        self.mark_normal.setEnabled(False)
        self.mark_normal.setToolTip("현재 사진을 정상으로 분류하고 확인 대상 목록에서 제외합니다.")
        self.mark_normal.clicked.connect(self.reclassify_normal)
        self.overlay = QPushButton("분석 표시")
        self.overlay.setCheckable(True)
        self.overlay.toggled.connect(self.view.set_overlay)
        for widget in (self.previous, self.mark_normal, self.next, self.overlay):
            nav.addWidget(widget)
        right_layout.addLayout(nav)
        info = QHBoxLayout()
        self.preview_state = QLabel("목록에서 사진을 선택하세요")
        self.preview_state.setWordWrap(True)
        self.position = QLabel("0 / 0")
        self.position.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        info.addWidget(self.preview_state, 1)
        info.addWidget(self.position)
        right_layout.addLayout(info)
        self.details = QTextBrowser()
        self.details.setMaximumHeight(160)
        right_layout.addWidget(self.details)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([500, 500])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        footer = QHBoxLayout()
        footer.addStretch()
        self.copy = QPushButton("사진 복사")
        self.copy.setEnabled(False)
        self.copy.setToolTip("현재 검색·필터로 표시된 확인 대상 사진을 하위 폴더 구조대로 복사합니다.")
        self.copy.clicked.connect(self.choose_copy_folder)
        footer.addWidget(self.copy)
        self.export = QPushButton("결과 저장")
        self.export.setEnabled(False)
        self.export.clicked.connect(self.save_excel)
        footer.addWidget(self.export)
        layout.addLayout(footer)
        for target in (self.table, self.view):
            for key, delta in (("Left", -1), ("Right", 1)):
                shortcut = QShortcut(QKeySequence(key), target)
                shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
                shortcut.activated.connect(lambda d=delta: self.move(d))
        self.update_counts()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "사진 폴더 선택", self.folder.text())
        if folder:
            self.folder.setText(folder)

    def open_settings(self):
        if not self.settings.isEnabled() or (self.worker and self.worker.isRunning()):
            return
        dialog = SettingsDialog(self.criteria, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.criteria = dialog.criteria
            self.state.setText("검사 설정 저장됨 · 다음 검사부터 적용됩니다. 기존 결과는 검사 당시 기준을 유지합니다.")

    def start_scan(self):
        if self.copy_worker is not None:
            return
        root = Path(self.folder.text().strip()).expanduser()
        try:
            valid = bool(self.folder.text().strip()) and root.is_dir()
            if valid:
                # Opening directory enumeration verifies read/list permission without writes.
                import os
                with os.scandir(root):
                    pass
        except PermissionError:
            QMessageBox.warning(self, "폴더 접근 권한 확인", "이 폴더를 읽을 권한이 없습니다. 읽기 가능한 폴더나 사본을 선택하세요.")
            return
        except OSError as error:
            QMessageBox.warning(self, "폴더 접근 실패", str(error))
            return
        if not valid:
            QMessageBox.warning(self, "폴더 확인", "접근 가능한 사진 폴더를 선택하세요.")
            return
        if self.worker and self.worker.isRunning():
            return
        self.results.clear()
        self.counts.clear()
        self.model.clear()
        self.total = self.excluded = 0
        self.discovery_issues = []
        self.discovery_cancelled = False
        self.clear_preview()
        self.search.clear()
        self.reason_filter.setCurrentIndex(0)
        self.update_counts()
        self.set_running(True)
        self.progress.setRange(0, 0)
        self.worker = ScanWorker(root.resolve(), self.recursive.isChecked(), self, criteria=self.criteria)
        self.worker.collected.connect(self.collected)
        self.worker.batch.connect(self.received)
        self.worker.message.connect(self.state.setText)
        self.worker.completed.connect(self.completed)
        self.worker.finished.connect(self.thread_finished)
        self.worker.start()

    def set_running(self, running):
        self.scanning = running
        for widget in (self.folder, self.pick, self.recursive, self.start, self.settings):
            widget.setEnabled(not running)
        self.cancel.setEnabled(running)
        self.update_actions()

    def update_actions(self):
        busy = self.scanning or self.copy_worker is not None
        self.start.setEnabled(not busy)
        self.export.setEnabled(not busy and bool(self.results))
        self.copy.setEnabled(not busy and self.proxy.rowCount() > 0)
        self.mark_normal.setEnabled(not busy and self.current is not None and
                                    self.current.status != Status.NORMAL and self.view.photo is not None)

    def cancel_scan(self):
        if self.worker:
            self.worker.cancel()
            self.state.setText("취소 중… 현재 파일 처리가 끝나면 중단합니다.")
            self.cancel.setEnabled(False)

    def collected(self, collection):
        self.total, self.excluded = len(collection.paths), collection.excluded
        self.discovery_issues = collection.issues
        self.discovery_cancelled = collection.cancelled
        self.progress.setRange(0, max(self.total, 1))
        self.update_counts()

    def received(self, results):
        self.results.extend(results)
        self.counts.update(r.status for r in results)
        self.model.add(results)
        self.progress.setValue(len(self.results))
        self.state.setText(f"검사 중 · {len(self.results):,} / {self.total:,}건 처리")
        self.update_counts()
        if not self.table.currentIndex().isValid() and self.proxy.rowCount():
            self.table.selectRow(0)

    def completed(self, cancelled, error=""):
        # QThread.finished enables a new run only after resources are fully released.
        text = "검사 실행 오류" if error else "검사 취소됨" if cancelled else "검사 완료" if len(self.results) == self.total else "검사 중단됨"
        text += f" · 처리 {len(self.results):,}건 · 미처리 {self.total - len(self.results):,}건 · 비이미지 제외 {self.excluded:,}건"
        if self.discovery_cancelled:
            text += " · 후보 수집 중 취소되어 전체 파일 수는 미확정"
        if self.discovery_issues:
            text += f" · 폴더 접근 오류 {len(self.discovery_issues)}건 (일부 파일 누락 가능)"
        if error:
            text += " · " + error
        self.state.setText(text)
        self.state.setToolTip("\n".join(self.discovery_issues))
        self.progress.setRange(0, max(self.total, 1))
        self.progress.setValue(len(self.results))
        self.update_counts()

    def thread_finished(self):
        self.set_running(False)
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        if self.closing:
            self.close()

    def update_counts(self):
        self.summary.setText(f"전체 {self.total:,}   ·   정상 {self.counts[Status.NORMAL]:,}   ·   확인 필요 {self.counts[Status.REVIEW]:,}   ·   파일 오류 {self.counts[Status.ERROR]:,}   ·   미처리 {max(0, self.total - len(self.results)):,}")
        row = self.table.currentIndex().row()
        count = self.proxy.rowCount()
        self.position.setText(f"{row + 1 if row >= 0 else 0} / {count}")
        self.previous.setEnabled(row > 0)
        self.next.setEnabled(count > 0 and row < count - 1)
        self.update_actions()

    def filter_changed(self, *_):
        self.proxy.update_filter(self.search.text(), self.reason_filter.currentText())
        if self.proxy.rowCount():
            self.table.selectRow(0)
            self.selected(self.proxy.index(0, 0))
        else:
            self.table.clearSelection()
            self.table.setCurrentIndex(QModelIndex())
            self.clear_preview()
        self.update_counts()

    def clear_preview(self):
        self.preview_id += 1
        self.pool.clear()
        self.current = None
        self.view.clear()
        self.details.clear()
        self.preview_state.setText("목록에서 사진을 선택하세요" if self.proxy.rowCount() else "표시할 확인 대상이 없습니다")
        self.preview_state.setToolTip("")
        self.update_actions()

    def selected(self, index, *_):
        if not index.isValid():
            return
        result = self.model.rows[self.proxy.mapToSource(index).row()]
        self.current = result
        self.preview_id += 1
        self.pool.clear()
        self.view.clear()
        self.preview_state.setText("사진 불러오는 중…")
        details = [str(result.path), f"분류: {result.status.value}",
                   f"파일: {result.file_check.value}  |  방향: {result.direction_check.value}  |  구도: {result.framing_check.value}",
                   *["• " + reason for reason in result.reasons],
                   f"검사 일시: {result.checked_at}"]
        if result.criteria_settings:
            c = result.criteria_settings
            details.append(f"적용 기준: 얼굴 높이 {c['face_height_min']:.1%} ({'검사' if c['check_height'] else '해제'}), 기울기 {c['roll_degrees']:g}° ({'검사' if c['check_roll'] else '해제'}), 신뢰도 {c['confidence']:g} ({'검사' if c['check_confidence'] else '해제'}) · 설정 {result.criteria_id}")
            if "check_aspect" in c:
                details.append(f"사진 비율: {c['aspect_width']:g}:{c['aspect_height']:g}, 허용 오차 비율 {c['aspect_tolerance']:g} ({'검사' if c['check_aspect'] else '해제'})")
            if "check_text" in c:
                details.append(f"글자 포함: 연속 {c.get('text_min_chars', 3):g}글자 이상, 글자별 신뢰도 {c.get('text_rec_confidence', .6):g} 이상 · 검출 신뢰도 {c['text_confidence']:g}, 영역 높이 {c['text_height_min']:.1%} 이상 ({'검사' if c['check_text'] else '해제'}) · 주황색 상자로 위치 표시")
        self.details.setPlainText("\n".join(details))
        self.update_counts()
        job = PreviewWorker(self.preview_id, result.path)
        job.signals.ready.connect(self.preview_ready)
        self.pool.start(job)

    def preview_ready(self, request_id, image, error):
        if request_id != self.preview_id or self.current is None:
            return
        if image is None:
            self.preview_state.setText("미리보기 불가 · " + error)
        else:
            self.preview_state.setText(self.current.path.name)
            self.preview_state.setToolTip(str(self.current.path))
            self.view.display(image, self.current, self.overlay.isChecked())
        self.update_actions()

    def move(self, delta):
        row = self.table.currentIndex().row() + delta
        if 0 <= row < self.proxy.rowCount():
            self.table.selectRow(row)
            self.table.scrollTo(self.proxy.index(row, 0))

    def reclassify_normal(self):
        if not self.mark_normal.isEnabled() or self.current is None:
            return
        result = self.current
        row = self.table.currentIndex().row()
        result.mark_normal()
        self.clear_preview()
        self.table.clearSelection()
        self.table.setCurrentIndex(QModelIndex())
        self.model.remove(result)
        self.counts = Counter(r.status for r in self.results)
        if self.proxy.rowCount():
            row = min(max(0,row),self.proxy.rowCount()-1)
            self.table.selectRow(row)
            self.selected(self.proxy.index(row,0))
        else:
            self.clear_preview()
        self.update_counts()
        self.state.setText(f"정상으로 재분류: {result.path.name} · 엑셀 저장·사진 복사 대상에서 제외됨")

    def displayed_results(self):
        return [self.model.rows[self.proxy.mapToSource(self.proxy.index(row,0)).row()]
                for row in range(self.proxy.rowCount())]

    def choose_copy_folder(self):
        if not self.copy.isEnabled():
            return
        rows = self.displayed_results()
        destination = QFileDialog.getExistingDirectory(self,"확인 대상 사진을 복사할 폴더 선택")
        if not destination:
            return
        self.copy_worker = CopyWorker(rows,Path(destination),self)
        self.copy_progress = QProgressDialog("사진 복사 준비 중…", "취소", 0, len(rows), self)
        self.copy_progress.setWindowTitle("사진 복사")
        self.copy_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.copy_progress.setMinimumDuration(0)
        self.copy_progress.setAutoClose(False)
        self.copy_progress.setAutoReset(False)
        self.copy_progress.setMinimumWidth(380)
        self.copy_progress.canceled.connect(self.copy_worker.cancel)
        self.copy_progress.setValue(0)
        self.copy_progress.show()
        self.copy_worker.progress.connect(self.copy_progress_changed)
        self.copy_worker.completed.connect(self.copy_completed)
        self.copy_worker.finished.connect(self.copy_finished)
        self.update_actions()
        self.copy_worker.start()

    def copy_progress_changed(self, done, total):
        text = f"사진 복사 중 · {done:,} / {total:,}건"
        self.state.setText(text)
        if self.copy_progress is not None:
            self.copy_progress.setLabelText(text)
            self.copy_progress.setValue(done)

    def copy_completed(self,report):
        if self.copy_progress is not None:
            self.copy_progress.hide()
            self.copy_progress.deleteLater()
            self.copy_progress = None
        self.state.setText(f"사진 복사 {'중단' if report.cancelled else '완료'} · 복사 {report.copied:,}건 · 기존 파일 등 제외 {len(report.skipped):,}건 · 실패 {len(report.errors):,}건")
        if not self.closing:
            message = QMessageBox(self)
            message.setWindowTitle("사진 복사 결과")
            message.setIcon(QMessageBox.Icon.Warning if report.errors else QMessageBox.Icon.Information)
            message.setText(self.state.text())
            message.setInformativeText("원본과 기존 파일은 덮어쓰지 않습니다.")
            if report.errors or report.skipped:
                message.setDetailedText('\n'.join(report.errors+report.skipped))
            message.exec()

    def copy_finished(self):
        if self.copy_worker:
            self.copy_worker.deleteLater()
            self.copy_worker = None
        self.update_actions()
        if self.closing:
            self.close()

    def save_excel(self):
        if not self.export.isEnabled():
            return
        from PySide6.QtCore import QStandardPaths
        documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        default = str(Path(documents or str(Path.home())) / "사진검수_결과.xlsx")
        name, _ = QFileDialog.getSaveFileName(self, "결과 저장", default, "엑셀 파일 (*.xlsx)")
        if not name:
            return
        target = Path(name)
        if target.suffix.lower() != ".xlsx":
            target = target.with_name(target.name + ".xlsx")
            if target.exists() and QMessageBox.question(self, "기존 결과 덮어쓰기", f"{target}\n기존 파일을 덮어쓰시겠습니까?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
        if any(target.resolve() == r.path.resolve() for r in self.results):
            QMessageBox.warning(self, "저장 경로 확인", "원본 사진 경로에는 저장할 수 없습니다.")
            return
        try:
            count = export_excel(target, self.results)
            self.state.setText(f"확인 대상 결과 {count:,}건 저장: {target} · 정상·미처리 건 제외")
        except PermissionError as error:
            message = "파일이 다른 프로그램에서 열려 있습니다. 엑셀 파일을 닫거나 다른 이름으로 저장하세요." if getattr(error, "winerror", None) in (32, 33) else "저장 권한이 없거나 파일이 읽기 전용·사용 중입니다. 열린 엑셀 파일을 닫거나 문서 폴더 등 저장 가능한 위치를 선택하세요."
            QMessageBox.warning(self, "결과 저장 권한 확인", message + "\n현재 검사 결과와 기존 파일은 유지됩니다.")
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "결과 저장 실패", str(error))

    def closeEvent(self, event):
        if self.copy_worker is not None:
            self.closing = True
            self.copy_worker.cancel()
            self.setEnabled(False)
            event.ignore()
            return
        if self.worker and self.worker.isRunning():
            self.closing = True
            self.cancel_scan()
            self.setEnabled(False)
            event.ignore()
            return
        self.preview_id += 1
        self.pool.clear()
        self.pool.waitForDone()
        event.accept()
