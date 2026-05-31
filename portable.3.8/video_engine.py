# type: ignore

import gc
import glob
import os
import re
import subprocess
from collections import deque

import cv2
from PySide2.QtCore import QThread, Signal

from logger import Logger
from utils import get_resource_path

# Попытка импортировать PyAV для супер-быстрой и точной перемотки оригинальных MP4/MKV
try:
    import av

    HAS_PYAV = True
except ImportError:
    HAS_PYAV = False


IS_DEBUG = "__compiled__" not in globals()
logger = Logger(IS_DEBUG)


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
        self.process = None

    def run(self):
        # 1. Получаем общее количество кадров для прогресс-бара
        cap = cv2.VideoCapture(self.input_path)
        total_frames = 1
        if cap.isOpened():
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()

        if total_frames <= 0:
            total_frames = 1

        # 2. Формируем команду FFmpeg
        # scale=-2:540 (сохраняет пропорции, делает ширину четной, высота 540)
        vf_scale = f"scale=-2:{self.target_height}"

        # Подбираем энкодер
        if self.codec == "MJPG":
            vcodec = "mjpeg"
            extra_args = ["-q:v", "3"]  # Качество для mjpeg
        elif self.codec == "hevc":
            vcodec = "libx265"
            extra_args = ["-preset", "fast", "-crf", "26"]
        else:  # avc1 / mp4v -> H.264
            vcodec = "libx264"
            extra_args = ["-preset", "veryfast", "-crf", "23"]

        ffmpeg_path = get_resource_path("ffmpeg.exe")

        cmd = (
            [
                ffmpeg_path,
                "-y",
                "-hwaccel",
                "auto",
                "-i",
                self.input_path,
                "-vf",
                vf_scale,
                "-c:v",
                vcodec,
            ]
            + extra_args
            + ["-an", self.output_path]
        )

        try:
            # Запускаем ffmpeg, перехватывая stderr, куда он пишет прогресс
            self.process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            # Регулярка для поиска слова "frame=  123" в выводе FFmpeg
            frame_regex = re.compile(r"frame=\s*(\d+)")

            for line in self.process.stderr:
                if not self._is_running:
                    self.process.terminate()
                    break

                match = frame_regex.search(line)
                if match:
                    current_frame = int(match.group(1))
                    percent = int((current_frame / total_frames) * 100)
                    self.progress_signal.emit(min(percent, 100))

            self.process.wait()

            if self._is_running and self.process.returncode == 0:
                self.progress_signal.emit(100)
                self.finished_signal.emit(True, self.output_path)
            else:
                # Если прервали или ошибка
                if os.path.exists(self.output_path):
                    try:
                        os.remove(self.output_path)
                    except:
                        pass
                self.finished_signal.emit(False, "")

        except FileNotFoundError:
            logger.file(
                "FFmpeg не найден в системе! Пожалуйста, скачайте ffmpeg.exe и положите рядом с программой."
            )
            self.finished_signal.emit(False, "")
        except Exception as e:
            logger.file(f"Proxy generation failed: {e}")
            self.finished_signal.emit(False, "")

    def stop(self):
        self.set_playing(False)
        self._run_flag = False

        # принудительно будим поток, если он уснул в ожидании кэширования,
        self.state_mutex.lock()
        try:
            self.wait_condition.wakeAll()
        finally:
            self.state_mutex.unlock()

        # ждем штатного завершения (1 секунда)
        self.wait(1000)

        # терминируем только в крайнем случае
        if self.isRunning():
            self.terminate()
            self.wait()

    def full_release(self):
        self.stop()

        # Пробуем захватить мьютекс, но если он заблокировался из-за terminate(),
        # то просто игнорируем, чтобы не вызвать белый экран (deadlock).
        locked = self.engine_mutex.tryLock(500)
        try:
            self.engine.release()
        finally:
            if locked:
                self.engine_mutex.unlock()


