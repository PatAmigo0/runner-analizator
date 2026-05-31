from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class RightPanelWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(290)
        self.init_ui()

    def init_ui(self):
        rl = QVBoxLayout(self)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(5)
        rl.setAlignment(Qt.AlignTop)

        # --- Анализ ---
        gb_calc = QGroupBox("Анализ")
        gb_calc.setStyleSheet("QGroupBox { border: 1px solid #0078d7; }")
        lc = QVBoxLayout()
        lc.setSpacing(4)

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

        for w in [
            self.lbl_global_frame,
            self.lbl_global_time,
            self.lbl_info_seg,
            self.lbl_rel_frame,
            self.lbl_rel_time,
            self.lbl_seg_total_frames,
            self.lbl_seg_duration,
            self.lbl_seg_marks,
            self.lbl_tempo,
        ]:
            lc.addWidget(w)

        gb_calc.setLayout(lc)
        rl.addWidget(gb_calc)

        self.btn_formulas = QPushButton("📐 Конструктор формул")
        self.btn_formulas.setStyleSheet(
            "background-color: #6a0dad; margin-top: 5px; padding: 10px;"
        )
        rl.addWidget(self.btn_formulas)

        # --- Скорость ---
        gb_speed = QGroupBox("Скорость")
        hs = QHBoxLayout()
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.1, 5.0)
        self.spin_speed.setValue(1.0)
        self.spin_speed.setSingleStep(0.1)
        self.spin_speed.setFocusPolicy(Qt.ClickFocus)
        hs.addWidget(self.spin_speed)
        gb_speed.setLayout(hs)
        rl.addWidget(gb_speed)

        # --- Рисование ---
        gb_draw = QGroupBox("Рисование (на паузе)")
        ld = QVBoxLayout()
        ld.setSpacing(6)

        self.btn_draw_none = QPushButton("🖱 Обзор / Масштаб")
        self.btn_draw_line = QPushButton("➖ Начертить линию")
        self.btn_draw_angle = QPushButton("📐 Найти угол (3 клика)")
        self.btn_draw_erase = QPushButton("🧹 Стереть элемент")
        self.btn_draw_clear = QPushButton("🗑 Очистить этот кадр")

        for btn in [
            self.btn_draw_none,
            self.btn_draw_line,
            self.btn_draw_angle,
            self.btn_draw_erase,
            self.btn_draw_clear,
        ]:
            ld.addWidget(btn)

        gb_draw.setLayout(ld)
        rl.addWidget(gb_draw)

        rl.addStretch()
