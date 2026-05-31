import time

from PySide2.QtCore import QMutex, QThread, QWaitCondition, Signal

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

        self.playing = False
        self.fps = 30
        self.speed = 1.0
        self.current_frame_num = 0

        # ОПТИМИЗАЦИЯ ПОТОКОВ:
        # engine_mutex - блокирует только тяжелые операции OpenCV/PyAV
        # state_mutex - блокирует мгновенные переменные интерфейса, чтобы UI никогда не зависал
        self.engine_mutex = QMutex()
        self.state_mutex = QMutex()

        self.wait_condition = QWaitCondition()
        self.pending_seek = None
        self.last_seek_time = time.time()

    def set_playing(self, play_state):
        self.state_mutex.lock()
        try:
            self.playing = play_state
            self.wait_condition.wakeAll()
        finally:
            self.state_mutex.unlock()

    def update_settings_live(self):
        self.engine_mutex.lock()
        try:
            self.engine.update_settings_live()
        finally:
            self.engine_mutex.unlock()

    def load_video(self, path, try_proxy=True):
        self.set_playing(False)
        self.engine_mutex.lock()
        try:
            if self.engine.load(path, try_proxy):
                info = self.engine.get_info()
                self.fps = info["fps"] if info["fps"] > 0 else 30
                self.current_frame_num = 0
                self.video_info_signal.emit(info)
        finally:
            self.engine_mutex.unlock()

        self.read_one_frame()

        if not self.isRunning():
            self.start()

    def read_one_frame(self):
        self.engine_mutex.lock()
        try:
            ret, fr, idx = self.engine.read()
            if ret:
                self.current_frame_num = idx
                self.change_pixmap_signal.emit(fr)
        finally:
            self.engine_mutex.unlock()

    def seek(self, n):
        # МГНОВЕННАЯ ОПЕРАЦИЯ: GUI поток никогда не зависнет здесь
        self.state_mutex.lock()
        try:
            self.pending_seek = n
            self.last_seek_time = time.time()
            self.wait_condition.wakeAll()
        finally:
            self.state_mutex.unlock()

    def run(self):
        self._run_flag = True
        start_playback_time = time.time()
        frames_played_in_loop = 0

        while self._run_flag:
            target_seek = None
            is_active_play = False

            # Быстрое чтение команд от UI
            self.state_mutex.lock()
            try:
                if self.pending_seek is not None:
                    target_seek = self.pending_seek
                    self.pending_seek = None
                is_active_play = self.playing
            finally:
                self.state_mutex.unlock()

            # --- ОБРАБОТКА ПОЛЗУНКА И СТРЕЛОЧЕК ---
            if target_seek is not None:
                self.engine_mutex.lock()
                try:
                    ret, fr, idx = self.engine.seek(target_seek)
                finally:
                    self.engine_mutex.unlock()

                if ret:
                    self.current_frame_num = idx
                    self.change_pixmap_signal.emit(fr)

                start_playback_time = time.time()
                frames_played_in_loop = 0
                continue  # Возвращаемся в начало, чтобы пропустить устаревшие кадры

            # --- РЕЖИМ ВОСПРОИЗВЕДЕНИЯ ---
            if is_active_play:
                self.engine_mutex.lock()
                fr_r = False
                fr = None
                try:
                    ret, fr, idx = self.engine.read()
                    if ret:
                        self.current_frame_num = idx
                        fr_r = True
                    else:
                        self.finished_signal.emit()
                        self.set_playing(False)
                finally:
                    self.engine_mutex.unlock()

                if fr_r and fr is not None:
                    self.change_pixmap_signal.emit(fr)

                if self.fps > 0:
                    frames_played_in_loop += 1
                    expected_time = frames_played_in_loop / (self.fps * self.speed)
                    actual_time = time.time() - start_playback_time
                    sleep_needed = expected_time - actual_time

                    if sleep_needed > 0:
                        self.state_mutex.lock()
                        try:
                            self.wait_condition.wait(
                                self.state_mutex, int(sleep_needed * 1000)
                            )
                        finally:
                            self.state_mutex.unlock()
                    elif sleep_needed < -0.2:
                        start_playback_time = time.time()
                        frames_played_in_loop = 0

            # --- РЕЖИМ ПАУЗЫ (ФОНОВОЕ КЭШИРОВАНИЕ) ---
            else:
                prefetch_target = None

                # Ждем 100мс после последнего движения ползунка, чтобы префетч
                # не воровал мощности процессора во время активного скраббинга
                if time.time() - self.last_seek_time > 0.1:
                    self.engine_mutex.lock()
                    try:
                        for offset in range(1, 46):
                            cand = self.current_frame_num + offset
                            if cand >= self.engine.total_frames:
                                break
                            if cand not in self.engine.cache_index_map:
                                prefetch_target = cand
                                break
                    finally:
                        self.engine_mutex.unlock()

                if prefetch_target is not None:
                    self.engine_mutex.lock()
                    try:
                        old_idx = self.current_frame_num
                        self.engine.seek(prefetch_target)
                        self.engine.current_frame_index = old_idx
                    finally:
                        self.engine_mutex.unlock()

                    self.state_mutex.lock()
                    try:
                        self.wait_condition.wait(self.state_mutex, 2)
                    finally:
                        self.state_mutex.unlock()
                else:
                    # Спим глубоко, если все закэшировано
                    self.state_mutex.lock()
                    try:
                        self.wait_condition.wait(self.state_mutex, 45)
                    finally:
                        self.state_mutex.unlock()

                start_playback_time = time.time()
                frames_played_in_loop = 0

    def stop(self):
        self.set_playing(False)
        self._run_flag = False
        self.wait(500)
        if self.isRunning():
            self.terminate()

    def full_release(self):
        self.stop()
        self.engine_mutex.lock()
        try:
            self.engine.release()
        finally:
            self.engine_mutex.unlock()
