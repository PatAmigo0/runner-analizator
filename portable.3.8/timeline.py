from PySide2.QtCore import QPointF, QRectF, Qt, Signal
from PySide2.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide2.QtWidgets import QWidget


class TimelineWidget(QWidget):
    seek_requested = Signal(int)
    segment_selected = Signal(int)
    marker_selected = Signal(int)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(140)
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
        self.track_height = 50
        self.track_y = 50

    def set_data(self, total_frames, fps, segments, markers):
        self.total_frames = total_frames
        self.fps = fps
        self.segments = segments
        self.markers = markers
        self.update()

    def set_current_frame(self, frame):
        self.current_frame = frame
        self.update()

    def set_merge_mode(self, active):
        self.merge_mode = active
        self.merge_candidates = []
        self.update()

    def frame_to_pixel(self, frame):
        if self.total_frames == 0:
            return self.margin_left
        width = self.width() - (self.margin_left + self.margin_right)
        return self.margin_left + (frame / self.total_frames) * width

    def pixel_to_frame(self, x):
        width = self.width() - (self.margin_left + self.margin_right)
        if width == 0:
            return 0
        ratio = (x - self.margin_left) / width
        frame = int(ratio * self.total_frames)
        return max(0, min(frame, self.total_frames))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg_color = QColor("#111") if self.merge_mode else QColor("#222")
        painter.fillRect(self.rect(), bg_color)

        # SEGMENTS
        for idx, seg in enumerate(self.segments):
            x1 = self.frame_to_pixel(seg["start"])
            x2 = self.frame_to_pixel(seg["end"])
            w = max(2, x2 - x1)
            rect = QRectF(x1, self.track_y, w, self.track_height)

            if self.merge_mode:
                if idx in self.merge_candidates:
                    fill_color = QColor("#00aa00")
                    border_color = QColor("#fff")
                else:
                    fill_color = QColor("#333")
                    border_color = QColor("#555")
                thickness = 2
            else:
                if idx == self.selected_segment_idx:
                    fill_color = QColor("#d4a017")
                    border_color = QColor("#fff")
                    thickness = 2
                else:
                    fill_color = QColor("#444")
                    border_color = QColor("#666")
                    thickness = 1

            painter.setBrush(QBrush(fill_color))
            painter.setPen(QPen(border_color, thickness))
            painter.drawRoundedRect(rect, 4, 4)

            painter.setPen(QColor("#fff"))
            painter.drawText(rect, Qt.AlignCenter, f"S{idx + 1}")

        # MARKERS
        if not self.merge_mode:
            font_tag = QFont("Arial", 9, QFont.Bold)
            painter.setFont(font_tag)

            for i, m in enumerate(self.markers):
                if not m.get("visible", True):
                    continue

                mx = self.frame_to_pixel(m["frame"])
                base_y = self.track_y + self.track_height

                color = QColor(m.get("color", "#ff0000"))

                if i == self.selected_marker_idx:
                    pen = QPen(Qt.white, 2)
                else:
                    pen = QPen(color.darker(150), 1)

                # Dotted Line
                painter.setPen(QPen(color, 1, Qt.DashLine))
                painter.drawLine(int(mx), int(self.track_y), int(mx), int(base_y))

                # Triangle Body
                painter.setBrush(QBrush(color))
                painter.setPen(pen)

                tri_w = 12
                tri_h = 24

                polygon = QPolygonF(
                    [
                        QPointF(mx, base_y - 5),
                        QPointF(mx - tri_w, base_y + tri_h),
                        QPointF(mx + tri_w, base_y + tri_h),
                    ]
                )
                painter.drawPolygon(polygon)

                # Single Letter Tag
                tag = m.get("tag", "")
                if tag:
                    letter = tag[0].upper()  # Only first letter
                    # Draw inside triangle
                    text_rect = QRectF(mx - tri_w, base_y + 2, tri_w * 2, tri_h)
                    painter.setPen(QColor("#ffffff"))  # White text
                    painter.drawText(text_rect, Qt.AlignCenter, letter)

        # PLAYHEAD
        cx = self.frame_to_pixel(self.current_frame)
        painter.setPen(QPen(QColor("#00ff00"), 2))
        painter.drawLine(int(cx), 0, int(cx), self.height())

    def mousePressEvent(self, event):
        # PySide2: event.pos().x() вместо event.position().x()
        x = event.pos().x()
        y = event.pos().y()
        frame = self.pixel_to_frame(x)

        if self.merge_mode:
            if self.track_y <= y <= self.track_y + self.track_height:
                for i, seg in enumerate(self.segments):
                    sx1 = self.frame_to_pixel(seg["start"])
                    sx2 = self.frame_to_pixel(seg["end"])
                    if sx1 < x < sx2:
                        self.segment_selected.emit(i)
                        return
            return

        # Markers
        base_y = self.track_y + self.track_height
        if y > base_y - 5:
            for i, m in enumerate(self.markers):
                if not m.get("visible", True):
                    continue
                mx = self.frame_to_pixel(m["frame"])
                if abs(x - mx) < 15:  # Wider hitbox
                    if event.button() == Qt.RightButton:
                        self.selected_marker_idx = i
                        self.marker_selected.emit(i)
                    else:
                        self.selected_marker_idx = i
                        self.selected_segment_idx = -1
                        self.drag_mode = "move_marker"
                        self.drag_target_idx = i
                        self.update()
                        self.marker_selected.emit(i)
                        self.segment_selected.emit(-1)
                    return

        # Segments
        if self.track_y <= y <= self.track_y + self.track_height:
            threshold = 8
            for i, seg in enumerate(self.segments):
                sx1 = self.frame_to_pixel(seg["start"])
                sx2 = self.frame_to_pixel(seg["end"])

                if abs(x - sx1) < threshold:
                    self.drag_mode = "move_seg_start"
                    self.drag_target_idx = i
                    self.selected_segment_idx = i
                    return
                elif abs(x - sx2) < threshold:
                    self.drag_mode = "move_seg_end"
                    self.drag_target_idx = i
                    self.selected_segment_idx = i
                    return

                if sx1 < x < sx2:
                    self.selected_segment_idx = i
                    self.selected_marker_idx = -1
                    self.segment_selected.emit(i)
                    self.marker_selected.emit(-1)
                    self.update()
                    return

        # Seek (Don't deselect)
        self.seek_requested.emit(frame)
        self.update()

    def mouseMoveEvent(self, event):
        if self.merge_mode:
            return

        x = event.pos().x()
        y = event.pos().y()
        frame = self.pixel_to_frame(x)

        if self.drag_mode and self.drag_target_idx != -1:
            if self.drag_mode == "move_marker":
                if self.drag_target_idx < len(self.markers):
                    self.markers[self.drag_target_idx]["frame"] = frame
                    self.seek_requested.emit(frame)

            elif self.drag_mode == "move_seg_start":
                idx = self.drag_target_idx
                if idx < len(self.segments):
                    seg = self.segments[idx]
                    prev_limit = self.segments[idx - 1]["end"] if idx > 0 else 0
                    max_val = seg["end"] - 1
                    seg["start"] = max(prev_limit, min(frame, max_val))
                    self.seek_requested.emit(seg["start"])

            elif self.drag_mode == "move_seg_end":
                idx = self.drag_target_idx
                if idx < len(self.segments):
                    seg = self.segments[idx]
                    next_limit = (
                        self.segments[idx + 1]["start"]
                        if idx < len(self.segments) - 1
                        else self.total_frames
                    )
                    min_val = seg["start"] + 1
                    seg["end"] = max(min_val, min(frame, next_limit))
                    self.seek_requested.emit(seg["end"])

            self.update()
            if "seg" in self.drag_mode:
                self.segment_selected.emit(self.drag_target_idx)
            else:
                self.marker_selected.emit(self.drag_target_idx)
            return

        # Cursor
        base_y = self.track_y + self.track_height
        if y > base_y - 5:
            for m in self.markers:
                if not m.get("visible", True):
                    continue
                mx = self.frame_to_pixel(m["frame"])
                if abs(x - mx) < 15:
                    self.setCursor(Qt.PointingHandCursor)
                    return

        if self.track_y <= y <= self.track_y + self.track_height:
            threshold = 8
            for seg in self.segments:
                sx1 = self.frame_to_pixel(seg["start"])
                sx2 = self.frame_to_pixel(seg["end"])
                if abs(x - sx1) < threshold or abs(x - sx2) < threshold:
                    self.setCursor(Qt.SizeHorCursor)
                    return

        self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self.drag_mode == "move_marker":
            self.markers.sort(key=lambda x: x["frame"])
        self.drag_mode = None
        self.drag_target_idx = -1
