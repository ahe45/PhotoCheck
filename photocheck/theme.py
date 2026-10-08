"""A consistent light theme, independent of the Windows system palette."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette


def apply_light_theme(app):
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    app.setStyle("Fusion")
    app.setFont(QFont("Malgun Gothic", 10))
    palette = QPalette()
    colors = {
        "Window": "#f8fafc", "WindowText": "#243247",
        "Base": "#ffffff", "AlternateBase": "#f8fafc", "Text": "#243247",
        "Button": "#ffffff", "ButtonText": "#243247",
        "ToolTipBase": "#ffffff", "ToolTipText": "#243247",
        "Highlight": "#dbeafe", "HighlightedText": "#17345c",
        "Link": "#2563eb", "LinkVisited": "#1d4ed8", "BrightText": "#ffffff",
        "PlaceholderText": "#667085", "Light": "#ffffff",
        "Midlight": "#eef2f7", "Mid": "#cbd5e1", "Dark": "#94a3b8",
        "Shadow": "#64748b", "Accent": "#2563eb",
    }
    # Set active AND inactive colors; unfocused windows must stay readable too.
    for name, color in colors.items():
        palette.setColor(getattr(QPalette.ColorRole, name), QColor(color))
    for name in ("WindowText", "Text", "ButtonText", "PlaceholderText"):
        palette.setColor(QPalette.ColorGroup.Disabled,
                         getattr(QPalette.ColorRole, name), QColor("#8492a6"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#f1f3f6"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor("#f1f3f6"))
    app.setPalette(palette)
    app.setStyleSheet("""
        QMainWindow { background: #f8fafc; }
        QWidget { color: #243247; }
        QWidget:disabled { color: #8492a6; }
        QLineEdit, QComboBox, QDoubleSpinBox {
            background: white; color: #243247; border: 1px solid #cbd5e1;
            border-radius: 4px; padding: 7px;
            selection-background-color: #dbeafe; selection-color: #17345c;
        }
        QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus { border-color: #2563eb; }
        QDoubleSpinBox { padding-right: 24px; }
        QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 20px; }
        QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 20px; }
        QLineEdit:disabled, QComboBox:disabled, QDoubleSpinBox:disabled { background: #f1f3f6; color: #8492a6; }
        QDialog, QScrollArea, QScrollArea > QWidget > QWidget { background: #f8fafc; }
        QGroupBox { background: white; border: 1px solid #d5dde7; border-radius: 5px; }
        QTabWidget::pane { border: 1px solid #d5dde7; background: #f8fafc; }
        QTabBar::tab { background: #eef2f7; padding: 8px 16px; color: #475569; }
        QTabBar::tab:selected { background: white; color: #1d4ed8; }
        QComboBox QAbstractItemView {
            background: white; color: #243247; border: 1px solid #cbd5e1;
            selection-background-color: #dbeafe; selection-color: #17345c;
        }
        QPushButton {
            color: #243247; padding: 7px; border: 1px solid #cbd5e1;
            border-radius: 5px; background: white;
        }
        QPushButton:hover { background: #edf2fa; }
        QPushButton:pressed { background: #dbeafe; }
        QPushButton:checked { background: #dbeafe; color: #1d4ed8; border-color: #3b82f6; }
        QPushButton:focus { border-color: #2563eb; }
        QPushButton:disabled { color: #8492a6; background: #f1f3f6; }
        QPushButton#primary { background: #2563eb; color: white; border: 0; }
        QPushButton#primary:hover { background: #1d4ed8; }
        QPushButton#primary:disabled { background: #a7b9da; color: white; }
        QCheckBox { color: #243247; spacing: 6px; }
        QCheckBox:disabled { color: #8492a6; }
        QTableView, QTextBrowser {
            background: white; color: #243247; border: 1px solid #d5dde7;
            alternate-background-color: #f8fafc;
            selection-background-color: #dbeafe; selection-color: #17345c;
            gridline-color: #e2e8f0;
        }
        QHeaderView::section {
            background: #eef2f7; color: #243247; padding: 6px;
            font-weight: 600; border: 0; border-bottom: 1px solid #d5dde7;
        }
        QTableCornerButton::section { background: #eef2f7; border: 0; }
        QGraphicsView { border: 1px solid #d5dde7; }
        QProgressBar {
            background: #e8eef5; color: #243247; border: 1px solid #d5dde7;
            border-radius: 4px; text-align: center; max-height: 20px;
        }
        QProgressBar::chunk { background: #3b82f6; border-radius: 3px; }
        QToolTip { background: white; color: #243247; border: 1px solid #cbd5e1; padding: 5px; }
    """)
