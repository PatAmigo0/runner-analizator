import ctypes
import os
import sys
from ctypes import byref, c_int, sizeof
from functools import wraps

from PySide2.QtWidgets import QMessageBox


def undoable(func):
    """Декоратор: сохраняет состояние (Undo) перед выполнением."""

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if hasattr(self, "save_state"):
            self.save_state()
        return func(self, *args, **kwargs)

    return wrapper


def stop_playback(func):
    """Декоратор: останавливает воспроизведение."""

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if hasattr(self, "playing") and self.playing:
            self.toggle_play()
        return func(self, *args, **kwargs)

    return wrapper


def apply_dark_title_bar(window):
    """
    Применяет темный заголовок окна.
    """
    try:
        hwnd = window.winId()
        # Попытка для Windows 10 2004+ / Windows 11
        attrib = 20
        val = c_int(1)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            int(hwnd), attrib, byref(val), sizeof(val)
        )
        # Если не вышло, пробуем для старых Win 10
        if result != 0:
            attrib = 19
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(hwnd), attrib, byref(val), sizeof(val)
            )
    except Exception:
        pass


def create_dark_msg_box(
    parent, title, text, icon=QMessageBox.Information, buttons=QMessageBox.Ok
):
    """Создает QMessageBox с темным заголовком и стилем."""
    msg = QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setIcon(icon)
    msg.setStandardButtons(buttons)

    apply_dark_title_bar(msg)

    msg.setStyleSheet("""
        QMessageBox { background-color: #2b2b2b; color: #f0f0f0; }
        QLabel { color: #f0f0f0; font-size: 14px; }
        QPushButton { 
            background-color: #3a3a3a; 
            border: 1px solid #555; 
            padding: 6px 20px; 
            color: white; 
            border-radius: 3px;
            min-width: 60px;
        }
        QPushButton:hover { background-color: #505050; border-color: #777; }
        QPushButton:pressed { background-color: #0078d7; border-color: #0078d7; }
    """)
    return msg


def get_resource_path(relative_path):
    """
    Возвращает абсолютный путь к ресурсу

    """
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)
