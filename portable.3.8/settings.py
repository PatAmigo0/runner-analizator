# type: ignore

import glob
import json
import os
import time

from PySide2.QtCore import QStandardPaths, Qt


class SettingsManager:
    def __init__(self):
        try:
            config_path = QStandardPaths.writableLocation(
                QStandardPaths.AppConfigLocation
            )
            self.app_dir = os.path.join(config_path, "ProSportsAnalyzer")
            if not os.path.exists(self.app_dir):
                os.makedirs(self.app_dir)
        except Exception:
            self.app_dir = os.getcwd()

        self.filepath = os.path.join(self.app_dir, "settings.json")
        self.proxies_dir = os.path.join(self.app_dir, "proxies")
        if not os.path.exists(self.proxies_dir):
            os.makedirs(self.proxies_dir)

        self.default_hotkeys = {
            "play_pause": int(Qt.Key_Space),
            "mark": int(Qt.Key_M),
            "split": int(Qt.Key_S),
            "delete": int(Qt.Key_Delete),
            "undo": int(Qt.CTRL | Qt.Key_Z),
            "redo": int(Qt.CTRL | Qt.Key_Y),
            "frame_prev": int(Qt.Key_Left),
            "frame_next": int(Qt.Key_Right),
            "seg_prev": int(Qt.Key_A),
            "seg_next": int(Qt.Key_D),
        }

        self.default_general = {
            "cache_size": 100,
            "use_gpu": False,
            "video_backend": "AUTO",
            "seek_effort": 20,
            "use_proxy": True,
            "proxy_quality": 540,
            "proxy_codec": "MJPG",
            "last_dir": "",
            "ask_proxy_creation": True,
        }

        self.data = {
            "hotkeys": self.default_hotkeys.copy(),
            "general": self.default_general.copy(),
            "formulas": [],
        }
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    if content.strip():
                        loaded = json.loads(content)
                        if "hotkeys" in loaded:
                            for k, v in loaded["hotkeys"].items():
                                self.data["hotkeys"][k] = int(v)
                            for k, v in self.default_hotkeys.items():
                                if k not in self.data["hotkeys"]:
                                    self.data["hotkeys"][k] = v

                        if "general" in loaded:
                            for k, v in loaded["general"].items():
                                self.data["general"][k] = v
                        for k, v in self.default_general.items():
                            if k not in self.data["general"]:
                                self.data["general"][k] = v

                        if "formulas" in loaded:
                            self.data["formulas"] = loaded["formulas"]
                        if "last_dir" in loaded and isinstance(loaded["last_dir"], str):
                            self.data["general"]["last_dir"] = loaded["last_dir"]
            except Exception as e:
                print(f"Error loading settings: {e}")

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get(self, key, default=None):
        return self.data["general"].get(key, default)

    def set(self, key, value):
        self.data["general"][key] = value

    def get_proxy_extension(self):
        codec = self.get("proxy_codec", "MJPG")
        if codec == "MJPG":
            return ".avi"
        return ".mp4"

    def _safe_delete(self, path, retries=5, delay=0.1):
        """
        Безопасное удаление файла с повторными попытками
        Решает проблему блокировки файла Windows (Race Condition)
        """
        if not os.path.exists(path):
            return True

        for i in range(retries):
            try:
                os.remove(path)
                return True  # Удалили успешно, выходим сразу
            except PermissionError:
                # Файл занят системой. Ждем и пробуем снова.
                time.sleep(delay)
            except OSError as e:
                print(f"Error deleting {path}: {e}")
                return False

        print(f"Failed to delete {path} after {retries} retries")
        return False

    def cleanup_old_proxies(self, original_filename_no_ext):
        """Удаляет старые версии прокси, используя безопасный метод"""
        try:
            extensions = [".mp4", ".avi"]
            for ext in extensions:
                pattern = os.path.join(
                    self.proxies_dir, f"{original_filename_no_ext}_proxy_*{ext}"
                )
                for f in glob.glob(pattern):
                    self._safe_delete(f)
        except Exception as e:
            print(f"Cleanup error: {e}")

    def clear_all_proxies(self):
        try:
            # Убран naked time.sleep(0.2)
            success = True
            for filename in os.listdir(self.proxies_dir):
                file_path = os.path.join(self.proxies_dir, filename)
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    if not self._safe_delete(file_path):
                        success = False
            return success
        except Exception as e:
            print(f"Failed to delete proxies: {e}")
            return False

    def delete_single_proxy(self, proxy_path):
        # Используем тот же универсальный безопасный метод
        return self._safe_delete(proxy_path, retries=10, delay=0.1)
