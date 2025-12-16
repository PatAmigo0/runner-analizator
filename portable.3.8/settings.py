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
            # Изменили на AUTO, так как на Win8/AVI он работает быстрее
            "video_backend": "AUTO",  # "AUTO", "MSMF", "DSHOW", "FFMPEG"
            "seek_effort": 20,  # Глубина поиска ключевого кадра (Lookback)
            "use_proxy": True,
            "proxy_quality": 540,
            "proxy_codec": "MJPG",  # "MJPG" (быстро, но большой файл) или "mp4v" (медленно, но маленький)
            "last_dir": "",
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
        """Возвращает расширение файла в зависимости от выбранного кодека"""
        codec = self.get("proxy_codec", "MJPG")
        if codec == "MJPG":
            return ".avi"  # MJPEG лучше всего работает в контейнере AVI
        return ".mp4"  # mp4v/h264 лучше в MP4

    def cleanup_old_proxies(self, original_filename_no_ext):
        """Удаляет ВСЕ старые версии прокси для этого файла (и avi, и mp4)"""
        try:
            time.sleep(0.1)
            # Ищем и удаляем файлы с обоими расширениями, чтобы при смене кодека не копился мусор
            extensions = [".mp4", ".avi"]

            for ext in extensions:
                pattern = os.path.join(
                    self.proxies_dir, f"{original_filename_no_ext}_proxy_*{ext}"
                )
                for f in glob.glob(pattern):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
        except Exception as e:
            print(f"Cleanup error: {e}")

    def clear_all_proxies(self):
        try:
            time.sleep(0.2)
            for filename in os.listdir(self.proxies_dir):
                file_path = os.path.join(self.proxies_dir, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                except OSError as e:
                    print(f"File locked: {e}")
            return True
        except Exception as e:
            print(f"Failed to delete proxies: {e}")
            return False

    def delete_single_proxy(self, proxy_path):
        if proxy_path and os.path.exists(proxy_path):
            for _ in range(5):  # 5 попыток с задержкой
                try:
                    os.remove(proxy_path)
                    return True
                except OSError:
                    time.sleep(0.2)
            print(f"Could not delete {proxy_path}")
        return False
