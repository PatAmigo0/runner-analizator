# type: ignore

import ctypes
import os
import sys
from ctypes import byref, c_int, sizeof
from functools import wraps

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QMessageBox


def undoable(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if hasattr(self, "save_state"):
            self.save_state()
        return func(self, *args, **kwargs)

    return wrapper


def stop_playback(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if hasattr(self, "playing") and self.playing:
            self.toggle_play()
        return func(self, *args, **kwargs)

    return wrapper


def apply_dark_title_bar(window):
    try:
        hwnd = window.winId()
        attrib = 20
        val = c_int(1)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            int(hwnd), attrib, byref(val), sizeof(val)
        )
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
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)


def normalize_key(key_code):
    """
    Конвертирует кириллические коды клавиш (Qt) в соответствующие латинские.
    Позволяет горячим клавишам работать при русской раскладке.
    """
    cyr_to_lat = {
        1049: Qt.Key_Q,
        1062: Qt.Key_W,
        1059: Qt.Key_E,
        1050: Qt.Key_R,
        1045: Qt.Key_T,
        1053: Qt.Key_Y,
        1043: Qt.Key_U,
        1064: Qt.Key_I,
        1065: Qt.Key_O,
        1047: Qt.Key_P,
        1061: Qt.Key_BracketLeft,
        1066: Qt.Key_BracketRight,
        1060: Qt.Key_A,
        1067: Qt.Key_S,
        1099: Qt.Key_S,  # Ы (иногда мапится иначе)
        1042: Qt.Key_D,
        1040: Qt.Key_F,
        1055: Qt.Key_G,
        1056: Qt.Key_H,
        1054: Qt.Key_J,
        1051: Qt.Key_K,
        1044: Qt.Key_L,
        1046: Qt.Key_Semicolon,
        1069: Qt.Key_Apostrophe,
        1071: Qt.Key_Z,
        1063: Qt.Key_X,
        1057: Qt.Key_C,
        1052: Qt.Key_V,
        1048: Qt.Key_B,
        1058: Qt.Key_N,
        1068: Qt.Key_M,
        1041: Qt.Key_Comma,
        1070: Qt.Key_Period,
    }
    return cyr_to_lat.get(key_code, key_code)
