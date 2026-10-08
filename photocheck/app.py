import sys


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--permission-test":
        from .permission_check import run
        return run(sys.argv[2], sys.argv[3])
    if len(sys.argv) in (4, 5) and sys.argv[1] == "--validate-folder":
        from .validation import run
        return run(sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) == 5 else 0)
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        from .smoke import run
        return run(sys.argv[2])
    from PySide6.QtWidgets import QApplication
    from .theme import apply_light_theme
    from .ui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("PhotoCheck")
    apply_light_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()
