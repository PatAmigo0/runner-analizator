# type: ignore

import os

import cv2
from PySide2.QtCore import Qt
from PySide2.QtGui import QKeySequence, QShowEvent
from PySide2.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from utils import apply_dark_title_bar, create_dark_msg_box, normalize_key

DIALOG_STYLESHEET = """
    QDialog { 
        background-color: #1e1e1e; 
        color: #f0f0f0; 
        font-family: Segoe UI; 
        font-size: 14px; 
    }
    QLabel { 
        color: #e0e0e0; 
    }
    QGroupBox { 
        border: 1px solid #444; 
        margin-top: 22px; 
        font-weight: bold; 
        border-radius: 4px; 
        padding-top: 35px; 
        background-color: #252526;
    }
    QGroupBox::title { 
        subcontrol-origin: margin; 
        subcontrol-position: top left; 
        padding: 0 5px; 
        left: 10px; 
        top: 0px;
        background-color: #252526;
        color: #0078d7;
    }
    QPushButton { 
        background-color: #3a3a3a; 
        border: 1px solid #555; 
        padding: 8px 16px; 
        color: white; 
        border-radius: 3px; 
        min-width: 70px;
        font-weight: bold;
    }
    QPushButton:hover { background-color: #505050; border-color: #777; }
    QPushButton:pressed { background-color: #0078d7; border-color: #0078d7; }
    
    QSpinBox, QComboBox, QLineEdit {
        background-color: #1e1e1e;
        color: white;
        border: 1px solid #555;
        padding: 5px;
        border-radius: 2px;
        selection-background-color: #0078d7;
    }
    QSpinBox:hover, QComboBox:hover, QLineEdit:hover {
        border-color: #0078d7;
    }
    QSpinBox::up-button, QSpinBox::down-button { 
        background: #333; 
        border: none; 
        width: 16px;
    }
    
    QComboBox::drop-down {
        border: none;
        background: #333;
        width: 20px;
    }
    QComboBox QAbstractItemView {
        background-color: #1e1e1e;
        color: white;
        border: 1px solid #555;
        selection-background-color: #0078d7;
    }

    QTableWidget {
        background-color: #252526;
        color: white;
        gridline-color: #444;
        border: 1px solid #444;
    }
    
    QHeaderView {
        background-color: #252526;
        border: none;
    }
    QHeaderView::section {
        background-color: #333;
        color: #ddd;
        padding: 4px;
        border: 1px solid #444;
        font-weight: bold;
    }
    QTableCornerButton::section {
        background-color: #333;
        border: 1px solid #444;
    }

    QCheckBox { spacing: 8px; color: #eee; }
    QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #555; background: #1e1e1e; }
    QCheckBox::indicator:checked { background: #0078d7; border-color: #0078d7; }
    
    QRadioButton { spacing: 8px; color: #eee; }
    QRadioButton::indicator { width: 18px; height: 18px; border-radius: 9px; border: 1px solid #555; background: #1e1e1e; }
    QRadioButton::indicator:checked { background: #0078d7; border-color: #0078d7; }
"""


