# player.py
import wave
import threading
import numpy as np
import sounddevice as sd

class WavPlayer:
    """基于 sounddevice 的轻量播放器，支持播放/暂停/跳转/进度获取"""
    def __init__(self, wav_path: str):
        self.wav_path = wav_path
        self.sr = 44100
        self.channels = 1
        self._frames = None          # numpy int16 [n, channels]
        self._pos = 0                # 当前位置(帧)
        self._lock = threading.RLock()
        self._stream = None
        self._playing = False
        self._load_wav()

    def _load_wav(self):
        with wave.open(self.wav_path, "rb") as wf:
            self.channels = wf.getnchannels()
            self.sr = wf.getframerate()
            nframes = wf.getnframes()
            raw = wf.readframes(nframes)
        data = np.frombuffer(raw, dtype=np.int16)
        if self.channels > 1:
            data = data.reshape(-1, self.channels)
        else:
            data = data.reshape(-1, 1)
        self._frames = data
        self._pos = 0

    def _callback(self, outdata, frames, time_info, status):
        with self._lock:
            if not self._playing or self._frames is None:
                outdata[:] = 0
                return
            end = min(self._pos + frames, len(self._frames))
            chunk = self._frames[self._pos:end]
            outdata[:len(chunk), :self.channels] = chunk
            if len(chunk) < frames:
                outdata[len(chunk):] = 0
                self._playing = False
            self._pos = end

    def play(self):
        with self._lock:
            if self._stream is None:
                self._stream = sd.OutputStream(
                    samplerate=self.sr, channels=self.channels, dtype="int16",
                    callback=self._callback, blocksize=0)
                self._stream.start()
            self._playing = True

    def pause(self):
        with self._lock:
            self._playing = False

    def stop(self):
        with self._lock:
            self._playing = False
            self._pos = 0

    def close(self):
        with self._lock:
            self._playing = False
            if self._stream is not None:
                self._stream.stop(); self._stream.close()
                self._stream = None

    def seek(self, t_seconds: float):
        with self._lock:
            t_seconds = max(0.0, min(t_seconds, self.duration()))
            self._pos = int(t_seconds * self.sr)

    def current_time(self) -> float:
        with self._lock:
            return self._pos / float(self.sr)

    def duration(self) -> float:
        return len(self._frames) / float(self.sr)
