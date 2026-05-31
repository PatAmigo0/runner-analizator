# type: ignore

import os
import sys
import time
import traceback

from PySide2.QtCore import QPointF, Qt, Slot
from PySide2.QtGui import (
    QColor,
    QFont,
    QIcon,
    QKeyEvent,
)
from PySide2.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollBar,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from dialogs import (
    GeneralSettingsDialog,
    HotkeyEditor,
    ProxyProgressDialog,
    SplitDialog,
)
from drawing_manager import DrawingManager
from formulas import FormulasWindow
from settings import SettingsManager
from state_manager import StateManager
from timeline import TimelineWidget
from ui_left_panel import LeftPanelWidget
from ui_right_panel import RightPanelWidget
from ui_video_container import VideoContainerWidget
from utils import (
    apply_dark_title_bar,
    create_dark_msg_box,
    get_resource_path,
    normalize_key,
    stop_playback,
    undoable,
)
from video_engine import IS_DEBUG, ProxyGeneratorThread, logger
from video_thread import VideoThread
from viewport_handler import ViewportHandler

if IS_DEBUG:
    import PySide2

    dirname = os.path.dirname(PySide2.__file__)
    plugin_path = os.path.join(dirname, "plugins", "platforms")
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugin_path
    os.environ["OPENCV_VIDEOIO_DEBUG"] = "1"
    os.environ["OPENCV_FFMPEG_DEBUG"] = "1"
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "video_codec;h264_cuvid"

VERSION = 1.8

try:
    import ctypes

    appid = f"arseni.kuskou.prosportsanalyzer.{VERSION}.stable"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)
except ImportError:
    pass


def global_exception_hook(exctype, value, tb):
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    print("CRITICAL ERROR:", error_msg)
    try:
        if "logger" in globals():
            logger.file(f"GLOBAL CRASH: {error_msg}")
    except:
        pass
    try:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setText("Critical Error")
        msg.setInformativeText(str(value))
        msg.setDetailedText(error_msg)
        msg.exec_()
    except:
        pass
    sys.__excepthook__(exctype, value, tb)


sys.excepthook = global_exception_hook


class ProSportsAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = SettingsManager()
        self.setWindowTitle(f"Pro Sports Analyzer v{VERSION}.{int(not IS_DEBUG)}")

        self.resize(1400, 820)
        self.setAcceptDrops(True)
        apply_dark_title_bar(self)

        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; color: #f0f0f0; font-family: Segoe UI; }
            QWidget { font-size: 14px; }
            QMessageBox { background-color: #2b2b2b; color: #f0f0f0; }
            
            QGroupBox { border: 1px solid #444; margin-top: 10px; font-weight: bold; background-color: #2b2b2b; border-radius: 3px; padding-top: 15px; color: #ccc;}
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; left: 10px; top: 0px; color: #fff; }
            
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
            
            QDoubleSpinBox { background-color: #1e1e1e; color: white; border: 1px solid #555; padding: 4px; border-radius: 2px; }
            
            QSlider::groove:horizontal { border: 1px solid #444; height: 8px; background: #333; margin: 2px 0; border-radius: 4px; }
            QSlider::handle:horizontal { background: #0078d7; border: 1px solid #0078d7; width: 18px; height: 18px; margin: -6px 0; border-radius: 9px; }
            
            QProgressBar { border: 1px solid #444; text-align: center; color: white; }
            QProgressBar::chunk { background-color: #0078d7; }

            QScrollBar:horizontal { border: none; background: #1e1e1e; height: 14px; margin: 0px 0px 0px 0px; }
            QScrollBar::handle:horizontal { background: #444; min-width: 20px; border-radius: 4px; }
            QScrollBar::handle:horizontal:hover { background: #666; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: #2b2b2b; }
        """)

        # Инициализация менеджеров логики
        self.state = StateManager()
        self.drawing_manager = DrawingManager()

        self.current_frame = 0
        self.playing = False
        self.playback_speed = 1.0
        self.current_ext = ""
        self.last_frame = None

        self.is_merge_mode = False
        self.merge_buffer = []

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

        # Инициализация Viewport (передаем новый аппаратный холст)
        self.viewport = ViewportHandler(self.video_canvas)

    def init_ui(self):
        icon_path = get_resource_path("favicon.ico")
        self.setWindowIcon(QIcon(icon_path))
        cw = QWidget()
        self.setCentralWidget(cw)
        ml = QVBoxLayout(cw)
        ml.setContentsMargins(10, 5, 10, 5)
        ml.setSpacing(8)

        top_layout = QHBoxLayout()

        # --- Левая Панель ---
        self.left_panel = LeftPanelWidget()
        top_layout.addWidget(self.left_panel)

        # Маппинг и подписка
        self.btn_mark = self.left_panel.btn_mark
        self.lbl_marker_mode = self.left_panel.lbl_marker_mode
        self.btn_color = self.left_panel.btn_color
        self.inp_tag = self.left_panel.inp_tag
        self.list_filters = self.left_panel.list_filters
        self.btn_undo = self.left_panel.btn_undo
        self.btn_redo = self.left_panel.btn_redo
        self.btn_split = self.left_panel.btn_split
        self.btn_merge = self.left_panel.btn_merge
        self.btn_cancel_merge = self.left_panel.btn_cancel_merge
        self.btn_delete = self.left_panel.btn_delete
        self.btn_create_proxy_manual = self.left_panel.btn_create_proxy
        self.lbl_vid_res = self.left_panel.lbl_vid_res
        self.lbl_vid_fps = self.left_panel.lbl_vid_fps
        self.lbl_proxy_status = self.left_panel.lbl_proxy_status

        self.left_panel.btn_open.clicked.connect(self.open_file)
        self.left_panel.btn_hotkeys.clicked.connect(self.open_hotkeys_dialog)
        self.left_panel.btn_settings.clicked.connect(self.open_general_settings)
        self.btn_create_proxy_manual.clicked.connect(self.manual_create_proxy)
        self.btn_mark.clicked.connect(self.add_mark)
        self.btn_color.clicked.connect(self.pick_color)
        self.inp_tag.returnPressed.connect(self.setFocus)
        self.inp_tag.textChanged.connect(self.update_marker_props_live)
        self.list_filters.itemChanged.connect(self.on_filter_changed)
        self.btn_undo.clicked.connect(self.undo_action)
        self.btn_redo.clicked.connect(self.redo_action)
        self.btn_split.clicked.connect(self.split_segment)
        self.btn_merge.clicked.connect(self.start_merge_mode)
        self.btn_cancel_merge.clicked.connect(self.stop_merge_mode)
        self.btn_delete.clicked.connect(self.delete_selection)

        # --- Видео Контейнер ---
        self.video_container = VideoContainerWidget()
        top_layout.addWidget(self.video_container, stretch=1)

        self.video_canvas = self.video_container.video_canvas
        self.overlay_widget = self.video_container.overlay_widget

        self.video_container.wheel_scrolled.connect(self.video_wheel_event)
        self.video_container.mouse_pressed.connect(self.video_mouse_press)
        self.video_container.mouse_moved.connect(self.video_mouse_move)
        self.video_container.mouse_released.connect(self.video_mouse_release)

        # --- Правая Панель ---
        self.right_panel = RightPanelWidget()
        top_layout.addWidget(self.right_panel)

        self.lbl_global_frame = self.right_panel.lbl_global_frame
        self.lbl_global_time = self.right_panel.lbl_global_time
        self.lbl_info_seg = self.right_panel.lbl_info_seg
        self.lbl_rel_frame = self.right_panel.lbl_rel_frame
        self.lbl_rel_time = self.right_panel.lbl_rel_time
        self.lbl_seg_total_frames = self.right_panel.lbl_seg_total_frames
        self.lbl_seg_duration = self.right_panel.lbl_seg_duration
        self.lbl_seg_marks = self.right_panel.lbl_seg_marks
        self.lbl_tempo = self.right_panel.lbl_tempo
        self.spin_speed = self.right_panel.spin_speed

        self.btn_draw_none = self.right_panel.btn_draw_none
        self.btn_draw_line = self.right_panel.btn_draw_line
        self.btn_draw_angle = self.right_panel.btn_draw_angle
        self.btn_draw_erase = self.right_panel.btn_draw_erase
        self.btn_draw_clear = self.right_panel.btn_draw_clear

        self.right_panel.btn_formulas.clicked.connect(self.show_formulas)
        self.spin_speed.valueChanged.connect(self.change_speed)
        self.btn_draw_none.clicked.connect(lambda: self.set_drawing_tool("none"))
        self.btn_draw_line.clicked.connect(lambda: self.set_drawing_tool("line"))
        self.btn_draw_angle.clicked.connect(lambda: self.set_drawing_tool("angle"))
        self.btn_draw_erase.clicked.connect(lambda: self.set_drawing_tool("erase"))
        self.btn_draw_clear.clicked.connect(self.clear_drawings_frame)

        ml.addLayout(top_layout)

        # --- Нижняя часть (Timeline и Scrubber) ---
        self.scrubber = QSlider(Qt.Horizontal)
        self.scrubber.setRange(0, 100)
        self.scrubber.setEnabled(False)
        self.scrubber.sliderMoved.connect(self.on_scrubber_change)
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
        for btn in self.findChildren(QPushButton):
            btn.setFocusPolicy(Qt.ClickFocus)
        self.scrubber.setFocusPolicy(Qt.NoFocus)
        self.timeline_scroll.setFocusPolicy(Qt.NoFocus)
        self.setFocus()

    # --- INPUT EVENTS ---
    def video_wheel_event(self, event):
        self.viewport.handle_wheel(event.angleDelta().y())
        self.redraw_current_frame()

    def video_mouse_press(self, event):
        self.setFocus()
        if self.playing:
            if event.button() == Qt.LeftButton and self.viewport.zoom > 1.0:
                self.dragging_video = True
                self.last_mouse_pos = event.pos()
                self.video_container.setCursor(Qt.ClosedHandCursor)
            return

        if (
            event.button() == Qt.LeftButton
            and self.drawing_manager.current_tool != "none"
        ):
            p_orig = self.viewport.screen_to_original(
                event.pos(),
                self.last_frame.shape if self.last_frame is not None else None,
            )
            if p_orig:
                self.drawing_manager.handle_press(self.current_frame, p_orig)
                self.redraw_current_frame()
            return

        if event.button() == Qt.LeftButton and self.viewport.zoom > 1.0:
            self.dragging_video = True
            self.last_mouse_pos = event.pos()
            self.video_container.setCursor(Qt.ClosedHandCursor)

    def video_mouse_move(self, event):
        if self.playing:
            if self.dragging_video:
                delta = event.pos() - self.last_mouse_pos
                self.last_mouse_pos = event.pos()
                self.viewport.add_pan(delta.x(), delta.y())
                self.redraw_current_frame()
            return

        if self.drawing_manager.current_tool != "none":
            p_orig = self.viewport.screen_to_original(
                event.pos(),
                self.last_frame.shape if self.last_frame is not None else None,
            )
            if p_orig:
                self.drawing_manager.handle_move(p_orig)
            self.redraw_current_frame()
            return

        if self.dragging_video:
            delta = event.pos() - self.last_mouse_pos
            self.last_mouse_pos = event.pos()
            self.viewport.add_pan(delta.x(), delta.y())
            self.redraw_current_frame()

    def video_mouse_release(self, event):
        if self.playing:
            self.dragging_video = False
            self.video_container.setCursor(Qt.ArrowCursor)
            return

        if (
            event.button() == Qt.LeftButton
            and self.drawing_manager.current_tool != "none"
        ):
            self.drawing_manager.handle_release(self.current_frame)
            self.redraw_current_frame()
            return

        self.dragging_video = False
        self.video_container.setCursor(Qt.ArrowCursor)

    # --- DRAWING TOOLS ---
    def set_drawing_tool(self, tool_name):
        if self.playing:
            return
        self.drawing_manager.set_tool(tool_name)
        self.update_tool_buttons()
        self.redraw_current_frame()

    def clear_drawings_frame(self):
        if self.playing:
            return
        self.drawing_manager.clear_frame(self.current_frame)
        self.redraw_current_frame()

    def update_tool_buttons(self):
        tool = self.drawing_manager.current_tool
        self.btn_draw_none.setStyleSheet(
            "background-color: #0078d7; color: white; font-weight: bold;"
            if tool == "none"
            else ""
        )
        self.btn_draw_line.setStyleSheet(
            "background-color: #0078d7; color: white; font-weight: bold;"
            if tool == "line"
            else ""
        )
        self.btn_draw_angle.setStyleSheet(
            "background-color: #0078d7; color: white; font-weight: bold;"
            if tool == "angle"
            else ""
        )
        self.btn_draw_erase.setStyleSheet(
            "background-color: #0078d7; color: white; font-weight: bold;"
            if tool == "erase"
            else ""
        )

    # --- TIMELINE AND SCRUBBER ---
    def on_scrubber_change(self, val):
        if hasattr(self, "thread") and (
            self.thread.engine.av_container or self.thread.engine.cap
        ):
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

    # --- SETTINGS / OPEN FILE ---
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
            pre_dialog_state = self.state.capture_session_state()

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
                    if eng.cap is None and eng.av_container is None:
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

    # --- UNDO / REDO ---
    def save_state(self):
        self.state.save_state()
        self.btn_undo.setEnabled(True)

    def _sync_timeline_with_state(self):
        self.timeline.set_data(
            self.state.total_frames,
            self.state.fps,
            self.state.segments,
            self.state.markers,
        )
        self.list_filters.clear()
        self.update_filter_list()
        self.calculate_stats()
        self.redraw_current_frame()

    def undo_action(self):
        if self.state.undo():
            self._sync_timeline_with_state()
            self.btn_redo.setEnabled(True)
            self.btn_undo.setEnabled(len(self.state.history) > 0)

    def redo_action(self):
        if self.state.redo():
            self._sync_timeline_with_state()
            self.btn_redo.setEnabled(len(self.state.redo_stack) > 0)
            self.btn_undo.setEnabled(True)

    # --- MARKERS AND LOGIC ---
    def pick_color(self):
        init = self.current_marker_color
        idx = self.timeline.selected_marker_idx
        if idx != -1 and idx < len(self.state.markers):
            init = self.state.markers[idx]["color"]
        col = QColorDialog.getColor(initial=QColor(init))
        if col.isValid():
            self.apply_color(col.name())

    @undoable
    def apply_color(self, c):
        idx = self.timeline.selected_marker_idx
        if idx != -1 and idx < len(self.state.markers):
            self.state.markers[idx]["color"] = c
            self.timeline._bg_dirty = True
            self.timeline.update()
            self.redraw_current_frame()
        else:
            self.current_marker_color = c
        self.update_ui_marker_controls()

    def update_marker_props_live(self, text=""):
        t = text if text else self.inp_tag.text()

        idx = self.timeline.selected_marker_idx
        if idx != -1 and idx < len(self.state.markers):
            self.state.markers[idx]["tag"] = t
            self.timeline._bg_dirty = True
            self.timeline.update()
            self.redraw_current_frame()
        else:
            self.current_marker_tag = t

    def update_ui_marker_controls(self):
        idx = self.timeline.selected_marker_idx
        if idx != -1 and idx < len(self.state.markers):
            m = self.state.markers[idx]
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
        tags = sorted(list(set(m["tag"] for m in self.state.markers)))
        for t in tags:
            it = QListWidgetItem(t)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            is_visible = True
            for m in self.state.markers:
                if m["tag"] == t:
                    is_visible = m.get("visible", True)
                    break
            it.setCheckState(Qt.Checked if is_visible else Qt.Unchecked)
            self.list_filters.addItem(it)
        self.list_filters.blockSignals(False)

    def on_filter_changed(self, item):
        t = item.text()
        v = item.checkState() == Qt.Checked
        for m in self.state.markers:
            if m["tag"] == t:
                m["visible"] = v
        self.timeline._bg_dirty = True
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

        if eng.find_existing_proxy(path) and not eng.is_proxy_active:
            current_pos = self.current_frame
            self.check_and_load_video(path, try_proxy=True, force_proxy=True)
            if self.thread.engine.is_proxy_active:
                self.seek_video(current_pos)
                msg = create_dark_msg_box(
                    self, "Успех", "Прокси успешно подключен!", QMessageBox.Information
                )
                msg.exec_()
            return

        self._temp_state_for_reload = self.state.capture_session_state()
        self.thread.full_release()
        self.playing = False
        self.scrubber.setEnabled(False)
        self.video_canvas.frame = None
        self.video_canvas.update()

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
            self.thread.set_playing(False)

        self.current_ext = os.path.splitext(path)[1]
        use_proxy_global = self.settings.get("use_proxy", True)
        ask_to_create = self.settings.get("ask_proxy_creation", True)

        effective_try = True if force_proxy else (try_proxy and use_proxy_global)
        self.thread.load_video(path, try_proxy=effective_try)
        eng = self.thread.engine

        if not eng.is_proxy_active and not force_proxy and use_proxy_global:
            if not eng.find_existing_proxy(path) and ask_to_create:
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
                        self._temp_state_for_reload = self.state.capture_session_state()
                    self.settings.cleanup_old_proxies(name)
                    qual = self.settings.get("proxy_quality", 540)
                    gen_path = eng.generate_proxy_path(path, qual)
                    self.start_proxy_generation(path, gen_path)
                    self.thread.set_playing(False)
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
            else:
                msg = create_dark_msg_box(
                    self,
                    "Ошибка",
                    "Файл прокси пуст.\nЗагружаю оригинал.",
                    QMessageBox.Warning,
                )
                msg.exec_()
                self.thread.load_video(
                    self.thread.engine.original_path, try_proxy=False
                )
        else:
            msg = create_dark_msg_box(
                self, "Инфо", "Отменено. Загружаю оригинал.", QMessageBox.Information
            )
            msg.exec_()
            self.thread.load_video(self.thread.engine.original_path, try_proxy=False)
            if self.current_frame > 0:
                self.seek_video(self.current_frame)

        self.update_proxy_ui_status()

    def reset_session_data(self):
        self.playing = False
        if hasattr(self, "thread"):
            self.thread.set_playing(False)

        self.state.reset()
        self.btn_undo.setEnabled(False)
        self.btn_redo.setEnabled(False)

        self.merge_buffer = []
        self.is_merge_mode = False
        self.current_frame = 0
        self.viewport.reset()

        self.scrubber.setEnabled(False)
        self.scrubber.setValue(0)
        self.timeline.set_data(0, 30, [], [])

        self.video_canvas.frame = None
        self.video_canvas.update()

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
        self.drawing_manager.clear_all()

    def set_video_info(self, info):
        logger.debug(f"set_video_info: {info}")

        if self._temp_state_for_reload:
            old_fps = self._temp_state_for_reload.get("fps", info["fps"])
            self.state.load_session_state(self._temp_state_for_reload)
            if abs(info["fps"] - old_fps) > 0.1 and old_fps > 0:
                ratio = info["fps"] / old_fps
                self.state.remap_history_data(ratio)

            self.btn_undo.setEnabled(len(self.state.history) > 0)
            self.btn_redo.setEnabled(len(self.state.redo_stack) > 0)
            self._temp_state_for_reload = None
        else:
            self.state.init_video(info["total"], info["fps"])
            self.btn_undo.setEnabled(False)
            self.btn_redo.setEnabled(False)

        self.scrubber.blockSignals(True)
        self.scrubber.setRange(0, self.state.total_frames - 1)
        self.scrubber.setValue(0)
        self.scrubber.setEnabled(True)
        self.scrubber.blockSignals(False)

        self.timeline.set_data(
            self.state.total_frames,
            self.state.fps,
            self.state.segments,
            self.state.markers,
        )
        self.timeline.selected_segment_idx = 0
        self.lbl_vid_res.setText(f"Разрешение: {info['width']}x{info['height']}")
        self.lbl_vid_fps.setText(f"FPS: {self.state.fps:.2f}")

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

    # ИСПОЛЬЗУЕМ QOpenGLWidget ДЛЯ АППАРАТНОГО РЕНДЕРИНГА
    def draw_frame(self, frame):
        if frame is None:
            return

        self.video_canvas.update_data(
            frame=frame,
            idx=self.current_frame,
            markers=self.state.markers,
            dm=self.drawing_manager,
            viewport=self.viewport,
            playing=self.playing,
            merge_mode=self.is_merge_mode,
            main_win=self,
        )
        self.timeline.set_current_frame(self.current_frame)
        self.calculate_stats()

    def draw_debug_overlay_painter(self, painter, w, h):
        try:
            eng = self.thread.engine

            painter.setBrush(QColor(0, 0, 0, 180))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(10, 10, 370, 130, 5, 5)

            painter.setPen(QColor("#00ff00"))
            painter.setFont(QFont("Consolas", 11, QFont.Bold))

            backend_name = "Нет"
            decode_mode = "CPU"

            if hasattr(eng, "cap") and eng.cap and eng.cap.isOpened():
                backend_name = eng.cap.getBackendName()
                if eng.use_gpu:
                    decode_mode = "GPU (OpenCV HW)"
            elif hasattr(eng, "is_av_active") and eng.is_av_active:
                backend_name = "PyAV (FFmpeg)"
                decode_mode = (
                    "CPU (Многопоточно)"  # PyAV в данном скрипте использует CPU потоки
                )

            render_type = (
                "GPU OpenGL" if "Canvas" in type(self.video_canvas).__name__ else "CPU"
            )
            proxy_state = "ВКЛЮЧЕН (Быстро)" if eng.is_proxy_active else "ОТКЛЮЧЕН"

            stats = [
                f"Рендер   : {render_type}",
                f"Чтение   : {backend_name} | {decode_mode}",
                f"Proxy    : {proxy_state}",
                f"Кэш RAM  : {len(eng.cache)} / {eng.CACHE_SIZE} кадров",
                f"Источник : {eng.width}x{eng.height} @ {eng.fps:.1f} FPS",
            ]

            for i, text in enumerate(stats):
                painter.drawText(25, 35 + i * 22, text)

            # Визуализация кэша
            bar_h = 15
            y = h - bar_h - 15
            margin = 50
            bar_w = w - 2 * margin

            painter.setBrush(QColor(0, 0, 0, 180))
            painter.setPen(Qt.NoPen)
            painter.drawRect(margin, y, bar_w, bar_h)

            range_val = 60
            center_x = margin + bar_w / 2
            rect_w = bar_w / (range_val * 2)
            cached_keys = eng.get_cached_set()

            for offset in range(-range_val, range_val):
                abs_frame = self.current_frame + offset
                if abs_frame < 0 or abs_frame >= self.state.total_frames:
                    continue
                x = center_x + offset * rect_w
                if abs_frame in cached_keys:
                    painter.setBrush(QColor(0, 255, 0, 200))
                else:
                    painter.setBrush(QColor(255, 0, 0, 100))
                painter.drawRect(int(x), y, int(rect_w) + 1, bar_h)

            painter.setPen(QColor(255, 255, 255))
            painter.drawLine(int(center_x), y - 5, int(center_x), y + bar_h + 5)

        except Exception:
            pass

    @undoable
    def add_mark(self):
        for m in self.state.markers:
            if m["frame"] == self.current_frame:
                return
        self.state.save_state()
        new_marker = {
            "frame": self.current_frame,
            "color": self.current_marker_color,
            "tag": self.current_marker_tag,
            "visible": True,
        }
        self.state.markers.append(new_marker)
        self.state.markers.sort(key=lambda x: x["frame"])
        self.update_filter_list()
        self.timeline._bg_dirty = True
        self.timeline.update()
        self.calculate_stats()
        self.redraw_current_frame()

    @stop_playback
    def split_segment(self):
        if self.is_merge_mode:
            return
        idx = -1
        for i, seg in enumerate(self.state.segments):
            if seg["start"] <= self.current_frame < seg["end"]:
                idx = i
                break
        if idx != -1:
            dlg = SplitDialog(self)
            if dlg.exec_() == QDialog.Accepted:
                self.state.save_state()
                old = self.state.segments[idx]
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
                    self.state.segments.pop(idx)
                    self.state.segments.insert(idx, s2)
                    self.state.segments.insert(idx, s1)
                    self.timeline.selected_segment_idx = (
                        idx if dlg.choice == "left" else idx + 1
                    )
                    self.timeline._bg_dirty = True
                    self.timeline.update()
                    self.calculate_stats()
            self.setFocus()

    @undoable
    def delete_selection(self):
        if self.timeline.selected_marker_idx != -1:
            self.state.markers.pop(self.timeline.selected_marker_idx)
            self.timeline.selected_marker_idx = -1
            self.update_filter_list()
        elif self.timeline.selected_segment_idx != -1:
            idx = self.timeline.selected_segment_idx
            if len(self.state.segments) > 1:
                deleted = self.state.segments.pop(idx)
                if idx > 0:
                    self.state.segments[idx - 1]["end"] = deleted["end"]
                else:
                    self.state.segments[0]["start"] = deleted["start"]
                self.timeline.selected_segment_idx = -1
        self.timeline._bg_dirty = True
        self.timeline.update()
        self.calculate_stats()
        self.update_ui_marker_controls()
        self.redraw_current_frame()

    @undoable
    def perform_merge(self, i1, i2):
        seg1 = self.state.segments[i1]
        seg2 = self.state.segments[i2]
        new_seg = {
            "start": min(seg1["start"], seg2["start"]),
            "end": max(seg1["end"], seg2["end"]),
        }
        self.state.segments.pop(max(i1, i2))
        self.state.segments.pop(min(i1, i2))
        self.state.segments.insert(min(i1, i2), new_seg)
        self.timeline.selected_segment_idx = min(i1, i2)
        self.stop_merge_mode()
        self.timeline._bg_dirty = True
        self.timeline.update()
        self.calculate_stats()

    def deselect_all(self):
        self.timeline.selected_segment_idx = -1
        self.timeline.selected_marker_idx = -1
        self.update_ui_marker_controls()
        self.timeline._bg_dirty = True
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
        self.timeline._bg_dirty = True
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
                self.timeline._bg_dirty = True
                self.timeline.update()

    def calculate_stats(self):
        if self.scrubber.isEnabled():
            self.scrubber.blockSignals(True)
            self.scrubber.setValue(self.current_frame)
            self.scrubber.blockSignals(False)

        self.lbl_global_frame.setText(f"Кадр: {self.current_frame}")
        t = self.current_frame / self.state.fps if self.state.fps > 0 else 0
        self.lbl_global_time.setText(f"Время: {t:.2f}s")

        idx = self.timeline.selected_segment_idx
        if self.timeline.selected_marker_idx != -1:
            if self.timeline.selected_marker_idx < len(self.state.markers):
                m = self.state.markers[self.timeline.selected_marker_idx]
                self.lbl_info_seg.setText(f"МЕТКА: {m['tag']}")
                self.lbl_rel_time.setText(
                    f"Время: {m['frame'] / self.state.fps:.3f}s"
                    if self.state.fps > 0
                    else "0.000s"
                )
                self.lbl_rel_frame.setText(f"Кадр: {m['frame']}")
                self.lbl_seg_total_frames.setText("Кадров (всего): -")
                self.lbl_seg_duration.setText("Длит. (всего): -")
                self.lbl_seg_marks.setText("-")
                self.lbl_tempo.setText("")
        elif idx != -1 and idx < len(self.state.segments):
            seg = self.state.segments[idx]
            s, e = seg["start"], seg["end"]
            is_inside = s <= self.current_frame <= e
            rel_f = self.current_frame - s
            rel_t = rel_f / self.state.fps if self.state.fps > 0 else 0

            color_style_time = (
                "color: #00ffff; font-weight: bold;" if is_inside else "color: #777;"
            )
            color_style_frame = "color: #e0e0e0;" if is_inside else "color: #777;"
            suffix = "" if is_inside else " (вне)"

            k = e - s
            dur = k / self.state.fps if self.state.fps > 0 else 0
            vis_marks = [
                m
                for m in self.state.markers
                if s <= m["frame"] <= e and m.get("visible", True)
            ]
            n = len(vis_marks)
            tempo = (n / dur * 60) if (dur > 0 and self.state.fps > 0) else 0

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
        self.thread.set_playing(False)

    def toggle_play(self):
        if (
            self.thread.engine.cap is None and self.thread.engine.av_container is None
        ) or self.is_merge_mode:
            return
        self.playing = not self.playing
        if self.playing:
            self.set_drawing_tool("none")
        self.thread.set_playing(self.playing)
        if not self.playing:
            self.redraw_current_frame()

    def change_speed(self, val):
        self.playback_speed = val
        self.thread.speed = val
        self.setFocus()

    def seek_video(self, frame):
        self.current_frame = frame
        self.playing = False
        self.thread.set_playing(False)
        self.thread.seek(frame)
        self.calculate_stats()

    @stop_playback
    def step_frame(self, step):
        target = self.current_frame + step
        if 0 <= target < self.state.total_frames:
            self.thread.seek(target)
            self.calculate_stats()

    def next_segment(self):
        if not self.state.segments:
            return
        curr = self.timeline.selected_segment_idx
        new_idx = min(len(self.state.segments) - 1, curr + 1)
        self.timeline.selected_segment_idx = new_idx
        self.timeline.selected_marker_idx = -1
        self.timeline._bg_dirty = True
        self.timeline.update()
        self.seek_video(self.state.segments[new_idx]["start"])
        self.calculate_stats()

    def prev_segment(self):
        if not self.state.segments:
            return
        curr = self.timeline.selected_segment_idx
        new_idx = max(0, curr - 1)
        self.timeline.selected_segment_idx = new_idx
        self.timeline.selected_marker_idx = -1
        self.timeline._bg_dirty = True
        self.timeline.update()
        self.seek_video(self.state.segments[new_idx]["start"])
        self.calculate_stats()

    def keyPressEvent(self, event: QKeyEvent):
        if self.is_merge_mode:
            return super().keyPressEvent(event)

        raw_key = event.key()
        modifiers = event.modifiers()

        if raw_key == Qt.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
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
        self.thread.set_playing(False)
        self.redraw_current_frame()
        self.overlay_widget.show()
        self.btn_merge.hide()
        self.btn_cancel_merge.show()
        self.btn_split.setEnabled(False)
        self.btn_delete.setEnabled(False)
        self.merge_buffer = []
        self.timeline.set_merge_mode(True)
        self.timeline.selected_segment_idx = -1
        self.timeline._bg_dirty = True
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
        self.timeline._bg_dirty = True
        self.timeline.update()

    @stop_playback
    def show_formulas(self):
        self.formulas_window.show()

    def get_current_context(self):
        idx = self.timeline.selected_segment_idx
        if idx == -1:
            return None
        seg = self.state.segments[idx]
        k = seg["end"] - seg["start"]
        t = k / self.state.fps if self.state.fps > 0 else 0
        n = len(
            [
                m
                for m in self.state.markers
                if seg["start"] <= m["frame"] <= seg["end"] and m.get("visible", True)
            ]
        )
        return {"n": n, "k": k, "t": t, "fps": self.state.fps}


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app_icon = QIcon(get_resource_path("favicon.ico"))
    app.setWindowIcon(app_icon)

    window = ProSportsAnalyzer()
    window.setWindowIcon(app_icon)
    window.show()
    sys.exit(app.exec_())
