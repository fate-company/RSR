import os
import sys
import tarfile
import traceback
import urllib.request
import json
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QFileDialog,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QSpacerItem,
)

APP_VERSION = "1.2.1"
GITHUB_LATEST_JSON = (
    "https://raw.githubusercontent.com/fate-company/RSR/main/latest.json"
)

# ----------------------------------------------------------------------
#   Вспомогательные функции
# ----------------------------------------------------------------------


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def human_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def backup_dir() -> str:
    # Папка с бэкапами (универсально, но фактически ~/RSR_backups)
    return os.path.expanduser("~/RSR_backups")


def test_restore_base_dir() -> str:
    return os.path.expanduser("~/RSR_test_restore")


EXCLUDED_DIRS = (
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/tmp",
    "/mnt",
    "/media",
    "/lost+found",
    "/var/tmp",
    "/var/run",
)


# ----------------------------------------------------------------------
#   Поток бэкапа
# ----------------------------------------------------------------------


class BackupWorker(QThread):
    progress_changed = Signal(int)  # 0-100
    log_message = Signal(str)
    finished = Signal(bool, str)  # success, message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self._do_backup()
        except Exception as e:  # noqa: BLE001
            tb = traceback.format_exc()
            self.log_message.emit(f"[{human_ts()}] Критическая ошибка: {e}")
            self.log_message.emit(tb)
            self.finished.emit(False, f"Ошибка при создании бэкапа: {e}")

    # Основная логика бэкапа
    def _do_backup(self):
        root = "/"
        dest_root = backup_dir()
        ensure_dir(dest_root)

        ts_name = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_file = os.path.join(dest_root, f"rsr_full_{ts_name}.tar.gz")

        self.log_message.emit(
            f"[{human_ts()}] Старт полного бэкапа системы '/' -> {dest_file}"
        )
        self.progress_changed.emit(0)

        # 1. Собираем список файлов
        self.log_message.emit(
            f"[{human_ts()}] Подготовка списка файлов (это может занять время)..."
        )
        all_files = []
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            if self._cancelled:
                self.finished.emit(False, "Бэкап отменён")
                return

            # Фильтруем исключённые директории
            abs_dirpath = os.path.abspath(dirpath)
            for ex in EXCLUDED_DIRS:
                if abs_dirpath == ex or abs_dirpath.startswith(ex + os.sep):
                    dirnames[:] = []
                    filenames[:] = []
                    break

            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                all_files.append(full_path)

        total = len(all_files)
        if total == 0:
            self.finished.emit(False, "Не найдено файлов для бэкапа.")
            return

        self.log_message.emit(
            f"[{human_ts()}] Всего файлов для архивации: {total}"
        )

        # 2. Создаём tar.gz
        added = 0
        with tarfile.open(dest_file, "w:gz") as tar:
            for idx, full_path in enumerate(all_files, start=1):
                if self._cancelled:
                    self.finished.emit(False, "Бэкап отменён")
                    return

                # отрезаем ведущий / чтобы внутри архива не было пустого элемента
                arcname = full_path.lstrip(os.sep)

                try:
                    tar.add(full_path, arcname=arcname, recursive=False)
                    added += 1
                except PermissionError:
                    self.log_message.emit(
                        f"[{human_ts()}] Пропуск (нет доступа): {full_path}"
                    )
                except FileNotFoundError:
                    # Файл мог исчезнуть между сканированием и добавлением
                    self.log_message.emit(
                        f"[{human_ts()}] Пропуск (файл исчез): {full_path}"
                    )
                except Exception as e:  # noqa: BLE001
                    self.log_message.emit(
                        f"[{human_ts()}] Пропуск {full_path}: {e}"
                    )

                # прогресс
                if idx % 50 == 0 or idx == total:
                    percent = int(idx * 100 / total)
                    self.progress_changed.emit(percent)

        self.progress_changed.emit(100)
        self.log_message.emit(
            f"[{human_ts()}] Бэкап завершён. Добавлено файлов: {added}"
        )
        self.finished.emit(True, f"Полный бэкап создан:\n{dest_file}")


