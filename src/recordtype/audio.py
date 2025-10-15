# src/recordtype/audio.py
import queue
import wave
import threading
import time
from typing import List, Tuple, Optional

import sounddevice as sd


class AudioRecorder:
    """
    录音器：
    - 支持选择输入设备（index 或 None）
    - 更稳健的设备枚举（WASAPI -> DirectSound -> MME 逐级回退）
    - 16-bit PCM 写 WAV（后台线程写入，避免 UI 卡顿）
    - 提供 elapsed_hms() 与 elapsed_seconds() 供 UI / 锚点使用
    """

    def __init__(
        self,
        samplerate: int = 44100,
        channels: int = 1,
        sample_width: int = 2,  # 16-bit
        device: Optional[int] = None,
    ):
        self.sr = samplerate
        self.channels = channels
        self.sample_width = sample_width
        self.device = device  # 可为 None 或 输入设备索引(int)

        self.stream: Optional[sd.RawInputStream] = None
        self.wave_file: Optional[wave.Wave_write] = None
        self.q: "queue.Queue[bytes]" = queue.Queue()
        self._writer: Optional[threading.Thread] = None

        self.is_recording: bool = False
        self._start_perf: Optional[float] = None
        self.audio_path: Optional[str] = None

    # ----------------------------------------------------------------------
    # 设备枚举（稳健版）
    # ----------------------------------------------------------------------
    @staticmethod
    def list_input_devices() -> List[Tuple[int, str]]:
        """
        返回可用输入设备列表：[(index, "index - name (HostAPI)"), ...]
        策略：优先 Windows WASAPI -> Windows DirectSound -> MME；若失败则兜底。
        """
        def _try_with_hostapi(name: str):
            try:
                has = sd.query_hostapis()
                idx = next((i for i, h in enumerate(has) if h.get("name") == name), None)
                if idx is None:
                    return []
                sd.default.hostapi = idx  # 仅影响本进程
                devs = sd.query_devices()
                out = []
                for i, d in enumerate(devs):
                    if d.get("hostapi") == idx and d.get("max_input_channels", 0) > 0:
                        out.append((i, f"{i} - {d.get('name', 'Unknown')} ({name})"))
                return out
            except Exception:
                return []

        # 分别尝试三种常见 HostAPI
        for api in ("Windows WASAPI", "Windows DirectSound", "MME"):
            out = _try_with_hostapi(api)
            if out:
                return out

        # 兜底：不限定 HostAPI，返回所有可用输入设备
        try:
            devs = sd.query_devices()
            return [
                (i, f"{i} - {d.get('name', 'Unknown')}")
                for i, d in enumerate(devs)
                if d.get("max_input_channels", 0) > 0
            ]
        except Exception as e:
            # 抛给上层，由 UI 负责展示错误信息
            raise e

    def set_device(self, device_index: Optional[int]):
        """设置输入设备索引（None 表示让 PortAudio 选择默认设备）"""
        self.device = device_index

    # ----------------------------------------------------------------------
    # 录音
    # ----------------------------------------------------------------------
    def _callback(self, indata, frames, time_info, status):
        # status 非空表示底层有提醒/溢出等，不在这里阻塞写日志
        if status:
            # 可在 UI 的 logger 里记录 status
            pass
        # RawInputStream + dtype=int16 -> indata 已是 bytes-like；转 bytes 入队
        self.q.put(bytes(indata))

    def start(self, audio_path: str):
        """开始录音（异步写入 WAV）。"""
        self.audio_path = audio_path
        # 准备 WAV 文件
        self.wave_file = wave.open(audio_path, "wb")
        self.wave_file.setnchannels(self.channels)
        self.wave_file.setsampwidth(self.sample_width)
        self.wave_file.setframerate(self.sr)

        # 打开输入流
        self.stream = sd.RawInputStream(
            samplerate=self.sr,
            channels=self.channels,
            dtype="int16",
            callback=self._callback,
            blocksize=0,          # 由后端决定块大小，通常延迟更低
            device=self.device,   # 可为 None 或 具体 index
        )
        self.stream.start()

        self.is_recording = True
        self._start_perf = time.perf_counter()

        # 后台写线程
        self._writer = threading.Thread(target=self._writer_worker, daemon=True)
        self._writer.start()

    def _writer_worker(self):
        """后台线程：把队列里的音频块写入 WAV。"""
        while self.is_recording or not self.q.empty():
            try:
                chunk = self.q.get(timeout=0.2)
                if self.wave_file:
                    self.wave_file.writeframes(chunk)
            except queue.Empty:
                continue

    def elapsed_hms(self) -> str:
        """录音已进行时间（HH:MM:SS）。"""
        if not self._start_perf:
            return "00:00:00"
        sec = max(0.0, time.perf_counter() - self._start_perf)
        h, r = divmod(int(sec), 3600)
        m, s = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def elapsed_seconds(self) -> float:
        """录音已进行的秒数（浮点）。供自动锚点使用。"""
        if not self._start_perf:
            return 0.0
        return max(0.0, time.perf_counter() - self._start_perf)

    def stop(self) -> float:
        """停止录音并关闭资源，返回时长（秒）。"""
        duration = 0.0
        if self._start_perf:
            duration = time.perf_counter() - self._start_perf

        self.is_recording = False

        if self.stream:
            try:
                self.stream.stop()
            finally:
                self.stream.close()
            self.stream = None

        if self._writer and self._writer.is_alive():
            # 等待写线程把剩余数据落盘
            self._writer.join(timeout=2.0)
        self._writer = None

        if self.wave_file:
            self.wave_file.close()
            self.wave_file = None

        self._start_perf = None
        return round(duration, 3)
