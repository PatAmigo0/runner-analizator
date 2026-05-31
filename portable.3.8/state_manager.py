import copy


class StateManager:
    def __init__(self):
        self.total_frames = 0
        self.fps = 30.0
        self.segments = []
        self.markers = []
        self.history = []
        self.redo_stack = []
        self.is_undoing = False

    def reset(self):
        self.segments = []
        self.markers = []
        self.history = []
        self.redo_stack = []
        self.total_frames = 0
        self.fps = 30.0

    def init_video(self, total_frames, fps):
        self.total_frames = total_frames
        self.fps = fps
        self.segments = [{"start": 0, "end": total_frames}]
        self.markers = []
        self.history = []
        self.redo_stack = []

    def capture_session_state(self):
        return {
            "segments": copy.deepcopy(self.segments),
            "markers": copy.deepcopy(self.markers),
            "history": copy.deepcopy(self.history),
            "redo_stack": copy.deepcopy(self.redo_stack),
            "fps": self.fps,
        }

    def load_session_state(self, state):
        self.segments = state.get("segments", [])
        self.markers = state.get("markers", [])
        self.history = state.get("history", [])
        self.redo_stack = state.get("redo_stack", [])
        self.fps = state.get("fps", 30.0)

    def save_state(self):
        if self.is_undoing:
            return
        self.redo_stack.clear()
        self.history.append(
            {
                "segments": copy.deepcopy(self.segments),
                "markers": copy.deepcopy(self.markers),
            }
        )
        if len(self.history) > 1000:
            self.history.pop(0)

    def undo(self):
        if not self.history:
            return False
        self.redo_stack.append(
            {
                "segments": copy.deepcopy(self.segments),
                "markers": copy.deepcopy(self.markers),
            }
        )
        self.is_undoing = True
        state = self.history.pop()

        if not state["segments"] and self.total_frames > 0:
            self.segments = [{"start": 0, "end": self.total_frames}]
        else:
            self.segments = state["segments"]

        self.markers = state["markers"]
        self.is_undoing = False
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        self.history.append(
            {
                "segments": copy.deepcopy(self.segments),
                "markers": copy.deepcopy(self.markers),
            }
        )
        self.is_undoing = True
        state = self.redo_stack.pop()
        self.segments = state["segments"]
        self.markers = state["markers"]
        self.is_undoing = False
        return True

    def remap_history_data(self, ratio):
        for state in self.history:
            if "segments" in state:
                for seg in state["segments"]:
                    seg["start"] = int(seg["start"] * ratio)
                    seg["end"] = int(seg["end"] * ratio)
            if "markers" in state:
                for mark in state["markers"]:
                    mark["frame"] = int(mark["frame"] * ratio)

        for state in self.redo_stack:
            if "segments" in state:
                for seg in state["segments"]:
                    seg["start"] = int(seg["start"] * ratio)
                    seg["end"] = int(seg["end"] * ratio)
            if "markers" in state:
                for mark in state["markers"]:
                    mark["frame"] = int(mark["frame"] * ratio)
