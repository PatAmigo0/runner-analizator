# type: ignore
from PySide2.QtCore import QPointF


class ViewportHandler:
    def __init__(self, video_widget):
        self.video_widget = video_widget
        self.zoom = 1.0
        self.pan = QPointF(0, 0)

    def reset(self):
        self.zoom = 1.0
        self.pan = QPointF(0, 0)

    def handle_wheel(self, angle_delta):
        MAX_ZOOM = 50.0
        MIN_ZOOM = 1.0
        ZOOM_STEP = 1.1
        if angle_delta > 0:
            self.zoom *= ZOOM_STEP
        else:
            self.zoom /= ZOOM_STEP

        if self.zoom > MAX_ZOOM:
            self.zoom = MAX_ZOOM
        elif self.zoom < MIN_ZOOM:
            self.zoom = MIN_ZOOM
            self.pan = QPointF(0, 0)

    def add_pan(self, delta_x, delta_y):
        self.pan += QPointF(delta_x, delta_y)

    def get_mapping_params(self, h_orig, w_orig):
        lbl_w = self.video_widget.width()
        lbl_h = self.video_widget.height()
        if lbl_w <= 1 or lbl_h <= 1:
            return None

        if self.zoom > 1.0:
            visible_w = w_orig / self.zoom
            visible_h = h_orig / self.zoom
            cx = w_orig / 2.0 - self.pan.x()
            cy = h_orig / 2.0 - self.pan.y()
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
            src_w = x2 - x1
            src_h = y2 - y1
        else:
            x1, y1 = 0, 0
            src_w, src_h = w_orig, h_orig

        aspect = src_w / src_h if src_h > 0 else 1
        if lbl_w / lbl_h > aspect:
            target_h = lbl_h
            target_w = int(lbl_h * aspect)
        else:
            target_w = lbl_w
            target_h = int(lbl_w / aspect)

        x_offset = (lbl_w - target_w) / 2
        y_offset = (lbl_h - target_h) / 2

        return {
            "x1": x1,
            "y1": y1,
            "src_w": src_w,
            "src_h": src_h,
            "target_w": target_w,
            "target_h": target_h,
            "x_offset": x_offset,
            "y_offset": y_offset,
        }

    def screen_to_original(self, pos, frame_shape):
        if frame_shape is None:
            return None
        params = self.get_mapping_params(frame_shape[0], frame_shape[1])
        if not params:
            return None
        x_pix = pos.x() - params["x_offset"]
        y_pix = pos.y() - params["y_offset"]

        if 0 <= x_pix <= params["target_w"] and 0 <= y_pix <= params["target_h"]:
            x_crop = (x_pix / params["target_w"]) * params["src_w"]
            y_crop = (y_pix / params["target_h"]) * params["src_h"]
            return (params["x1"] + x_crop, params["y1"] + y_crop)
        return None