class HotkeyEditor(QDialog):
    def __init__(self, parent, current_hotkeys):
        super().__init__(parent)
        self.setWindowTitle("Настройка горячих клавиш")
        self.resize(500, 600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        apply_dark_title_bar(self)
        self.setStyleSheet(DIALOG_STYLESHEET)
        self.hotkeys = current_hotkeys.copy()
        self.modified = False
        self.recording_key = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Действие", "Сочетание"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.doubleClicked.connect(self.start_recording)

        self.action_names = {
            "play_pause": "Старт/Пауза",
            "mark": "Поставить метку",
            "split": "Разрезать",
            "delete": "Удалить",
            "undo": "Отмена (Undo)",
            "redo": "Повтор (Redo)",
            "frame_prev": "Кадр назад",
            "frame_next": "Кадр вперед",
            "seg_prev": "Пред. отрезок",
            "seg_next": "След. отрезок",
        }

        self.refresh_table()
        layout.addWidget(self.table)

        lbl = QLabel(
            "Дважды кликните по строке, чтобы изменить клавишу.\nEsc - отмена записи."
        )
        lbl.setStyleSheet("color: #aaa; font-style: italic; margin: 5px 0;")
        layout.addWidget(lbl)

        bbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)

        for btn in bbox.buttons():
            btn.setFocusPolicy(Qt.StrongFocus)

        layout.addWidget(bbox)

    def refresh_table(self):
        self.table.setRowCount(0)
        for key_id, name in self.action_names.items():
            row = self.table.rowCount()
            self.table.insertRow(row)

            item_name = QTableWidgetItem(name)
            item_name.setData(Qt.UserRole, key_id)

            val = self.hotkeys.get(key_id, 0)
            seq = QKeySequence(val).toString(QKeySequence.NativeText)
            item_seq = QTableWidgetItem(seq)

            self.table.setItem(row, 0, item_name)
            self.table.setItem(row, 1, item_seq)

    def start_recording(self, index):
        self.recording_key = self.table.item(index.row(), 0).data(Qt.UserRole)
        self.table.item(index.row(), 1).setText("Нажмите клавишу...")
        self.grabKeyboard()

    def keyPressEvent(self, event):
        if self.recording_key:
            raw_key = event.key()
            if raw_key == Qt.Key_Escape:
                self.releaseKeyboard()
                self.refresh_table()
                self.recording_key = None
                return

            if raw_key in [Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta]:
                return

            modifiers = event.modifiers()
            key = normalize_key(raw_key)

            val = int(modifiers | key)
            self.hotkeys[self.recording_key] = val
            self.modified = True

            self.releaseKeyboard()
            self.recording_key = None
            self.refresh_table()
        else:
            super().keyPressEvent(event)


