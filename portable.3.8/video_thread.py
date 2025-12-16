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
        while self._run_flag:
            st = time.time()
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
                dt = time.time() - st
                td = 1.0 / (self.fps * self.speed)
                sl = td - dt
                if sl > 0:
                    self.msleep(int(sl * 1000))
                else:
                    self.msleep(1)

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
