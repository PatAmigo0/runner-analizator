import copy
import ctypes
import json
import os
import sys
from ctypes import byref, c_int

import cv2
from formulas import FormulasWindow
from PySide2 import __file__ as psf  # noqa
from PySide2.QtCore import QMutex, QRect, Qt, QThread, Signal, Slot
from PySide2.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
)
from PySide2.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollBar,
    QSizePolicy,
    QSlider,
    QStackedLayout,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from timeline import TimelineWidget

is_exe_version = 0
if "__compiled__" not in globals():
    import PySide2

    dirname = os.path.dirname(PySide2.__file__)
    plugin_path = os.path.join(dirname, "plugins", "platforms")
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugin_path
    print(f"Debug: Запуск скрипта. Путь к плагинам установлен вручную: {plugin_path}")
else:
    is_exe_version = 1

try:
    # Set App ID for Taskbar
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        "arseni.kuskou.prosportsanalyzer.1.5"
    )
except ImportError:
    pass


def get_resource_path(relative_path):
    try:
        base_path = os.path.dirname(__file__)
    except NameError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# --- SETTINGS MANAGER ---
class SettingsManager:
    def __init__(self):
        try:
            from PySide2.QtCore import QStandardPaths

            config_path = QStandardPaths.writableLocation(
                QStandardPaths.AppConfigLocation
            )
            self.app_dir = os.path.join(config_path, "ProSportsAnalyzer")
            if not os.path.exists(self.app_dir):
                os.makedirs(self.app_dir)
        except Exception:
            self.app_dir = os.getcwd()

        self.filepath = os.path.join(self.app_dir, "settings.json")

        self.default_hotkeys = {
            "play_pause": int(Qt.Key_Space),
            "mark": int(Qt.Key_M),
            "split": int(Qt.Key_S),
            "delete": int(Qt.Key_Delete),
            "undo": int(Qt.Key_Z),
            "frame_prev": int(Qt.Key_Left),
            "frame_next": int(Qt.Key_Right),
            "seg_prev": int(Qt.Key_A),
            "seg_next": int(Qt.Key_D),
        }
        self.data = {
            "hotkeys": self.default_hotkeys.copy(),
            "formulas": [],
            "last_dir": "",
        }
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    if not content.strip():
                        return
                    loaded = json.loads(content)

                    if "hotkeys" in loaded:
                        for k, v in loaded["hotkeys"].items():
                            self.data["hotkeys"][k] = int(v)
                        for k, v in self.default_hotkeys.items():
                            if k not in self.data["hotkeys"]:
                                self.data["hotkeys"][k] = v

                    if "formulas" in loaded:
                        self.data["formulas"] = loaded["formulas"]
                    if "last_dir" in loaded:
                        self.data["last_dir"] = loaded["last_dir"]
            except Exception as e:
                print(f"Error loading settings: {e}")

    def save(self):
        try:
            clean_hotkeys = {k: int(v) for k, v in self.data["hotkeys"].items()}
            data_to_save = {
                "hotkeys": clean_hotkeys,
                "formulas": self.data["formulas"],
                "last_dir": self.data["last_dir"],
            }
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")


