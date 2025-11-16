#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RSR — Rockfeller System Restore
Версия: 1.2.1

Функционал:
- Создать бэкап домашней папки в ~/RSR_backups/*.tar.gz
- Открыть папку с бэкапами
- Тестовое восстановление бэкапа в отдельную папку (НЕ перетирает систему)
- Проверка обновлений на GitHub
- Трей-иконка + меню

Стиль: тёмный фон, неон, стекло.
Используется PyQt6.
"""

from __future__ import annotations

import sys
import os
import tarfile
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QMovie, QAction
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QMessageBox,
    QFileDialog,
    QProgressBar,
    QSystemTrayIcon,
    QMenu,
)


APP_VERSION = "1.2.1"
GITHUB_REPO = "fate-company/RSR"


BASE_DIR = Path(__file__).resolve().parent
ICON_DIR = BASE_DIR / "icons"
BACKUP_DIR = Path.home() / "RSR_backups"
RESTORE_TEST_DIR = Path.home() / "RSR_restore_test"


# ---------- Рабочие воркеры в отдельных потоках ----------


class WorkerThread(QThread):
    """Простой воркер: выполняет callable в отдельном потоке."""

    started_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str, str)  # success, title, message

    def __init__(self, fn, description: str):
        super().__init__()
        self.fn = fn
        self.description = description

    def run(self):
        self.started_signal.emit(self.description)
        try:
            result_msg = self.fn()
            if not isinstance(result_msg, str):
                result_msg = "Готово."
            self.finished_signal.emit(True, "Готово", result_msg)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.finished_signal.emit(
                False,
                "Ошибка",
                f"{self.description}\n\n{e}",
            )


# ---------- Основное окно приложения ----------


class RSRWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"RSR — Rockfeller System Restore {APP_VERSION}")
        self.setMinimumSize(880, 520)
        self.setWindowIcon(self._load_icon("RSR_256.png", "RSR.svg"))

        # Трей
        self.tray_icon = None
        self._init_tray()

        # UI
        self._init_ui()

        # Текущий воркер
        self.current_worker: WorkerThread | None = None

    # ----- helpers -----

    @staticmethod
    def _load_icon(*names: str) -> QIcon:
        for name in names:
            p = ICON_DIR / name
            if p.is_file():
                return QIcon(str(p))
        return QIcon()

    # ----- UI -----

    def _init_ui(self):
        # Стеклянная центральная панель
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(16)

        title_label = QLabel("Rockfeller System Restore")
        title_label.setObjectName("TitleLabel")

        subtitle_label = QLabel("Быстрые резервные копии и восстановление\n"
                                "в фирменном стиле Rockfeller (неон + стекло).")
        subtitle_label.setObjectName("SubtitleLabel")
        subtitle_label.setWordWrap(True)

        header_box = QVBoxLayout()
        header_box.addWidget(title_label)
        header_box.addWidget(subtitle_label)

        # Стеклянный блок с кнопками
        glass_frame = QFrame()
        glass_frame.setObjectName("GlassFrame")
        glass_layout = QVBoxLayout(glass_frame)
        glass_layout.setContentsMargins(24, 24, 24, 24)
        glass_layout.setSpacing(16)

        # Ряд 1: бэкап
        row1 = QHBoxLayout()
        self.btn_backup_home = QPushButton("Создать бэкап домашней папки")
        self.btn_backup_home.clicked.connect(self.on_backup_home)

        self.btn_open_backups = QPushButton("Открыть папку с бэкапами")
        self.btn_open_backups.clicked.connect(self.on_open_backups)

        row1.addWidget(self.btn_backup_home)
        row1.addWidget(self.btn_open_backups)

        # Ряд 2: восстановление (тестовое)
        row2 = QHBoxLayout()
        self.btn_restore_test = QPushButton("Тестовое восстановление в отдельную папку")
        self.btn_restore_test.clicked.connect(self.on_restore_test)

        self.btn_choose_backup = QPushButton("Выбрать .tar.gz бэкап…")
        self.btn_choose_backup.clicked.connect(self.on_choose_backup_for_restore)

        row2.addWidget(self.btn_restore_test)
        row2.addWidget(self.btn_choose_backup)

        # Ряд 3: обновления и инфо
        row3 = QHBoxLayout()
        self.btn_check_updates = QPushButton("Проверить обновления")
        self.btn_check_updates.clicked.connect(self.on_check_updates)

        self.btn_about = QPushButton("О программе")
        self.btn_about.clicked.connect(self.on_about)

        row3.addWidget(self.btn_check_updates)
        row3.addWidget(self.btn_about)

        # Прогресс/статус
        self.status_label = QLabel("Готово.")
        self.status_label.setObjectName("StatusLabel")

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setObjectName("ProgressBar")

        # Анимированный лоадер
        self.loader_label = QLabel()
        self.loader_label.setFixedSize(32, 32)
        loader_gif = ICON_DIR / "RSR_loader.gif"
        if loader_gif.is_file():
            self.loader_movie = QMovie(str(loader_gif))
            self.loader_label.setMovie(self.loader_movie)
        else:
            self.loader_movie = None
        self.loader_label.setVisible(False)

        footer_row = QHBoxLayout()
        footer_row.addWidget(self.status_label)
        footer_row.addStretch()
        footer_row.addWidget(self.loader_label)
        footer_row.addWidget(self.progress_bar)

        glass_layout.addLayout(row1)
        glass_layout.addLayout(row2)
        glass_layout.addLayout(row3)
        glass_layout.addSpacing(8)
        glass_layout.addLayout(footer_row)

        root_layout.addLayout(header_box)
        root_layout.addWidget(glass_frame)

    # ----- Трей -----

    def _init_tray(self):
        tray_icon = QSystemTrayIcon(self._load_icon("RSR_256.png", "RSR.svg"), self)
        menu = QMenu()

        open_action = QAction("Открыть окно", self)
        open_action.triggered.connect(self.show_normal_from_tray)
        menu.addAction(open_action)

        backup_action = QAction("Бэкап домашней папки", self)
        backup_action.triggered.connect(self.on_backup_home)
        menu.addAction(backup_action)

        menu.addSeparator()

        quit_action = QAction("Выйти", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)

        tray_icon.setContextMenu(menu)
        tray_icon.setToolTip(f"RSR {APP_VERSION}")
        tray_icon.show()

        self.tray_icon = tray_icon

    def show_normal_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    # ----- Обработка закрытия -----

    def closeEvent(self, event):  # noqa: N802
        # сворачиваем в трей
        if self.tray_icon is not None and self.tray_icon.isVisible():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "RSR",
                "Приложение свернуто в трей. Кликните по иконке, чтобы открыть окно.",
                QSystemTrayIcon.MessageIcon.Information,
                4000,
            )
        else:
            event.accept()

    # ---------- Хелперы статуса ----------

    def _set_busy(self, text: str):
        self.status_label.setText(text)
        self.progress_bar.setRange(0, 0)  # бесконечный индикатор
        self.progress_bar.setValue(0)
        if self.loader_movie:
            self.loader_label.setVisible(True)
            self.loader_movie.start()
        self._set_buttons_enabled(False)

    def _set_idle(self, text: str = "Готово."):
        self.status_label.setText(text)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        if self.loader_movie:
            self.loader_movie.stop()
            self.loader_label.setVisible(False)
        self._set_buttons_enabled(True)

    def _set_buttons_enabled(self, enabled: bool):
        for btn in [
            self.btn_backup_home,
            self.btn_open_backups,
            self.btn_restore_test,
            self.btn_choose_backup,
            self.btn_check_updates,
            self.btn_about,
        ]:
            btn.setEnabled(enabled)

    # ---------- Действия кнопок ----------

    # 1) Бэкап домашней папки
    def on_backup_home(self):
        if self.current_worker and self.current_worker.isRunning():
            return

        def job():
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_path = BACKUP_DIR / f"home_backup_{ts}.tar.gz"

            home = Path.home()

            # Создаем tar.gz c содержимым домашней папки
            with tarfile.open(backup_path, "w:gz") as tar:
                tar.add(str(home), arcname="home")

            return f"Бэкап домашней папки создан:\n{backup_path}"

        self.current_worker = WorkerThread(job, "Создание бэкапа домашней папки…")
        self.current_worker.started_signal.connect(self._set_busy)
        self.current_worker.finished_signal.connect(self._on_worker_finished)
        self.current_worker.start()

    # 2) Открыть папку с бэкапами
    def on_open_backups(self):
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        os.system(f'xdg-open "{BACKUP_DIR}" &')

    # 3) Тестовое восстановление (в отдельную папку)
    def on_restore_test(self):
        # Выбираем архив
        backup_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите .tar.gz бэкап для тестового восстановления",
            str(BACKUP_DIR),
            "Tar GZ (*.tar.gz);;Все файлы (*)",
        )
        if not backup_path:
            return

        backup_path = Path(backup_path)

        if self.current_worker and self.current_worker.isRunning():
            return

        def job():
            if not backup_path.is_file():
                raise FileNotFoundError(f"Файл не найден: {backup_path}")

            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            target_dir = RESTORE_TEST_DIR / f"restore_{ts}"
            target_dir.mkdir(parents=True, exist_ok=False)

            with tarfile.open(backup_path, "r:gz") as tar:
                tar.extractall(path=target_dir)

            return (
                "Тестовое восстановление выполнено.\n"
                "Файлы распакованы в отдельную папку (система не перезаписывалась):\n"
                f"{target_dir}"
            )

        self.current_worker = WorkerThread(job, "Тестовое восстановление…")
        self.current_worker.started_signal.connect(self._set_busy)
        self.current_worker.finished_signal.connect(self._on_worker_finished)
        self.current_worker.start()

    # 4) Выбор бэкапа → сразу тестовое восстановление
    def on_choose_backup_for_restore(self):
        self.on_restore_test()

    # 5) Проверка обновлений
    def on_check_updates(self):
        if self.current_worker and self.current_worker.isRunning():
            return

        def job():
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = Request(api_url, headers={"User-Agent": "RSR-Client"})
            try:
                with urlopen(req, timeout=10) as resp:  # noqa: S310
                    import json

                    data = json.loads(resp.read().decode("utf-8"))
                    latest_tag = data.get("tag_name", "").lstrip("v")
            except (URLError, HTTPError) as e:
                raise RuntimeError(f"Не удалось получить данные с GitHub: {e}") from e

            if not latest_tag:
                raise RuntimeError("Не удалось определить последнюю версию.")

            if latest_tag == APP_VERSION:
                return f"Установлена актуальная версия RSR ({APP_VERSION})."
            else:
                return (
                    f"Доступна новая версия RSR: {latest_tag}\n"
                    f"Установлена версия: {APP_VERSION}\n\n"
                    "Скачать обновление можно по ссылке:\n"
                    "https://github.com/fate-company/RSR/releases/latest"
                )

        self.current_worker = WorkerThread(job, "Проверка обновлений…")
        self.current_worker.started_signal.connect(self._set_busy)
        self.current_worker.finished_signal.connect(self._on_worker_finished)
        self.current_worker.start()

    # 6) О программе
    def on_about(self):
        QMessageBox.information(
            self,
            "О программе",
            (
                f"RSR — Rockfeller System Restore\n"
                f"Версия: {APP_VERSION}\n\n"
                "• Бэкап домашней папки в tar.gz\n"
                "• Тестовое восстановление в отдельную папку\n"
                "• Проверка обновлений с GitHub\n\n"
                "Автор: Rockfeller (Fateveli).\n"
                "Проект: https://github.com/fate-company/RSR"
            ),
        )

    # ----- обработка завершения воркеров -----

    def _on_worker_finished(self, success: bool, title: str, message: str):
        if success:
            self._set_idle(message)
        else:
            self._set_idle("Готово (с ошибкой).")
        QMessageBox.information(self, title, message)


# ---------- Стиль (неон + стекло) ----------


def apply_rockfeller_style(app: QApplication):
    app.setStyle("Fusion")
    app.setFont(app.font())  # на всякий случай

    qss = """
    QWidget {
        background-color: #050813;
        color: #E5E5F0;
        font-family: "SF Pro Text", "Segoe UI", "Ubuntu", sans-serif;
        font-size: 14px;
    }

    #TitleLabel {
        font-size: 26px;
        font-weight: 700;
        color: #FDD66B;
    }

    #SubtitleLabel {
        font-size: 14px;
        color: #9BA4C8;
    }

    #GlassFrame {
        background: rgba(15, 20, 40, 0.82);
        border-radius: 18px;
        border: 1px solid rgba(120, 180, 255, 0.5);
        box-shadow: 0 0 24px rgba(0, 180, 255, 0.35);
    }

    QPushButton {
        background-color: rgba(12, 22, 46, 0.9);
        border: 1px solid rgba(132, 196, 255, 0.7);
        border-radius: 10px;
        padding: 10px 18px;
        color: #E5ECFF;
        font-weight: 500;
    }
    QPushButton:hover {
        background-color: rgba(26, 44, 90, 0.95);
        border-color: #51C8FF;
        box-shadow: 0 0 18px rgba(81, 200, 255, 0.7);
    }
    QPushButton:pressed {
        background-color: rgba(10, 18, 38, 0.95);
        border-color: #FF6B6B;
    }
    QPushButton:disabled {
        background-color: rgba(10, 16, 30, 0.7);
        color: #555E80;
        border-color: rgba(60, 70, 90, 0.7);
    }

    #StatusLabel {
        color: #9BA4C8;
        font-size: 13px;
    }

    #ProgressBar {
        background-color: rgba(5, 8, 20, 0.0);
        border: 1px solid rgba(80, 110, 160, 0.7);
        border-radius: 8px;
        height: 10px;
    }
    #ProgressBar::chunk {
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 #24C4FF,
            stop:0.5 #FF6B6B,
            stop:1 #FFE06B
        );
        border-radius: 8px;
    }

    QToolTip {
        background-color: rgba(10, 16, 30, 0.95);
        color: #E5ECFF;
        border: 1px solid #51C8FF;
        padding: 4px 8px;
        border-radius: 6px;
    }
    """
    app.setStyleSheet(qss)


# ---------- entry point ----------


def main():
    # Для Wayland/Tray иногда помогает этот флаг
    os.environ.setdefault("QT_QPA_PLATFORM", "wayland,xcb")

    app = QApplication(sys.argv)
    apply_rockfeller_style(app)

    window = RSRWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
