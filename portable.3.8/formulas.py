# type: ignore

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
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
from utils import apply_dark_title_bar, create_dark_msg_box


class FormulasWindow(QDialog):
    def __init__(self, parent=None, stored_formulas=None):
        super().__init__(parent)
        self.setWindowTitle("Менеджер Формул")
        self.resize(600, 400)

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #fff; font-family: Segoe UI; }
            QTableWidget { background-color: #252526; color: #fff; gridline-color: #333; border: 1px solid #333; }
            QHeaderView::section { background-color: #333; color: #fff; padding: 4px; border: 1px solid #444; }
            QTextEdit { background-color: #252526; color: #fff; border: 1px solid #333; }
            QPushButton { background-color: #3a3a3a; color: #fff; border: 1px solid #555; padding: 6px; border-radius: 3px; }
            QPushButton:hover { background-color: #505050; }
            QPushButton:pressed { background-color: #0078d7; border-color: #0078d7; }
        """)

        apply_dark_title_bar(self)
        self.init_ui()

        if stored_formulas:
            self.load_from_data(stored_formulas)
        else:
            self.add_row_data("Шаги в минуту (SPM)", "(n / t) * 60")

    def init_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            "Переменные: n (метки), k (кадры), t (время), fps (кадры/сек)\n"
            "Синтаксис Python. Пример: (n / t) * 60"
        )
        info.setStyleSheet(
            "color: #ccc; background: #252526; padding: 10px; border: 1px solid #333; border-radius: 4px;"
        )
        layout.addWidget(info)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Название", "Формула"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        btn_add = QPushButton("Добавить")
        btn_add.clicked.connect(self.add_row)
        btn_del = QPushButton("Удалить")
        btn_del.clicked.connect(self.delete_row)
        btn_calc = QPushButton("РАССЧИТАТЬ")
        btn_calc.setStyleSheet(
            "background-color: #0078d7; font-weight: bold; border: 1px solid #005a9e;"
        )
        btn_calc.clicked.connect(self.calculate_all)

        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_del)
        btn_layout.addWidget(btn_calc)
        layout.addLayout(btn_layout)

    def add_row(self):
        self.add_row_data("Новая формула", "n / t")

    def add_row_data(self, name, expr):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        self.table.setItem(row, 1, QTableWidgetItem(expr))

    def delete_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def get_formulas(self):
        forms = []
        for i in range(self.table.rowCount()):
            name_item = self.table.item(i, 0)
            expr_item = self.table.item(i, 1)
            if name_item and expr_item:
                forms.append({"name": name_item.text(), "expr": expr_item.text()})
        return forms

    def load_from_data(self, data):
        self.table.setRowCount(0)
        for item in data:
            self.add_row_data(item.get("name", ""), item.get("expr", ""))

    def set_context_callback(self, callback):
        self.get_context = callback

    def calculate_all(self):
        if not hasattr(self, "get_context"):
            return
        ctx = self.get_context()
        if not ctx:
            msg = create_dark_msg_box(
                self, "Ошибка", "Не выбран отрезок!", QMessageBox.Warning
            )
            msg.exec_()
            return

        res_txt = f"Данные: N={ctx['n']}, T={ctx['t']:.3f}s\n\n"
        formulas = self.get_formulas()

        for f in formulas:
            try:
                val = eval(
                    f["expr"], {"__builtins__": None, "abs": abs, "round": round}, ctx
                )
                res_txt += f"✅ {f['name']}: {val:.2f}\n"
            except ZeroDivisionError:
                res_txt += f"⚠️ {f['name']}: Деление на 0\n"
            except Exception as e:
                res_txt += f"❌ {f['name']}: Ошибка ({e})\n"

        res_win = QDialog(self)
        res_win.setWindowTitle("Результат")
        res_win.resize(300, 200)

        res_win.setWindowFlags(res_win.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        apply_dark_title_bar(res_win)

        res_win.setStyleSheet(
            "background-color: #2b2b2b; color: #ffffff; font-family: Segoe UI;"
        )

        ll = QVBoxLayout(res_win)
        t = QTextEdit(res_txt)
        t.setReadOnly(True)
        t.setStyleSheet("border: 1px solid #444; background: #1e1e1e; color: #fff;")
        ll.addWidget(t)
        res_win.exec_()