# --- VIDEO ENGINE ---
class VideoEngine:
    def __init__(self, settings_manager):
        self.settings = settings_manager
        self.cap = None

        # Двухдвижковая структура: PyAV (FFmpeg) и OpenCV
        self.av_container = None
        self.av_stream = None
        self.av_frame_generator = None
        self.is_av_active = False

        self.total_frames = 0
        self.fps = 30.0
        self.width = 0
        self.height = 0
        self.current_frame_index = -1
        self.is_proxy_active = False
        self.original_path = ""
        self.proxy_path = ""

        # Ограничиваем кэш на 32-битных системах во избежание MemoryError
        import struct

        is_32bit = struct.calcsize("P") == 4
        max_allowed_cache = 120 if is_32bit else 300

        self.CACHE_SIZE = min(self.settings.get("cache_size", 100), max_allowed_cache)
        self.use_gpu = self.settings.get("use_gpu", False)

        self.cache = deque(maxlen=self.CACHE_SIZE)
        self.cache_index_map = {}

        self.smart_seek_lookback = 0
        self.is_fast_seek = False

    def update_settings_live(self):
        import struct

        is_32bit = struct.calcsize("P") == 4
        max_allowed_cache = 120 if is_32bit else 300

        new_cache = min(self.settings.get("cache_size", 100), max_allowed_cache)
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
                logger.debug(
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
                    logger.debug(f"Loaded PROXY: {found_proxy}")
                    return True

        logger.debug(f"Loaded ORIGINAL: {path}")
        return self.load_internal(path)

    def load_internal(self, path):
        self.full_stop()

        # Для прокси-файлов (обычно AVI / MJPEG) OpenCV идеален, так как каждый кадр ключевой.
        # Для оригинальных тяжелых MP4 используем PyAV (FFmpeg C-level) для аппаратной скорости.
        is_proxy_file = "proxy" in os.path.basename(
            path
        ).lower() or path.lower().endswith(".avi")

        if HAS_PYAV and not is_proxy_file:
            try:
                self.av_container = av.open(path)
                self.av_stream = self.av_container.streams.video[0]
                # Включаем многопоточное декодирование силами FFmpeg!
                self.av_stream.thread_type = "AUTO"

                # Читаем параметры
                self.fps = (
                    float(self.av_stream.average_rate)
                    if self.av_stream.average_rate
                    else 30.0
                )
                self.width = self.av_stream.width
                self.height = self.av_stream.height
                self.total_frames = self.av_stream.frames

                if self.total_frames <= 0:
                    # Резервный расчет по длительности
                    duration = self.av_container.duration
                    if duration:
                        self.total_frames = int((duration / 1000000.0) * self.fps)
                    else:
                        self.total_frames = 0

                self.is_av_active = True
                self.current_frame_index = -1
                self.cache.clear()
                self.cache_index_map.clear()
                self.av_frame_generator = None

                logger.debug(
                    f"PyAV SUCCESS: Opened {path}. {self.width}x{self.height} @ {self.fps:.2f}fps, total frames: {self.total_frames}"
                )
                return True
            except Exception as e:
                logger.debug(
                    f"PyAV failed to load {path}. Fallback to OpenCV. Error: {e}"
                )
                self.is_av_active = False
                if self.av_container:
                    self.av_container.close()
                    self.av_container = None

        # --- OPENCV FALLBACK / PROXY BACKEND ---
        backend_name = self.settings.get("video_backend", "AUTO")
        selected_api = cv2.CAP_ANY
        if backend_name != "AUTO":
            const_name = f"CAP_{backend_name}"
            if hasattr(cv2, const_name):
                selected_api = getattr(cv2, const_name)
            else:
                logger.file(
                    f"WARNING: Backend {backend_name} not found in cv2. Fallback to AUTO."
                )
                selected_api = cv2.CAP_ANY

        logger.debug(
            f"Attempting to open video with API: {backend_name} (Val: {selected_api})"
        )
        self.cap = cv2.VideoCapture(path, selected_api)

        if not self.cap.isOpened():
            if selected_api != cv2.CAP_ANY:
                logger.debug(
                    f"Backend {backend_name} failed to open file. Trying AUTO fallback..."
                )
                self.cap = cv2.VideoCapture(path, cv2.CAP_ANY)

        if self.cap.isOpened():
            real_backend = self.cap.getBackendName()
            logger.debug(
                f"SUCCESS: Video opened. Requested: {backend_name} -> Actual: {real_backend}"
            )

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

            logger.debug(
                f"Info: {self.width}x{self.height} @ {self.fps:.2f}fps, Codec: {fourcc_str}"
            )

            self.current_frame_index = -1
            self.cache.clear()
            self.cache_index_map.clear()
            return True

        logger.file("CRITICAL: Failed to open video with any backend.")
        return False

    def clear_av_generator(self):
        self.av_frame_generator = None

    def generate_proxy_path(self, original_path, quality):
        filename = os.path.basename(original_path)
        name, _ = os.path.splitext(filename)
        ext = self.settings.get_proxy_extension()
        return os.path.join(self.settings.proxies_dir, f"{name}_proxy_{quality}p{ext}")

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

            # Оптимизация аллокации: копируем кадр только если нужно сохранить в кэше
            frame_copy = frame.copy()
            self.cache.append((idx, frame_copy))
            self.cache_index_map[idx] = frame_copy

    def get_cached_set(self):
        # Возвращаем копию множества ключей кэша для безопасного чтения из UI-потока
        return set(self.cache_index_map.keys())

    def read(self):
        if self.is_av_active:
            try:
                if self.av_frame_generator is None:
                    self.av_frame_generator = self.av_container.decode(video=0)

                frame = next(self.av_frame_generator)
                if frame.pts is not None:
                    pts_time = float(frame.pts * self.av_stream.time_base)
                    pos = int(round(pts_time * self.fps))
                else:
                    pos = (
                        frame.index
                        if frame.index is not None
                        else self.current_frame_index + 1
                    )

                pos = max(0, min(pos, self.total_frames - 1))
                frame_bgr = frame.to_ndarray(format="bgr24")

                self.current_frame_index = pos
                self._update_cache(pos, frame_bgr)
                return True, frame_bgr, pos
            except StopIteration:
                self.av_frame_generator = None
                return False, None, self.current_frame_index
            except Exception as e:
                logger.debug(f"PyAV read error: {e}. Resetting generator.")
                self.av_frame_generator = None
                return False, None, self.current_frame_index

        # --- OpenCV Read ---
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
        target_frame = max(0, min(target_frame, self.total_frames - 1))

        if target_frame in self.cache_index_map:
            self.current_frame_index = target_frame
            return True, self.cache_index_map[target_frame], target_frame

        # --- PyAV Seek ---
        if self.is_av_active:
            self.clear_av_generator()
            stream = self.av_stream
            time_base = stream.time_base

            # Рассчитываем точное смещение в единицах time_base
            target_sec = target_frame / self.fps
            target_ts = int(target_sec / time_base)

            try:
                # Перемещаемся аппаратно к ключевому кадру (Keyframe) ДО целевой позиции
                self.av_container.seek(target_ts, stream=stream)

                found_frame = None
                self.av_frame_generator = self.av_container.decode(video=0)

                # Декодируем вперед до целевого кадра, параллельно забивая кэш
                for frame in self.av_frame_generator:
                    if frame.pts is not None:
                        pts_time = float(frame.pts * time_base)
                        current_idx = int(round(pts_time * self.fps))
                    else:
                        current_idx = frame.index if frame.index is not None else 0

                    current_idx = max(0, min(current_idx, self.total_frames - 1))
                    frame_bgr = frame.to_ndarray(format="bgr24")
                    self._update_cache(current_idx, frame_bgr)

                    if current_idx == target_frame:
                        found_frame = frame_bgr
                        self.current_frame_index = target_frame
                        break
                    elif current_idx > target_frame:
                        # Если случайно пролетели мимо целевого из-за особенностей контейнера
                        found_frame = frame_bgr
                        self.current_frame_index = current_idx
                        break

                if found_frame is not None:
                    return True, found_frame, self.current_frame_index
            except Exception as e:
                logger.debug(f"PyAV Seek failed: {e}. Reinitializing container.")
                try:
                    self.av_container = av.open(self.original_path)
                    self.av_stream = self.av_container.streams.video[0]
                    self.av_stream.thread_type = "AUTO"
                except:
                    pass

        # --- OpenCV Seek Fallback ---
        if not self.cap or not self.cap.isOpened():
            return False, None, -1

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
        if self.av_container:
            try:
                self.av_container.close()
            except:
                pass
            self.av_container = None
            self.av_stream = None
            self.av_frame_generator = None
            self.is_av_active = False

        # Форсированный сборщик мусора для освобождения дескрипторов файлов Windows
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
