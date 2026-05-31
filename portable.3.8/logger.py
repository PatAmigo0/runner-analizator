import datetime
import os
import sys
import traceback

from PySide2.QtCore import QStandardPaths


class Logger:
    def __init__(self, is_debug_mode):
        self.is_debug = is_debug_mode
        self.log_filename = "application_log.txt"

        # ИСПОЛЬЗУЕМ СТАНДАРТНУЮ ПАПКУ ДАННЫХ ПРИЛОЖЕНИЯ (AppData)
        # Это гарантирует права на запись в скомпилированной версии
        try:
            base_dir = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
            self.log_dir = os.path.join(base_dir, "ProSportsAnalyzer")
            if not os.path.exists(self.log_dir):
                os.makedirs(self.log_dir)
            self.log_path = os.path.join(self.log_dir, self.log_filename)
        except Exception:
            # Fallback на текущую папку, если совсем всё плохо
            self.log_path = "fallback_log.txt"

    def debug(self, *args):
        if self.is_debug:
            message = " ".join(map(str, args))
            print(f"[DEBUG] {message}")

    def file(self, *args):
        message = " ".join(map(str, args))
        if self.is_debug:
            print(f"[TO_FILE] {message}")
        self._write_to_disk(message)

    def error(self, e):
        """Новый метод для записи полных трейсбеков ошибок"""
        tb = "".join(traceback.format_tb(e.__traceback__))
        msg = f"EXCEPTION: {str(e)}\nTRACEBACK:\n{tb}"
        self._write_to_disk(msg)
        if self.is_debug:
            print(msg)

    def _write_to_disk(self, message):
        try:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{timestamp}] {message}\n"
            # Используем append ('a') и utf-8
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            # Если не смогли записать лог, пытаемся вывести в stderr (для консоли Nuitka)
            sys.stderr.write(f"LOGGING ERROR: {e}\n")
