"""Inspection preferences; edits are persisted only on a successful Save."""
from dataclasses import replace
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import (QAbstractSpinBox, QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QTabWidget, QVBoxLayout, QWidget, QScrollArea)

from .criteria import Criteria, RANGES, save_criteria


# label, storage key, multiplier for human-friendly percentages, decimal places
GROUPS = [
    ("기본 검사", [
        ("가로가 넓은 사진", "check_landscape", [], "사진 너비가 높이보다 크면 확인 필요"),
        ("증명사진 가로·세로 비율", "check_aspect", [
            ("기준 가로 비율", "aspect_width", 1, 1),
            ("기준 세로 비율", "aspect_height", 1, 1),
            ("허용 오차 비율", "aspect_tolerance", 1, 2)],
         "사진 가로를 기준 가로 값에 맞춰 환산한 뒤 세로−가로를 비교합니다.\n기준 3:4, 허용 오차 0.5이면 세로−가로 0.5~1.5를 허용합니다.\n양쪽 경계도 통과하며, EXIF 방향 반영 후 전체 사진 크기로 검사합니다."),
        ("얼굴 검출 신뢰도", "check_confidence", [("신뢰도 하한", "confidence", 1, 2)], "하한 이하이면 확인 필요"),
        ("얼굴 기울기", "check_roll", [("허용 기울기 (°)", "roll_degrees", 1, 1), ("최소 눈 간격 (%)", "eye_span_min", 100, 1)], "기울기의 절댓값이 기준 이상이거나 눈 간격이 기준 미만이면 확인 필요"),
        ("얼굴 높이", "check_height", [("최소 높이 (%)", "face_height_min", 100, 1)], "검출된 얼굴 영역 높이 ÷ 사진 높이 · 기준 이하이면 확인 필요"),
        ("중앙 위치", "check_center", [("중앙에서 허용 편차 (%)", "center_offset", 100, 1)], "사진 너비 기준 · 편차가 기준 이상이면 확인 필요"),
        ("머리·턱 여백", "check_boundary", [("테두리 최소 여백 (%)", "boundary_margin", 100, 1)], "눈·코·이마·턱·볼·입 특징점이 여백 안쪽 또는 경계이면 확인 필요"),
    ]),
    ("정면 검사", [
        ("정면 방향·얼굴 가림", "check_front", [
            ("코 좌우 편차 한계", "front_symmetry_max", 1, 3),
            ("눈 깊이 차이 한계", "depth_asymmetry_max", 1, 3),
            ("코 높이 비율 하한 (%)", "nose_height_min", 100, 1),
            ("코 높이 비율 상한 (%)", "nose_height_max", 100, 1)],
         "좌우·깊이 차이는 눈 간격 대비 비율이며 한계 이상이면 확인 필요.\n코 높이는 이마~턱에서의 비율이며 하한·상한과 같은 값도 확인 필요."),
    ]),
    ("재촬영 검사", [
        ("인화사진 재촬영 의심", "check_recapture", [
            ("종이 영역 최소 비율 (%)", "paper_area_min", 100, 1),
            ("종이 영역 최대 비율 (%)", "paper_area_max", 100, 1),
            ("최소 테두리 길이 (%)", "paper_edge_min", 100, 1),
            ("종이 안팎 최소 색 차이", "paper_contrast_min", 1, 1),
            ("외부 배경 최소 명암 변화", "paper_background_min", 1, 1)],
         "종이 테두리 3면, 안팎 색 차이, 외부 배경의 명암 변화를 함께 검사합니다.\n영역은 사진 면적, 테두리 길이는 사진 너비 기준입니다.\n색·명암 차이는 0~255 값입니다. 테두리가 잘리거나 배경이 균일한 재촬영은 놓칠 수 있습니다."),
    ]),
    ("글자 검사", [
        ("사진 내 글자 포함 의심", "check_text", [
            ("최소 연속 글자 수", "text_min_chars", 1, 0),
            ("글자별 최소 인식 신뢰도", "text_rec_confidence", 1, 2),
            ("최소 검출 신뢰도", "text_confidence", 1, 2),
            ("최소 글자 영역 높이 (%)", "text_height_min", 100, 1),
            ("분석 사본 최대 길이 (px)", "text_edge", 1, 0)],
         "글자 후보 영역에서 한글·영문·숫자를 인식해 연속 글자 수를 확인합니다.\n기본값은 신뢰도 0.60 이상인 글자가 3개 이상 연속된 경우에만 확인 필요입니다.\n공백·기호·낮은 신뢰도의 글자에서 구간을 끊으며, 별도 영역의 글자 수는 합산하지 않습니다.\n글자 내용은 화면·결과 파일에 저장하지 않습니다. 검출 신뢰도와 인식 신뢰도는 서로 다른 기준입니다.\n작거나 흐린 글자·필기체·그림만 있는 로고는 놓칠 수 있습니다. 분석 길이를 높이면 처리 시간이 늘 수 있습니다."),
    ]),
]


