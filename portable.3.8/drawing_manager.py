# type: ignore
import math

from PySide2.QtCore import QPointF, Qt
from PySide2.QtGui import QColor, QFont, QPen


class DrawingManager:
    def __init__(self):
        # Хранилище рисунков: { frame_idx: [ список объектов_dict ] }
        self.drawings = {}
        self.current_tool = "none"  # "none", "line", "angle", "erase"
        self.current_color = "#00ff00"  # Яркий неоновый зеленый для разметки

        # Временные буферы для интерактивного рисования
        self.active_line = None
        self.angle_points = []  # Точки для построения угла (макс. 3)

    def set_tool(self, tool_name):
        self.current_tool = tool_name
        self.active_line = None
        self.angle_points = []

    def clear_frame(self, frame_num):
        """Очищает рисунки только на указанном кадре"""
        if frame_num in self.drawings:
            self.drawings[frame_num] = []

    def clear_all(self):
        """Полный сброс при закрытии/смене видео"""
        self.drawings.clear()

    def calculate_angle(self, p1, p2, p3):
        """Вычисляет угол в градусах между векторами p2->p1 и p2->p3 (p2 - вершина угла)"""
        ba = (p1[0] - p2[0], p1[1] - p2[1])
        bc = (p3[0] - p2[0], p3[1] - p2[1])

        dot_prod = ba[0] * bc[0] + ba[1] * bc[1]
        mag_ba = math.hypot(ba[0], ba[1])
        mag_bc = math.hypot(bc[0], bc[1])

        if mag_ba == 0 or mag_bc == 0:
            return 0.0

        cos_angle = dot_prod / (mag_ba * mag_bc)
        cos_angle = max(-1.0, min(1.0, cos_angle))
        return math.degrees(math.acos(cos_angle))

    def point_to_segment_distance(self, p, a, b):
        """Кратчайшее расстояние от точки P до отрезка AB"""
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        if dx == 0 and dy == 0:
            return math.hypot(p[0] - a[0], p[1] - a[1])
        t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        closest_x = a[0] + t * dx
        closest_y = a[1] + t * dy
        return math.hypot(p[0] - closest_x, p[1] - closest_y)

    def erase_near(self, frame_num, pt_org, threshold=15):
        """Находит ближайший объект на кадре и удаляет его, если кликнули близко"""
        if frame_num not in self.drawings or not self.drawings[frame_num]:
            return

        drawings_list = self.drawings[frame_num]
        closest_idx = -1
        min_dist = float("inf")

        for idx, item in enumerate(drawings_list):
            if item["type"] == "line":
                dist = self.point_to_segment_distance(
                    pt_org, item["points"][0], item["points"][1]
                )
            elif item["type"] == "angle":
                d1 = self.point_to_segment_distance(
                    pt_org, item["points"][0], item["points"][1]
                )
                d2 = self.point_to_segment_distance(
                    pt_org, item["points"][1], item["points"][2]
                )
                dist = min(d1, d2)
            else:
                dist = float("inf")

            if dist < min_dist:
                min_dist = dist
                closest_idx = idx

        if closest_idx != -1 and min_dist < threshold:
            drawings_list.pop(closest_idx)

    def handle_press(self, frame_num, pt_org):
        if self.current_tool == "line":
            self.active_line = [pt_org, pt_org]
        elif self.current_tool == "angle":
            if len(self.angle_points) < 2:
                self.angle_points.append(pt_org)
            elif len(self.angle_points) == 2:
                p1, p2 = self.angle_points
                p3 = pt_org
                angle = self.calculate_angle(p1, p2, p3)
                if frame_num not in self.drawings:
                    self.drawings[frame_num] = []
                self.drawings[frame_num].append(
                    {
                        "type": "angle",
                        "points": [p1, p2, p3],
                        "color": self.current_color,
                        "value": angle,
                    }
                )
                self.angle_points = []
        elif self.current_tool == "erase":
            self.erase_near(frame_num, pt_org)

    def handle_move(self, pt_org):
        if self.current_tool == "line" and self.active_line:
            self.active_line[1] = pt_org

    def handle_release(self, frame_num):
        if self.current_tool == "line" and self.active_line:
            p1, p2 = self.active_line
            if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) > 3:
                if frame_num not in self.drawings:
                    self.drawings[frame_num] = []
                self.drawings[frame_num].append(
                    {"type": "line", "points": [p1, p2], "color": self.current_color}
                )
            self.active_line = None

    def draw_on_painter(self, painter, frame_num, map_func, current_mouse_orig=None):
        # 1. Отрисовка сохраненных элементов для текущего кадра
        if frame_num in self.drawings:
            for item in self.drawings[frame_num]:
                self._draw_item(painter, item, map_func)

        # 2. Отрисовка линии в реальном времени при перетаскивании
        if self.current_tool == "line" and self.active_line:
            preview_item = {
                "type": "line",
                "points": self.active_line,
                "color": self.current_color,
            }
            self._draw_item(painter, preview_item, map_func, is_preview=True)

        # 3. Отрисовка строящегося угла (динамические пунктирные превью)
        if (
            self.current_tool == "angle"
            and len(self.angle_points) > 0
            and current_mouse_orig
        ):
            pts = list(self.angle_points)
            pts.append(current_mouse_orig)

            if len(pts) == 2:
                preview_item = {
                    "type": "line",
                    "points": pts,
                    "color": self.current_color,
                }
                self._draw_item(painter, preview_item, map_func, is_preview=True)
            elif len(pts) == 3:
                angle = self.calculate_angle(pts[0], pts[1], pts[2])
                preview_item = {
                    "type": "angle",
                    "points": pts,
                    "color": self.current_color,
                    "value": angle,
                }
                self._draw_item(painter, preview_item, map_func, is_preview=True)

    def _draw_item(self, painter, item, map_func, is_preview=False):
        pen = QPen(QColor(item["color"]), 3)
        if is_preview:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)

        mapped_pts = [map_func(p[0], p[1]) for p in item["points"]]

        if item["type"] == "line":
            p1, p2 = mapped_pts
            painter.drawLine(QPointF(p1[0], p1[1]), QPointF(p2[0], p2[1]))
        elif item["type"] == "angle":
            p1, p2, p3 = mapped_pts
            painter.drawLine(QPointF(p1[0], p1[1]), QPointF(p2[0], p2[1]))
            painter.drawLine(QPointF(p2[0], p2[1]), QPointF(p3[0], p3[1]))

            val = item.get("value", 0.0)
            text = f"{val:.1f}°"
            font = QFont("Segoe UI", 11, QFont.Bold)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            tw = metrics.horizontalAdvance(text)
            th = metrics.height()

            tx, ty = p2[0] + 12, p2[1] - 12
            painter.setPen(QPen(Qt.white, 1))
            painter.setBrush(QColor(0, 0, 0, 160))
            painter.drawRect(tx - 3, ty - th + 2, tw + 6, th)

            painter.setPen(QColor(item["color"]))
            painter.drawText(tx, ty, text)
