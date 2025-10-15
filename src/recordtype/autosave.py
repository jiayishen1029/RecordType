import threading, time

class AutoSaver:
    def __init__(self, get_text_fn, save_fn, interval_sec=30):
        self.get_text = get_text_fn
        self.save = save_fn
        self.interval = interval_sec
        self._stop = threading.Event()
        self._t = None

    def start(self):
        self._stop.clear()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.save(self.get_text())
            except Exception:
                pass
            time.sleep(self.interval)

    def stop(self):
        self._stop.set()
        if self._t and self._t.is_alive():
            self._t.join(timeout=1.0)