def gear_icon():
    # Vector-drawn icon remains independent of installed symbol fonts.
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    points = []
    for i in range(48):
        angle = 2 * math.pi * i / 48
        radius = 27 if i % 6 in (1, 2, 3, 4) else 21
        points.append(QPointF(32+radius*math.cos(angle), 32+radius*math.sin(angle)))
    painter.setPen(QPen(QColor("#475569"), 2))
    painter.setBrush(QColor("#64748b"))
    painter.drawPolygon(QPolygonF(points))
    painter.setBrush(QColor("#ffffff"))
    painter.drawEllipse(QPointF(32,32), 10, 10)
    painter.end()
    return QIcon(pixmap)


class SettingsDialog(QDialog):
    def __init__(self, criteria, parent=None, path=None):
        super().__init__(parent)
        self.criteria = criteria
        self.path = path
        self.setWindowTitle("검사 기준 설정")
        self.resize(650, 710)
        self.fields, self.checks = {}, {}
        layout = QVBoxLayout(self)
        heading = QLabel("검사 항목과 기준값")
        heading.setStyleSheet("font-size:20px;font-weight:700;")
        layout.addWidget(heading)
        info = QLabel("저장한 설정은 다음 검사부터 적용됩니다. 기존 결과는 해당 검사 당시 기준을 유지합니다.")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        for title, groups in GROUPS:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            for label, switch, fields, help_text in groups:
                group = QGroupBox()
                box = QVBoxLayout(group)
                check = QCheckBox(label)
                self.checks[switch] = check
                box.addWidget(check)
                form = QFormLayout()
                for field_label, name, multiplier, decimals in fields:
                    spin = QDoubleSpinBox()
                    spin.setDecimals(decimals)
                    lo, hi = RANGES[name]
                    spin.setRange(lo*multiplier, hi*multiplier)
                    spin.setSingleStep(64 if name == "text_edge" else 1 if multiplier == 100 or name == "paper_contrast_min" else .1 if name == "roll_degrees" else 10**(-decimals))
                    spin.setFixedWidth(145)
                    spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
                    spin.setObjectName(name)
                    spin.setAccessibleName(field_label)
                    self.fields[name] = (spin, multiplier)
                    check.toggled.connect(spin.setEnabled)
                    form.addRow(field_label, spin)
                box.addLayout(form)
                note = QLabel(help_text)
                note.setWordWrap(True)
                note.setStyleSheet("color:#667085;font-size:11px;")
                box.addWidget(note)
                page_layout.addWidget(group)
            page_layout.addStretch()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.tabs.addTab(scroll, title)
        # Fundamental validity cannot be converted into an automatic pass.
        mandatory = QLabel("항상 검사: 파일 열기·손상, 얼굴 미검출·여러 얼굴, 분석 오류·특징점 충돌.\n정방향 얼굴 미검출 시 180°로 재검출합니다. 어깨·가슴은 검사하지 않습니다.")
        mandatory.setWordWrap(True)
        mandatory.setStyleSheet("color:#667085;font-size:11px;")
        layout.addWidget(mandatory)
        bottom = QHBoxLayout()
        restore = QPushButton("기본값 복원")
        restore.clicked.connect(lambda: self.populate(Criteria()))
        bottom.addWidget(restore)
        bottom.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("저장")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        bottom.addWidget(buttons)
        layout.addLayout(bottom)
        self.populate(criteria)

    def populate(self, criteria):
        for name, check in self.checks.items():
            check.setChecked(getattr(criteria, name))
        for name, (spin, multiplier) in self.fields.items():
            spin.setValue(getattr(criteria, name)*multiplier)
        for _, groups in GROUPS:
            for _, switch, fields, _ in groups:
                for _, name, _, _ in fields:
                    self.fields[name][0].setEnabled(self.checks[switch].isChecked())

    def edited_criteria(self):
        values = {name: check.isChecked() for name, check in self.checks.items()}
        values.update({name: spin.value()/multiplier for name, (spin, multiplier) in self.fields.items()})
        return replace(self.criteria, **values)

    def save(self):
        try:
            criteria = self.edited_criteria()
            save_criteria(criteria, self.path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "설정 저장 실패", f"설정을 저장하지 못했습니다. 기존 설정을 유지합니다.\n{error}")
            return
        self.criteria = criteria
        self.accept()