# --- HOTKEY EDITOR ---
class HotkeyEditor(QDialog):
    def __init__(self, parent, current_hotkeys):
        super().__init__(parent)
        self.setWindowTitle("Настройка горячих клавиш")
        self.resize(500, 400)
        self.hotkeys = current_hotkeys.copy()
        self.modified = False

        self.names = {
            "play_pause": "Старт / Пауза",
            "mark": "Поставить метку",
            "split": "Разрезать",
            "delete": "Удалить",
            "undo": "Отмена",
            "frame_prev": "Кадр назад",
            "frame_next": "Кадр вперед",
            "seg_prev": "Пред. отрезок",
            "seg_next": "След. отрезок",
        }

        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: #fff; }
            QTableWidget { background-color: #333; color: #fff; gridline-color: #555; }
            QHeaderView::section { background-color: #444; color: #fff; border: 1px solid #555; padding: 4px; }
            QPushButton { background-color: #444; color: #fff; border: 1px solid #666; padding: 6px; }
            QPushButton:hover { background-color: #555; }
        """)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Действие", "Клавиша"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.capture_key)
        layout.addWidget(self.table)

        layout.addWidget(QLabel("Дважды кликните по строке для изменения"))

        btn_box = QHBoxLayout()
        btn_save = QPushButton("Сохранить")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)
        self.refresh_table()

    def refresh_table(self):
        self.table.setRowCount(0)
        for key_code_name, key_val in self.hotkeys.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            name = self.names.get(key_code_name, key_code_name)
            self.table.setItem(row, 0, QTableWidgetItem(name))
            seq = QKeySequence(int(key_val)).toString()
            item = QTableWidgetItem(seq)
            item.setData(Qt.UserRole, key_code_name)
            self.table.setItem(row, 1, item)

    def capture_key(self, row, col):
        key_name_item = self.table.item(row, 0)
        action_internal = self.table.item(row, 1).data(Qt.UserRole)

        d = QDialog(self)
        d.setWindowTitle("Нажмите клавишу")
        d.resize(300, 150)
        ll = QVBoxLayout(d)
        ll.addWidget(QLabel(f"Нажмите новую клавишу для:\n{key_name_item.text()}"))

        captured = []

        def key_press(e):
            if e.key() not in [Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt]:
                captured.append(e.key())
                d.accept()

        d.keyPressEvent = key_press
        if d.exec_() == QDialog.Accepted and captured:
            self.hotkeys[action_internal] = captured[0]
            self.modified = True
            self.refresh_table()


# --- SPLIT DIALOG ---
class SplitDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор разреза")
        self.resize(300, 120)
        self.choice = None  # 'left' or 'right'

        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: #fff; }
            QLabel { color: #fff; font-size: 14px; }
            QPushButton { 
                background-color: #444; color: #fff; border: 1px solid #666; padding: 10px; font-size: 13px;
            }
            QPushButton:hover { background-color: #555; }
        """)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("К какому отрезку отнести ТЕКУЩИЙ кадр?"))
        layout.addWidget(QLabel("(Клавиши: 1 - Влево, 2 - Вправо)"))

        btn_layout = QHBoxLayout()

        btn_left = QPushButton("<- К левому (1)")
        btn_left.clicked.connect(lambda: self.set_choice("left"))

        btn_right = QPushButton("К правому -> (2)")
        btn_right.clicked.connect(lambda: self.set_choice("right"))

        btn_layout.addWidget(btn_left)
        btn_layout.addWidget(btn_right)
        layout.addLayout(btn_layout)

    def set_choice(self, val):
        self.choice = val
        self.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_1:
            self.set_choice("left")
        elif event.key() == Qt.Key_2:
            self.set_choice("right")
        else:
            super().keyPressEvent(event)


# --- VIDEO THREAD ---
class VideoThread(QThread):
    change_pixmap_signal = Signal(object)
    finished_signal = Signal()
    video_info_signal = Signal(dict)

    def __init__(self):
        super().__init__()
        self.cap = None
        self._run_flag = True
        self.fps = 30
        self.speed = 1.0
        self.current_frame_num = 0
        self.mutex = QMutex()

    def load_video(self, path):
        self.stop()
        self.mutex.lock()
        try:
            if self.cap:
                self.cap.release()
            self.cap = cv2.VideoCapture(path)
            if self.cap.isOpened():
                info = {
                    "fps": self.cap.get(cv2.CAP_PROP_FPS),
                    "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    "total": int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                }
                self.fps = info["fps"]
                self.current_frame_num = 0
                self.video_info_signal.emit(info)
        finally:
            self.mutex.unlock()
        self.read_one_frame()

    def read_one_frame(self):
        self.mutex.lock()
        try:
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    self.current_frame_num = (
                        int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
                    )
                    self.change_pixmap_signal.emit(frame)
        finally:
            self.mutex.unlock()

    def seek(self, frame_num):
        self.mutex.lock()
        try:
            if self.cap and self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = self.cap.read()
                if ret:
                    self.current_frame_num = (
                        int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
                    )
                    self.change_pixmap_signal.emit(frame)
        finally:
            self.mutex.unlock()

    def run(self):
        self._run_flag = True
        while self._run_flag:
            self.mutex.lock()
            try:
                if not self._run_flag:
                    break
                if self.cap and self.cap.isOpened():
                    ret, frame = self.cap.read()
                    if ret:
                        self.current_frame_num = (
                            int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
                        )
                        self.change_pixmap_signal.emit(frame)
                    else:
                        self.finished_signal.emit()
                        self._run_flag = False
                else:
                    break
            finally:
                self.mutex.unlock()

            if self._run_flag and self.fps > 0:
                self.msleep(int(1000.0 / (self.fps * self.speed)))

    def stop(self):
        self._run_flag = False
        self.wait(500)
        if self.isRunning():
            self.terminate()


# --- MAIN WINDOW ---
class ProSportsAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = SettingsManager()

        self.setWindowTitle(f"Pro Sports Analyzer v1.5.{is_exe_version}")
        self.resize(1600, 950)
        self.setAcceptDrops(True)

        try:
            hwnd = self.winId()
            value = c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(hwnd), 20, byref(value), ctypes.sizeof(value)
            )
        except Exception:
            pass

        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; color: #f0f0f0; font-family: Segoe UI; }
            QWidget { font-size: 14px; }
            
            QMessageBox { background-color: #2b2b2b; color: #f0f0f0; }
            QMessageBox QLabel { color: #f0f0f0; }
            QMessageBox QPushButton {
                background-color: #3a3a3a; color: #fff; border: 1px solid #555;
                padding: 6px 15px; border-radius: 3px; min-width: 60px;
            }
            QMessageBox QPushButton:hover { background-color: #4a4a4a; }
            
            QGroupBox { 
                border: 1px solid #444; margin-top: 20px; font-weight: bold; 
                color: #ccc; background-color: #2b2b2b; border-radius: 3px; padding-top: 15px;
            }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; left: 10px; color: #fff; }
            
            QPushButton { 
                background-color: #3a3a3a; border: 1px solid #555; padding: 6px 12px; 
                color: white; border-radius: 2px; 
            }
            QPushButton:hover { background-color: #505050; border-color: #777; }
            QPushButton:pressed { background-color: #0078d7; border-color: #0078d7; }
            QPushButton:disabled { background-color: #2a2a2a; color: #555; border-color: #333; }
            
            QLineEdit { background-color: #1e1e1e; color: #fff; padding: 4px; border: 1px solid #555; }
            QLineEdit:focus { border: 1px solid #0078d7; }
            
            QLabel { color: #e0e0e0; }
            
            QListWidget { background-color: #222; border: 1px solid #444; color: #ffffff; outline: none; }
            QListWidget::item { color: #ffffff; padding: 4px; }
            QListWidget::item:hover { background-color: #2a2a2a; }
            QListWidget::item:selected { background-color: #222; color: #ffffff; }
            
            QCheckBox { color: #ffffff; spacing: 5px; }
            QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #666; background: #333; }
            QCheckBox::indicator:checked { background: #0078d7; border-color: #0078d7; }

            QDoubleSpinBox { 
                background-color: #222; color: #fff; border: 1px solid #555; padding: 4px; 
                selection-background-color: #222; 
                selection-color: #fff;
            }
            QDoubleSpinBox:focus { border: 1px solid #0078d7; }

            /* SCROLLBAR / SLIDER STYLE */
            QSlider::groove:horizontal {
                border: 1px solid #444;
                height: 8px;
                background: #333;
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #0078d7;
                border: 1px solid #0078d7;
                width: 18px;
                height: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #1e8feb;
            }
            QSlider::sub-page:horizontal:disabled {
                background: #333;
            }
            
            QScrollBar:horizontal {
                border: 1px solid #333;
                background: #222;
                height: 15px;
                margin: 0px 20px 0 20px;
            }
            QScrollBar::handle:horizontal {
                background: #555;
                min-width: 20px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                background: none;
                width: 0px;
            }
        """)

        # Data
        self.total_frames = 100
        self.fps = 30.0
        self.current_frame = 0
        self.playing = False
        self.playback_speed = 1.0
        self.current_ext = ""
        self.last_frame = None

        self.segments = []
        self.markers = []
        self.history = []
        self.is_undoing = False
        self.is_merge_mode = False
        self.merge_buffer = []

        self.current_marker_color = "#ff0000"
        self.current_marker_tag = "Main"

        self.thread = VideoThread()
        self.thread.change_pixmap_signal.connect(self.update_image)
        self.thread.finished_signal.connect(self.on_video_finished)
        self.thread.video_info_signal.connect(self.set_video_info)

        self.formulas_window = FormulasWindow(self, self.settings.data["formulas"])
        self.formulas_window.set_context_callback(self.get_current_context)

        self.init_ui()

    def init_ui(self):
        icon_path = get_resource_path("favicon.ico")
        self.setWindowIcon(QIcon(icon_path))

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        top_layout = QHBoxLayout()

        # LEFT PANEL
        left_panel = QWidget()
        left_panel.setFixedWidth(320)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setAlignment(Qt.AlignTop)

        gb_file = QGroupBox("Файл и Управление")
        l_file = QVBoxLayout()
        btn_open = QPushButton("📂 Открыть видео")
        btn_open.clicked.connect(self.open_file)
        btn_hotkeys = QPushButton("⌨ Горячие клавиши")
        btn_hotkeys.clicked.connect(self.open_hotkeys_dialog)
        l_file.addWidget(btn_open)
        l_file.addWidget(btn_hotkeys)

        l_info_grid = QVBoxLayout()
        l_info_grid.setSpacing(2)
        self.lbl_vid_res = QLabel("Разрешение: -")
        self.lbl_vid_fps = QLabel("FPS: -")
        self.lbl_vid_frames = QLabel("Всего кадров: -")
        self.lbl_vid_ext = QLabel("Формат: -")
        for lbl in [
            self.lbl_vid_res,
            self.lbl_vid_fps,
            self.lbl_vid_frames,
            self.lbl_vid_ext,
        ]:
            lbl.setStyleSheet("color: #aaa; font-size: 12px;")
            l_info_grid.addWidget(lbl)
        l_file.addLayout(l_info_grid)
        gb_file.setLayout(l_file)
        left_layout.addWidget(gb_file)

        gb_markers = QGroupBox("Метки")
        l_markers = QVBoxLayout()

        self.btn_mark = QPushButton("🚩 ПОСТАВИТЬ МЕТКУ")
        self.btn_mark.setMinimumHeight(40)
        self.btn_mark.setStyleSheet(
            "background-color: #b30000; font-weight: bold; font-size: 14px; border: 1px solid #f00;"
        )
        self.btn_mark.clicked.connect(self.add_mark)
        l_markers.addWidget(self.btn_mark)

        self.lbl_marker_mode = QLabel("Режим: Создание")
        self.lbl_marker_mode.setStyleSheet(
            "color: #888; font-style: italic; margin-top: 5px;"
        )
        l_markers.addWidget(self.lbl_marker_mode)

        h_m1 = QHBoxLayout()
        self.btn_color = QPushButton("")
        self.btn_color.setFixedSize(24, 24)
        self.btn_color.setStyleSheet(
            f"background-color: {self.current_marker_color}; border: 1px solid #fff; border-radius: 12px;"
        )
        self.btn_color.clicked.connect(self.pick_color)

        self.inp_tag = QLineEdit("Main")
        self.inp_tag.setPlaceholderText("Тег")
        self.inp_tag.returnPressed.connect(self.setFocus)
        self.inp_tag.textChanged.connect(self.update_marker_props_live)

        h_m1.addWidget(QLabel("Цвет:"))
        h_m1.addWidget(self.btn_color)
        h_m1.addWidget(self.inp_tag)
        l_markers.addLayout(h_m1)

        l_markers.addWidget(QLabel("Список меток (фильтр):"))
        self.list_filters = QListWidget()
        self.list_filters.setMinimumHeight(150)
        self.list_filters.setSelectionMode(QListWidget.NoSelection)
        self.list_filters.itemChanged.connect(self.on_filter_changed)
        self.list_filters.setFocusPolicy(Qt.NoFocus)
        l_markers.addWidget(self.list_filters)

        gb_markers.setLayout(l_markers)
        left_layout.addWidget(gb_markers)

        gb_actions = QGroupBox("Действия")
        l_actions = QVBoxLayout()
        self.btn_undo = QPushButton("↶ Отмена")
        self.btn_undo.clicked.connect(self.undo_action)
        self.btn_split = QPushButton("✂ Разрезать")
        self.btn_split.clicked.connect(self.split_segment)
        self.btn_merge = QPushButton("🔗 Объединить")
        self.btn_merge.clicked.connect(self.start_merge_mode)

        self.btn_cancel_merge = QPushButton("❌ Отмена объед.")
        self.btn_cancel_merge.clicked.connect(self.stop_merge_mode)
        self.btn_cancel_merge.hide()

        self.btn_delete = QPushButton("🗑 Удалить")
        self.btn_delete.clicked.connect(self.delete_selection)

        l_actions.addWidget(self.btn_undo)
        l_actions.addWidget(self.btn_split)
        l_actions.addWidget(self.btn_merge)
        l_actions.addWidget(self.btn_cancel_merge)
        l_actions.addWidget(self.btn_delete)
        gb_actions.setLayout(l_actions)
        left_layout.addWidget(gb_actions)

        left_layout.addStretch()
        top_layout.addWidget(left_panel)

        # CENTER VIDEO
        self.video_container = QWidget()
        self.video_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_container.setStyleSheet(
            "background-color: black; border: 1px solid #333;"
        )
        # FORCE FOCUS ON VIDEO CLICK
        self.video_container.mousePressEvent = self.on_video_container_click

        self.stack_layout = QStackedLayout(self.video_container)
        self.stack_layout.setStackingMode(QStackedLayout.StackAll)

        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.video_label.setScaledContents(False)
        self.stack_layout.addWidget(self.video_label)

        self.overlay_widget = QLabel("РЕЖИМ ОБЪЕДИНЕНИЯ\nВЫБЕРИТЕ 2 ОТРЕЗКА")
        self.overlay_widget.setAlignment(Qt.AlignCenter)
        self.overlay_widget.setStyleSheet(
            "background-color: rgba(0, 50, 0, 200); color: #0f0; font-size: 24px; font-weight: bold;"
        )
        self.overlay_widget.hide()
        self.stack_layout.addWidget(self.overlay_widget)

        top_layout.addWidget(self.video_container, stretch=1)

        # RIGHT PANEL
        right_panel = QWidget()
        right_panel.setFixedWidth(300)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setAlignment(Qt.AlignTop)

        gb_calc = QGroupBox("Анализ")
        gb_calc.setStyleSheet("QGroupBox { border: 1px solid #0078d7; }")
        l_calc = QVBoxLayout()

        self.lbl_global_frame = QLabel("Кадр: 0")
        self.lbl_global_time = QLabel("Время: 0.00s")
        self.lbl_global_duration = QLabel("Длительность: 0.00s")
        self.lbl_total_marks = QLabel("Всего меток: 0")

        font_head = QFont("Segoe UI", 11, QFont.Bold)
        font_data = QFont("Segoe UI", 10)

        for ll in [
            self.lbl_global_frame,
            self.lbl_global_time,
            self.lbl_global_duration,
            self.lbl_total_marks,
        ]:
            ll.setFont(font_data)
            l_calc.addWidget(ll)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #444;")
        l_calc.addWidget(sep)

        self.lbl_info_seg = QLabel("Нет выбора")
        self.lbl_info_seg.setFont(font_head)
        self.lbl_info_seg.setStyleSheet("color: #fff; margin-top: 5px;")
        l_calc.addWidget(self.lbl_info_seg)

        self.lbl_rel_frame = QLabel("Кадр (отр): -")
        self.lbl_rel_frame.setFont(font_data)
        l_calc.addWidget(self.lbl_rel_frame)

        self.lbl_rel_time = QLabel("Время (отр): -")
        self.lbl_rel_time.setFont(font_data)
        self.lbl_rel_time.setStyleSheet("color: #00ffff; font-weight: bold;")
        l_calc.addWidget(self.lbl_rel_time)

        self.lbl_seg_total_frames = QLabel("Кадров (всего): -")
        self.lbl_seg_total_frames.setFont(font_data)
        l_calc.addWidget(self.lbl_seg_total_frames)

        self.lbl_seg_duration = QLabel("Длит. (всего): -")
        self.lbl_seg_duration.setFont(font_data)
        l_calc.addWidget(self.lbl_seg_duration)

        self.lbl_seg_marks = QLabel("Метки (отр): -")
        self.lbl_seg_marks.setFont(font_data)
        l_calc.addWidget(self.lbl_seg_marks)

        self.lbl_tempo = QLabel("SPM: 0.0")
        self.lbl_tempo.setStyleSheet(
            "color: #00ff00; font-size: 22px; font-weight: bold; margin-top: 10px; background: #222; padding: 5px; border-radius: 4px; border: 1px solid #005500;"
        )
        l_calc.addWidget(self.lbl_tempo)

        gb_calc.setLayout(l_calc)
        right_layout.addWidget(gb_calc)

        btn_formulas = QPushButton("📐 Конструктор формул")
        btn_formulas.clicked.connect(self.show_formulas)
        btn_formulas.setStyleSheet(
            "background-color: #6a0dad; margin-top: 10px; padding: 10px;"
        )
        right_layout.addWidget(btn_formulas)

        gb_speed = QGroupBox("Скорость воспроизведения")
        h_speed = QHBoxLayout()
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.1, 5.0)
        self.spin_speed.setSingleStep(0.1)
        self.spin_speed.setValue(1.0)
        self.spin_speed.valueChanged.connect(self.change_speed)
        self.spin_speed.setFocusPolicy(Qt.ClickFocus)
        h_speed.addWidget(self.spin_speed)
        gb_speed.setLayout(h_speed)
        right_layout.addWidget(gb_speed)

        right_layout.addStretch()
        top_layout.addWidget(right_panel)
        main_layout.addLayout(top_layout)

        # --- SLIDER (SCRUBBER) ---
        self.scrubber = QSlider(Qt.Horizontal)
        self.scrubber.setRange(0, 100)
        self.scrubber.setEnabled(False)  # Disable initially
        self.scrubber.setFocusPolicy(Qt.NoFocus)
        self.scrubber.valueChanged.connect(self.on_scrubber_change)
        main_layout.addWidget(self.scrubber)

        # --- SPACER ---
        main_layout.addSpacing(15)

        # --- TIMELINE ---
        self.timeline = TimelineWidget()
        self.timeline.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.timeline.seek_requested.connect(self.seek_video)
        self.timeline.segment_selected.connect(self.on_timeline_click)
        self.timeline.marker_selected.connect(self.on_selection_changed)
        # Connect zoom signal to update scrollbar
        self.timeline.view_changed.connect(self.update_timeline_scrollbar)
        main_layout.addWidget(self.timeline)

        # --- TIMELINE SCROLLBAR ---
        self.timeline_scroll = QScrollBar(Qt.Horizontal)
        self.timeline_scroll.setRange(0, 0)
        self.timeline_scroll.setEnabled(False)
        self.timeline_scroll.setFocusPolicy(Qt.NoFocus)
        self.timeline_scroll.valueChanged.connect(self.on_timeline_scroll)
        main_layout.addWidget(self.timeline_scroll)

        self.fix_focus_policies()

    def fix_focus_policies(self):
        for btn in self.findChildren(QPushButton):
            btn.setFocusPolicy(Qt.NoFocus)
        self.setFocus()

    def on_video_container_click(self, event):
        # Force focus back to main window when video area is clicked
        self.setFocus()
        if hasattr(QWidget, "mousePressEvent"):
            # Call base implementation if needed, though QWidget doesn't do much
            pass

    def on_scrubber_change(self, val):
        # FIX: Check if video is actually loaded to prevent crash
        if (
            not hasattr(self, "thread")
            or not self.thread.cap
            or not self.thread.cap.isOpened()
        ):
            return

        try:
            # Only seek if the difference is significant or user is dragging
            # Check signalsBlocked to avoid seeking when we update slider programmatically
            if self.scrubber.isEnabled() and not self.scrubber.signalsBlocked():
                self.seek_video(val)
        except Exception:
            pass  # Avoid crashes during init

        # ALWAYS reset focus to Main Window so Hotkeys work after dragging
        self.setFocus()

    def update_timeline_scrollbar(self, start, length, total):
        # Logic to update scrollbar based on timeline zoom
        if length >= total or total == 0:
            self.timeline_scroll.setEnabled(False)
            self.timeline_scroll.setRange(0, 0)
        else:
            self.timeline_scroll.setEnabled(True)
            self.timeline_scroll.setPageStep(length)
            self.timeline_scroll.setRange(0, total - length)
            self.timeline_scroll.blockSignals(True)
            self.timeline_scroll.setValue(start)
            self.timeline_scroll.blockSignals(False)

    def on_timeline_scroll(self, val):
        if not self.timeline_scroll.signalsBlocked():
            self.timeline.set_view_start_from_scrollbar(val)

    def open_hotkeys_dialog(self):
        dlg = HotkeyEditor(self, self.settings.data["hotkeys"])
        if dlg.exec_() == QDialog.Accepted:
            if dlg.modified:
                self.settings.data["hotkeys"] = dlg.hotkeys
                self.settings.save()
                QMessageBox.information(self, "Инфо", "Настройки сохранены.")
        self.setFocus()

    def closeEvent(self, event):
        self.thread.stop()
        forms = self.formulas_window.get_formulas()
        self.settings.data["formulas"] = forms
        self.settings.save()
        super().closeEvent(event)

    def mousePressEvent(self, event):
        self.setFocus()
        self.deselect_all()
        super().mousePressEvent(event)

    def undo_action(self):
        if not self.history:
            return
        self.is_undoing = True
        state = self.history.pop()
        self.segments = state["segments"]
        self.markers = state["markers"]
        self.timeline.set_data(self.total_frames, self.fps, self.segments, self.markers)
        self.update_filter_list()
        self.calculate_stats()
        self.redraw_current_frame()
        self.is_undoing = False

    def save_state(self):
        if self.is_undoing:
            return
        state = {
            "segments": copy.deepcopy(self.segments),
            "markers": copy.deepcopy(self.markers),
        }
        self.history.append(state)
        if len(self.history) > 1000:
            self.history.pop(0)

    def pick_color(self):
        init = self.current_marker_color
        idx = self.timeline.selected_marker_idx
        if idx != -1 and idx < len(self.markers):
            init = self.markers[idx]["color"]
        color = QColorDialog.getColor(initial=QColor(init))
        if color.isValid():
            self.apply_color(color.name())

    def apply_color(self, color_name):
        idx = self.timeline.selected_marker_idx
        if idx != -1 and idx < len(self.markers):
            m = self.markers[idx]
            if m["color"] != color_name:
                m["color"] = color_name
                self.timeline.update()
                self.redraw_current_frame()
        else:
            self.current_marker_color = color_name
        self.update_ui_marker_controls()

    def update_marker_props_live(self):
        tag = self.inp_tag.text()
        idx = self.timeline.selected_marker_idx
        if idx != -1 and idx < len(self.markers):
            m = self.markers[idx]
            m["tag"] = tag
            self.timeline.update()
            self.redraw_current_frame()
        else:
            self.current_marker_tag = tag

    def update_ui_marker_controls(self):
        idx = self.timeline.selected_marker_idx
        if idx != -1 and idx < len(self.markers):
            m = self.markers[idx]
            self.lbl_marker_mode.setText("Режим: ИЗМЕНЕНИЕ")
            self.lbl_marker_mode.setStyleSheet(
                "color: #0f0; font-weight: bold; margin-top: 5px;"
            )
            self.inp_tag.blockSignals(True)
            self.inp_tag.setText(m["tag"])
            self.inp_tag.blockSignals(False)
            self.btn_color.setStyleSheet(
                f"background-color: {m['color']}; border: 1px solid #fff; border-radius: 12px;"
            )
        else:
            self.lbl_marker_mode.setText("Режим: СОЗДАНИЕ")
            self.lbl_marker_mode.setStyleSheet(
                "color: #888; font-style: italic; margin-top: 5px;"
            )
            self.inp_tag.blockSignals(True)
            self.inp_tag.setText(self.current_marker_tag)
            self.inp_tag.blockSignals(False)
            self.btn_color.setStyleSheet(
                f"background-color: {self.current_marker_color}; border: 1px solid #fff; border-radius: 12px;"
            )

    def update_filter_list(self):
        tags = sorted(list(set(m["tag"] for m in self.markers)))
        checked_tags = []
        for i in range(self.list_filters.count()):
            item = self.list_filters.item(i)
            if item.checkState() == Qt.Checked:
                checked_tags.append(item.text())

        self.list_filters.clear()
        first_run = len(checked_tags) == 0 and len(tags) > 0

        for t in tags:
            item = QListWidgetItem(t)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if first_run or t in checked_tags:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
            self.list_filters.addItem(item)

    def on_filter_changed(self, item):
        tag = item.text()
        visible = item.checkState() == Qt.Checked
        for m in self.markers:
            if m["tag"] == tag:
                m["visible"] = visible
        self.timeline.update()
        self.calculate_stats()
        self.redraw_current_frame()
        self.setFocus()

    def open_file(self):
        start_dir = self.settings.data.get("last_dir", "")
        f, _ = QFileDialog.getOpenFileName(self, "Открыть видео", start_dir)
        if f:
            self.settings.data["last_dir"] = os.path.dirname(f)
            self.load_video(f)
        self.activateWindow()
        self.setFocus()

    def reset_session_data(self):
        # Stop thread
        self.playing = False
        if hasattr(self, "thread"):
            self.thread.stop()
            self.thread.wait()  # Ensure stopped

        # Clear data
        self.segments = []
        self.markers = []
        self.history = []
        self.merge_buffer = []
        self.is_merge_mode = False
        self.current_frame = 0
        self.total_frames = 0
        self.fps = 30.0
        self.last_frame = None

        # Reset UI
        self.scrubber.setEnabled(False)
        self.scrubber.setValue(0)
        self.timeline.set_data(0, 30, [], [])
        self.video_label.clear()
        self.overlay_widget.hide()
        self.btn_merge.show()
        self.btn_cancel_merge.hide()
        self.btn_split.setEnabled(True)
        self.btn_delete.setEnabled(True)
        self.list_filters.clear()

        # Reset scrollbar
        self.timeline_scroll.setEnabled(False)
        self.timeline_scroll.setRange(0, 0)

        # Reset Labels
        self.lbl_vid_res.setText("Разрешение: -")
        self.lbl_vid_fps.setText("FPS: -")
        self.lbl_vid_frames.setText("Всего кадров: -")
        self.lbl_vid_ext.setText("Формат: -")

        self.calculate_stats()

    def load_video(self, path):
        self.reset_session_data()  # Reset everything before loading new

        self.save_state()
        self.current_ext = os.path.splitext(path)[1]
        self.thread.load_video(path)

    def set_video_info(self, info):
        self.fps = info["fps"]
        self.total_frames = info["total"]
        self.segments = [{"start": 0, "end": self.total_frames}]
        self.markers = []

        # Update Scrubber Range and Enable
        self.scrubber.setRange(0, self.total_frames - 1)
        self.scrubber.setValue(0)
        self.scrubber.setEnabled(True)

        self.timeline.set_data(self.total_frames, self.fps, self.segments, self.markers)
        self.timeline.selected_segment_idx = 0

        self.lbl_vid_res.setText(f"Разрешение: {info['width']}x{info['height']}")
        self.lbl_vid_fps.setText(f"FPS: {self.fps:.2f}")
        self.lbl_vid_frames.setText(f"Всего кадров: {self.total_frames}")
        self.lbl_vid_ext.setText(f"Формат: {self.current_ext}")

        self.calculate_stats()
        self.setFocus()

    @Slot(object)
    def update_image(self, frame):
        self.last_frame = frame
        self.current_frame = self.thread.current_frame_num
        self.draw_frame(frame)

    def redraw_current_frame(self):
        if self.last_frame is not None:
            self.draw_frame(self.last_frame)

    def draw_frame(self, frame):
        h, w, ch = frame.shape
        lbl_w = self.video_label.width()
        lbl_h = self.video_label.height()
        if lbl_w > 0 and lbl_h > 0:
            aspect = w / h
            target_w = lbl_w
            target_h = int(target_w / aspect)
            if target_h > lbl_h:
                target_h = lbl_h
                target_w = int(target_h * aspect)
            frame_resized = cv2.resize(
                frame, (target_w, target_h), interpolation=cv2.INTER_AREA
            )
        else:
            frame_resized = frame

        rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
        qimg = QImage(
            rgb.data,
            frame_resized.shape[1],
            frame_resized.shape[0],
            rgb.strides[0],
            QImage.Format_RGB888,
        )
        pixmap = QPixmap.fromImage(qimg)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. MARKER
        for m in self.markers:
            if m.get("visible", True) and m["frame"] == self.current_frame:
                tag_text = f"🚩 {m.get('tag', 'Mark')}"
                font = QFont("Segoe UI", 16, QFont.Bold)
                painter.setFont(font)
                metrics = painter.fontMetrics()
                text_w = metrics.horizontalAdvance(tag_text)
                text_h = metrics.height()

                pad = 10
                box_w = text_w + pad * 2
                box_h = text_h + pad
                box_x = pixmap.width() - box_w - 20
                box_y = 20

                bg_color = QColor(m["color"])
                bg_color.setAlpha(220)
                painter.setBrush(QBrush(bg_color))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(box_x, box_y, box_w, box_h, 5, 5)

                painter.setPen(QPen(Qt.white))
                painter.drawText(
                    QRect(box_x, box_y, box_w, box_h), Qt.AlignCenter, tag_text
                )
                break

        # 2. PAUSE INDICATOR
        if not self.playing and not self.is_merge_mode:
            pause_text = "⏸ ПАУЗА"
            font_p = QFont("Segoe UI", 16, QFont.Bold)
            painter.setFont(font_p)
            metrics_p = painter.fontMetrics()
            pw = metrics_p.horizontalAdvance(pause_text)
            ph = metrics_p.height()

            p_pad = 10
            p_box_w = pw + p_pad * 3
            p_box_h = ph + p_pad
            p_box_x = 20
            p_box_y = 20

            p_bg = QColor(0, 0, 0, 150)
            painter.setBrush(QBrush(p_bg))
            painter.setPen(QPen(QColor(255, 255, 255, 100), 2))
            painter.drawRoundedRect(p_box_x, p_box_y, p_box_w, p_box_h, 5, 5)

            painter.setPen(QPen(Qt.white))
            painter.drawText(
                QRect(p_box_x, p_box_y, p_box_w, p_box_h), Qt.AlignCenter, pause_text
            )

        painter.end()

        self.video_label.setPixmap(pixmap)
        self.timeline.set_current_frame(self.current_frame)
        self.calculate_stats()

    def add_mark(self):
        for m in self.markers:
            if m["frame"] == self.current_frame:
                return

        self.save_state()
        new_marker = {
            "frame": self.current_frame,
            "color": self.current_marker_color,
            "tag": self.current_marker_tag,
            "visible": True,
        }
        self.markers.append(new_marker)
        self.markers.sort(key=lambda x: x["frame"])
        self.update_filter_list()
        self.timeline.update()
        self.calculate_stats()
        self.redraw_current_frame()

    def split_segment(self):
        if self.is_merge_mode:
            return
        idx = -1
        # Find which segment contains the current frame
        for i, seg in enumerate(self.segments):
            if seg["start"] <= self.current_frame < seg["end"]:
                idx = i
                break

        if idx != -1:
            # Show Dialog
            dlg = SplitDialog(self)
            if dlg.exec_() == QDialog.Accepted:
                self.save_state()
                old = self.segments[idx]
                mid = self.current_frame

                if dlg.choice == "left":
                    s1 = {
                        "start": old["start"],
                        "end": mid + 1,
                    }  # Python range style (exclusive end)
                    s2 = {"start": mid + 1, "end": old["end"]}
                else:  # right
                    s1 = {"start": old["start"], "end": mid}
                    s2 = {"start": mid, "end": old["end"]}

                # Validation to prevent empty segments
                valid = True
                if s1["end"] <= s1["start"] or s2["end"] <= s2["start"]:
                    QMessageBox.warning(
                        self, "Ошибка", "Нельзя разрезать на самом краю отрезка!"
                    )
                    valid = False

                if valid:
                    self.segments.pop(idx)
                    self.segments.insert(idx, s2)
                    self.segments.insert(idx, s1)
                    # Select appropriate segment based on split logic
                    self.timeline.selected_segment_idx = (
                        idx if dlg.choice == "left" else idx + 1
                    )
                    self.timeline.update()
                    self.calculate_stats()
            self.setFocus()

    def delete_selection(self):
        self.save_state()
        if self.timeline.selected_marker_idx != -1:
            self.markers.pop(self.timeline.selected_marker_idx)
            self.timeline.selected_marker_idx = -1
            self.update_filter_list()
        elif self.timeline.selected_segment_idx != -1:
            idx = self.timeline.selected_segment_idx
            if len(self.segments) > 1:
                deleted = self.segments.pop(idx)
                if idx > 0:
                    self.segments[idx - 1]["end"] = deleted["end"]
                else:
                    self.segments[0]["start"] = deleted["start"]
                self.timeline.selected_segment_idx = -1
        self.timeline.update()
        self.calculate_stats()
        self.update_ui_marker_controls()
        self.redraw_current_frame()

    def perform_merge(self, i1, i2):
        self.save_state()
        seg1 = self.segments[i1]
        seg2 = self.segments[i2]
        new_seg = {
            "start": min(seg1["start"], seg2["start"]),
            "end": max(seg1["end"], seg2["end"]),
        }
        self.segments.pop(i2)
        self.segments.pop(i1)
        self.segments.insert(i1, new_seg)
        self.timeline.selected_segment_idx = i1
        self.stop_merge_mode()
        self.timeline.update()
        self.calculate_stats()

    def deselect_all(self):
        self.timeline.selected_segment_idx = -1
        self.timeline.selected_marker_idx = -1
        self.update_ui_marker_controls()
        self.timeline.update()
        self.calculate_stats()

    def on_selection_changed(self, idx):
        self.update_ui_marker_controls()
        self.calculate_stats()
        self.setFocus()

    def on_timeline_click(self, idx):
        if not self.is_merge_mode:
            self.on_selection_changed(idx)
            return
        if idx == -1:
            return
        if idx in self.merge_buffer:
            self.merge_buffer.remove(idx)
        else:
            self.merge_buffer.append(idx)
            if len(self.merge_buffer) > 2:
                self.merge_buffer.pop(0)
        self.timeline.merge_candidates = self.merge_buffer
        self.timeline.update()
        if len(self.merge_buffer) == 2:
            i1, i2 = sorted(self.merge_buffer)
            if abs(i1 - i2) == 1:
                self.perform_merge(i1, i2)
            else:
                QMessageBox.warning(self, "Ошибка", "Можно объединять только соседние!")
                self.merge_buffer = []
                self.timeline.merge_candidates = []
                self.timeline.update()

    def calculate_stats(self):
        if self.scrubber.isEnabled():
            self.scrubber.blockSignals(True)
            self.scrubber.setValue(self.current_frame)
            self.scrubber.blockSignals(False)

        # 1. Global Stats
        self.lbl_global_frame.setText(f"Кадр: {self.current_frame}")
        t = self.current_frame / self.fps if self.fps > 0 else 0
        self.lbl_global_time.setText(f"Время: {t:.2f}s")

        total_sec = self.total_frames / self.fps if self.fps > 0 else 0
        self.lbl_global_duration.setText(f"Длительность: {total_sec:.2f}s")
        self.lbl_total_marks.setText(f"Всего меток: {len(self.markers)}")

        # 2. Selected Marker Stats
        if self.timeline.selected_marker_idx != -1:
            if self.timeline.selected_marker_idx < len(self.markers):
                m = self.markers[self.timeline.selected_marker_idx]
                self.lbl_info_seg.setText(f"МЕТКА: {m['tag']}")
                self.lbl_rel_time.setText(f"Время: {m['frame'] / self.fps:.3f}s")
                self.lbl_rel_frame.setText(f"Кадр: {m['frame']}")
                self.lbl_seg_total_frames.setText("Кадров (всего): -")
                self.lbl_seg_duration.setText("Длит. (всего): -")
                self.lbl_seg_marks.setText("-")
                self.lbl_tempo.setText("")
            return

        # 3. Selected Segment Stats
        idx = self.timeline.selected_segment_idx
        if idx != -1 and idx < len(self.segments):
            seg = self.segments[idx]
            s, e = seg["start"], seg["end"]

            is_inside = s <= self.current_frame <= e

            rel_f = self.current_frame - s
            rel_t = rel_f / self.fps if self.fps > 0 else 0

            if is_inside:
                color_style_time = "color: #00ffff; font-weight: bold;"
                color_style_frame = "color: #e0e0e0;"
                suffix = ""
            else:
                color_style_time = "color: #777;"
                color_style_frame = "color: #777;"
                suffix = " (вне)"

            k = e - s
            dur = k / self.fps if self.fps > 0 else 0

            vis_marks = [
                m
                for m in self.markers
                if s <= m["frame"] <= e and m.get("visible", True)
            ]
            n = len(vis_marks)
            tempo = (n / dur * 60) if dur > 0 else 0

            self.lbl_info_seg.setText(f"Отрезок #{idx + 1}")

            self.lbl_rel_frame.setText(f"Кадр (отр): {rel_f}{suffix}")
            self.lbl_rel_frame.setStyleSheet(color_style_frame)

            self.lbl_rel_time.setText(f"Время (отр): {rel_t:.2f}s{suffix}")
            self.lbl_rel_time.setStyleSheet(color_style_time)

            self.lbl_seg_total_frames.setText(f"Кадров (всего): {k}")
            self.lbl_seg_duration.setText(f"Длит. (всего): {dur:.2f}s")

            self.lbl_seg_marks.setText(f"Метки (отр): {n}")
            self.lbl_tempo.setText(f"SPM: {tempo:.1f}")
        else:
            self.lbl_info_seg.setText("Нет выбора")
            self.lbl_rel_frame.setText("Кадр (отр): -")
            self.lbl_rel_time.setText("Время (отр): -")
            self.lbl_seg_total_frames.setText("Кадров (всего): -")
            self.lbl_seg_duration.setText("Длит. (всего): -")
            self.lbl_seg_marks.setText("Метки (отр): -")
            self.lbl_tempo.setText("SPM: 0.0")

            self.lbl_rel_frame.setStyleSheet("color: #e0e0e0;")
            self.lbl_rel_time.setStyleSheet("color: #00ffff; font-weight: bold;")

    def on_video_finished(self):
        self.playing = False
        self.redraw_current_frame()
        self.thread.stop()

    def toggle_play(self):
        if not self.thread.cap or self.is_merge_mode:
            return
        self.playing = not self.playing
        if self.playing:
            self.thread.start()
        else:
            self.thread.stop()
            self.redraw_current_frame()

    def change_speed(self, val):
        self.playback_speed = val
        self.thread.speed = val
        self.setFocus()

    def seek_video(self, frame):
        self.current_frame = frame
        self.playing = False
        self.thread.stop()
        self.thread.seek(frame)
        self.calculate_stats()

    def step_frame(self, step):
        self.playing = False
        self.thread.stop()
        n = self.current_frame + step
        if 0 <= n < self.total_frames:
            self.thread.seek(n)
            self.calculate_stats()

    def next_segment(self):
        if not self.segments:
            return
        curr = self.timeline.selected_segment_idx
        if curr == -1:
            new_idx = 0
        else:
            new_idx = min(len(self.segments) - 1, curr + 1)

        self.timeline.selected_segment_idx = new_idx
        self.timeline.selected_marker_idx = -1
        self.timeline.update()

        new_start = self.segments[new_idx]["start"]
        self.seek_video(new_start)
        self.calculate_stats()

    def prev_segment(self):
        if not self.segments:
            return
        curr = self.timeline.selected_segment_idx
        if curr == -1:
            new_idx = 0
        else:
            new_idx = max(0, curr - 1)

        self.timeline.selected_segment_idx = new_idx
        self.timeline.selected_marker_idx = -1
        self.timeline.update()

        new_start = self.segments[new_idx]["start"]
        self.seek_video(new_start)
        self.calculate_stats()

    def normalize_key(self, key_code):
        cyr_to_lat = {
            1049: Qt.Key_Q,
            1062: Qt.Key_W,
            1059: Qt.Key_E,
            1050: Qt.Key_R,
            1045: Qt.Key_T,
            1053: Qt.Key_Y,
            1043: Qt.Key_U,
            1064: Qt.Key_I,
            1065: Qt.Key_O,
            1047: Qt.Key_P,
            1061: Qt.Key_BracketLeft,
            1066: Qt.Key_BracketRight,
            1060: Qt.Key_A,
            1067: Qt.Key_S,
            1099: Qt.Key_S,
            1042: Qt.Key_D,
            1040: Qt.Key_F,
            1055: Qt.Key_G,
            1056: Qt.Key_H,
            1054: Qt.Key_J,
            1051: Qt.Key_K,
            1044: Qt.Key_L,
            1046: Qt.Key_Semicolon,
            1069: Qt.Key_Apostrophe,
            1071: Qt.Key_Z,
            1063: Qt.Key_X,
            1057: Qt.Key_C,
            1052: Qt.Key_V,
            1048: Qt.Key_B,
            1058: Qt.Key_N,
            1068: Qt.Key_M,
            1041: Qt.Key_Comma,
            1070: Qt.Key_Period,
        }
        return cyr_to_lat.get(key_code, key_code)

    def keyPressEvent(self, event):
        if self.is_merge_mode:
            return super().keyPressEvent(event)

        raw_key = event.key()

        if raw_key == Qt.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            return

        k = self.normalize_key(raw_key)

        hk = self.settings.data["hotkeys"]

        if k == hk["play_pause"]:
            self.toggle_play()
        elif k == hk["mark"]:
            self.add_mark()
        elif k == hk["split"]:
            self.split_segment()
        elif k == hk["delete"]:
            self.delete_selection()
        elif k == hk["undo"] and (event.modifiers() & Qt.ControlModifier):
            self.undo_action()
        elif k == hk["frame_prev"]:
            self.step_frame(-1)
        elif k == hk["frame_next"]:
            self.step_frame(1)
        elif k == hk.get("seg_prev", Qt.Key_A):
            self.prev_segment()
        elif k == hk.get("seg_next", Qt.Key_D):
            self.next_segment()
        else:
            super().keyPressEvent(event)

    def start_merge_mode(self):
        self.is_merge_mode = True
        self.playing = False
        self.thread.stop()
        self.redraw_current_frame()
        self.overlay_widget.show()
        self.btn_merge.hide()
        self.btn_cancel_merge.show()
        self.btn_split.setEnabled(False)
        self.btn_delete.setEnabled(False)
        self.merge_buffer = []
        self.timeline.set_merge_mode(True)
        self.timeline.selected_segment_idx = -1
        self.timeline.update()

    def stop_merge_mode(self):
        self.is_merge_mode = False
        self.overlay_widget.hide()
        self.redraw_current_frame()
        self.btn_merge.show()
        self.btn_cancel_merge.hide()
        self.btn_split.setEnabled(True)
        self.btn_delete.setEnabled(True)
        self.timeline.set_merge_mode(False)
        self.timeline.update()

    def show_formulas(self):
        self.formulas_window.show()

    def get_current_context(self):
        idx = self.timeline.selected_segment_idx
        if idx == -1:
            return None
        seg = self.segments[idx]
        k = seg["end"] - seg["start"]
        t = k / self.fps if self.fps > 0 else 0
        n = len(
            [
                m
                for m in self.markers
                if seg["start"] <= m["frame"] <= seg["end"] and m.get("visible", True)
            ]
        )
        return {"n": n, "k": k, "t": t, "fps": self.fps}


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ProSportsAnalyzer()
    window.show()
    sys.exit(app.exec_())
