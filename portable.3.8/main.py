# type: ignore

import copy
import os
import sys
import time

import cv2
from dialogs import (
    GeneralSettingsDialog,
    HotkeyEditor,
    ProxyProgressDialog,
    SplitDialog,
)
from formulas import FormulasWindow
from PySide2.QtCore import QPointF, QRect, Qt, Slot
from PySide2.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QImage,
    QKeyEvent,
    QPainter,
    QPixmap,
)
from PySide2.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QColorDialog,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
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
    QVBoxLayout,
    QWidget,
)
from settings import SettingsManager
from timeline import TimelineWidget
from utils import (
    apply_dark_title_bar,
    create_dark_msg_box,
    get_resource_path,
    normalize_key,
    stop_playback,
    undoable,
)
from video_engine import IS_DEBUG, ProxyGeneratorThread
from video_thread import VideoThread

if IS_DEBUG:
    import PySide2

    dirname = os.path.dirname(PySide2.__file__)
    plugin_path = os.path.join(dirname, "plugins", "platforms")
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugin_path
    os.environ["OPENCV_VIDEOIO_DEBUG"] = "1"
    os.environ["OPENCV_FFMPEG_DEBUG"] = "1"
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "video_codec;h264_cuvid"

try:
    import ctypes

    appid = "arseni.kuskou.prosportsanalyzer.1.7.stable"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)
except ImportError:
    pass


class ProSportsAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = SettingsManager()
        self.setWindowTitle(f"Pro Sports Analyzer v1.7.{int(not IS_DEBUG)}")
        self.resize(1600, 950)
        self.setAcceptDrops(True)
        apply_dark_title_bar(self)

        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; color: #f0f0f0; font-family: Segoe UI; }
            QWidget { font-size: 14px; }
            QMessageBox { background-color: #2b2b2b; color: #f0f0f0; }
            QGroupBox { border: 1px solid #444; margin-top: 20px; font-weight: bold; background-color: #2b2b2b; border-radius: 3px; padding-top: 15px; color: #ccc;}
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; left: 10px; color: #fff; }
            QPushButton { background-color: #3a3a3a; border: 1px solid #555; padding: 6px 12px; color: white; border-radius: 2px; }
            QPushButton:hover { background-color: #505050; border-color: #777; }
            QPushButton:pressed { background-color: #0078d7; border-color: #0078d7; }
            QPushButton:disabled { background-color: #2a2a2a; color: #555; border-color: #333; }
            QLineEdit { background-color: #1e1e1e; color: #fff; padding: 4px; border: 1px solid #555; }
            QLineEdit:focus { border: 1px solid #0078d7; }
            QLabel { color: #e0e0e0; }
            QListWidget { background-color: #222; border: 1px solid #444; color: #ffffff; outline: none; }
            QListWidget::item:hover { background-color: #2a2a2a; }
            QListWidget::item:selected { background-color: #222; color: #ffffff; }
            
            QSlider::groove:horizontal { border: 1px solid #444; height: 8px; background: #333; margin: 2px 0; border-radius: 4px; }
            QSlider::handle:horizontal { background: #0078d7; border: 1px solid #0078d7; width: 18px; height: 18px; margin: -6px 0; border-radius: 9px; }
            
            QProgressBar { border: 1px solid #444; text-align: center; color: white; }
            QProgressBar::chunk { background-color: #0078d7; }

            /* --- СТИЛИ ДЛЯ СКРОЛЛБАРА (ТЕМНЫЙ) --- */
            QScrollBar:horizontal {
                border: none;
                background: #1e1e1e;
                height: 14px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:horizontal {
                background: #444;
                min-width: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #666;
            }
            QScrollBar::add-line:horizontal {
                width: 0px;
            }
            QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: #2b2b2b;
            }
        """)

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
        self.redo_stack = []
        self.is_undoing = False
        self.is_merge_mode = False
        self.merge_buffer = []
        self.video_zoom = 1.0
        self.video_pan = QPointF(0, 0)
        self.dragging_video = False
        self.last_mouse_pos = QPointF()
        self.current_marker_color = "#ff0000"
        self.current_marker_tag = "Main"
        self.proxy_thread = None
        self.proxy_dialog = None

        self._temp_state_for_reload = None

        self.thread = VideoThread(self.settings)
        self.thread.change_pixmap_signal.connect(self.update_image)
        self.thread.finished_signal.connect(self.on_video_finished)
        self.thread.video_info_signal.connect(self.set_video_info)

        self.formulas_window = FormulasWindow(self, self.settings.data["formulas"])
        self.formulas_window.set_context_callback(self.get_current_context)

        self.init_ui()

    def init_ui(self):
        icon_path = get_resource_path("favicon.ico")
        self.setWindowIcon(QIcon(icon_path))
        cw = QWidget()
        self.setCentralWidget(cw)
        ml = QVBoxLayout(cw)
        ml.setContentsMargins(10, 10, 10, 10)
        ml.setSpacing(10)

        top_layout = QHBoxLayout()

        # Left Panel
        lp = QWidget()
        lp.setFixedWidth(320)
        ll = QVBoxLayout(lp)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setAlignment(Qt.AlignTop)

        gb_f = QGroupBox("Файл и Управление")
        lf = QVBoxLayout()
        b_op = QPushButton("📂 Открыть видео")
        b_op.clicked.connect(self.open_file)

        h_sets = QHBoxLayout()
        b_hk = QPushButton("⌨ Клавиши")
        b_hk.clicked.connect(self.open_hotkeys_dialog)
        b_gs = QPushButton("⚙ Настройки")
        b_gs.clicked.connect(self.open_general_settings)
        h_sets.addWidget(b_hk)
        h_sets.addWidget(b_gs)

        lf.addWidget(b_op)
        lf.addLayout(h_sets)

        self.btn_create_proxy_manual = QPushButton("⚡ Создать Прокси")
        self.btn_create_proxy_manual.setStyleSheet(
            "background-color: #0078d7; font-weight: bold;"
        )
        self.btn_create_proxy_manual.hide()
        self.btn_create_proxy_manual.clicked.connect(self.manual_create_proxy)
        lf.addWidget(self.btn_create_proxy_manual)

        l_info = QVBoxLayout()
        self.lbl_vid_res = QLabel("Разрешение: -")
        self.lbl_vid_fps = QLabel("FPS: -")
        self.lbl_proxy_status = QLabel("")
        l_info.addWidget(self.lbl_vid_res)
        l_info.addWidget(self.lbl_vid_fps)
        l_info.addWidget(self.lbl_proxy_status)
        lf.addLayout(l_info)
        gb_f.setLayout(lf)
        ll.addWidget(gb_f)

        # Markers
        gb_m = QGroupBox("Метки")
        lm = QVBoxLayout()
        self.btn_mark = QPushButton("🚩 ПОСТАВИТЬ МЕТКУ")
        self.btn_mark.setMinimumHeight(40)
        self.btn_mark.setStyleSheet(
            "background-color: #b30000; font-weight: bold; font-size: 14px; border: 1px solid #f00;"
        )
        self.btn_mark.clicked.connect(self.add_mark)
        lm.addWidget(self.btn_mark)

        self.lbl_marker_mode = QLabel("Режим: Создание")
        lm.addWidget(self.lbl_marker_mode)

        h_m1 = QHBoxLayout()
        self.btn_color = QPushButton("")
        self.btn_color.setFixedSize(24, 24)
        self.btn_color.clicked.connect(self.pick_color)
        self.inp_tag = QLineEdit("Main")
        self.inp_tag.returnPressed.connect(self.setFocus)
        self.inp_tag.textChanged.connect(self.update_marker_props_live)
        h_m1.addWidget(QLabel("Цвет:"))
        h_m1.addWidget(self.btn_color)
        h_m1.addWidget(self.inp_tag)
        lm.addLayout(h_m1)

        lm.addWidget(QLabel("Список меток:"))
        self.list_filters = QListWidget()

        self.list_filters.setSelectionMode(QAbstractItemView.NoSelection)
        self.list_filters.setFocusPolicy(Qt.NoFocus)

        self.list_filters.itemChanged.connect(self.on_filter_changed)
        lm.addWidget(self.list_filters)
        gb_m.setLayout(lm)
        ll.addWidget(gb_m)

        # Actions
        gb_a = QGroupBox("Действия")
        la = QVBoxLayout()
        h_ur = QHBoxLayout()
        self.btn_undo = QPushButton("↶ Отмена")
        self.btn_undo.clicked.connect(self.undo_action)
        self.btn_redo = QPushButton("↷ Повтор")
        self.btn_redo.clicked.connect(self.redo_action)
        h_ur.addWidget(self.btn_undo)
        h_ur.addWidget(self.btn_redo)
        la.addLayout(h_ur)

        self.btn_split = QPushButton("✂ Разрезать")
        self.btn_split.clicked.connect(self.split_segment)
        self.btn_merge = QPushButton("🔗 Объединить")
        self.btn_merge.clicked.connect(self.start_merge_mode)
        self.btn_cancel_merge = QPushButton("❌ Отмена объед.")
        self.btn_cancel_merge.clicked.connect(self.stop_merge_mode)
        self.btn_cancel_merge.hide()
        self.btn_delete = QPushButton("🗑 Удалить")
        self.btn_delete.clicked.connect(self.delete_selection)

        la.addWidget(self.btn_split)
        la.addWidget(self.btn_merge)
        la.addWidget(self.btn_cancel_merge)
        la.addWidget(self.btn_delete)
        gb_a.setLayout(la)
        ll.addWidget(gb_a)

        ll.addStretch()
        top_layout.addWidget(lp)

        # Video Center
        self.video_container = QWidget()
        self.video_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_container.setStyleSheet(
            "background-color: black; border: 1px solid #333;"
        )
        self.video_container.setMouseTracking(True)
        self.video_container.wheelEvent = self.video_wheel_event
        self.video_container.mousePressEvent = self.video_mouse_press
        self.video_container.mouseMoveEvent = self.video_mouse_move
        self.video_container.mouseReleaseEvent = self.video_mouse_release

        sl = QStackedLayout(self.video_container)
        sl.setStackingMode(QStackedLayout.StackAll)
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.video_label.setScaledContents(False)
        sl.addWidget(self.video_label)

        self.overlay_widget = QLabel("РЕЖИМ ОБЪЕДИНЕНИЯ\nВЫБЕРИТЕ 2 ОТРЕЗКА")
        self.overlay_widget.setAlignment(Qt.AlignCenter)
        self.overlay_widget.setStyleSheet(
            "background-color: rgba(0, 50, 0, 200); color: #0f0; font-size: 24px; font-weight: bold;"
        )
        self.overlay_widget.hide()
        sl.addWidget(self.overlay_widget)
        top_layout.addWidget(self.video_container, stretch=1)

        # Right Panel
        rp = QWidget()
        rp.setFixedWidth(300)
        rl = QVBoxLayout(rp)
        rl.setAlignment(Qt.AlignTop)

        gb_calc = QGroupBox("Анализ")
        gb_calc.setStyleSheet("QGroupBox { border: 1px solid #0078d7; }")
        lc = QVBoxLayout()
        self.lbl_global_frame = QLabel("Кадр: 0")
        self.lbl_global_time = QLabel("Время: 0.00s")
        self.lbl_info_seg = QLabel("Нет выбора")
        self.lbl_info_seg.setStyleSheet(
            "color: #fff; font-weight: bold; font-size: 16px; margin-top: 5px;"
        )
        self.lbl_rel_frame = QLabel("Кадр (отр): -")
        self.lbl_rel_time = QLabel("Время (отр): -")
        self.lbl_rel_time.setStyleSheet("color: #00ffff; font-weight: bold;")
        self.lbl_seg_total_frames = QLabel("Кадров (всего): -")
        self.lbl_seg_duration = QLabel("Длит. (всего): -")
        self.lbl_seg_marks = QLabel("Метки (отр): -")
        self.lbl_tempo = QLabel("SPM: 0.0")
        self.lbl_tempo.setStyleSheet(
            "color: #00ff00; font-size: 22px; font-weight: bold; background: #222; padding: 5px; border-radius: 4px; margin-top: 5px;"
        )

        lc.addWidget(self.lbl_global_frame)
        lc.addWidget(self.lbl_global_time)
        lc.addWidget(self.lbl_info_seg)
        lc.addWidget(self.lbl_rel_frame)
        lc.addWidget(self.lbl_rel_time)
        lc.addWidget(self.lbl_seg_total_frames)
        lc.addWidget(self.lbl_seg_duration)
        lc.addWidget(self.lbl_seg_marks)
        lc.addWidget(self.lbl_tempo)
        gb_calc.setLayout(lc)
        rl.addWidget(gb_calc)

        btn_form = QPushButton("📐 Конструктор формул")
        btn_form.clicked.connect(self.show_formulas)
        btn_form.setStyleSheet(
            "background-color: #6a0dad; margin-top: 10px; padding: 10px;"
        )
        rl.addWidget(btn_form)

        gb_speed = QGroupBox("Скорость")
        hs = QHBoxLayout()
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.1, 5.0)
        self.spin_speed.setValue(1.0)
        self.spin_speed.setSingleStep(0.1)
        self.spin_speed.valueChanged.connect(self.change_speed)
        self.spin_speed.setFocusPolicy(Qt.ClickFocus)
        hs.addWidget(self.spin_speed)
        gb_speed.setLayout(hs)
        rl.addWidget(gb_speed)
        rl.addStretch()
        top_layout.addWidget(rp)
        ml.addLayout(top_layout)

        # Bottom
        self.scrubber = QSlider(Qt.Horizontal)
        self.scrubber.setRange(0, 100)
        self.scrubber.setEnabled(False)
        self.scrubber.valueChanged.connect(self.on_scrubber_change)
        ml.addWidget(self.scrubber)

        self.timeline = TimelineWidget()
        self.timeline.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.timeline.seek_requested.connect(self.seek_video)
        self.timeline.segment_selected.connect(self.on_timeline_click)
        self.timeline.marker_selected.connect(self.on_selection_changed)
        self.timeline.view_changed.connect(self.update_timeline_scrollbar)
        ml.addWidget(self.timeline)

        self.timeline_scroll = QScrollBar(Qt.Horizontal)
        self.timeline_scroll.setEnabled(False)
        self.timeline_scroll.valueChanged.connect(self.on_timeline_scroll)
        ml.addWidget(self.timeline_scroll)

        self.fix_focus_policies()
        self.update_ui_marker_controls()

    def fix_focus_policies(self):
        # Используем ClickFocus, чтобы кнопки можно было нажимать мышью,
        # но они не захватывали фокус при нажатии Tab.
        # Это более безопасно, чем NoFocus.
        for btn in self.findChildren(QPushButton):
            btn.setFocusPolicy(Qt.ClickFocus)
        self.scrubber.setFocusPolicy(Qt.NoFocus)
        self.timeline_scroll.setFocusPolicy(Qt.NoFocus)
        self.setFocus()

    def video_wheel_event(self, event):
        angle = event.angleDelta().y()
        MAX_ZOOM = 50.0
        MIN_ZOOM = 1.0
        ZOOM_STEP = 1.1
        if angle > 0:
            self.video_zoom *= ZOOM_STEP
        else:
            self.video_zoom /= ZOOM_STEP

        if self.video_zoom > MAX_ZOOM:
            self.video_zoom = MAX_ZOOM
        elif self.video_zoom < MIN_ZOOM:
            self.video_zoom = MIN_ZOOM
            self.video_pan = QPointF(0, 0)
        self.redraw_current_frame()

    def video_mouse_press(self, event):
        if event.button() == Qt.LeftButton and self.video_zoom > 1.0:
            self.dragging_video = True
            self.last_mouse_pos = event.pos()
            self.video_container.setCursor(Qt.ClosedHandCursor)
        self.setFocus()

    def video_mouse_move(self, event):
        if self.dragging_video:
            delta = event.pos() - self.last_mouse_pos
            self.last_mouse_pos = event.pos()
            self.video_pan += QPointF(delta.x(), delta.y())
            self.redraw_current_frame()

    def video_mouse_release(self, event):
        self.dragging_video = False
        self.video_container.setCursor(Qt.ArrowCursor)

    def on_scrubber_change(self, val):
        if hasattr(self, "thread") and self.thread.engine.cap:
            if self.scrubber.isEnabled() and not self.scrubber.signalsBlocked():
                self.seek_video(val)
        self.setFocus()

    def update_timeline_scrollbar(self, start, length, total):
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

    @stop_playback
    def open_hotkeys_dialog(self):
        dlg = HotkeyEditor(self, self.settings.data["hotkeys"])
        if dlg.exec_() == QDialog.Accepted:
            if dlg.modified:
                self.settings.data["hotkeys"] = dlg.hotkeys
                self.settings.save()
                msg = create_dark_msg_box(
                    self, "Инфо", "Настройки сохранены.", QMessageBox.Information
                )
                msg.exec_()
        self.setFocus()

    def capture_session_state(self):
        return {
            "segments": copy.deepcopy(self.segments),
            "markers": copy.deepcopy(self.markers),
            "history": copy.deepcopy(self.history),
            "redo_stack": copy.deepcopy(self.redo_stack),
            "fps": self.fps,
        }

    @stop_playback
    def open_general_settings(self):
        self.thread.stop()
        self.thread.wait()

        eng = self.thread.engine
        curr_proxy = getattr(eng, "proxy_path", None)
        original_path = getattr(eng, "original_path", None)

        pre_dialog_state = None
        current_pos = self.current_frame

        if original_path:
            pre_dialog_state = self.capture_session_state()

        dlg = GeneralSettingsDialog(self, self.settings, curr_proxy, original_path)
        result = dlg.exec_()

        if result == QDialog.Accepted:
            self.thread.update_settings_live()

            if dlg.delete_requested and original_path:
                self._temp_state_for_reload = pre_dialog_state
                self.thread.full_release()

                if self.settings.delete_single_proxy(curr_proxy):
                    msg = create_dark_msg_box(
                        self, "Готово", "Прокси удален.", QMessageBox.Information
                    )
                    msg.exec_()
                else:
                    msg = create_dark_msg_box(
                        self, "Ошибка", "Не удалось удалить файл.", QMessageBox.Warning
                    )
                    msg.exec_()

                self.check_and_load_video(original_path, force_proxy=False)
                if current_pos > 0:
                    self.seek_video(current_pos)
                return

            if dlg.need_restart and original_path:
                self._temp_state_for_reload = pre_dialog_state

                msg = create_dark_msg_box(
                    self,
                    "Перезагрузка",
                    "Настройки изменены (или файлы очищены).\nПерезагрузить видео?",
                    QMessageBox.Question,
                    QMessageBox.Yes | QMessageBox.No,
                )

                if msg.exec_() == QMessageBox.Yes:
                    if self.settings.get("proxy_quality") != dlg.old_quality:
                        name, _ = os.path.splitext(os.path.basename(original_path))
                        self.settings.cleanup_old_proxies(name)

                    self.check_and_load_video(original_path)
                    if current_pos > 0:
                        self.seek_video(current_pos)
                else:
                    if eng.cap is None or not eng.cap.isOpened():
                        self.check_and_load_video(original_path)
                        self.seek_video(current_pos)

            elif not dlg.delete_requested and not dlg.need_restart:
                msg = create_dark_msg_box(
                    self, "Инфо", "Настройки сохранены.", QMessageBox.Information
                )
                msg.exec_()

        self.setFocus()

    def closeEvent(self, event):
        self.thread.stop()
        forms = self.formulas_window.get_formulas()
        self.settings.data["formulas"] = forms
        self.settings.save()
        super().closeEvent(event)

    def undo_action(self):
        if not self.history:
            return
        self.redo_stack.append(
            {
                "segments": copy.deepcopy(self.segments),
                "markers": copy.deepcopy(self.markers),
            }
        )
        self.is_undoing = True
        state = self.history.pop()

        if not state["segments"] and self.total_frames > 0:
            self.segments = [{"start": 0, "end": self.total_frames}]
        else:
            self.segments = state["segments"]

        self.markers = state["markers"]
        self.timeline.set_data(self.total_frames, self.fps, self.segments, self.markers)
        self.update_filter_list()
        self.calculate_stats()
        self.redraw_current_frame()
        self.is_undoing = False
        self.btn_redo.setEnabled(True)
        self.btn_undo.setEnabled(len(self.history) > 0)

    def redo_action(self):
        if not self.redo_stack:
            return
        self.history.append(
            {
                "segments": copy.deepcopy(self.segments),
                "markers": copy.deepcopy(self.markers),
            }
        )
        self.is_undoing = True
        state = self.redo_stack.pop()
        self.segments = state["segments"]
        self.markers = state["markers"]
        self.timeline.set_data(self.total_frames, self.fps, self.segments, self.markers)
        self.update_filter_list()
        self.calculate_stats()
        self.redraw_current_frame()
        self.is_undoing = False
        self.btn_redo.setEnabled(len(self.redo_stack) > 0)
        self.btn_undo.setEnabled(True)

    def save_state(self):
        if self.is_undoing:
            return
        self.redo_stack.clear()
        self.btn_redo.setEnabled(False)
        self.history.append(
            {
                "segments": copy.deepcopy(self.segments),
                "markers": copy.deepcopy(self.markers),
            }
        )
        if len(self.history) > 1000:
            self.history.pop(0)
        self.btn_undo.setEnabled(True)

    def pick_color(self):
        init = self.current_marker_color
        idx = self.timeline.selected_marker_idx
        if idx != -1 and idx < len(self.markers):
            init = self.markers[idx]["color"]
        col = QColorDialog.getColor(initial=QColor(init))
        if col.isValid():
            self.apply_color(col.name())

    @undoable
    def apply_color(self, c):
        idx = self.timeline.selected_marker_idx
        if idx != -1 and idx < len(self.markers):
            self.markers[idx]["color"] = c
            self.timeline.update()
            self.redraw_current_frame()
        else:
            self.current_marker_color = c
        self.update_ui_marker_controls()

    def update_marker_props_live(self):
        t = self.inp_tag.text()
        idx = self.timeline.selected_marker_idx
        if idx != -1 and idx < len(self.markers):
            self.markers[idx]["tag"] = t
            self.timeline.update()
            self.redraw_current_frame()
        else:
            self.current_marker_tag = t

    def update_ui_marker_controls(self):
        idx = self.timeline.selected_marker_idx
        if idx != -1 and idx < len(self.markers):
            m = self.markers[idx]
            self.lbl_marker_mode.setText("Режим: ИЗМЕНЕНИЕ")
            self.lbl_marker_mode.setStyleSheet("color: #0f0; font-weight: bold;")
            self.inp_tag.blockSignals(True)
            self.inp_tag.setText(m["tag"])
            self.inp_tag.blockSignals(False)
            self.btn_color.setStyleSheet(
                f"background-color: {m['color']}; border: 1px solid #fff; border-radius: 12px;"
            )
        else:
            self.lbl_marker_mode.setText("Режим: СОЗДАНИЕ")
            self.lbl_marker_mode.setStyleSheet("color: #888; font-style: italic;")
            self.inp_tag.blockSignals(True)
            self.inp_tag.setText(self.current_marker_tag)
            self.inp_tag.blockSignals(False)
            self.btn_color.setStyleSheet(
                f"background-color: {self.current_marker_color}; border: 1px solid #fff; border-radius: 12px;"
            )

    def update_filter_list(self):
        self.list_filters.blockSignals(True)
        self.list_filters.clear()

        tags = sorted(list(set(m["tag"] for m in self.markers)))

        for t in tags:
            it = QListWidgetItem(t)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)

            is_visible = True
            for m in self.markers:
                if m["tag"] == t:
                    is_visible = m.get("visible", True)
                    break

            it.setCheckState(Qt.Checked if is_visible else Qt.Unchecked)
            self.list_filters.addItem(it)

        self.list_filters.blockSignals(False)

    def on_filter_changed(self, item):
        t = item.text()
        v = item.checkState() == Qt.Checked
        for m in self.markers:
            if m["tag"] == t:
                m["visible"] = v
        self.timeline.update()
        self.calculate_stats()
        self.redraw_current_frame()
        self.setFocus()

    def open_file(self):
        start_dir = self.settings.get("last_dir", "")
        f, _ = QFileDialog.getOpenFileName(self, "Открыть видео", start_dir)
        if f:
            self.settings.set("last_dir", os.path.dirname(f))
            self.settings.save()
            self.check_and_load_video(f)
        self.activateWindow()
        self.setFocus()

    def manual_create_proxy(self):
        if not self.thread.engine.original_path:
            return

        path = self.thread.engine.original_path
        eng = self.thread.engine

        proxy_exists = eng.find_existing_proxy(path)
        is_active = eng.is_proxy_active

        if proxy_exists and not is_active:
            current_pos = self.current_frame
            self.check_and_load_video(path, try_proxy=True, force_proxy=True)

            if self.thread.engine.is_proxy_active:
                self.seek_video(current_pos)
                msg = create_dark_msg_box(
                    self, "Успех", "Прокси успешно подключен!", QMessageBox.Information
                )
                msg.exec_()
            return

        self._temp_state_for_reload = self.capture_session_state()
        self.thread.full_release()
        self.playing = False
        self.scrubber.setEnabled(False)
        self.video_label.clear()

        name, _ = os.path.splitext(os.path.basename(path))
        self.settings.cleanup_old_proxies(name)

        try:
            qual = self.settings.get("proxy_quality", 540)
            proxy_path = eng.generate_proxy_path(path, qual)
        except AttributeError:
            return

        self.start_proxy_generation(path, proxy_path)

    def check_and_load_video(self, path, try_proxy=True, force_proxy=False):
        if not self._temp_state_for_reload:
            self.reset_session_data()
        else:
            self.playing = False
            self.thread.stop()
            self.thread.wait()

        self.current_ext = os.path.splitext(path)[1]

        use_proxy_global = self.settings.get("use_proxy", True)
        ask_to_create = self.settings.get("ask_proxy_creation", True)

        if force_proxy:
            effective_try = True
        else:
            effective_try = try_proxy and use_proxy_global

        self.thread.load_video(path, try_proxy=effective_try)

        eng = self.thread.engine

        if not eng.is_proxy_active and not force_proxy and use_proxy_global:
            proxy_exists = eng.find_existing_proxy(path)

            if not proxy_exists and ask_to_create:
                msg = create_dark_msg_box(
                    self,
                    "Создание Proxy",
                    "Для этого видео нет оптимизированной копии.\nСоздать?",
                    QMessageBox.Question,
                    QMessageBox.Yes | QMessageBox.No,
                )
                if msg.exec_() == QMessageBox.Yes:
                    name, _ = os.path.splitext(os.path.basename(path))
                    if not self._temp_state_for_reload:
                        self._temp_state_for_reload = self.capture_session_state()

                    self.settings.cleanup_old_proxies(name)
                    qual = self.settings.get("proxy_quality", 540)
                    gen_path = eng.generate_proxy_path(path, qual)

                    self.start_proxy_generation(path, gen_path)
                    self.thread.stop()
                    self.update_proxy_ui_status()
                    return

        self.update_proxy_ui_status()

    def start_proxy_generation(self, input_path, output_path):
        self.proxy_dialog = ProxyProgressDialog(self)
        target_h = self.settings.get("proxy_quality", 540)
        self.proxy_thread = ProxyGeneratorThread(
            input_path, output_path, target_height=target_h
        )
        self.proxy_thread.progress_signal.connect(self.proxy_dialog.set_progress)
        self.proxy_thread.finished_signal.connect(self.on_proxy_finished)
        self.proxy_thread.start()

        if self.proxy_dialog.exec_() == QDialog.Rejected:
            self.proxy_thread.stop()
            self.proxy_thread.wait()

    def on_proxy_finished(self, success, proxy_path):
        if self.proxy_dialog:
            self.proxy_dialog.accept()

        if success:
            time.sleep(0.5)

            if os.path.exists(proxy_path) and os.path.getsize(proxy_path) > 1000:
                msg = create_dark_msg_box(
                    self, "Успех", "Proxy создан и подключен!", QMessageBox.Information
                )
                msg.exec_()

                self.thread.load_video(self.thread.engine.original_path, try_proxy=True)

                if self.current_frame > 0:
                    self.seek_video(self.current_frame)

                self.update_proxy_ui_status()
            else:
                msg = create_dark_msg_box(
                    self,
                    "Ошибка",
                    "Файл прокси пуст или недоступен.\nЗагружаю оригинал.",
                    QMessageBox.Warning,
                )
                msg.exec_()
                self.thread.load_video(
                    self.thread.engine.original_path, try_proxy=False
                )
        else:
            msg = create_dark_msg_box(
                self,
                "Инфо",
                "Операция отменена. Загружаю оригинал.",
                QMessageBox.Information,
            )
            msg.exec_()
            self.thread.load_video(self.thread.engine.original_path, try_proxy=False)
            if self.current_frame > 0:
                self.seek_video(self.current_frame)

        self.update_proxy_ui_status()

    def reset_session_data(self):
        self.playing = False
        if hasattr(self, "thread"):
            self.thread.stop()
            self.thread.wait()

        self.segments = []
        self.markers = []
        self.history = []
        self.redo_stack = []
        self.btn_undo.setEnabled(False)
        self.btn_redo.setEnabled(False)
        self.merge_buffer = []
        self.is_merge_mode = False
        self.current_frame = 0
        self.total_frames = 0
        self.fps = 30.0
        self.last_frame = None
        self.video_zoom = 1.0
        self.video_pan = QPointF(0, 0)
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
        self.timeline_scroll.setEnabled(False)
        self.calculate_stats()
        self.lbl_proxy_status.setText("")
        self.btn_create_proxy_manual.hide()

    def _remap_history_data(self, history_list, ratio):
        for state in history_list:
            if "segments" in state:
                for seg in state["segments"]:
                    seg["start"] = int(seg["start"] * ratio)
                    seg["end"] = int(seg["end"] * ratio)

            if "markers" in state:
                for mark in state["markers"]:
                    mark["frame"] = int(mark["frame"] * ratio)

    def set_video_info(self, info):
        print(f"[DEBUG] set_video_info called: {info}")
        self.fps = info["fps"]
        self.total_frames = info["total"]

        if self._temp_state_for_reload:
            old_fps = self._temp_state_for_reload.get("fps", self.fps)

            saved_segments = self._temp_state_for_reload["segments"]
            saved_markers = self._temp_state_for_reload["markers"]
            saved_history = self._temp_state_for_reload["history"]
            saved_redo = self._temp_state_for_reload["redo_stack"]

            # Prevent drift: Only remap if FPS difference is significant
            if abs(self.fps - old_fps) > 0.1 and old_fps > 0:
                ratio = self.fps / old_fps
                print(
                    f"FPS changed: {old_fps:.2f} -> {self.fps:.2f}. Remapping history."
                )

                for seg in saved_segments:
                    seg["start"] = int(seg["start"] * ratio)
                    seg["end"] = int(seg["end"] * ratio)

                for mark in saved_markers:
                    mark["frame"] = int(mark["frame"] * ratio)

                self._remap_history_data(saved_history, ratio)
                self._remap_history_data(saved_redo, ratio)

            self.segments = saved_segments
            self.markers = saved_markers
            self.history = saved_history
            self.redo_stack = saved_redo

            self.btn_undo.setEnabled(len(self.history) > 0)
            self.btn_redo.setEnabled(len(self.redo_stack) > 0)

            self._temp_state_for_reload = None

        else:
            self.segments = [{"start": 0, "end": self.total_frames}]
            self.markers = []
            self.history = []
            self.redo_stack = []
            self.btn_undo.setEnabled(False)
            self.btn_redo.setEnabled(False)

        self.scrubber.blockSignals(True)
        self.scrubber.setRange(0, self.total_frames - 1)
        self.scrubber.setValue(0)
        self.scrubber.setEnabled(True)
        self.scrubber.blockSignals(False)

        self.timeline.set_data(self.total_frames, self.fps, self.segments, self.markers)
        self.timeline.selected_segment_idx = 0
        self.lbl_vid_res.setText(f"Разрешение: {info['width']}x{info['height']}")
        self.lbl_vid_fps.setText(f"FPS: {self.fps:.2f}")

        self.update_proxy_ui_status()
        self.calculate_stats()
        self.setFocus()

    def update_proxy_ui_status(self):
        eng = self.thread.engine

        if not eng.original_path:
            self.lbl_proxy_status.setText("")
            self.btn_create_proxy_manual.hide()
            return

        proxy_exists = eng.find_existing_proxy(eng.original_path)

        if eng.is_proxy_active:
            self.lbl_proxy_status.setText("🚀 PROXY АКТИВЕН")
            self.lbl_proxy_status.setStyleSheet("color: #0f0; font-weight: bold;")

            self.btn_create_proxy_manual.setText("⚡ Пересоздать Прокси")
            self.btn_create_proxy_manual.setStyleSheet(
                "background-color: #5a7; font-weight: bold; color: #000;"
            )
            self.btn_create_proxy_manual.show()

        else:
            if proxy_exists:
                self.lbl_proxy_status.setText("🐢 ОРИГИНАЛ (Прокси найден)")
                self.lbl_proxy_status.setStyleSheet("color: #fa0; font-weight: bold;")

                self.btn_create_proxy_manual.setText("🔗 Подключить Прокси")
                self.btn_create_proxy_manual.setStyleSheet(
                    "background-color: #0078d7; font-weight: bold; color: #fff;"
                )
                self.btn_create_proxy_manual.show()
            else:
                self.lbl_proxy_status.setText("🐢 ОРИГИНАЛ")
                self.lbl_proxy_status.setStyleSheet("color: #aaa; font-weight: bold;")

                self.btn_create_proxy_manual.setText("⚡ Создать Прокси")
                self.btn_create_proxy_manual.setStyleSheet(
                    "background-color: #444; border: 1px solid #666; color: #fff;"
                )

                self.btn_create_proxy_manual.show()

    @Slot(object)
    def update_image(self, frame):
        self.last_frame = frame
        self.current_frame = self.thread.current_frame_num
        self.draw_frame(frame)

    def redraw_current_frame(self):
        if self.last_frame is not None:
            self.draw_frame(self.last_frame)

    def draw_frame(self, frame):
        # print("[DEBUG] draw_frame called")
        if frame is None:
            return
        h_orig, w_orig, ch = frame.shape
        lbl_w = self.video_label.width()
        lbl_h = self.video_label.height()
        if lbl_w <= 1 or lbl_h <= 1:
            return

        if self.video_zoom > 1.0:
            visible_w = w_orig / self.video_zoom
            visible_h = h_orig / self.video_zoom
            cx = w_orig / 2.0 - self.video_pan.x()
            cy = h_orig / 2.0 - self.video_pan.y()
            x1 = cx - visible_w / 2.0
            y1 = cy - visible_h / 2.0
            x2 = x1 + visible_w
            y2 = y1 + visible_h
            if x1 < 0:
                x2 -= x1
                x1 = 0
            if y1 < 0:
                y2 -= y1
                y1 = 0
            if x2 > w_orig:
                x1 -= x2 - w_orig
                x2 = w_orig
            if y2 > h_orig:
                y1 -= y2 - h_orig
                y2 = h_orig
            x1, y1 = max(0, int(x1)), max(0, int(y1))
            x2, y2 = min(w_orig, int(x2)), min(h_orig, int(y2))
            if (x2 - x1) < 2 or (y2 - y1) < 2:
                cropped = frame
            else:
                cropped = frame[y1:y2, x1:x2]
        else:
            cropped = frame

        src_h, src_w = cropped.shape[:2]
        if src_w == 0 or src_h == 0:
            return
        aspect = src_w / src_h
        if lbl_w / lbl_h > aspect:
            target_h = lbl_h
            target_w = int(lbl_h * aspect)
        else:
            target_w = lbl_w
            target_h = int(lbl_w / aspect)

        if self.video_zoom > 3.0:
            interp = cv2.INTER_NEAREST
        elif self.video_zoom < 1.0:
            interp = cv2.INTER_AREA
        else:
            interp = cv2.INTER_LINEAR

        try:
            frame_resized = cv2.resize(
                cropped, (target_w, target_h), interpolation=interp
            )
        except cv2.error:
            print("[DEBUG] cv2.error in resize")
            return

        # print("[DEBUG] converting color")
        rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)

        # Safer QImage creation without immediate .copy() on potentially unstable memory
        # We also explicitly calculate bytesPerLine to avoid Stride mismatch crashes
        height, width, channel = rgb.shape
        bytesPerLine = 3 * width

        # print(f"[DEBUG] Creating QImage: {width}x{height}, line={bytesPerLine}")

        # NOTE: We keep a reference to 'rgb' only as long as qimg is needed for conversion
        # QPixmap.fromImage makes a deep copy into video memory immediately
        qimg = QImage(rgb.data, width, height, bytesPerLine, QImage.Format_RGB888)

        # print("[DEBUG] Creating Pixmap")
        pixmap = QPixmap.fromImage(qimg)

        # print("[DEBUG] Starting Painter")
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        for m in self.markers:
            if m.get("visible", True) and m["frame"] == self.current_frame:
                tag_text = f"🚩 {m.get('tag', 'Mark')}"
                font = QFont("Segoe UI", 16, QFont.Bold)
                painter.setFont(font)
                metrics = painter.fontMetrics()
                text_w = metrics.horizontalAdvance(tag_text)
                text_h = metrics.height()
                pad = 10
                box_x = pixmap.width() - (text_w + pad * 2) - 20
                box_y = 20
                painter.setBrush(QBrush(QColor(m["color"])))
                painter.setPen(Qt.white)
                painter.drawRoundedRect(
                    box_x, box_y, text_w + pad * 2, text_h + pad, 5, 5
                )
                painter.drawText(
                    QRect(box_x, box_y, text_w + pad * 2, text_h + pad),
                    Qt.AlignCenter,
                    tag_text,
                )
                break

        if not self.playing and not self.is_merge_mode:
            self.draw_overlay_text(painter, "⏸ ПАУЗА", 20, 20)

        if self.video_zoom > 1.01:
            self.draw_overlay_text(
                painter,
                f"ZOOM: {self.video_zoom:.1f}x",
                20,
                pixmap.height() - 50,
                bg_alpha=100,
            )

        from video_engine import IS_DEBUG

        if IS_DEBUG:
            # print("[DEBUG] Drawing debug overlay")
            self.draw_debug_overlay(painter, pixmap.width(), pixmap.height())

        painter.end()
        # print("[DEBUG] Setting Pixmap")
        self.video_label.setPixmap(pixmap)
        self.timeline.set_current_frame(self.current_frame)
        self.calculate_stats()
        # print("[DEBUG] draw_frame finished")

    def draw_debug_overlay(self, painter, w, h):
        # Replaced Mutex Lock with Try/Except
        # Locking mutex from UI thread while Video thread is running causes deadlocks/crashes
        try:
            bar_h = 20
            y = h - bar_h - 10
            margin = 50
            bar_w = w - 2 * margin

            painter.setBrush(QColor(0, 0, 0, 150))
            painter.setPen(Qt.NoPen)
            painter.drawRect(margin, y, bar_w, bar_h)

            range_val = 60
            center_x = margin + bar_w / 2

            eng = self.thread.engine

            rect_w = bar_w / (range_val * 2)

            for offset in range(-range_val, range_val):
                abs_frame = self.current_frame + offset
                if abs_frame < 0 or abs_frame >= self.total_frames:
                    continue

                x = center_x + offset * rect_w

                if abs_frame in eng.cache_index_map:
                    painter.setBrush(QColor(0, 255, 0, 200))
                else:
                    painter.setBrush(QColor(255, 0, 0, 100))

                painter.drawRect(int(x), y, int(rect_w) + 1, bar_h)

            painter.setPen(QColor(255, 255, 255))
            painter.drawLine(int(center_x), y - 5, int(center_x), y + bar_h + 5)

            painter.setPen(Qt.white)
            font = QFont("Arial", 10)
            painter.setFont(font)

            painter.drawText(
                margin, y - 10, f"Cache: {len(eng.cache)}/{eng.CACHE_SIZE}"
            )
        except RuntimeError:
            # Dictionary changed size during iteration, just skip this frame's debug
            pass
        except Exception as e:
            print(f"[DEBUG] Overlay error: {e}")

    def draw_overlay_text(self, painter, text, x, y, bg_alpha=150):
        font = QFont("Segoe UI", 16, QFont.Bold)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        w = metrics.horizontalAdvance(text) + 20
        h = metrics.height() + 10
        painter.setBrush(QBrush(QColor(0, 0, 0, bg_alpha)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(x, y, w, h, 5, 5)
        painter.setPen(Qt.white)
        painter.drawText(QRect(x, y, w, h), Qt.AlignCenter, text)

    @undoable
    def add_mark(self):
        for m in self.markers:
            if m["frame"] == self.current_frame:
                return
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

    @stop_playback
    def split_segment(self):
        if self.is_merge_mode:
            return
        idx = -1
        for i, seg in enumerate(self.segments):
            if seg["start"] <= self.current_frame < seg["end"]:
                idx = i
                break
        if idx != -1:
            dlg = SplitDialog(self)
            if dlg.exec_() == QDialog.Accepted:
                self.save_state()
                old = self.segments[idx]
                mid = self.current_frame
                if dlg.choice == "left":
                    s1 = {"start": old["start"], "end": mid + 1}
                    s2 = {"start": mid + 1, "end": old["end"]}
                else:
                    s1 = {"start": old["start"], "end": mid}
                    s2 = {"start": mid, "end": old["end"]}

                if s1["end"] <= s1["start"] or s2["end"] <= s2["start"]:
                    msg = create_dark_msg_box(
                        self,
                        "Ошибка",
                        "Нельзя разрезать на самом краю!",
                        QMessageBox.Warning,
                    )
                    msg.exec_()
                else:
                    self.segments.pop(idx)
                    self.segments.insert(idx, s2)
                    self.segments.insert(idx, s1)
                    self.timeline.selected_segment_idx = (
                        idx if dlg.choice == "left" else idx + 1
                    )
                    self.timeline.update()
                    self.calculate_stats()
            self.setFocus()

    @undoable
    def delete_selection(self):
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

    @undoable
    def perform_merge(self, i1, i2):
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
                msg = create_dark_msg_box(
                    self,
                    "Ошибка",
                    "Можно объединять только соседние!",
                    QMessageBox.Warning,
                )
                msg.exec_()
                self.merge_buffer = []
                self.timeline.merge_candidates = []
                self.timeline.update()

    def calculate_stats(self):
        if self.scrubber.isEnabled():
            self.scrubber.blockSignals(True)
            self.scrubber.setValue(self.current_frame)
            self.scrubber.blockSignals(False)

        self.lbl_global_frame.setText(f"Кадр: {self.current_frame}")
        t = self.current_frame / self.fps if self.fps > 0 else 0
        self.lbl_global_time.setText(f"Время: {t:.2f}s")

        idx = self.timeline.selected_segment_idx
        if self.timeline.selected_marker_idx != -1:
            if self.timeline.selected_marker_idx < len(self.markers):
                m = self.markers[self.timeline.selected_marker_idx]
                self.lbl_info_seg.setText(f"МЕТКА: {m['tag']}")
                # [FIX] Protect division by zero
                if self.fps > 0:
                    self.lbl_rel_time.setText(f"Время: {m['frame'] / self.fps:.3f}s")
                else:
                    self.lbl_rel_time.setText("Время: 0.000s")

                self.lbl_rel_frame.setText(f"Кадр: {m['frame']}")
                self.lbl_seg_total_frames.setText("Кадров (всего): -")
                self.lbl_seg_duration.setText("Длит. (всего): -")
                self.lbl_seg_marks.setText("-")
                self.lbl_tempo.setText("")
        elif idx != -1 and idx < len(self.segments):
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

            # Safe division for tempo
            tempo = (n / dur * 60) if (dur > 0 and self.fps > 0) else 0

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

    def on_video_finished(self):
        self.playing = False
        self.redraw_current_frame()
        self.thread.stop()

    def toggle_play(self):
        if not self.thread.engine.cap or self.is_merge_mode:
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

    @stop_playback
    def step_frame(self, step):
        target = self.current_frame + step
        if 0 <= target < self.total_frames:
            self.thread.seek(target)
            self.calculate_stats()

    def next_segment(self):
        if not self.segments:
            return
        curr = self.timeline.selected_segment_idx
        new_idx = min(len(self.segments) - 1, curr + 1)
        self.timeline.selected_segment_idx = new_idx
        self.timeline.selected_marker_idx = -1
        self.timeline.update()
        self.seek_video(self.segments[new_idx]["start"])
        self.calculate_stats()

    def prev_segment(self):
        if not self.segments:
            return
        curr = self.timeline.selected_segment_idx
        new_idx = max(0, curr - 1)
        self.timeline.selected_segment_idx = new_idx
        self.timeline.selected_marker_idx = -1
        self.timeline.update()
        self.seek_video(self.segments[new_idx]["start"])
        self.calculate_stats()

    def mousePressEvent(self, event):
        focused_widget = QApplication.focusWidget()
        if isinstance(focused_widget, QLineEdit) or isinstance(
            focused_widget, QDoubleSpinBox
        ):
            focused_widget.clearFocus()
            self.setFocus()
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if self.is_merge_mode:
            return super().keyPressEvent(event)

        raw_key = event.key()
        modifiers = event.modifiers()

        if raw_key == Qt.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            return

        norm_key = normalize_key(raw_key)
        full_code = int(modifiers | norm_key)
        hk = self.settings.data["hotkeys"]

        if full_code == hk["play_pause"]:
            self.toggle_play()
        elif full_code == hk["mark"]:
            self.add_mark()
        elif full_code == hk["split"]:
            self.split_segment()
        elif full_code == hk["delete"]:
            self.delete_selection()
        elif full_code == hk["undo"]:
            self.undo_action()
        elif full_code == hk.get("redo", int(Qt.CTRL | Qt.Key_Y)):
            self.redo_action()
        elif full_code == hk["frame_prev"]:
            self.step_frame(-1)
        elif full_code == hk["frame_next"]:
            self.step_frame(1)
        elif full_code == hk.get("seg_prev", Qt.Key_A):
            self.prev_segment()
        elif full_code == hk.get("seg_next", Qt.Key_D):
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

    @stop_playback
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

    app_icon = QIcon(get_resource_path("favicon.ico"))
    app.setWindowIcon(app_icon)

    window = ProSportsAnalyzer()
    window.setWindowIcon(app_icon)
    window.show()
    sys.exit(app.exec_())
