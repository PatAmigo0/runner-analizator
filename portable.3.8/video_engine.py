# type: ignore

import os
import time
from collections import deque

import cv2
from PySide2.QtCore import QThread, Signal

IS_DEBUG = "__compiled__" not in globals()


def debug_log(msg):
    if IS_DEBUG:
        print(f"[ENGINE] {time.time() % 100:.3f}: {msg}")


# --- PROXY GENERATOR ---
class ProxyGeneratorThread(QThread):
    progress_signal = Signal(int)
    finished_signal = Signal(bool, str)

    def __init__(self, input_path, output_path, codec="MJPG", target_height=540):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.codec = codec
        self.target_height = target_height
        self._is_running = True

    def run(self):
        # Для генерации прокси используем CAP_ANY (самый надежный для чтения)
        cap = cv2.VideoCapture(self.input_path, cv2.CAP_ANY)
        if not cap.isOpened():
            self.finished_signal.emit(False, "")
            return

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Расчет размеров
        if self.target_height > 0 and height > self.target_height:
            new_height = self.target_height
            ratio = new_height / height
            new_width = int(width * ratio)
            if new_width % 2 != 0:
                new_width += 1
            if new_height % 2 != 0:
                new_height += 1
        else:
            new_height = height
            new_width = width
            if new_width % 2 != 0:
                new_width += 1
            if new_height % 2 != 0:
                new_height += 1

        write_fps = round(fps)
        if write_fps <= 0:
            write_fps = 30
        if write_fps > 60:
            write_fps = 60

        # Выбор кодека
        if self.codec == "MJPG":
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        elif self.codec == "mp4v":
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        elif self.codec == "avc1":
            fourcc = cv2.VideoWriter_fourcc(*"avc1")
        else:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")

        out = cv2.VideoWriter(
            self.output_path, fourcc, write_fps, (new_width, new_height)
        )

        if not out.isOpened():
            debug_log(f"Codec {self.codec} failed. Fallback to mp4v.")
            root, _ = os.path.splitext(self.output_path)
            self.output_path = root + ".mp4"
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(
                self.output_path, fourcc, write_fps, (new_width, new_height)
            )
            if not out.isOpened():
                cap.release()
                self.finished_signal.emit(False, "")
                return

        start_time = time.time()
        count = 0
        while self._is_running:
            ret, frame = cap.read()
            if not ret:
                break

            # БЕЗОПАСНАЯ ЗАПИСЬ
            # Защита от сбоев ресайза и битых кадров, чтобы не крашить поток
            try:
                if new_height != height or new_width != width:
                    resized = cv2.resize(
                        frame, (new_width, new_height), interpolation=cv2.INTER_AREA
                    )
                    out.write(resized)
                else:
                    out.write(frame)
            except Exception as e:
                debug_log(f"Proxy gen error at frame {count}: {e}")
                # Просто пропускаем сбойный кадр и идем дальше

            count += 1
            if total > 0 and count % 10 == 0:
                percent = int((count / total) * 100)
                self.progress_signal.emit(percent)

                if count % 100 == 0:
                    dt = time.time() - start_time
                    if dt > 0:
                        perf_fps = count / dt
                        debug_log(
                            f"Encoding {self.codec}: {percent}% @ {perf_fps:.1f} FPS"
                        )

        cap.release()
        out.release()

        if self._is_running:
            self.finished_signal.emit(True, self.output_path)
        else:
            if os.path.exists(self.output_path):
                try:
                    os.remove(self.output_path)
                except OSError:
                    pass
            self.finished_signal.emit(False, "")

    def stop(self):
        self._is_running = False


