from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)


class FormulasWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Менеджер Формул")
        self.resize(600, 400)

        # Хранение формул: list of dicts {'name': str, 'expr': str}
        self.formulas = []

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Инструкция
        info = QLabel(
            "Доступные переменные:\n"
            "n - кол-во меток в отрезке\n"
            "k - кол-во кадров в отрезке\n"
            "t - время отрезка (сек)\n"
            "fps - частота кадров\n"
            "Пример: (n / t) * 60  -> Шагов в минуту"
        )
        info.setStyleSheet("color: #aaa; background: #222; padding: 5px;")
        layout.addWidget(info)

        # Таблица
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Название", "Формула (Python syntax)"])
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table)

        # Кнопки редактирования
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("Добавить")
        btn_add.clicked.connect(self.add_row)
        btn_del = QPushButton("Удалить выбранное")
        btn_del.clicked.connect(self.delete_row)
        btn_calc = QPushButton("РАССЧИТАТЬ (В новом окне)")
        btn_calc.setStyleSheet("background-color: #0078d7; font-weight: bold;")
        btn_calc.clicked.connect(self.calculate_all)

        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_del)
        btn_layout.addWidget(btn_calc)
        layout.addLayout(btn_layout)

    def add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem("Новая формула"))
        self.table.setItem(row, 1, QTableWidgetItem("n / t"))

    def delete_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def get_formulas(self):
        forms = []
        for i in range(self.table.rowCount()):
            name = self.table.item(i, 0).text()
            expr = self.table.item(i, 1).text()
            forms.append({"name": name, "expr": expr})
        return forms

    def set_context_callback(self, callback):
        self.get_context = callback

    def calculate_all(self):
        if not hasattr(self, "get_context"):
            return

        ctx = self.get_context()  # {'n': 5, 'k': 100, ...}
        if not ctx:
            QMessageBox.warning(self, "Ошибка", "Не выбран отрезок для расчетов!")
            return

        results_text = "=== РЕЗУЛЬТАТЫ ДЛЯ ОТРЕЗКА ===\n"
        results_text += (
            f"Входные данные: N={ctx['n']}, T={ctx['t']:.3f}s, K={ctx['k']}\n\n"
        )

        formulas = self.get_formulas()
        if not formulas:
            results_text += "Нет формул."

        for f in formulas:
            try:
                # Безопаснее использовать eval с ограниченным scope, но для локального тула сойдет
                # Подставляем переменные
                val = eval(f["expr"], {"__builtins__": None}, ctx)
                results_text += f"✅ {f['name']}: {val:.4f}\n"
            except Exception as e:
                results_text += f"❌ {f['name']}: Ошибка ({e})\n"

        # Показываем результат
        res_win = QDialog(self)
        res_win.setWindowTitle("Результаты вычислений")
        res_win.resize(400, 300)
        ll = QVBoxLayout(res_win)
        txt = QTextEdit()
        txt.setText(results_text)
        txt.setReadOnly(True)
        txt.setStyleSheet("font-size: 14px; font-family: Consolas;")
        ll.addWidget(txt)
        res_win.exec()
