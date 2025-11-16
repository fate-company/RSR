import sys
import os

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QSystemTrayIcon, QMenu, QFrame
)
from PyQt6.QtGui import QIcon, QMovie
from PyQt6.QtCore import Qt, QTimer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(BASE_DIR, "icons")

APP_VERSION = "1.1.0"


def resource_path(*parts: str) -> str:
    return os.path.join(ICON_DIR, *parts)


class SplashScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(420, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("splashContainer")
        container_layout = QVBoxLayout(container)

        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        gif_path = resource_path("RSR_loader.gif")
        if os.path.exists(gif_path):
            movie = QMovie(gif_path)
            label.setMovie(movie)
            movie.start()
        else:
            label.setText("Rockfeller System Restore")
            label.setStyleSheet("color: #FFD95A; font-size: 20px;")

        title = QLabel("Rockfeller System Restore")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #FFD95A; font-size: 18px; font-weight: 600;")

        container_layout.addStretch()
        container_layout.addWidget(label)
        container_layout.addWidget(title)
        container_layout.addStretch()

        layout.addWidget(container)

        self.setStyleSheet("""
        #splashContainer {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #111418,
                stop:1 #050608
            );
            border-radius: 28px;
            border: 1px solid rgba(255, 255, 255, 0.15);
        }
        """)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Rockfeller System Restore 1.1 | RSR 1.1")
        self.resize(1100, 680)

        icon_file = resource_path("RSR_256.png")
        if os.path.exists(icon_file):
            self.setWindowIcon(QIcon(icon_file))

        self._init_ui()
        self._init_tray()
        self._init_pulse()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(16)

        # LEFT PANEL
        left = QFrame()
        left.setObjectName("leftPanel")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(18, 18, 18, 18)

        logo_row = QHBoxLayout()
        logo = QLabel()
        logo.setFixedSize(40, 40)
        if os.path.exists(resource_path("RSR_256.png")):
            logo.setPixmap(QIcon(resource_path("RSR_256.png")).pixmap(40, 40))
        title = QLabel("RSR Panel")
        title.setStyleSheet("color: #F5F5F7; font-size: 18px; font-weight: 600;")
        logo_row.addWidget(logo)
        logo_row.addWidget(title)
        logo_row.addStretch()
        left_layout.addLayout(logo_row)

        left_layout.addWidget(self._nav_button("Создать резервную копию"))
        left_layout.addWidget(self._nav_button("Восстановление системы"))
        left_layout.addWidget(self._nav_button("Настройки"))
        left_layout.addWidget(self._nav_button("Логи и отчёты"))

        left_layout.addStretch()

        news_btn = self._nav_button("Новости и обновления")
        news_btn.clicked.connect(self._open_news)
        left_layout.addWidget(news_btn)

        # RIGHT PANEL
        right = QFrame()
        right.setObjectName("rightPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(22, 22, 22, 22)

        header = QLabel("Обзор системы")
        header.setStyleSheet("color: #F9FAFB; font-size: 20px; font-weight: 600;")
        right_layout.addWidget(header)

        info = QLabel(
            "Rockfeller System Restore 1.1\n\n"
            "• Полная копия системы (rootfs)\n"
            "• Настройки профилей\n"
            "• Логи\n"
            "• Автообновления скоро"
        )
        info.setStyleSheet("color: #C7CBD4; font-size: 13px;")
        info.setWordWrap(True)
        right_layout.addWidget(info)
        right_layout.addStretch()

        root_layout.addWidget(left, 1)
        root_layout.addWidget(right, 3)

        self._apply_style()

    def _nav_button(self, text):
        btn = QPushButton(text)
        btn.setObjectName("navButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(40)
        return btn

    def _apply_style(self):
        self.setStyleSheet("""
        QMainWindow {
            background: #05070B;
        }

        #leftPanel {
            background: rgba(9, 11, 18, 0.95);
            border-radius: 22px;
            border: 1px solid rgba(122, 215, 255, 0.35);
        }

        #rightPanel {
            background: rgba(13, 15, 22, 0.96);
            border-radius: 22px;
            border: 1px solid rgba(255, 217, 90, 0.40);
        }

        QPushButton#navButton {
            background: rgba(18, 22, 34, 0.9);
            color: #E4E7F0;
            border-radius: 16px;
            border: 1px solid rgba(110, 119, 140, 0.55);
            padding-left: 14px;
            text-align: left;
        }

        QPushButton#navButton:hover {
            border-color: #7AD7FF;
        }
        """)

    # TRAY
    def _init_tray(self):
        icon_file = resource_path("RSR_256.png")
        self.tray = QSystemTrayIcon(QIcon(icon_file), self)

        menu = QMenu()
        open_action = QAction("Открыть RSR", self)
        open_action.triggered.connect(self.showNormal)
        menu.addAction(open_action)

        check_action = QAction("Проверить обновления", self)
        check_action.triggered.connect(self._check_updates)
        menu.addAction(check_action)

        quit_action = QAction("Выход", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.show()

    # Pulse animation
    def _init_pulse(self):
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(lambda: None)
        self._pulse_timer.start(800)

    def _check_updates(self):
        self.tray.showMessage(
            "RSR Update",
            "Пока заглушка. Дальше подключим GitHub Pages → latest.json",
            QSystemTrayIcon.MessageIcon.Information
        )

    def _open_news(self):
        self.tray.showMessage(
            "Новости RSR",
            "В следующей версии здесь появится лента изменений.",
            QSystemTrayIcon.MessageIcon.Information
        )


def main():
    app = QApplication(sys.argv)

    splash = SplashScreen()

    screen = app.primaryScreen()
    if screen:
        center = screen.geometry().center()
        geo = splash.frameGeometry()
        geo.moveCenter(center)
        splash.move(geo.topLeft())

    splash.show()

    QTimer.singleShot(1800, lambda: open_main_window(app, splash))

    sys.exit(app.exec())


def open_main_window(app, splash):
    splash.close()
    win = MainWindow()
    win.show()
    app._win = win


if __name__ == "__main__":
    main()
