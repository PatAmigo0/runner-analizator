import copy
import os
import sys
import time

import cv2
from PySide6.QtCore import QMutex, Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from formulas import FormulasWindow
from timeline import TimelineWidget


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
                time.sleep(1.0 / (self.fps * self.speed))

    def stop(self):
        self._run_flag = False
        self.wait()


# --- MAIN WINDOW ---
class ProSportsAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pro Sports Analyzer v1.1")
        self.resize(1600, 950)
        self.setAcceptDrops(True)

        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; color: #fff; font-family: Segoe UI; }
            QLabel { color: #ddd; }
            QPushButton { background-color: #3a3a3a; border: 1px solid #555; padding: 6px; color: white; border-radius: 4px; }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #222; }
            QGroupBox { border: 1px solid #444; margin-top: 10px; font-weight: bold; color: #aaa; border-radius: 4px; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; }
            QLineEdit { background-color: #2b2b2b; color: #fff; padding: 4px; border: 1px solid #555; border-radius: 4px; }
            QLineEdit:focus { border: 1px solid #0078d7; }
            QListWidget { background-color: #2b2b2b; border: 1px solid #444; border-radius: 4px; }
            QDoubleSpinBox { background-color: #2b2b2b; color: #fff; padding: 4px; border: 1px solid #555; }
        """)

        # Data
        self.total_frames = 100
        self.fps = 30.0
        self.current_frame = 0
        self.playing = False
        self.playback_speed = 1.0
        self.current_ext = ""

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

        self.formulas_window = FormulasWindow(self)
        self.formulas_window.set_context_callback(self.get_current_context)

        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # TOP
        top_layout = QHBoxLayout()

        # LEFT PANEL
        left_panel = QWidget()
        left_panel.setFixedWidth(300)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # File
        gb_file = QGroupBox("Файл")
        l_file = QVBoxLayout()
        h_file = QHBoxLayout()
        self.btn_open = QPushButton("📂 Открыть")
        self.btn_open.clicked.connect(self.open_file)
        self.btn_undo = QPushButton("↶ Отмена (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.undo_action)
        h_file.addWidget(self.btn_open)
        h_file.addWidget(self.btn_undo)
        l_file.addLayout(h_file)

        self.lbl_vid_res = QLabel("Разрешение: - x -")
        self.lbl_vid_fps = QLabel("FPS: -")
        self.lbl_vid_frames = QLabel("Всего кадров: -")
        self.lbl_vid_ext = QLabel("Формат: -")
        for ll in [
            self.lbl_vid_res,
            self.lbl_vid_fps,
            self.lbl_vid_frames,
            self.lbl_vid_ext,
        ]:
            ll.setStyleSheet("color: #888; font-size: 9pt;")
            l_file.addWidget(ll)

        gb_file.setLayout(l_file)
        left_layout.addWidget(gb_file)

        # Markers
        gb_markers = QGroupBox("Настройки меток")
        l_markers = QVBoxLayout()

        self.lbl_marker_mode = QLabel("Режим: Создание")
        self.lbl_marker_mode.setStyleSheet("color: #aaa; font-style: italic;")
        l_markers.addWidget(self.lbl_marker_mode)

        h_m1 = QHBoxLayout()
        self.btn_color = QPushButton("")
        self.btn_color.setFixedSize(30, 30)
        self.btn_color.setStyleSheet(
            f"background-color: {self.current_marker_color}; border: 2px solid #fff; border-radius: 15px;"
        )
        self.btn_color.clicked.connect(self.pick_color)

        self.inp_tag = QLineEdit("Main")
        self.inp_tag.setPlaceholderText("Имя тега")
        self.inp_tag.returnPressed.connect(self.setFocus)
        self.inp_tag.textChanged.connect(self.update_marker_props_live)

        h_m1.addWidget(QLabel("Цвет:"))
        h_m1.addWidget(self.btn_color)
        h_m1.addWidget(self.inp_tag)
        l_markers.addLayout(h_m1)

        l_markers.addWidget(QLabel("Фильтр (видимость):"))
        self.list_filters = QListWidget()
        self.list_filters.setFixedHeight(120)
        self.list_filters.itemChanged.connect(self.on_filter_changed)
        self.list_filters.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        l_markers.addWidget(self.list_filters)

        gb_markers.setLayout(l_markers)
        left_layout.addWidget(gb_markers)

        # Player
        gb_play = QGroupBox("Воспроизведение")
        l_play = QVBoxLayout()
        h_speed = QHBoxLayout()
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.1, 5.0)
        self.spin_speed.setSingleStep(0.1)
        self.spin_speed.setValue(1.0)
        self.spin_speed.valueChanged.connect(self.change_speed)
        self.spin_speed.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        h_speed.addWidget(QLabel("Скорость:"))
        h_speed.addWidget(self.spin_speed)
        l_play.addLayout(h_speed)

        h_nav = QHBoxLayout()
        btn_pp = QPushButton("Play / Pause (Space)")
        btn_pp.clicked.connect(self.toggle_play)
        h_nav.addWidget(btn_pp)
        l_play.addLayout(h_nav)
        gb_play.setLayout(l_play)
        left_layout.addWidget(gb_play)

        left_layout.addStretch()
        top_layout.addWidget(left_panel)

        # 2. CENTER
        self.video_container = QWidget()
        self.video_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.stack_layout = QStackedLayout(self.video_container)
        self.stack_layout.setStackingMode(QStackedLayout.StackingMode.StackAll)

        self.video_label = QLabel("Перетащите видео файл сюда")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet(
            "background-color: #000; border: 1px solid #333;"
        )
        self.video_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        self.video_label.setScaledContents(False)
        self.stack_layout.addWidget(self.video_label)

        self.overlay_widget = QLabel("РЕЖИМ ОБЪЕДИНЕНИЯ\nВыберите два соседних отрезка")
        self.overlay_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overlay_widget.setStyleSheet(
            "background-color: rgba(0, 0, 0, 180); color: #00ff00; font-size: 24px; font-weight: bold;"
        )
        self.overlay_widget.hide()
        self.stack_layout.addWidget(self.overlay_widget)

        top_layout.addWidget(self.video_container, stretch=1)

        # 3. RIGHT
        right_panel = QWidget()
        right_panel.setFixedWidth(300)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        gb_calc = QGroupBox("Анализ")
        gb_calc.setStyleSheet("QGroupBox { border: 1px solid #00ff00; }")
        l_calc = QVBoxLayout()

        font_head = QFont("Segoe UI", 11, QFont.Weight.Bold)
        font_data = QFont("Segoe UI", 10)

        self.lbl_global_frame = QLabel("Кадр: 0")
        self.lbl_global_time = QLabel("Время: 0.00s")
        self.lbl_total_marks = QLabel("Всего меток: 0")

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #555;")

        self.lbl_info_seg = QLabel("Нет выбора")
        self.lbl_info_seg.setFont(font_head)
        self.lbl_info_seg.setStyleSheet("color: #fff; margin-top: 5px;")

        self.lbl_rel_frame = QLabel("Кадр (отр): -")
        self.lbl_rel_time = QLabel("Время (отр): -")
        self.lbl_rel_time.setStyleSheet("color: #00ffff; font-weight: bold;")
        self.lbl_seg_marks = QLabel("Метки (отр): -")

        self.lbl_tempo = QLabel("ТЕМП (SPM): 0.0")
        self.lbl_tempo.setStyleSheet(
            "color: #00ff00; font-size: 22px; font-weight: bold; margin-top: 5px;"
        )

        for w in [
            self.lbl_global_frame,
            self.lbl_global_time,
            self.lbl_total_marks,
            sep,
            self.lbl_info_seg,
            self.lbl_rel_frame,
            self.lbl_rel_time,
            self.lbl_seg_marks,
            self.lbl_tempo,
        ]:
            if isinstance(w, QLabel):
                w.setFont(font_data)
            if w == self.lbl_info_seg:
                w.setFont(font_head)
            l_calc.addWidget(w)

        gb_calc.setLayout(l_calc)
        right_layout.addWidget(gb_calc)

        # ИСПРАВЛЕНИЕ: Кнопки теперь self.
        gb_edit = QGroupBox("Действия с отрезком")
        l_edit = QVBoxLayout()
        h_edit = QHBoxLayout()

        self.btn_split = QPushButton("✂ Разрезать")
        self.btn_split.clicked.connect(self.split_segment)
        self.btn_split.setStyleSheet("background-color: #d4a017; color: black;")

        self.btn_merge = QPushButton("🔗 Объединить")
        self.btn_merge.clicked.connect(self.start_merge_mode)
        self.btn_merge.setStyleSheet("background-color: #00aa00;")

        h_edit.addWidget(self.btn_split)
        h_edit.addWidget(self.btn_merge)
        l_edit.addLayout(h_edit)

        self.btn_cancel_merge = QPushButton("❌ Отмена объединения")
        self.btn_cancel_merge.clicked.connect(self.stop_merge_mode)
        self.btn_cancel_merge.hide()
        l_edit.addWidget(self.btn_cancel_merge)

        self.btn_delete = QPushButton("🗑 Удалить выделенное")
        self.btn_delete.clicked.connect(self.delete_selection)
        self.btn_delete.setStyleSheet("background-color: #800;")
        l_edit.addWidget(self.btn_delete)

        gb_edit.setLayout(l_edit)
        right_layout.addWidget(gb_edit)

        btn_f = QPushButton("📐 Конструктор формул")
        btn_f.clicked.connect(self.show_formulas)
        btn_f.setStyleSheet("background-color: #6a0dad; padding: 8px;")
        right_layout.addWidget(btn_f)

        right_layout.addStretch()
        top_layout.addWidget(right_panel)
        main_layout.addLayout(top_layout)

        # BOTTOM
        action_bar = QHBoxLayout()
        self.btn_mark = QPushButton("🚩 ПОСТАВИТЬ МЕТКУ [M]")
        self.btn_mark.setFixedWidth(200)
        self.btn_mark.setStyleSheet(
            "background-color: #b30000; font-weight: bold; padding: 8px;"
        )
        self.btn_mark.clicked.connect(self.add_mark)
        action_bar.addWidget(self.btn_mark)

        lbl_hint = QLabel(
            "Подсказки: M - Метка | Пробел - Пауза | Стрелки - Кадры | Enter - Применить текст"
        )
        lbl_hint.setStyleSheet("color: #888; margin-left: 10px;")
        action_bar.addWidget(lbl_hint)
        main_layout.addLayout(action_bar)

        self.timeline = TimelineWidget()
        self.timeline.seek_requested.connect(self.seek_video)
        self.timeline.segment_selected.connect(self.on_timeline_click)
        self.timeline.marker_selected.connect(self.on_selection_changed)
        main_layout.addWidget(self.timeline)

        self.remove_focus_from_buttons()

    # --- CORE METHODS ---
    def mousePressEvent(self, event):
        self.setFocus()
        self.deselect_all()
        super().mousePressEvent(event)

    def remove_focus_from_buttons(self):
        for w in self.findChildren(QPushButton):
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for w in self.findChildren(QDoubleSpinBox):
            w.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        for w in self.findChildren(QLineEdit):
            w.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    # --- UNDO ---
    def save_state(self):
        if self.is_undoing:
            return
        state = {
            "segments": copy.deepcopy(self.segments),
            "markers": copy.deepcopy(self.markers),
        }
        self.history.append(state)
        if len(self.history) > 50:
            self.history.pop(0)

    def undo_action(self):
        if not self.history:
            return
        self.is_undoing = True
        state = self.history.pop()
        self.segments = state["segments"]
        self.markers = state["markers"]

        if self.timeline.selected_segment_idx >= len(self.segments):
            self.timeline.selected_segment_idx = -1
        if self.timeline.selected_marker_idx >= len(self.markers):
            self.timeline.selected_marker_idx = -1

        self.timeline.set_data(self.total_frames, self.fps, self.segments, self.markers)
        self.update_filter_list()
        self.calculate_stats()
        self.timeline.update()
        self.is_undoing = False

    # --- MARKERS ---
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
        else:
            self.current_marker_tag = tag

    def update_ui_marker_controls(self):
        idx = self.timeline.selected_marker_idx
        if idx != -1 and idx < len(self.markers):
            m = self.markers[idx]
            self.lbl_marker_mode.setText("Режим: РЕДАКТИРОВАНИЕ")
            self.lbl_marker_mode.setStyleSheet("color: #0f0; font-weight: bold;")
            self.inp_tag.blockSignals(True)
            self.inp_tag.setText(m["tag"])
            self.inp_tag.blockSignals(False)
            self.btn_color.setStyleSheet(
                f"background-color: {m['color']}; border: 2px solid #fff; border-radius: 15px;"
            )
        else:
            self.lbl_marker_mode.setText("Режим: СОЗДАНИЕ")
            self.lbl_marker_mode.setStyleSheet("color: #aaa; font-style: italic;")
            self.inp_tag.blockSignals(True)
            self.inp_tag.setText(self.current_marker_tag)
            self.inp_tag.blockSignals(False)
            self.btn_color.setStyleSheet(
                f"background-color: {self.current_marker_color}; border: 2px solid #fff; border-radius: 15px;"
            )

    def update_filter_list(self):
        tags = sorted(list(set(m["tag"] for m in self.markers)))
        checked_tags = []
        for i in range(self.list_filters.count()):
            item = self.list_filters.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked_tags.append(item.text())

        self.list_filters.clear()
        first_run = len(checked_tags) == 0 and len(tags) > 0

        for t in tags:
            item = QListWidgetItem(t)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if first_run or t in checked_tags:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            self.list_filters.addItem(item)

    def on_filter_changed(self, item):
        tag = item.text()
        visible = item.checkState() == Qt.CheckState.Checked
        for m in self.markers:
            if m["tag"] == tag:
                m["visible"] = visible
        self.timeline.update()
        self.calculate_stats()
        self.setFocus()

    # --- VIDEO ---
    def load_video(self, path):
        self.save_state()
        self.playing = False
        self.thread.stop()
        self.history = []
        self.current_ext = os.path.splitext(path)[1]
        self.thread.load_video(path)

    def set_video_info(self, info):
        self.fps = info["fps"]
        self.total_frames = info["total"]
        self.segments = [{"start": 0, "end": self.total_frames}]
        self.markers = []
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
        self.current_frame = self.thread.current_frame_num
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

        for m in self.markers:
            if m.get("visible", True) and m["frame"] == self.current_frame:
                cv2.circle(
                    frame_resized,
                    (frame_resized.shape[1] - 30, 30),
                    10,
                    QColor(m["color"]).rgb(),
                    -1,
                )

        rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
        qimg = QImage(
            rgb.data,
            frame_resized.shape[1],
            frame_resized.shape[0],
            rgb.strides[0],
            QImage.Format.Format_RGB888,
        )
        self.video_label.setPixmap(QPixmap.fromImage(qimg))
        self.timeline.set_current_frame(self.current_frame)
        self.calculate_stats()

    # --- ACTIONS ---
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
        self.thread.seek(self.current_frame)
        self.calculate_stats()

    def split_segment(self):
        if self.is_merge_mode:
            return
        idx = -1
        for i, seg in enumerate(self.segments):
            if seg["start"] < self.current_frame < seg["end"]:
                idx = i
                break
        if idx != -1:
            self.save_state()
            old = self.segments[idx]
            mid = self.current_frame
            s1 = {"start": old["start"], "end": mid}
            s2 = {"start": mid, "end": old["end"]}
            self.segments.pop(idx)
            self.segments.insert(idx, s2)
            self.segments.insert(idx, s1)
            self.timeline.selected_segment_idx = idx + 1
            self.timeline.update()
            self.calculate_stats()

    def delete_selection(self):
        if self.is_merge_mode:
            return
        if (
            self.timeline.selected_marker_idx != -1
            or self.timeline.selected_segment_idx != -1
        ):
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
                QMessageBox.warning(self, "Ошибка", "Соседние только!")
                self.merge_buffer = []
                self.timeline.merge_candidates = []
                self.timeline.update()

    def calculate_stats(self):
        self.lbl_global_frame.setText(f"Кадр: {self.current_frame}")
        self.lbl_global_time.setText(
            f"Время: {self.current_frame / self.fps:.2f}s" if self.fps > 0 else "0s"
        )
        self.lbl_total_marks.setText(f"Всего меток: {len(self.markers)}")

        if self.timeline.selected_marker_idx != -1:
            if self.timeline.selected_marker_idx < len(self.markers):
                m = self.markers[self.timeline.selected_marker_idx]
                self.lbl_info_seg.setText(f"МЕТКА: {m['tag']}")
                self.lbl_rel_time.setText(f"Время: {m['frame'] / self.fps:.3f}s")
                self.lbl_tempo.setText("")
                self.lbl_rel_frame.setText(f"Кадр: {m['frame']}")
                self.lbl_seg_marks.setText("")
            return

        idx = self.timeline.selected_segment_idx
        if idx != -1 and idx < len(self.segments):
            seg = self.segments[idx]
            s, e = seg["start"], seg["end"]

            rel_f = max(0, self.current_frame - s)
            rel_t = rel_f / self.fps if self.fps > 0 else 0

            if self.current_frame < s or self.current_frame > e:
                self.lbl_rel_time.setStyleSheet("color: #888;")
            else:
                self.lbl_rel_time.setStyleSheet("color: #00ffff; font-weight: bold;")

            self.lbl_rel_frame.setText(f"Кадр (отр): {rel_f}")
            self.lbl_rel_time.setText(f"Время (отр): {rel_t:.2f}s")

            visible_markers = [
                m
                for m in self.markers
                if s <= m["frame"] <= e and m.get("visible", True)
            ]
            n = len(visible_markers)
            k = e - s
            t = k / self.fps if self.fps > 0 else 0
            tempo = (n / t * 60) if t > 0 else 0

            self.lbl_info_seg.setText(f"Отрезок #{idx + 1} ({s}-{e})")
            self.lbl_seg_marks.setText(f"Метки (отр): {n}")
            self.lbl_tempo.setText(f"SPM: {tempo:.1f}")
        else:
            self.lbl_info_seg.setText("Нет выбора")
            self.lbl_rel_frame.setText("Кадр (отр): -")
            self.lbl_rel_time.setText("Время (отр): -")
            self.lbl_seg_marks.setText("Метки (отр): -")
            self.lbl_tempo.setText("")

    # Helpers
    def dragEnterEvent(self, event):
        event.accept() if event.mimeData().hasUrls() else event.ignore()

    def dropEvent(self, event):
        self.load_video(event.mimeData().urls()[0].toLocalFile())

    def open_file(self):
        f = QFileDialog(self)
        if f.exec():
            self.load_video(f.selectedFiles()[0])

    def on_video_finished(self):
        self.playing = False
        self.thread.stop()

    def toggle_play(self):
        if not self.thread.cap or self.is_merge_mode:
            return
        self.playing = not self.playing
        self.thread.start() if self.playing else self.thread.stop()

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

    def keyPressEvent(self, event):
        if self.is_merge_mode:
            return super().keyPressEvent(event)
        k = event.key()
        t = event.text().lower()
        if (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and k == Qt.Key.Key_Z
        ):
            self.undo_action()
            return
        if k == Qt.Key.Key_Space:
            self.toggle_play()
        elif k == Qt.Key.Key_M or t in ["m", "ь"]:
            self.add_mark()
        elif k == Qt.Key.Key_Delete:
            self.delete_selection()
        elif k == Qt.Key.Key_Left:
            self.step_frame(-1)
        elif k == Qt.Key.Key_Right:
            self.step_frame(1)
        else:
            super().keyPressEvent(event)

    def start_merge_mode(self):
        self.is_merge_mode = True
        self.playing = False
        self.thread.stop()
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
        return {
            "n": n,
            "k": k,
            "t": t,
            "fps": self.fps,
            "total_frames": self.total_frames,
        }


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ProSportsAnalyzer()
    window.show()
    sys.exit(app.exec())
