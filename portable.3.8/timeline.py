from PySide2.QtCore import QPointF, QRectF, Qt, Signal
from PySide2.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap, QPolygonF
from PySide2.QtWidgets import QWidget


class TimelineWidget(QWidget):
    seek_requested = Signal(int)
    segment_selected = Signal(int)
    marker_selected = Signal(int)
    view_changed = Signal(int, int, int)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(115)
        self.setMouseTracking(True)

        self.total_frames = 100
        self.fps = 30.0
        self.current_frame = 0
        self.segments = []
        self.markers = []

        self.selected_segment_idx = -1
        self.selected_marker_idx = -1

        self.merge_mode = False
        self.merge_candidates = []

        self.drag_mode = None
        self.drag_target_idx = -1

        self.margin_left = 15
        self.margin_right = 15
        self.track_height = 38
        self.track_y = 25

        self.view_start = 0.0
        self.view_length = 100.0

        # --- ОПТИМИЗАЦИЯ: Двойная буферизация ---
        self._bg_pixmap = None
        self._bg_dirty = True

    def set_data(self, total_frames, fps, segments, markers):
        self.total_frames = max(1, total_frames)
        self.fps = fps
        self.segments = segments
        self.markers = markers

        self.view_start = 0.0
        self.view_length = float(self.total_frames)

        self._bg_dirty = True  # Данные изменились, нужна перерисовка фона
        self.update()
        self.emit_view_changed()

    def set_current_frame(self, frame):
        self.current_frame = frame
        if self.view_length < self.total_frames:
            view_end = self.view_start + self.view_length
            if frame >= view_end:
                self.view_start = frame - self.view_length + (self.view_length * 0.05)
                self._bg_dirty = True
            elif frame < self.view_start:
                self.view_start = frame - (self.view_length * 0.05)
                self._bg_dirty = True

            if self.view_start < 0:
                self.view_start = 0.0
            if self.view_start + self.view_length > self.total_frames:
                self.view_start = float(self.total_frames) - self.view_length
                if self.view_start < 0:
                    self.view_start = 0.0

            if self._bg_dirty:
                self.emit_view_changed()

        self.update()  # Обновляем только Playhead (зеленую линию)

    def set_merge_mode(self, active):
        self.merge_mode = active
        self.merge_candidates = []
        self._bg_dirty = True
        self.update()

    def frame_to_pixel(self, frame):
        width = self.width() - (self.margin_left + self.margin_right)
        if self.view_length <= 0:
            return self.margin_left
        ratio = (frame - self.view_start) / self.view_length
        return self.margin_left + ratio * width

    def pixel_to_frame(self, x):
        width = self.width() - (self.margin_left + self.margin_right)
        if width <= 0:
            return 0
        ratio = (x - self.margin_left) / width
        frame = self.view_start + ratio * self.view_length
        return int(max(0, min(frame, self.total_frames - 1)))

    def emit_view_changed(self):
        self.view_changed.emit(
            int(self.view_start), int(self.view_length), int(self.total_frames)
        )

    def set_view_start_from_scrollbar(self, val):
        self.view_start = float(val)
        if self.view_start < 0:
            self.view_start = 0
        if self.view_start + self.view_length > self.total_frames:
            self.view_start = self.total_frames - self.view_length
        self._bg_dirty = True
        self.update()

    def resizeEvent(self, event):
        self._bg_dirty = True
        super().resizeEvent(event)

    def wheelEvent(self, event):
        angle = event.angleDelta().y()
        if angle == 0:
            return

        zoom_factor = 0.9 if angle > 0 else 1.1
        mx = event.pos().x()
        width = self.width() - (self.margin_left + self.margin_right)
        if width <= 0:
            return

        ratio = (mx - self.margin_left) / width
        cursor_frame = self.view_start + ratio * self.view_length
        new_length = self.view_length * zoom_factor

        if new_length < 10:
            new_length = 10
        if new_length > self.total_frames:
            new_length = float(self.total_frames)

        new_start = cursor_frame - ratio * new_length
        if new_start < 0:
            new_start = 0
        if new_start + new_length > self.total_frames:
            new_start = self.total_frames - new_length
            if new_start < 0:
                new_start = 0

        self.view_start = new_start
        self.view_length = new_length

        self._bg_dirty = True
        self.update()
        self.emit_view_changed()

    def _draw_background_to_pixmap(self):
        """Отрисовывает всю статику (фон, сегменты, маркеры) в кэш"""
        self._bg_pixmap = QPixmap(self.size())
        self._bg_pixmap.fill(Qt.transparent)

        painter = QPainter(self._bg_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        bg_color = QColor("#111") if self.merge_mode else QColor("#222")
        painter.fillRect(self.rect(), bg_color)

        visible_min = self.view_start - self.view_length * 0.1
        visible_max = self.view_start + self.view_length * 1.1

        # SEGMENTS
        for idx, seg in enumerate(self.segments):
            if seg["end"] < visible_min or seg["start"] > visible_max:
                continue

            x1 = self.frame_to_pixel(seg["start"])
            x2 = self.frame_to_pixel(seg["end"])
            w = max(1, x2 - x1)
            rect = QRectF(x1, self.track_y, w, self.track_height)

            if self.merge_mode:
                if idx in self.merge_candidates:
                    fill_color, border_color, thickness = (
                        QColor("#00aa00"),
                        QColor("#fff"),
                        2,
                    )
                else:
                    fill_color, border_color, thickness = (
                        QColor("#333"),
                        QColor("#555"),
                        2,
                    )
            else:
                if idx == self.selected_segment_idx:
                    fill_color, border_color, thickness = (
                        QColor("#d4a017"),
                        QColor("#fff"),
                        2,
                    )
                else:
                    fill_color, border_color, thickness = (
                        QColor("#444"),
                        QColor("#666"),
                        1,
                    )

            painter.setBrush(QBrush(fill_color))
            painter.setPen(QPen(border_color, thickness))
            painter.drawRoundedRect(rect, 4, 4)

            if w > 20:
                painter.setPen(QColor("#fff"))
                painter.drawText(rect, Qt.AlignCenter, f"S{idx + 1}")

        # MARKERS
        if not self.merge_mode:
            font_tag = QFont("Arial", 9, QFont.Bold)
            painter.setFont(font_tag)

            for i, m in enumerate(self.markers):
                if not m.get("visible", True):
                    continue
                if m["frame"] < visible_min or m["frame"] > visible_max:
                    continue

                mx = self.frame_to_pixel(m["frame"])
                base_y = self.track_y + self.track_height
                color = QColor(m.get("color", "#ff0000"))

                pen = (
                    QPen(Qt.white, 2)
                    if i == self.selected_marker_idx
                    else QPen(color.darker(150), 1)
                )

                painter.setPen(QPen(color, 1, Qt.DashLine))
                painter.drawLine(int(mx), int(self.track_y), int(mx), int(base_y))

                painter.setBrush(QBrush(color))
                painter.setPen(pen)

                tri_w, tri_h = 10, 20
                polygon = QPolygonF(
                    [
                        QPointF(mx, base_y - 3),
                        QPointF(mx - tri_w, base_y + tri_h),
                        QPointF(mx + tri_w, base_y + tri_h),
                    ]
                )
                painter.drawPolygon(polygon)

                tag = m.get("tag", "")
                if tag:
                    text_rect = QRectF(mx - tri_w, base_y + 1, tri_w * 2, tri_h)
                    painter.setPen(QColor("#ffffff"))
                    painter.drawText(text_rect, Qt.AlignCenter, tag[0].upper())
        painter.end()

    def paintEvent(self, event):
        painter = QPainter(self)

        # Если данные изменились или размер поменялся - перерисовываем фон
        if (
            self._bg_dirty
            or self._bg_pixmap is None
            or self._bg_pixmap.size() != self.size()
        ):
            self._draw_background_to_pixmap()
            self._bg_dirty = False

        # Рисуем статичный кэшированный фон
        painter.drawPixmap(0, 0, self._bg_pixmap)

        # Динамически рисуем только ползунок (очень быстрая операция)
        visible_min = self.view_start - self.view_length * 0.1
        visible_max = self.view_start + self.view_length * 1.1
        if visible_min <= self.current_frame <= visible_max:
            cx = self.frame_to_pixel(self.current_frame)
            painter.setPen(QPen(QColor("#00ff00"), 2))
            painter.drawLine(int(cx), 0, int(cx), self.height())

    def mousePressEvent(self, event):
        x, y = event.pos().x(), event.pos().y()
        frame = self.pixel_to_frame(x)

        if self.merge_mode:
            if self.track_y <= y <= self.track_y + self.track_height:
                for i, seg in enumerate(self.segments):
                    if seg["start"] <= frame < seg["end"]:
                        self.segment_selected.emit(i)
                        return
            return

        base_y = self.track_y + self.track_height
        if y > base_y - 5:
            for i, m in enumerate(self.markers):
                if not m.get("visible", True):
                    continue
                mx = self.frame_to_pixel(m["frame"])
                if abs(x - mx) < 15:
                    if event.button() == Qt.RightButton:
                        self.selected_marker_idx = i
                        self.marker_selected.emit(i)
                    else:
                        self.selected_marker_idx = i
                        self.selected_segment_idx = -1
                        self.drag_mode = "move_marker"
                        self.drag_target_idx = i
                        self._bg_dirty = True
                        self.update()
                        self.marker_selected.emit(i)
                        self.segment_selected.emit(-1)
                    return

        if self.track_y <= y <= self.track_y + self.track_height:
            for i, seg in enumerate(self.segments):
                if seg["start"] <= frame < seg["end"]:
                    self.selected_segment_idx = i
                    self.selected_marker_idx = -1
                    self.segment_selected.emit(i)
                    self.marker_selected.emit(-1)
                    self._bg_dirty = True
                    self.update()
                    return

        self.seek_requested.emit(frame)

    def mouseMoveEvent(self, event):
        if self.merge_mode:
            return

        x, y = event.pos().x(), event.pos().y()
        frame = self.pixel_to_frame(x)

        if self.drag_mode and self.drag_target_idx != -1:
            if self.drag_mode == "move_marker" and self.drag_target_idx < len(
                self.markers
            ):
                self.markers[self.drag_target_idx]["frame"] = frame
                self.seek_requested.emit(frame)
                self._bg_dirty = True

            self.update()
            if "seg" in self.drag_mode:
                self.segment_selected.emit(self.drag_target_idx)
            else:
                self.marker_selected.emit(self.drag_target_idx)
            return

        base_y = self.track_y + self.track_height
        if y > base_y - 5:
            for m in self.markers:
                if not m.get("visible", True):
                    continue
                if abs(x - self.frame_to_pixel(m["frame"])) < 15:
                    self.setCursor(Qt.PointingHandCursor)
                    return

        self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self.drag_mode == "move_marker":
            self.markers.sort(key=lambda x: x["frame"])
            self._bg_dirty = True
            self.update()
        self.drag_mode = None
        self.drag_target_idx = -1

    # В main.py везде, где вызывается self.timeline.update() для сегментов/маркеров,
    # теперь нужно вызывать self.timeline._bg_dirty = True перед update().