class GeneralSettingsDialog(QDialog):
    def __init__(
        self, parent, settings_manager, current_proxy_path=None, current_video_path=None
    ):
        super().__init__(parent)
        self.settings = settings_manager
        self.current_proxy_path = current_proxy_path
        self.current_video_path = current_video_path
        self.setWindowTitle("Настройки")
        self.resize(550, 750)  # Slightly taller
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        apply_dark_title_bar(self)
        self.setStyleSheet(DIALOG_STYLESHEET)

        self.delete_requested = False
        self.need_restart = False
        self.old_quality = self.settings.get("proxy_quality", 540)
        self.old_codec = self.settings.get("proxy_codec", "MJPG")
        self.old_backend = self.settings.get("video_backend", "MSMF")
        self.old_ask_proxy = self.settings.get("ask_proxy_creation", True)

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(20)

        gb_proxy = QGroupBox("Настройки Proxy (Оптимизация)")
        form = QFormLayout()
        form.setSpacing(15)
        form.setContentsMargins(15, 35, 15, 15)
        form.setLabelAlignment(Qt.AlignLeft)

        self.cb_use_proxy = QCheckBox("Использовать Proxy файлы")
        self.cb_use_proxy.setChecked(self.settings.get("use_proxy", True))
        self.cb_use_proxy.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        self.cb_use_proxy.setCursor(Qt.PointingHandCursor)
        form.addRow(self.cb_use_proxy)

        self.cb_ask_proxy = QCheckBox(
            "Показывать диалог 'Создать Proxy' при открытии видео"
        )
        self.cb_ask_proxy.setChecked(self.settings.get("ask_proxy_creation", True))
        self.cb_ask_proxy.setCursor(Qt.PointingHandCursor)
        form.addRow(self.cb_ask_proxy)

        # --- NEW PROXY LOCATION LABEL ---
        lbl_loc = QLabel("Папка хранения:")
        lbl_loc.setStyleSheet("color: #ccc;")

        self.le_path = QLineEdit(self.settings.proxies_dir)
        self.le_path.setReadOnly(True)
        self.le_path.setStyleSheet(
            "background-color: #333; color: #aaa; border: 1px solid #444;"
        )
        form.addRow(lbl_loc, self.le_path)
        # --------------------------------

        self.combo_quality = QComboBox()
        qualities = [
            ("240p", 240),
            ("360p", 360),
            ("480p", 480),
            ("540p", 540),
            ("720p", 720),
            ("1080p", 1080),
        ]

        current_q = self.settings.get("proxy_quality", 540)
        selected_idx = 3

        for i, (text, val) in enumerate(qualities):
            self.combo_quality.addItem(text, val)
            if val == current_q:
                selected_idx = i

        self.combo_quality.setCurrentIndex(selected_idx)
        form.addRow("Качество:", self.combo_quality)

        self.combo_codec = QComboBox()
        self.combo_codec.addItem("MJPG", "MJPG")
        self.combo_codec.addItem("mp4v", "mp4v")
        self.combo_codec.addItem("H.264", "avc1")
        self.combo_codec.addItem("H.265 (HEVC)", "hevc")

        curr_codec = self.settings.get("proxy_codec", "MJPG")
        idx = self.combo_codec.findData(curr_codec)
        if idx >= 0:
            self.combo_codec.setCurrentIndex(idx)
        else:
            self.combo_codec.setCurrentIndex(0)

        form.addRow("Кодек:", self.combo_codec)

        lbl_hint = QLabel(
            "MJPG: Быстрая перемотка, большой файл.\navc1/hevc: Маленький файл, нужен GPU."
        )
        lbl_hint.setStyleSheet("color: #888; font-size: 12px; margin-top: 5px;")
        form.addRow("", lbl_hint)

        gb_proxy.setLayout(form)
        main_layout.addWidget(gb_proxy)

        if self.current_proxy_path and os.path.exists(self.current_proxy_path):
            name = os.path.basename(self.current_proxy_path)
            btn_del = QPushButton("Удалить прокси для тек. видео")
            btn_del.setToolTip(f"Файл: {name}")
            btn_del.setStyleSheet("""
                QPushButton { background-color: #4a1010; border: 1px solid #700; color: #ffcccc; }
                QPushButton:hover { background-color: #700000; border-color: #f00; }
            """)
            btn_del.clicked.connect(self.request_delete)
            btn_del.setFocusPolicy(Qt.StrongFocus)
            main_layout.addWidget(btn_del)

        btn_clear_all = QPushButton("Очистить папку Proxies (Все файлы)")
        btn_clear_all.clicked.connect(self.clear_all_proxies)
        btn_clear_all.setFocusPolicy(Qt.StrongFocus)
        main_layout.addWidget(btn_clear_all)

        gb_perf = QGroupBox("Движок и Производительность")
        form2 = QFormLayout()
        form2.setSpacing(15)
        form2.setContentsMargins(15, 35, 15, 15)

        self.spin_cache = QSpinBox()
        self.spin_cache.setRange(10, 1000)
        self.spin_cache.setValue(self.settings.get("cache_size", 100))
        self.spin_cache.setMinimumWidth(120)
        form2.addRow("Размер кэша (кадров):", self.spin_cache)

        self.cb_gpu = QCheckBox("Использовать аппаратное ускорение (GPU)")
        self.cb_gpu.setChecked(self.settings.get("use_gpu", False))
        self.cb_gpu.setCursor(Qt.PointingHandCursor)
        form2.addRow(self.cb_gpu)

        self.combo_backend = QComboBox()
        self.combo_backend.addItem("Auto", "AUTO")
        self.combo_backend.addItem("MSMF (Windows)", "MSMF")
        self.combo_backend.addItem("DirectShow", "DSHOW")
        self.combo_backend.addItem("FFmpeg", "FFMPEG")
        self.combo_backend.addItem("GStreamer", "GSTREAMER")
        self.combo_backend.addItem("Intel MFX", "INTEL_MFX")
        self.combo_backend.addItem("CUDA", "CUDA")

        curr_backend = self.settings.get("video_backend", "MSMF")
        b_idx = self.combo_backend.findData(curr_backend)
        if b_idx >= 0:
            self.combo_backend.setCurrentIndex(b_idx)
        else:
            self.combo_backend.setCurrentIndex(1)
        form2.addRow("API Видео (Backend):", self.combo_backend)

        self.combo_lookback = QComboBox()
        self.combo_lookback.addItem("Низкая (Быстро)", 5)
        self.combo_lookback.addItem("Стандартная (Баланс)", 20)
        self.combo_lookback.addItem("Высокая (Точно)", 100)

        curr_effort = self.settings.get("seek_effort", 20)
        l_idx = self.combo_lookback.findData(curr_effort)
        if l_idx >= 0:
            self.combo_lookback.setCurrentIndex(l_idx)
        else:
            self.combo_lookback.setCurrentIndex(1)
        form2.addRow("Точность поиска (MP4):", self.combo_lookback)

        gb_perf.setLayout(form2)
        main_layout.addWidget(gb_perf)

        main_layout.addStretch()

        bbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bbox.accepted.connect(self.apply_settings)
        bbox.rejected.connect(self.reject)

        for btn in bbox.buttons():
            btn.setFocusPolicy(Qt.StrongFocus)

        main_layout.addWidget(bbox)

    def clear_all_proxies(self):
        msg = create_dark_msg_box(
            self,
            "Подтверждение",
            "Вы уверены? Это удалит ВСЕ созданные ранее прокси файлы.",
            QMessageBox.Question,
            QMessageBox.Yes | QMessageBox.No,
        )
        if msg.exec_() == QMessageBox.Yes:
            try:
                main_window = self.parent()
                if main_window and hasattr(main_window, "thread"):
                    main_window.thread.full_release()
            except Exception as e:
                print(f"Could not release video before clearing: {e}")

            if self.settings.clear_all_proxies():
                msg_ok = create_dark_msg_box(
                    self, "Успех", "Папка очищена.", QMessageBox.Information
                )
                msg_ok.exec_()
                self.need_restart = True
            else:
                msg_err = create_dark_msg_box(
                    self,
                    "Ошибка",
                    "Не удалось удалить некоторые файлы.",
                    QMessageBox.Warning,
                )
                msg_err.exec_()

    def request_delete(self):
        self.delete_requested = True
        self.accept()

    def apply_settings(self):
        new_backend_str: str = self.combo_backend.currentData()
        old_backend: str = self.settings.get("video_backend", "AUTO")

        # Если меняем Backend и видео загружено - проверяем, откроется ли оно
        if (
            new_backend_str != old_backend
            and self.current_video_path
            and os.path.exists(self.current_video_path)
        ):
            # 1. Строгий маппинг строк на имена констант OpenCV
            # Мы не используем getattr с дефолтом ANY, чтобы избежать самообмана
            backend_const_name = f"CAP_{new_backend_str}"

            # Исключение для AUTO
            if new_backend_str == "AUTO":
                selected_api = cv2.CAP_ANY
            else:
                # Проверяем, существует ли такая константа в текущем cv2
                if not hasattr(cv2, backend_const_name):
                    msg = create_dark_msg_box(
                        self,
                        "Ошибка совместимости",
                        f"Ваша версия OpenCV не поддерживает движок '{new_backend_str}'.\n"
                        f"Константа cv2.{backend_const_name} не найдена.",
                        QMessageBox.Critical,
                    )
                    msg.exec_()
                    # Возврат на старое
                    idx = self.combo_backend.findData(old_backend)
                    self.combo_backend.setCurrentIndex(idx)
                    return

                selected_api = getattr(cv2, backend_const_name)

            # 2. Пробуем открыть
            try:
                cap_test = cv2.VideoCapture(self.current_video_path, selected_api)
                is_opened = cap_test.isOpened()

                # Получаем реальное имя движка, который сработал
                real_backend = cap_test.getBackendName() if is_opened else "NONE"
                cap_test.release()

                if not is_opened:
                    msg = create_dark_msg_box(
                        self,
                        "Ошибка открытия",
                        f"Движок '{new_backend_str}' не смог открыть это видео.",
                        QMessageBox.Warning,
                    )
                    msg.exec_()
                    idx = self.combo_backend.findData(old_backend)
                    self.combo_backend.setCurrentIndex(idx)
                    return

                # 3. ПРОВЕРКА НА ПОДМЕНУ (Silent Fallback)
                # Если мы просили CUDA, а OpenCV втихую подсунул MSMF/FFMPEG - ругаемся.
                if (
                    new_backend_str not in ["AUTO", "ANY"]
                    and real_backend != new_backend_str
                ):
                    msg = create_dark_msg_box(
                        self,
                        "Ошибка применения",
                        f"Вы выбрали '{new_backend_str}', но OpenCV автоматически переключился на '{real_backend}'.\n"
                        "Скорее всего, у вас не установлены необходимые библиотеки (CUDA/GStreamer) или драйверы.",
                        QMessageBox.Warning,
                    )
                    msg.exec_()
                    idx = self.combo_backend.findData(old_backend)
                    self.combo_backend.setCurrentIndex(idx)
                    return

            except Exception as e:
                print(f"Validation error: {e}")
                msg = create_dark_msg_box(self, "Ошибка", str(e), QMessageBox.Critical)
                msg.exec_()
                return

        # Если все проверки прошли - сохраняем
        self.settings.set("use_proxy", self.cb_use_proxy.isChecked())

        ask_proxy = self.cb_ask_proxy.isChecked()
        self.settings.set("ask_proxy_creation", ask_proxy)

        new_q = self.combo_quality.currentData()
        self.settings.set("proxy_quality", new_q)

        new_codec = self.combo_codec.currentData()
        self.settings.set("proxy_codec", new_codec)

        self.settings.set("cache_size", self.spin_cache.value())
        self.settings.set("use_gpu", self.cb_gpu.isChecked())

        self.settings.set("video_backend", new_backend_str)

        new_effort = self.combo_lookback.currentData()
        self.settings.set("seek_effort", new_effort)

        self.settings.save()

        if (
            new_q != self.old_quality
            or new_codec != self.old_codec
            or new_backend_str != old_backend
            or ask_proxy != self.old_ask_proxy
        ):
            self.need_restart = True

        self.accept()


class SplitDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Разрезание")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFocusPolicy(Qt.StrongFocus)
        apply_dark_title_bar(self)
        self.setStyleSheet(DIALOG_STYLESHEET)
        self.resize(350, 180)
        self.choice = "left"
        self.init_ui()

    def showEvent(self, event: QShowEvent):
        self.activateWindow()
        super().showEvent(event)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        lbl = QLabel("Как разрезать текущий кадр?")
        lbl.setStyleSheet(
            "font-size: 16px; font-weight: bold; margin-bottom: 5px; color: #0078d7;"
        )
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)

        self.btn_left = QPushButton("Отнести к ЛЕВОМУ (1 или A)")
        self.btn_left.setMinimumHeight(45)
        self.btn_left.setCursor(Qt.PointingHandCursor)
        self.btn_left.setFocusPolicy(Qt.StrongFocus)
        self.btn_left.clicked.connect(self.select_left)

        self.btn_right = QPushButton("Отнести к ПРАВОМУ (2 или D)")
        self.btn_right.setMinimumHeight(45)
        self.btn_right.setCursor(Qt.PointingHandCursor)
        self.btn_right.setFocusPolicy(Qt.StrongFocus)
        self.btn_right.clicked.connect(self.select_right)

        layout.addWidget(self.btn_left)
        layout.addWidget(self.btn_right)

        layout.addSpacing(10)

        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.clicked.connect(self.reject)
        layout.addWidget(self.btn_cancel)

    def select_left(self):
        self.choice = "left"
        self.accept()

    def select_right(self):
        self.choice = "right"
        self.accept()

    def keyPressEvent(self, event):
        key = normalize_key(event.key())
        if key in [Qt.Key_1, Qt.Key_A]:
            self.select_left()
        elif key in [Qt.Key_2, Qt.Key_D]:
            self.select_right()
        else:
            super().keyPressEvent(event)


class ProxyProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Создание Proxy")
        self.setFixedSize(400, 160)
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowContextHelpButtonHint
            & ~Qt.WindowCloseButtonHint
        )
        apply_dark_title_bar(self)
        self.setStyleSheet(DIALOG_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        self.lbl = QLabel(
            "Конвертация видео для плавного просмотра...\nПожалуйста, подождите."
        )
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.lbl)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #555;
                background-color: #222;
                text-align: center;
                height: 25px;
                border-radius: 3px;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #0078d7;
                width: 10px;
            }
        """)
        layout.addWidget(self.bar)

        btn = QPushButton("Отмена")
        btn.setFixedSize(100, 30)
        btn.clicked.connect(self.reject)
        btn.setFocusPolicy(Qt.StrongFocus)

        h_layout = QHBoxLayout()
        h_layout.addStretch()
        h_layout.addWidget(btn)
        h_layout.addStretch()

        layout.addLayout(h_layout)

    def set_progress(self, val):
        self.bar.setValue(val)
