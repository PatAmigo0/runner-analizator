import time

from PySide2.QtCore import QMutex, QThread, Signal
from video_engine import VideoEngine


class VideoThread(QThread):
    change_pixmap_signal = Signal(object)
    finished_signal = Signal()
    video_info_signal = Signal(dict)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.engine = VideoEngine(settings)
        self._run_flag = True
        self.fps = 30
        self.speed = 1.0
        self.current_frame_num = 0
        self.mutex = QMutex()

    def update_settings_live(self):
        self.mutex.lock()
        try:
            self.engine.update_settings_live()
        finally:
            self.mutex.unlock()

    def load_video(self, path, try_proxy=True):
        self.stop()
        self.mutex.lock()
        try:
            if self.engine.load(path, try_proxy):
                info = self.engine.get_info()
                self.fps = info["fps"] if info["fps"] > 0 else 30
                self.current_frame_num = 0
                self.video_info_signal.emit(info)
        finally:
            self.mutex.unlock()
        self.read_one_frame()

    def read_one_frame(self):
        self.mutex.lock()
        try:
            ret, fr, idx = self.engine.read()
            if ret:
                self.current_frame_num = idx
                self.change_pixmap_signal.emit(fr)
        finally:
            self.mutex.unlock()

    def seek(self, n):
        self.mutex.lock()
        try:
            ret, fr, idx = self.engine.seek(n)
            if ret:
                self.current_frame_num = idx
                self.change_pixmap_signal.emit(fr)
        finally:
            self.mutex.unlock()

    def run(self):
        self._run_flag = True

        # [FIX] Better sync logic
        start_playback_time = time.time()
        frames_played_in_loop = 0

        while self._run_flag:
            self.mutex.lock()
            fr_r = False
            fr = None
            try:
                if not self._run_flag:
                    self.mutex.unlock()
                    break
                ret, fr, idx = self.engine.read()
                if ret:
                    self.current_frame_num = idx
                    fr_r = True
                else:
                    self.finished_signal.emit()
                    self._run_flag = False
            finally:
                self.mutex.unlock()

            if fr_r and fr is not None:
                self.change_pixmap_signal.emit(fr)

            if self._run_flag and self.fps > 0:
                frames_played_in_loop += 1

                # Calculate expected time based on frames played
                expected_time = frames_played_in_loop / (self.fps * self.speed)
                actual_time = time.time() - start_playback_time

                # Calculate sleep needed to match expected time
                sleep_needed = expected_time - actual_time

                # If we are ahead (rendering fast), sleep
                if sleep_needed > 0:
                    self.msleep(int(sleep_needed * 1000))
                # If we are behind by more than 0.2s, reset clock to avoid aggressive catch-up
                elif sleep_needed < -0.2:
                    start_playback_time = time.time()
                    frames_played_in_loop = 0

    def stop(self):
        self._run_flag = False
        self.wait(500)
        if self.isRunning():
            self.terminate()

    def full_release(self):
        self.stop()
        self.mutex.lock()
        try:
            self.engine.release()
        finally:
            self.mutex.unlock()
