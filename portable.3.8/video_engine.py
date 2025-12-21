# type: ignore

import gc  # [FIX] Added for garbage collection
import glob
import os
import time
from collections import deque

import cv2
from PySide2.QtCore import QThread, Signal

IS_DEBUG = "__compiled__" not in globals()


def debug_log(msg):
    if IS_DEBUG:
        print(f"[ENGINE] {msg}")


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
        cap = cv2.VideoCapture(self.input_path, cv2.CAP_ANY)
        if not cap.isOpened():
            self.finished_signal.emit(False, "")
            return

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Расчет размера
        if self.target_height > 0 and height > self.target_height:
            new_height = self.target_height
            ratio = new_height / height
            new_width = int(width * ratio)
        else:
            new_height = height
            new_width = width

        # [FIX] Ensure dimensions are even for codecs
        if new_width % 2 != 0:
            new_width += 1
        if new_height % 2 != 0:
            new_height += 1

        write_fps = round(fps)
        if write_fps <= 0:
            write_fps = 30
        if write_fps > 60:
            write_fps = 60

        # Выбор FOURCC
        if self.codec == "MJPG":
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        elif self.codec == "mp4v":
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        elif self.codec == "avc1":
            fourcc = cv2.VideoWriter_fourcc(*"avc1")
        elif self.codec == "hevc":
            fourcc = cv2.VideoWriter_fourcc(*"HEVC")
        else:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")

        out = cv2.VideoWriter(
            self.output_path, fourcc, write_fps, (new_width, new_height)
        )

        # Fallback, если кодек не открылся
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
        self.is_fast_seek = False

    def update_settings_live(self):
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

        self.use_gpu = self.settings.get("use_gpu", False)

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

        if try_proxy:
            quality = self.settings.get("proxy_quality", 540)
            expected_proxy = self.generate_proxy_path(path, quality)
            base, _ = os.path.splitext(expected_proxy)
            candidates = [expected_proxy, base + ".avi", base + ".mp4"]

            found_proxy = None
            for cand in candidates:
                if os.path.exists(cand) and os.path.getsize(cand) > 1000:
                    found_proxy = cand
                    break

            if not found_proxy:
                filename = os.path.basename(path)
                name, _ = os.path.splitext(filename)
                pattern = os.path.join(self.settings.proxies_dir, f"{name}_proxy_*")
                all_proxies = glob.glob(pattern + ".avi") + glob.glob(pattern + ".mp4")
                if all_proxies:
                    for p in all_proxies:
                        if os.path.getsize(p) > 1000:
                            found_proxy = p
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
        backend_name = self.settings.get("video_backend", "AUTO")

        # Строгий выбор API без fallbacks на этапе инициализации
        selected_api = cv2.CAP_ANY
        if backend_name != "AUTO":
            # Ищем точное совпадение имени константы
            const_name = f"CAP_{backend_name}"
            if hasattr(cv2, const_name):
                selected_api = getattr(cv2, const_name)
            else:
                debug_log(
                    f"WARNING: Backend {backend_name} not found in cv2. Fallback to AUTO."
                )
                selected_api = cv2.CAP_ANY

        debug_log(
            f"Attempting to open video with API: {backend_name} (Val: {selected_api})"
        )

        self.cap = cv2.VideoCapture(path, selected_api)

        if not self.cap.isOpened():
            if selected_api != cv2.CAP_ANY:
                debug_log(
                    f"Backend {backend_name} failed to open file. Trying AUTO fallback..."
                )
                self.cap = cv2.VideoCapture(path, cv2.CAP_ANY)

        if self.cap.isOpened():
            # --- REAL DEBUGGING ---
            real_backend = self.cap.getBackendName()
            debug_log(
                f"SUCCESS: Video opened. Requested: {backend_name} -> Actual: {real_backend}"
            )

            # --- ЛОГИКА АППАРАТНОГО УСКОРЕНИЯ ---
            if self.use_gpu:
                backends_to_try = []
                if hasattr(cv2, "VIDEO_ACCELERATION_D3D11"):
                    backends_to_try.append(cv2.VIDEO_ACCELERATION_D3D11)
                if hasattr(cv2, "VIDEO_ACCELERATION_CUDA"):
                    backends_to_try.append(cv2.VIDEO_ACCELERATION_CUDA)
                if hasattr(cv2, "VIDEO_ACCELERATION_MFX"):
                    backends_to_try.append(cv2.VIDEO_ACCELERATION_MFX)
                if hasattr(cv2, "VIDEO_ACCELERATION_ANY"):
                    backends_to_try.append(cv2.VIDEO_ACCELERATION_ANY)

                for backend in backends_to_try:
                    self.cap.set(cv2.CAP_PROP_HW_ACCELERATION, backend)
                    val = self.cap.get(cv2.CAP_PROP_HW_ACCELERATION)
                    if int(val) == backend:
                        break

            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if self.fps <= 0:
                self.fps = 30.0
            if self.total_frames <= 0:
                self.total_frames = 0

            try:
                fourcc_int = int(self.cap.get(cv2.CAP_PROP_FOURCC))
                fourcc_str = "".join(
                    [chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)]
                ).upper()
            except:
                fourcc_str = "UNKNOWN"

            user_lookback = self.settings.get("seek_effort", 20)
            if "MJPG" in fourcc_str or path.lower().endswith(".avi"):
                self.is_fast_seek = True
                self.smart_seek_lookback = 0
            else:
                self.is_fast_seek = False
                self.smart_seek_lookback = user_lookback

            debug_log(
                f"Info: {self.width}x{self.height} @ {self.fps:.2f}fps, Codec: {fourcc_str}"
            )

            self.current_frame_index = -1
            self.cache.clear()
            self.cache_index_map.clear()
            return True

        debug_log("CRITICAL: Failed to open video with any backend.")
        return False

    def generate_proxy_path(self, original_path, quality):
        filename = os.path.basename(original_path)
        name, _ = os.path.splitext(filename)
        ext = self.settings.get_proxy_extension()
        return os.path.join(self.settings.proxies_dir, f"{name}_proxy_{quality}p{ext}")

    def get_proxy_filename(self, path):
        qual = self.settings.get("proxy_quality", 540)
        return self.generate_proxy_path(path, qual)

    def find_existing_proxy(self, original_path):
        if not original_path:
            return False
        try:
            filename = os.path.basename(original_path)
            name, _ = os.path.splitext(filename)
            proxies_dir = self.settings.proxies_dir
            patterns = [
                os.path.join(proxies_dir, f"{name}_proxy_*.avi"),
                os.path.join(proxies_dir, f"{name}_proxy_*.mp4"),
            ]
            for p in patterns:
                candidates = glob.glob(p)
                for c in candidates:
                    if os.path.exists(c) and os.path.getsize(c) > 1000:
                        return True
            return False
        except:
            return False

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
            pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
            if pos < 0:
                pos = self.current_frame_index + 1

            self.current_frame_index = pos
            self._update_cache(pos, frame)
            return True, frame, pos
        return False, None, self.current_frame_index

    def seek(self, target_frame):
        if not self.cap or not self.cap.isOpened():
            return False, None, -1

        target_frame = max(0, min(target_frame, self.total_frames - 1))

        if target_frame in self.cache_index_map:
            self.current_frame_index = target_frame
            return True, self.cache_index_map[target_frame], target_frame

        diff = target_frame - self.current_frame_index
        if 0 < diff <= 10:
            while self.current_frame_index < target_frame:
                ret, frame, _ = self.read()
                if not ret:
                    break
                if self.current_frame_index == target_frame:
                    return True, frame, target_frame

            if self.current_frame_index in self.cache_index_map:
                return (
                    True,
                    self.cache_index_map[self.current_frame_index],
                    self.current_frame_index,
                )

        t0 = time.time()

        if self.smart_seek_lookback == 0:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame, _ = self.read()
            if ret:
                return True, frame, self.current_frame_index
        else:
            start_fill = max(0, target_frame - self.smart_seek_lookback)
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_fill)

            current_decode_pos = start_fill
            found_frame = None

            while current_decode_pos <= target_frame:
                ret, frame = self.cap.read()
                if not ret:
                    break

                self._update_cache(current_decode_pos, frame)
                if current_decode_pos == target_frame:
                    found_frame = frame

                current_decode_pos += 1

            if found_frame is not None:
                self.current_frame_index = target_frame
                dt = time.time() - t0
                if dt > 0.1:
                    debug_log(f"Seek lag: {dt:.3f}s (Target: {target_frame})")
                return True, found_frame, target_frame

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame, _ = self.read()
        if ret:
            return True, frame, target_frame

        return False, None, self.current_frame_index

    def full_stop(self):
        if self.cap:
            self.cap.release()
            self.cap = None
        # Force Garbage Collection to release Windows file locks
        gc.collect()

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
