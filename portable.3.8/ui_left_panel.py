from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LeftPanelWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(310)
        self.init_ui()

    def init_ui(self):
        ll = QVBoxLayout(self)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(5)
        ll.setAlignment(Qt.AlignTop)

        # --- Файл и Управление ---
        gb_f = QGroupBox("Файл и Управление")
        lf = QVBoxLayout()
        lf.setSpacing(6)

        self.btn_open = QPushButton("📂 Открыть видео")

        h_sets = QHBoxLayout()
        self.btn_hotkeys = QPushButton("⌨ Клавиши")
        self.btn_settings = QPushButton("⚙ Настройки")
        h_sets.addWidget(self.btn_hotkeys)
        h_sets.addWidget(self.btn_settings)

        lf.addWidget(self.btn_open)
        lf.addLayout(h_sets)

        self.btn_create_proxy = QPushButton("⚡ Создать Прокси")
        self.btn_create_proxy.setStyleSheet(
            "background-color: #0078d7; font-weight: bold;"
        )
        self.btn_create_proxy.hide()
        lf.addWidget(self.btn_create_proxy)

        l_info = QVBoxLayout()
        l_info.setSpacing(2)
        self.lbl_vid_res = QLabel("Разрешение: -")
        self.lbl_vid_fps = QLabel("FPS: -")
        self.lbl_proxy_status = QLabel("")
        l_info.addWidget(self.lbl_vid_res)
        l_info.addWidget(self.lbl_vid_fps)
        l_info.addWidget(self.lbl_proxy_status)
        lf.addLayout(l_info)

        gb_f.setLayout(lf)
        ll.addWidget(gb_f)

        # --- Метки ---
        gb_m = QGroupBox("Метки")
        lm = QVBoxLayout()
        lm.setSpacing(6)

        self.btn_mark = QPushButton("🚩 ПОСТАВИТЬ МЕТКУ")
        self.btn_mark.setMinimumHeight(38)
        self.btn_mark.setStyleSheet(
            "background-color: #b30000; font-weight: bold; font-size: 14px; border: 1px solid #f00;"
        )
        lm.addWidget(self.btn_mark)

        self.lbl_marker_mode = QLabel("Режим: Создание")
        lm.addWidget(self.lbl_marker_mode)

        h_m1 = QHBoxLayout()
        self.btn_color = QPushButton("")
        self.btn_color.setFixedSize(22, 22)
        self.inp_tag = QLineEdit("Main")
        h_m1.addWidget(QLabel("Цвет:"))
        h_m1.addWidget(self.btn_color)
        h_m1.addWidget(self.inp_tag)
        lm.addLayout(h_m1)

        lm.addWidget(QLabel("Список меток:"))
        self.list_filters = QListWidget()
        self.list_filters.setFixedHeight(100)
        self.list_filters.setSelectionMode(QAbstractItemView.NoSelection)
        self.list_filters.setFocusPolicy(Qt.NoFocus)
        lm.addWidget(self.list_filters)

        gb_m.setLayout(lm)
        ll.addWidget(gb_m)

        # --- Действия ---
        gb_a = QGroupBox("Действия")
        la = QVBoxLayout()
        la.setSpacing(6)

        h_ur = QHBoxLayout()
        self.btn_undo = QPushButton("↶ Отмена")
        self.btn_redo = QPushButton("↷ Повтор")
        h_ur.addWidget(self.btn_undo)
        h_ur.addWidget(self.btn_redo)
        la.addLayout(h_ur)

        self.btn_split = QPushButton("✂ Разрезать")
        self.btn_merge = QPushButton("🔗 Объединить")
        self.btn_cancel_merge = QPushButton("❌ Отмена объед.")
        self.btn_cancel_merge.hide()
        self.btn_delete = QPushButton("🗑 Удалить")

        la.addWidget(self.btn_split)
        la.addWidget(self.btn_merge)
        la.addWidget(self.btn_cancel_merge)
        la.addWidget(self.btn_delete)

        gb_a.setLayout(la)
        ll.addWidget(gb_a)

        ll.addStretch()
