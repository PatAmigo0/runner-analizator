from PySide2.QtCore import QRect, Qt, Signal
from PySide2.QtGui import QBrush, QColor, QFont, QImage, QPainter
from PySide2.QtWidgets import (
    QLabel,
    QOpenGLWidget,
    QSizePolicy,
    QStackedLayout,
    QWidget,
)

from video_engine import IS_DEBUG


class VideoCanvas(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.frame = None
        self.current_frame_idx = 0
        self.markers = []
        self.drawing_manager = None
        self.viewport = None
        self.playing = False
        self.is_merge_mode = False
        self.zoom = 1.0
        self.main_window = None

    def update_data(
        self, frame, idx, markers, dm, viewport, playing, merge_mode, main_win
    ):
        self.frame = frame
        self.current_frame_idx = idx
        self.markers = markers
        self.drawing_manager = dm
        self.viewport = viewport
        self.playing = playing
        self.is_merge_mode = merge_mode
        self.zoom = viewport.zoom if viewport else 1.0
        self.main_window = main_win
        self.update()  # Запрашивает перерисовку у видеокарты

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), Qt.black)

        if self.frame is None or self.viewport is None:
            painter.end()
            return

        h, w, _ = self.frame.shape
        params = self.viewport.get_mapping_params(h, w)
        if not params:
            painter.end()
            return

        # ИЗБЕГАЕМ cv2.cvtColor! Передаем сырые BGR байты напрямую
        try:
            qimg = QImage(
                self.frame.data, w, h, self.frame.strides[0], QImage.Format_BGR888
            )
        except AttributeError:
            # Fallback для старых версий PySide2 (или сломанной среды)
            import cv2

            rgb = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888)

        # АППАРАТНЫЙ Crop & Resize силами QOpenGLWidget!
        source_rect = QRect(
            int(params["x1"]),
            int(params["y1"]),
            int(params["src_w"]),
            int(params["src_h"]),
        )
        target_rect = QRect(
            int(params["x_offset"]),
            int(params["y_offset"]),
            int(params["target_w"]),
            int(params["target_h"]),
        )

        painter.drawImage(target_rect, qimg, source_rect)

        # --- Отрисовка маркеров поверх видео ---
        for m in self.markers:
            if m.get("visible", True) and m["frame"] == self.current_frame_idx:
                tag_text = f"🚩 {m.get('tag', 'Mark')}"
                font = QFont("Segoe UI", 16, QFont.Bold)
                painter.setFont(font)
                metrics = painter.fontMetrics()
                text_w = metrics.horizontalAdvance(tag_text)
                text_h = metrics.height()
                pad = 10
                box_x = self.width() - (text_w + pad * 2) - 20
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

        # --- Отрисовка текста (ПАУЗА / ZOOM) ---
        if not self.playing and not self.is_merge_mode:
            self._draw_overlay_text(painter, "⏸ ПАУЗА", 20, 20)

        if self.zoom > 1.01:
            self._draw_overlay_text(
                painter, f"ZOOM: {self.zoom:.1f}x", 20, self.height() - 50, bg_alpha=100
            )

        # --- Отрисовка графики (линии, углы) ---
        if self.drawing_manager and self.main_window:

            def map_orig_to_pix(x_o, y_o):
                x_c = x_o - params["x1"]
                y_c = y_o - params["y1"]
                x_p = params["x_offset"] + (x_c / params["src_w"]) * params["target_w"]
                y_p = params["y_offset"] + (y_c / params["src_h"]) * params["target_h"]
                return (x_p, y_p)

            current_mouse_screen = self.mapFromGlobal(self.cursor().pos())
            current_mouse_orig = self.viewport.screen_to_original(
                current_mouse_screen, self.frame.shape
            )

            self.drawing_manager.draw_on_painter(
                painter, self.current_frame_idx, map_orig_to_pix, current_mouse_orig
            )

        # --- Debug Overlay ---
        if (
            IS_DEBUG
            and self.main_window
            and hasattr(self.main_window, "draw_debug_overlay_painter")
        ):
            self.main_window.draw_debug_overlay_painter(
                painter, self.width(), self.height()
            )

        painter.end()

    def _draw_overlay_text(self, painter, text, x, y, bg_alpha=150):
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


class VideoContainerWidget(QWidget):
    wheel_scrolled = Signal(object)
    mouse_pressed = Signal(object)
    mouse_moved = Signal(object)
    mouse_released = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background-color: black; border: 1px solid #333;")
        self.setMouseTracking(True)

        sl = QStackedLayout(self)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setStackingMode(QStackedLayout.StackAll)

        # ИСПОЛЬЗУЕМ АППАРАТНЫЙ QOpenGLWidget
        self.video_canvas = VideoCanvas(self)
        self.video_canvas.setMouseTracking(True)
        sl.addWidget(self.video_canvas)

        self.overlay_widget = QLabel("РЕЖИМ ОБЪЕДИНЕНИЯ\nВЫБЕРИТЕ 2 ОТРЕЗКА")
        self.overlay_widget.setAlignment(Qt.AlignCenter)
        self.overlay_widget.setStyleSheet(
            "background-color: rgba(0, 50, 0, 200); color: #0f0; font-size: 24px; font-weight: bold;"
        )
        self.overlay_widget.hide()
        sl.addWidget(self.overlay_widget)

    def wheelEvent(self, event):
        self.wheel_scrolled.emit(event)

    def mousePressEvent(self, event):
        self.mouse_pressed.emit(event)

    def mouseMoveEvent(self, event):
        self.mouse_moved.emit(event)

    def mouseReleaseEvent(self, event):
        self.mouse_released.emit(event)