# ----------------------------------------------------------------------
#   Поток восстановления
# ----------------------------------------------------------------------


class RestoreWorker(QThread):
    progress_changed = Signal(int)
    log_message = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, archive_path: str, extract_dir: str, parent=None):
        super().__init__(parent)
        self.archive_path = archive_path
        self.extract_dir = extract_dir
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self._do_restore()
        except Exception as e:  # noqa: BLE001
            tb = traceback.format_exc()
            self.log_message.emit(f"[{human_ts()}] Критическая ошибка: {e}")
            self.log_message.emit(tb)
            self.finished.emit(False, f"Ошибка при восстановлении: {e}")

    def _do_restore(self):
        self.log_message.emit(
            f"[{human_ts()}] Старт тестового восстановления "
            f"{self.archive_path} -> {self.extract_dir}"
        )
        ensure_dir(self.extract_dir)

        with tarfile.open(self.archive_path, "r:gz") as tar:
            members = tar.getmembers()
            total = len(members)
            if total == 0:
                self.finished.emit(False, "Архив пустой.")
                return

            for idx, member in enumerate(members, start=1):
                if self._cancelled:
                    self.finished.emit(False, "Восстановление отменено")
                    return

                try:
                    tar.extract(member, path=self.extract_dir)
                except PermissionError:
                    self.log_message.emit(
                        f"[{human_ts()}] Пропуск (нет доступа): {member.name}"
                    )
                except Exception as e:  # noqa: BLE001
                    self.log_message.emit(
                        f"[{human_ts()}] Пропуск {member.name}: {e}"
                    )

                if idx % 50 == 0 or idx == total:
                    percent = int(idx * 100 / total)
                    self.progress_changed.emit(percent)

        self.progress_changed.emit(100)
        self.log_message.emit(
            f"[{human_ts()}] Тестовое восстановление завершено."
        )
        self.finished.emit(
            True,
            f"Тестовое восстановление завершено.\nКаталог: {self.extract_dir}",
        )


# ----------------------------------------------------------------------
#   Основное окно
# ----------------------------------------------------------------------


class RSRWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"RSR — Rockfeller System Restore {APP_VERSION}")
        self.setWindowIcon(self._load_icon())
        self.resize(960, 560)

        self.backup_worker: BackupWorker | None = None
        self.restore_worker: RestoreWorker | None = None

        self._build_ui()
        self._apply_style()
        self._setup_neon_line_animation()

    # ---------------- UI ----------------

    def _load_icon(self) -> QIcon:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_dir, "icons", "RSR_256.png")
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # Неоновая линия (прогресс-анимация состояния)
        self.neon_line = QProgressBar()
        self.neon_line.setTextVisible(False)
        self.neon_line.setRange(0, 0)  # indeterminate
        self.neon_line.setFixedHeight(4)
        main_layout.addWidget(self.neon_line)

        # Заголовок
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        title_label = QLabel("Rockfeller System Restore")
        title_label.setObjectName("TitleLabel")
        title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        subtitle_label = QLabel("Pro Edition · full system backup")
        subtitle_label.setObjectName("SubtitleLabel")

        title_block = QVBoxLayout()
        title_block.addWidget(title_label)
        title_block.addWidget(subtitle_label)

        header_layout.addLayout(title_block)
        header_layout.addStretch()

        version_label = QLabel(f"v{APP_VERSION}")
        version_label.setObjectName("VersionLabel")
        header_layout.addWidget(version_label)

        main_layout.addLayout(header_layout)

        # Центральная панель: кнопки слева, логи справа
        center_layout = QHBoxLayout()
        center_layout.setSpacing(16)

        # Левая колонка с кнопками
        left_panel = QVBoxLayout()
        left_panel.setSpacing(12)

        self.btn_full_backup = QPushButton("Создать полный бэкап системы")
        self.btn_full_backup.clicked.connect(self.on_full_backup_clicked)
        self.btn_full_backup.setObjectName("PrimaryButton")

        self.btn_restore_test = QPushButton("Тестовое восстановление в папку")
        self.btn_restore_test.clicked.connect(self.on_restore_test_clicked)
        self.btn_restore_test.setObjectName("SecondaryButton")

        self.btn_check_updates = QPushButton("Проверить обновления")
        self.btn_check_updates.clicked.connect(self.on_check_updates_clicked)
        self.btn_check_updates.setObjectName("SecondaryButton")

        self.btn_about = QPushButton("О программе")
        self.btn_about.clicked.connect(self.on_about_clicked)
        self.btn_about.setObjectName("GhostButton")

        left_panel.addWidget(self.btn_full_backup)
        left_panel.addWidget(self.btn_restore_test)
        left_panel.addSpacing(8)
        left_panel.addWidget(self.btn_check_updates)
        left_panel.addWidget(self.btn_about)
        left_panel.addItem(
            QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        )

        # Правая стеклянная панель для логов
        logs_block = QVBoxLayout()
        logs_title = QLabel("Логи операций")
        logs_title.setObjectName("LogsTitle")

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("LogView")

        logs_block.addWidget(logs_title)
        logs_block.addWidget(self.log_view)

        # Оборачиваем правую панель в виджет, чтобы к нему применить стеклянный стиль
        logs_container = QWidget()
        logs_container.setObjectName("LogsContainer")
        logs_container.setLayout(logs_block)

        center_layout.addLayout(left_panel, 1)
        center_layout.addWidget(logs_container, 2)

        main_layout.addLayout(center_layout)

        # Нижняя строка: прогресс + статус
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(12)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")

        self.status_label = QLabel("Готово.")
        self.status_label.setObjectName("StatusLabel")

        bottom_layout.addWidget(self.progress_bar, 2)
        bottom_layout.addWidget(self.status_label, 1)

        main_layout.addLayout(bottom_layout)

    def _apply_style(self):
        # Базовый шрифт
        font = QFont()
        font.setPointSize(10)
        self.setFont(font)

        # Тёмный металлический + неон
        self.setStyleSheet(
            """
            QWidget {
                background-color: #05060a;
                color: #e8edf5;
            }

            #TitleLabel {
                font-size: 22px;
                font-weight: 600;
                letter-spacing: 0.5px;
            }

            #SubtitleLabel {
                font-size: 11px;
                color: #9aa4c0;
            }

            #VersionLabel {
                padding: 4px 10px;
                border-radius: 8px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1c2738,
                    stop:1 #101522
                );
                color: #a6c9ff;
                border: 1px solid rgba(120, 170, 255, 0.6);
            }

            QPushButton {
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 13px;
                border: 1px solid rgba(140, 160, 200, 0.35);
                background-color: rgba(18, 23, 35, 0.96);
                color: #e8edf5;
            }
            QPushButton:hover {
                border-color: rgba(180, 220, 255, 0.9);
                background-color: rgba(26, 34, 52, 0.98);
            }
            QPushButton:pressed {
                background-color: rgba(12, 15, 25, 1.0);
            }
            QPushButton:disabled {
                color: #6f7a90;
                border-color: rgba(80, 90, 110, 0.7);
                background-color: rgba(15, 19, 28, 0.9);
            }

            QPushButton#PrimaryButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1c4272,
                    stop:0.5 #2f6fb0,
                    stop:1 #1c4272
                );
                border: 1px solid rgba(190, 230, 255, 0.95);
                color: #f6fbff;
                font-weight: 600;
                box-shadow: 0 0 16px rgba(120, 190, 255, 0.6);
            }
            QPushButton#PrimaryButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #245287,
                    stop:0.5 #3f86cb,
                    stop:1 #245287
                );
            }

            QPushButton#SecondaryButton {
                border: 1px solid rgba(160, 190, 255, 0.5);
                background-color: rgba(18, 23, 38, 0.96);
            }

            QPushButton#GhostButton {
                border: 1px dashed rgba(160, 190, 255, 0.5);
                background-color: transparent;
                color: #aab5d0;
            }
            QPushButton#GhostButton:hover {
                background-color: rgba(30, 38, 60, 0.8);
                color: #dde7ff;
            }

            QPlainTextEdit#LogView {
                background: rgba(7, 9, 15, 0.86);
                border-radius: 14px;
                padding: 8px 10px;
                border: 1px solid rgba(80, 95, 130, 0.85);
                font-family: "JetBrains Mono", "Fira Code", monospace;
                font-size: 11px;
            }

            QLabel#LogsTitle {
                font-size: 12px;
                color: #a9b4d2;
                margin-bottom: 4px;
            }

            QWidget#LogsContainer {
                border-radius: 20px;
                background: qradialgradient(
                    cx:0.2, cy:0.0, radius:1.2,
                    fx:0.2, fy:0.0,
                    stop:0 rgba(120, 180, 255, 0.25),
                    stop:0.4 rgba(26, 31, 50, 0.96),
                    stop:1 rgba(11, 13, 22, 0.98)
                );
                border: 1px solid rgba(110, 130, 170, 0.85);
            }

            QProgressBar {
                background-color: rgba(10, 13, 20, 0.9);
                border-radius: 10px;
                border: 1px solid rgba(70, 90, 130, 0.9);
                text-align: center;
                color: #d0e2ff;
                font-size: 11px;
            }
            QProgressBar::chunk {
                border-radius: 9px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #c04060,
                    stop:0.5 #f06292,
                    stop:1 #a4d3ff
                );
            }

            #StatusLabel {
                font-size: 11px;
                color: #8f9ab8;
            }

            QProgressBar#neonLine {
                border: none;
                border-radius: 0px;
                background: transparent;
            }
            """
        )

        # Дополнительный стиль отдельно для неоновой линии
        self.neon_line.setObjectName("neonLine")
        self.neon_line.setStyleSheet(
            """
            QProgressBar#neonLine {
                border: none;
                background-color: transparent;
            }
            QProgressBar#neonLine::chunk {
                border-radius: 3px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff4b6e,
                    stop:0.5 #ffc94b,
                    stop:1 #4fd1ff
                );
            }
            """
        )

    def _setup_neon_line_animation(self):
        # Небольшой трюк: раз в N мс меняем value, чтобы добиться эффекта “бегущей линии”
        self._neon_step = 0
        self._neon_timer = QTimer(self)
        self._neon_timer.timeout.connect(self._advance_neon)
        self._neon_timer.start(60)

    @Slot()
    def _advance_neon(self):
        # Просто бегущий прогресс 0–100
        self._neon_step = (self._neon_step + 2) % 100
        self.neon_line.setRange(0, 100)
        self.neon_line.setValue(self._neon_step)

    # ---------------- Логика кнопок ----------------

    def _set_busy(self, busy: bool, text: str | None = None):
        for btn in (
            self.btn_full_backup,
            self.btn_restore_test,
            self.btn_check_updates,
            self.btn_about,
        ):
            btn.setDisabled(busy)
        if text:
            self.status_label.setText(text)
        else:
            self.status_label.setText("Готово.")

    def log(self, msg: str):
        self.log_view.appendPlainText(msg)
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    # --- Бэкап ---

    @Slot()
    def on_full_backup_clicked(self):
        if self.backup_worker is not None and self.backup_worker.isRunning():
            QMessageBox.warning(
                self,
                "RSR",
                "Бэкап уже выполняется.",
            )
            return

        # Проверим/создадим папку бэкапов
        dest_root = backup_dir()
        try:
            ensure_dir(dest_root)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(
                self,
                "RSR",
                f"Не удалось создать папку для бэкапов:\n{dest_root}\n\n{e}",
            )
            return

        self.progress_bar.setValue(0)
        self.log(f"[{human_ts()}] ----------------------------")
        self.backup_worker = BackupWorker()
        self.backup_worker.progress_changed.connect(self._on_backup_progress)
        self.backup_worker.log_message.connect(self.log)
        self.backup_worker.finished.connect(self._on_backup_finished)
        self.backup_worker.start()
        self._set_busy(True, "Создание полного бэкапа системы...")

    @Slot(int)
    def _on_backup_progress(self, value: int):
        self.progress_bar.setValue(value)

    @Slot(bool, str)
    def _on_backup_finished(self, success: bool, message: str):
        self._set_busy(False)
        self.log(f"[{human_ts()}] Завершение бэкапа: {message}")
        QMessageBox.information(
            self,
            "RSR — Бэкап системы",
            message,
        )

    # --- Тестовое восстановление ---

    @Slot()
    def on_restore_test_clicked(self):
        if (
            self.restore_worker is not None
            and self.restore_worker.isRunning()
        ):
            QMessageBox.warning(
                self,
                "RSR",
                "Восстановление уже выполняется.",
            )
            return

        archive_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите архив бэкапа (.tar.gz)",
            backup_dir(),
            "Архивы RSR (*.tar.gz);;Все файлы (*)",
        )
        if not archive_path:
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_dir = test_restore_base_dir()
        extract_dir = os.path.join(base_dir, f"RSR_test_{ts}")

        self.progress_bar.setValue(0)
        self.log(f"[{human_ts()}] ----------------------------")
        self.restore_worker = RestoreWorker(archive_path, extract_dir)
        self.restore_worker.progress_changed.connect(
            self._on_restore_progress
        )
        self.restore_worker.log_message.connect(self.log)
        self.restore_worker.finished.connect(self._on_restore_finished)
        self.restore_worker.start()
        self._set_busy(True, "Тестовое восстановление...")

    @Slot(int)
    def _on_restore_progress(self, value: int):
        self.progress_bar.setValue(value)

    @Slot(bool, str)
    def _on_restore_finished(self, success: bool, message: str):
        self._set_busy(False)
        self.log(f"[{human_ts()}] Завершение восстановления: {message}")
        QMessageBox.information(
            self,
            "RSR — Тестовое восстановление",
            message,
        )

    # --- Проверка обновлений ---

    @Slot()
    def on_check_updates_clicked(self):
        self._set_busy(True, "Проверка обновлений...")
        self.log(f"[{human_ts()}] Проверка обновлений...")

        def done(msg: str):
            self._set_busy(False)
            self.log(f"[{human_ts()}] {msg}")
            QMessageBox.information(self, "Проверка обновлений", msg)

        try:
            with urllib.request.urlopen(GITHUB_LATEST_JSON, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latest = str(data.get("version", "")).strip()
            if not latest:
                done("Не удалось определить последнюю версию.")
                return

            if latest == APP_VERSION:
                done(f"У вас установлена актуальная версия: {APP_VERSION}")
            else:
                url = data.get("download_url", "")
                msg = (
                    f"Доступна новая версия: {latest}\n"
                    f"Текущая: {APP_VERSION}\n\n"
                )
                if url:
                    msg += f"Скачать можно по ссылке:\n{url}"
                else:
                    msg += "Откройте страницу проекта на GitHub."
                done(msg)
        except Exception as e:  # noqa: BLE001
            done(f"Ошибка при проверке обновлений: {e}")

    # --- О программе ---

    @Slot()
    def on_about_clicked(self):
        text = (
            f"<b>Rockfeller System Restore</b> v{APP_VERSION}<br><br>"
            "Инструмент для бэкапа и тестового восстановления системы "
            "в фирменном стиле Rockfeller (неон + стекло).<br><br>"
            "• Полный бэкап / в tar.gz<br>"
            "• Тестовое восстановление в отдельную папку<br>"
            "• Логи и прогресс-бар<br><br>"
            "Автор идеи: Alexey (Rockfeller)<br>"
            "UI/код: RSR Pro Edition"
        )
        QMessageBox.information(self, "О программе RSR", text)


# ----------------------------------------------------------------------
#   Точка входа
# ----------------------------------------------------------------------


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RSR — Rockfeller System Restore")
    window = RSRWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

