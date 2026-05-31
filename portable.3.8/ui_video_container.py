from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import QLabel, QSizePolicy, QStackedLayout, QWidget


class VideoContainerWidget(QWidget):
    # Сигналы для связи с контроллером
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

    def wheelEvent(self, event):
        self.wheel_scrolled.emit(event)

    def mousePressEvent(self, event):
        self.mouse_pressed.emit(event)

    def mouseMoveEvent(self, event):
        self.mouse_moved.emit(event)

    def mouseReleaseEvent(self, event):
        self.mouse_released.emit(event)
