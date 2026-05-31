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
        self.playing = (
            False  # Управляет ходом воспроизведения внутри единого бесконечного потока
        )
        self.fps = 30
        self.speed = 1.0
        self.current_frame_num = 0
        self.mutex = QMutex()
        self.wait_condition = QWaitCondition()
        self.pending_seek = None

    def set_playing(self, play_state):
        self.mutex.lock()
        try:
            self.playing = play_state
            self.wait_condition.wakeAll()  # Пробуждаем поток немедленно!
        finally:
            self.mutex.unlock()

    def update_settings_live(self):
        self.mutex.lock()
        try:
            self.engine.update_settings_live()
        finally:
            self.mutex.unlock()

    def load_video(self, path, try_proxy=True):
        # Не выключаем QThread полностью, а временно приостанавливаем проигрывание
        self.set_playing(False)
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

        # Если поток еще не был запущен в ОС, запускаем его
        if not self.isRunning():
            self.start()

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
            self.pending_seek = n
            self.wait_condition.wakeAll()  # Пробуждаем поток немедленно!
        finally:
            self.mutex.unlock()

    def run(self):
        self._run_flag = True
        start_playback_time = time.time()
        frames_played_in_loop = 0

        while self._run_flag:
            # 1. Проверяем, есть ли асинхронный запрос на перемещение (seek)
            target_seek = None
            self.mutex.lock()
            try:
                if self.pending_seek is not None:
                    target_seek = self.pending_seek
                    self.pending_seek = None
            finally:
                self.mutex.unlock()

            if target_seek is not None:
                self.mutex.lock()
                try:
                    ret, fr, idx = self.engine.seek(target_seek)
                    if ret:
                        self.current_frame_num = idx
                        self.change_pixmap_signal.emit(fr)
                finally:
                    self.mutex.unlock()

                # Сбрасываем тайминги воспроизведения после перехода
                start_playback_time = time.time()
                frames_played_in_loop = 0
                continue  # Сразу переходим к следующей итерации

            is_active_play = False
            self.mutex.lock()
            try:
                is_active_play = self.playing
            finally:
                self.mutex.unlock()

            if is_active_play:
                # --- РЕЖИМ ВОСПРОИЗВЕДЕНИЯ ---
                self.mutex.lock()
                fr_r = False
                fr = None
                try:
                    ret, fr, idx = self.engine.read()
                    if ret:
                        self.current_frame_num = idx
                        fr_r = True
                    else:
                        self.finished_signal.emit()
                        self.playing = False
                finally:
                    self.mutex.unlock()

                if fr_r and fr is not None:
                    self.change_pixmap_signal.emit(fr)

                if self.fps > 0:
                    frames_played_in_loop += 1
                    expected_time = frames_played_in_loop / (self.fps * self.speed)
                    actual_time = time.time() - start_playback_time
                    sleep_needed = expected_time - actual_time

                    if sleep_needed > 0:
                        self.mutex.lock()
                        try:
                            self.wait_condition.wait(
                                self.mutex, int(sleep_needed * 1000)
                            )
                        finally:
                            self.mutex.unlock()
                    elif sleep_needed < -0.2:
                        start_playback_time = time.time()
                        frames_played_in_loop = 0
            else:
                # --- РЕЖИМ ПАУЗЫ: Алгоритм двунаправленного фонового префетча ---
                prefetch_target = None
                self.mutex.lock()
                try:
                    # Сканируем будущее (до 45 кадров вперед) на наличие незакэшированных кадров
                    for offset in range(1, 46):
                        cand = self.current_frame_num + offset
                        if cand >= self.engine.total_frames:
                            break
                        if cand not in self.engine.cache_index_map:
                            prefetch_target = cand
                            break
                finally:
                    self.mutex.unlock()

                if prefetch_target is not None:
                    self.mutex.lock()
                    try:
                        old_idx = self.current_frame_num
                        self.engine.seek(prefetch_target)
                        self.engine.current_frame_index = old_idx
                    finally:
                        self.mutex.unlock()

                    # Даем маленькую паузу, но если придет seek - просыпаемся мгновенно!
                    self.mutex.lock()
                    try:
                        self.wait_condition.wait(self.mutex, 8)
                    finally:
                        self.mutex.unlock()
                else:
                    # Если все будущие кадры уже закэшированы, засыпаем глубже
                    self.mutex.lock()
                    try:
                        self.wait_condition.wait(self.mutex, 45)
                    finally:
                        self.mutex.unlock()

                # Сбрасываем тайминг синхронизации плеера
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
        self.mutex.lock()
        try:
            self.engine.release()
        finally:
            self.mutex.unlock()