# --- VIDEO ENGINE ---
class VideoEngine:
    def __init__(self, settings_manager):
        self.settings = settings_manager
        self.cap = None
        self.total_frames = 0
        self.fps = 30.0
        self.width = 0
        self.height = 0
        self.current_frame_index = -1
        self.is_proxy_active = False
        self.original_path = ""
        self.proxy_path = ""

        self.CACHE_SIZE = self.settings.get("cache_size", 100)
        self.use_gpu = self.settings.get("use_gpu", False)

        self.cache = deque(maxlen=self.CACHE_SIZE)
        self.cache_index_map = {}

        self.smart_seek_lookback = 0
        self.is_fast_seek = (
            False  # Флаг: поддерживает ли видео быстрый поиск (MJPG/AVI)
        )

    def update_settings_live(self):
        # 1. Кэш
        new_cache = self.settings.get("cache_size", 100)
        if new_cache != self.CACHE_SIZE:
            self.CACHE_SIZE = new_cache
            old_data = list(self.cache)
            if len(old_data) > new_cache:
                old_data = old_data[-new_cache:]
            self.cache = deque(old_data, maxlen=self.CACHE_SIZE)
            valid_indices = {item[0] for item in self.cache}
            keys_to_del = [k for k in self.cache_index_map if k not in valid_indices]
            for k in keys_to_del:
                del self.cache_index_map[k]

        # GPU (применится при следующей загрузке, но сохраняем)
        self.use_gpu = self.settings.get("use_gpu", False)

        # Lookback (применяем мгновенно, если это не MJPG/AVI)
        if not self.is_fast_seek:
            new_effort = self.settings.get("seek_effort", 20)
            if self.smart_seek_lookback != new_effort:
                self.smart_seek_lookback = new_effort
                debug_log(
                    f"Live settings update: Lookback set to {self.smart_seek_lookback}"
                )

    def load(self, path, try_proxy=True):
        self.original_path = path
        self.is_proxy_active = False
        self.proxy_path = ""

        # Логика загрузки прокси
        if try_proxy:
            quality = self.settings.get("proxy_quality", 540)
            expected_proxy = self.generate_proxy_path(path, quality)

            # Проверяем .avi и .mp4
            base, _ = os.path.splitext(expected_proxy)
            candidates = [expected_proxy, base + ".avi", base + ".mp4"]

            found_proxy = None
            for cand in candidates:
                if os.path.exists(cand) and os.path.getsize(cand) > 1000:
                    found_proxy = cand
                    break

            if found_proxy:
                if self.load_internal(found_proxy):
                    self.is_proxy_active = True
                    self.proxy_path = found_proxy
                    debug_log(f"Loaded PROXY: {found_proxy}")
                    return True

        debug_log(f"Loaded ORIGINAL: {path}")
        return self.load_internal(path)

    def load_internal(self, path):
        self.full_stop()

        # ВЫБОР BACKEND
        # "AUTO" выбирает cv2.CAP_ANY.
        backend_name = self.settings.get("video_backend", "AUTO")
        backend_map = {
            "MSMF": cv2.CAP_MSMF,
            "DSHOW": cv2.CAP_DSHOW,
            "FFMPEG": cv2.CAP_FFMPEG,
            "AUTO": cv2.CAP_ANY,
        }

        selected_backend = backend_map.get(backend_name, cv2.CAP_ANY)

        # Защита от выбора Windows-специфичных бэкендов на других ОС
        if os.name != "nt" and selected_backend in [cv2.CAP_MSMF, cv2.CAP_DSHOW]:
            selected_backend = cv2.CAP_ANY

        # Попытка открыть с выбранным бэкендом
        self.cap = cv2.VideoCapture(path, selected_backend)

        # АВТОМАТИЧЕСКИЙ FALLBACK
        # Если выбрали специфичный бэкенд (DSHOW/MSMF), но файл не открылся - пробуем AUTO
        if not self.cap.isOpened() and selected_backend != cv2.CAP_ANY:
            debug_log(
                f"Backend {backend_name} failed to open file. Switching to AUTO (FFMPEG/MSMF)."
            )
            self.cap.release()
            self.cap = cv2.VideoCapture(path, cv2.CAP_ANY)

        # --- GPU УСКОРЕНИЕ ---
        # Работает в основном с MSMF на Windows 8/10/11
        if self.use_gpu and self.cap.isOpened():
            try:
                # D3D11 - лучший вариант для Windows 8/10/11
                self.cap.set(cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_D3D11)
            except:
                # Если D3D11 константа недоступна или драйвер не поддерживает
                pass

        if self.cap.isOpened():
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

            if self.fps <= 0:
                self.fps = 30.0
            if self.total_frames <= 0:
                self.total_frames = 0

            # ОПРЕДЕЛЕНИЕ КОДЕКА И НАСТРОЙКА LOOKBACK
            try:
                fourcc_int = int(self.cap.get(cv2.CAP_PROP_FOURCC))
                fourcc_str = "".join(
                    [chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)]
                ).upper()
            except:
                fourcc_str = "UNKNOWN"

            # ЛОГИКА ПРОИЗВОДИТЕЛЬНОСТИ
            user_lookback = self.settings.get("seek_effort", 20)

            # Если это MJPG (Proxy) или просто AVI файл - ищем мгновенно
            if "MJPG" in fourcc_str or path.lower().endswith(".avi"):
                self.is_fast_seek = True
                self.smart_seek_lookback = 0
                debug_log(f"Codec {fourcc_str}: FAST SEEK ENABLED (Lookback=0)")
            else:
                self.is_fast_seek = False
                self.smart_seek_lookback = user_lookback
                debug_log(
                    f"Codec {fourcc_str}: COMPRESSED (Lookback={self.smart_seek_lookback})"
                )

            self.current_frame_index = -1
            self.cache.clear()
            self.cache_index_map.clear()
            return True
        return False

    def generate_proxy_path(self, original_path, quality):
        filename = os.path.basename(original_path)
        name, _ = os.path.splitext(filename)
        ext = self.settings.get_proxy_extension()
        return os.path.join(self.settings.proxies_dir, f"{name}_proxy_{quality}p{ext}")

    def get_proxy_filename(self, path):
        qual = self.settings.get("proxy_quality", 540)
        return self.generate_proxy_path(path, qual)

    def _update_cache(self, idx, frame):
        if idx not in self.cache_index_map:
            if len(self.cache) == self.cache.maxlen:
                oldest_idx, _ = self.cache.popleft()
                if oldest_idx in self.cache_index_map:
                    del self.cache_index_map[oldest_idx]

            frame_copy = frame.copy()
            self.cache.append((idx, frame_copy))
            self.cache_index_map[idx] = frame_copy

    def read(self):
        if not self.cap or not self.cap.isOpened():
            return False, None, self.current_frame_index

        ret, frame = self.cap.read()
        if ret:
            # -1 потому что read() сдвигает позицию на следующий кадр
            pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
            self.current_frame_index = pos
            self._update_cache(pos, frame)
            return True, frame, pos
        return False, None, self.current_frame_index

    def seek(self, target_frame):
        if not self.cap or not self.cap.isOpened():
            return False, None, -1

        target_frame = max(0, min(target_frame, self.total_frames - 1))

        # Сначала ищем в кэше (самое быстрое)
        if target_frame in self.cache_index_map:
            self.current_frame_index = target_frame
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            return True, self.cache_index_map[target_frame], target_frame

        # Если cap уже стоит перед нужным кадром
        current_internal = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
        if target_frame == current_internal:
            return self.read()

        t0 = time.time()

        # Умный поиск с учетом кодека
        if self.smart_seek_lookback == 0:
            # Для MJPG прыгаем прямо в цель
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        else:
            # Для MP4 прыгаем назад, чтобы попасть в KeyFrame
            start_fill = max(0, target_frame - self.smart_seek_lookback)
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_fill)

        found_frame = None

        # Читаем кадры, пока не дойдем до цели
        # Это заполняет кэш "дырами" и обеспечивает плавность декодера
        while True:
            ret, frame = self.cap.read()
            if not ret:
                break

            curr_pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
            self._update_cache(curr_pos, frame)

            if curr_pos == target_frame:
                found_frame = frame

            # Читаем немного вперед, чтобы буфер заполнился
            if curr_pos >= target_frame:
                break

        dt = time.time() - t0
        if dt > 0.1:
            debug_log(f"Seek lag: {dt:.3f}s (Target: {target_frame})")

        if found_frame is not None:
            self.current_frame_index = target_frame
            return True, found_frame, target_frame

        return False, None, self.current_frame_index

    def full_stop(self):
        if self.cap:
            self.cap.release()
            self.cap = None

    def release(self):
        self.full_stop()
        self.cache.clear()
        self.cache_index_map.clear()

    def get_info(self):
        return {
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "total": self.total_frames,
            "is_proxy": self.is_proxy_active,
        }
