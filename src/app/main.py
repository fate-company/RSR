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

APP_VERSION = "1.2.1"


def resource_path(*parts: str) -> str:
    """Return absolute path to a resource inside icons/ next to main.py."""
    return os.path.join(ICON_DIR, *parts)


class SplashScreen(QWidget):
    """Neon splash with RSR loader animation."""
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
        container_layout.setContentsMargins(24, 24, 24, 24)

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
        title.setStyleSheet("""
            color: #FFD95A;
            font-size: 18px;
            font-weight: 600;
        """)

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
    """Main Rockfeller System Restore window with neon + glass UI."""
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"Rockfeller System Restore {APP_VERSION} | RSR {APP_VERSION}")
        self.resize(1100, 680)
        self.setMinimumSize(900, 580)

        icon_file = resource_path("RSR_256.png")
        if os.path.exists(icon_file):
            self.setWindowIcon(QIcon(icon_file))

        self._init_ui()
        self._apply_style()
        self._init_tray()
        self._init_pulse()

    # ---------- UI ----------
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(16)

        # LEFT PANEL (navigation)
        left_panel = QFrame()
        left_panel.setObjectName("leftPanel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(18, 18, 18, 18)
        left_layout.setSpacing(12)

        logo_row = QHBoxLayout()
        logo_label = QLabel()
        logo_label.setFixedSize(40, 40)
        icon_file = resource_path("RSR_256.png")
        if os.path.exists(icon_file):
            logo_label.setPixmap(QIcon(icon_file).pixmap(40, 40))
        title_label = QLabel("RSR Panel")
        title_label.setStyleSheet("""
            color: #F5F5F7;
            font-size: 18px;
            font-weight: 600;
        """)
        logo_row.addWidget(logo_label)
        logo_row.addWidget(title_label)
        logo_row.addStretch()

        left_layout.addLayout(logo_row)

        subtitle = QLabel("Rockfeller System Restore")
        subtitle.setStyleSheet("color: #9EA6B8; font-size: 12px;")
        left_layout.addWidget(subtitle)

        left_layout.addSpacing(10)

        self.btn_backup = self._nav_button("Создать резервную копию")
        self.btn_restore = self._nav_button("Восстановление системы")
        self.btn_config = self._nav_button("Настройки")
        self.btn_logs = self._nav_button("Логи и отчёты")
        self.btn_news = self._nav_button("Новости и обновления")

        left_layout.addWidget(self.btn_backup)
        left_layout.addWidget(self.btn_restore)
        left_layout.addWidget(self.btn_config)
        left_layout.addWidget(self.btn_logs)
        left_layout.addSpacing(10)
        left_layout.addWidget(self.btn_news)
        left_layout.addStretch()

        neon_hint = QLabel("Neon • Glass • Rockfeller Design")
        neon_hint.setStyleSheet("color: #7AD7FF; font-size: 11px;")
        left_layout.addWidget(neon_hint)

        # RIGHT PANEL (content)
        right_panel = QFrame()
        right_panel.setObjectName("rightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(22, 22, 22, 22)
        right_layout.setSpacing(16)

        header_row = QHBoxLayout()
        header_title = QLabel("Обзор системы")
        header_title.setStyleSheet("""
            color: #F9FAFB;
            font-size: 20px;
            font-weight: 600;
        """)
        header_row.addWidget(header_title)

        header_row.addStretch()

        self.btn_check_updates = QPushButton("Проверить обновления")
        self.btn_check_updates.setObjectName("primaryButton")
        self.btn_check_updates.setCursor(Qt.CursorShape.PointingHandCursor)
        header_row.addWidget(self.btn_check_updates)

        right_layout.addLayout(header_row)

        info = QLabel(
            f"Rockfeller System Restore {APP_VERSION}\n\n"
            "Скоро здесь будет:\n"
            "• Полная копия системы (rootfs, конфиги, boot)\n"
            "• Планировщик резервных копий\n"
            "• Восстановление из образа в 1 клик\n"
            "• Экспорт настроек и профилей\n"
            "• Отчёты и логирование операций"
        )
        info.setStyleSheet("""
            color: #D0D3DE;
            font-size: 13px;
        """)
        info.setWordWrap(True)

        right_layout.addWidget(info)
        right_layout.addStretch()

        root_layout.addWidget(left_panel, 1)
        root_layout.addWidget(right_panel, 3)

        # wiring
        self.btn_check_updates.clicked.connect(self._on_check_updates_clicked)
        self.btn_news.clicked.connect(self._on_open_news)

    def _nav_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(40)
        btn.setObjectName("navButton")
        return btn

    def _apply_style(self):
        self.setStyleSheet("""
        QMainWindow {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #05070B,
                stop:1 #020308
            );
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
            padding: 6px 12px;
            text-align: left;
            font-size: 13px;
        }

        QPushButton#navButton:hover {
            border-color: #7AD7FF;
            background: rgba(30, 40, 60, 0.95);
        }

        QPushButton#navButton:pressed {
            background: rgba(12, 16, 26, 0.95);
        }

        QPushButton#primaryButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #FFB347,
                stop:1 #FF6B6B
            );
            color: #050608;
            border-radius: 18px;
            padding: 8px 18px;
            font-size: 13px;
            font-weight: 600;
            border: 0px;
        }
        """)

    # ---------- Tray ----------
    def _init_tray(self):
        icon_file = resource_path("RSR_256.png")
        icon = QIcon(icon_file) if os.path.exists(icon_file) else self.windowIcon()

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Rockfeller System Restore")

        menu = QMenu()

        action_open = menu.addAction("Открыть панель RSR")
        action_open.triggered.connect(self._on_tray_open)

        action_check = menu.addAction("Проверить обновления")
        action_check.triggered.connect(self._on_check_updates_clicked)

        menu.addSeparator()

        action_quit = menu.addAction("Выход")
        action_quit.triggered.connect(self._on_tray_quit)

        self.tray.setContextMenu(menu)
        self.tray.show()

    # ---------- Pulse effect ----------
    def _init_pulse(self):
        self._pulse_state = 0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._update_pulse)
        self._pulse_timer.start(900)

    def _update_pulse(self):
        # Light pulse on the "Check updates" button
        self._pulse_state = (self._pulse_state + 1) % 2
        if self._pulse_state == 0:
            self.btn_check_updates.setStyleSheet("""
                QPushButton#primaryButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #FFB347,
                        stop:1 #FF6B6B
                    );
                    color: #050608;
                    border-radius: 18px;
                    padding: 8px 18px;
                    font-size: 13px;
                    font-weight: 600;
                    border: 0px;
                }
            """)
        else:
            self.btn_check_updates.setStyleSheet("""
                QPushButton#primaryButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #FFE08A,
                        stop:1 #FF8C6B
                    );
                    color: #050608;
                    border-radius: 18px;
                    padding: 8px 18px;
                    font-size: 13px;
                    font-weight: 600;
                    border: 0px;
                }
            """)

    # ---------- Handlers ----------
    def _on_tray_open(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_quit(self):
        QApplication.quit()

    def _on_check_updates_clicked(self):
        # Пока заглушка — позже подключим latest.json с GitHub Pages
        if hasattr(self, "tray") and self.tray:
            self.tray.showMessage(
                "RSR Update",
                "Проверка обновлений (заглушка).\n"
                "Дальше подключим latest.json на GitHub Pages.",
                QSystemTrayIcon.MessageIcon.Information
            )

    def _on_open_news(self):
        if hasattr(self, "tray") and self.tray:
            self.tray.showMessage(
                "RSR • Новости",
                "В следующих версиях здесь будет лента изменений RSR.",
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

    def open_main():
        splash.close()
        win = MainWindow()
        win.show()
        # keep ref
        app._main_win = win

    QTimer.singleShot(1800, open_main)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
