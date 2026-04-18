import sys
import threading
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, QUrl
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QSystemTrayIcon

import uvicorn

from devgrow import db

PORT = 7331
_URL = f"http://127.0.0.1:{PORT}"
_ASSETS = Path(__file__).parent / "assets"


def _run_server() -> None:
    db.init_db()
    uvicorn.run("devgrow.web:app", host="127.0.0.1", port=PORT, log_level="error")


def _wait_ready(timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(_URL + "/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.1)
    return False


class DevGrowWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DevGrow")
        self.setMinimumSize(QSize(1100, 700))

        settings = QSettings("DevGrow", "DevGrow")
        geom = settings.value("geometry")
        if geom:
            self.restoreGeometry(geom)
        else:
            self.resize(1280, 820)

        icon_path = _ASSETS / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.view = QWebEngineView()
        self.view.setUrl(QUrl(_URL))
        self.setCentralWidget(self.view)

        QShortcut(QKeySequence.StandardKey.ZoomIn,  self, lambda: self._zoom(0.1))
        QShortcut(QKeySequence.StandardKey.ZoomOut, self, lambda: self._zoom(-0.1))
        QShortcut(QKeySequence("Ctrl+0"), self, lambda: self.view.setZoomFactor(1.0))

        self._setup_tray()

    def _zoom(self, delta: float) -> None:
        f = max(0.5, min(3.0, self.view.zoomFactor() + delta))
        self.view.setZoomFactor(f)

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self)
        icon_path = _ASSETS / "icon.png"
        self.tray.setIcon(
            QIcon(str(icon_path)) if icon_path.exists()
            else self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon)
        )

        menu = QMenu()
        for label, slot in [
            ("Show DevGrow",  self._show_window),
            (None, None),
            ("Dashboard",     lambda: self._nav("/")),
            ("Quiz Now",      lambda: self._nav("/quiz")),
            ("Log Session",   lambda: self._nav("/learn")),
            ("Weekly Review", lambda: self._nav("/review")),
            (None, None),
            ("Quit",          QApplication.quit),
        ]:
            if label is None:
                menu.addSeparator()
            else:
                a = QAction(label, self)
                a.triggered.connect(slot)
                menu.addAction(a)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _nav(self, path: str) -> None:
        self._show_window()
        self.view.setUrl(QUrl(_URL + path))

    def _show_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def closeEvent(self, event) -> None:
        QSettings("DevGrow", "DevGrow").setValue("geometry", self.saveGeometry())
        super().closeEvent(event)


def main() -> None:
    thread = threading.Thread(target=_run_server, daemon=True)
    thread.start()
    _wait_ready()

    app = QApplication(sys.argv)
    app.setApplicationName("DevGrow")
    app.setOrganizationName("DevGrow")
    app.setQuitOnLastWindowClosed(False)

    icon_path = _ASSETS / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = DevGrowWindow()
    window.show()
    sys.exit(app.exec())
