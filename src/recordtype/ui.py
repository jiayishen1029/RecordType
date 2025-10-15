import tkinter as tk
from tkinter import messagebox, filedialog
from tkinter import ttk
import os, logging, traceback, re, json

from .audio import AudioRecorder
from .storage import (
    new_session_dir, save_text, save_json, export_dir,
    load_recent, add_recent, remove_recent, default_sessions_root
)
from .autosave import AutoSaver
from .player import WavPlayer

# ===== 应用信息（已按你的要求设置）=====
APP_NAME = "RecordType"
APP_VERSION = "2.1.0"
APP_AUTHOR = "Jiayi Shen"
APP_ORG = "Chia_i_Shen Studio"
APP_DESC = "语音同步笔记工具：边录音边记笔记，支持回放与时间轴跳转。"
APP_COPYRIGHT = "© 2025 Chia_i_Shen Studio. All rights reserved."
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

TIMESTAMP_RE = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\]")

class MainWindow:
    def __init__(self, root, app_title="RecordType"):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION} — by {APP_AUTHOR}")
        self.root.geometry("1000x680")

        # 日志
        self.logger = logging.getLogger("recordtype")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            ch = logging.StreamHandler(); ch.setLevel(logging.INFO)
            self.logger.addHandler(ch)
        self.file_handler = None

        # 状态
        self.rec = AudioRecorder()
        self.session_dir = None
        self.meta = {}
        self.player: WavPlayer | None = None

        # 自动锚点
        self.anchors = []
        self._anchor_timer = None

        # 回放数据
        self.review_markers = []
        self.review_clean_text = ""
        self.review_total = 0.0
        self._progress_updater = None

        # ===== 菜单栏（帮助->关于）=====
        menubar = tk.Menu(self.root)
        menu_help = tk.Menu(menubar, tearoff=0)
        menu_help.add_command(label="关于", command=self.show_about, accelerator="F1")
        menubar.add_cascade(label="帮助", menu=menu_help)
        self.root.config(menu=menubar)
        self.root.bind("<F1>", lambda e: self.show_about())

        # Notebook
        self.nb = ttk.Notebook(root); self.nb.pack(expand=True, fill=tk.BOTH)
        self.lib_frame = tk.Frame(self.nb); self.nb.add(self.lib_frame, text="会话库")
        self.rec_frame = tk.Frame(self.nb); self.nb.add(self.rec_frame, text="录音")
        self.rev_frame = tk.Frame(self.nb); self.nb.add(self.rev_frame, text="回放查看")

        self._build_library_tab(self.lib_frame)
        self._build_record_tab(self.rec_frame)
        self._build_review_tab(self.rev_frame)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_library()

    # ================= 会话库 =================
    def _build_library_tab(self, parent):
        top = tk.Frame(parent); top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        tk.Label(top, text=f"默认保存位置：{default_sessions_root()}").pack(side=tk.LEFT)

        btns = tk.Frame(parent); btns.pack(side=tk.TOP, fill=tk.X, padx=10)
        tk.Button(btns, text="刷新", width=10, command=self.refresh_library).pack(side=tk.LEFT, padx=4)
        tk.Button(btns, text="浏览添加…", width=12, command=self.browse_add_session).pack(side=tk.LEFT, padx=4)
        self.btn_open_from_lib = tk.Button(btns, text="打开所选", width=12, command=self.open_selected_from_library, state=tk.DISABLED)
        self.btn_open_from_lib.pack(side=tk.LEFT, padx=4)
        self.btn_remove_from_lib = tk.Button(btns, text="从列表删除", width=12, command=self.remove_selected_from_library, state=tk.DISABLED)
        self.btn_remove_from_lib.pack(side=tk.LEFT, padx=4)
        tk.Button(btns, text="关于", width=10, command=self.show_about).pack(side=tk.RIGHT, padx=4)

        self.listbox = tk.Listbox(parent, height=18)
        self.listbox.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        self.listbox.bind("<<ListboxSelect>>", self._on_lib_select)
        self.listbox.bind("<Double-Button-1>", lambda e: self.open_selected_from_library())

    def refresh_library(self):
        self.listbox.delete(0, tk.END)
        self._lib_items = load_recent()
        for p in self._lib_items:
            name = os.path.basename(os.path.normpath(p))
            mtime = ""
            try:
                ts = os.path.getmtime(p)
                import datetime as dt
                mtime = dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
            self.listbox.insert(tk.END, f"{name}    ({mtime})\n{p}")
        self._update_lib_buttons()

    def _on_lib_select(self, *_): self._update_lib_buttons()
    def _update_lib_buttons(self):
        sel = self.listbox.curselection()
        enabled = tk.NORMAL if sel else tk.DISABLED
        self.btn_open_from_lib.config(state=enabled)
        self.btn_remove_from_lib.config(state=enabled)

    def _get_selected_path(self):
        sel = self.listbox.curselection()
        if not sel: return None
        idx = sel[0]
        try: return self._lib_items[idx]
        except Exception: return None

    def open_selected_from_library(self):
        p = self._get_selected_path()
        if not p: return
        if not os.path.isdir(p):
            messagebox.showwarning("无效条目", "该路径不存在，已从列表移除。")
            remove_recent(p); self.refresh_library(); return
        self._open_session_path(p); self.nb.select(self.rev_frame)

    def remove_selected_from_library(self):
        p = self._get_selected_path()
        if not p: return
        remove_recent(p); self.refresh_library()

    def browse_add_session(self):
        d = filedialog.askdirectory(title="选择 session_XXXX 目录")
        if not d: return
        audio_ok = os.path.exists(os.path.join(d, "audio.wav")) or os.path.exists(os.path.join(d, "audio"))
        if not audio_ok:
            messagebox.showwarning("不是会话目录", "未找到 audio.wav"); return
        add_recent(d); self.refresh_library()

    # ================= 录音 =================
    def _build_record_tab(self, parent):
        top = tk.Frame(parent); top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        tk.Label(top, text="输入设备：").pack(side=tk.LEFT, padx=(0,4))
        self.device_var = tk.StringVar()
        self.device_box = ttk.Combobox(top, textvariable=self.device_var, state="readonly", width=46)
        self.device_box.pack(side=tk.LEFT, padx=(0,6))
        tk.Button(top, text="刷新设备", command=self.refresh_devices).pack(side=tk.LEFT, padx=4)

        self.btn_start = tk.Button(top, text="▶ 开始录音", width=12, command=self.start); self.btn_start.pack(side=tk.LEFT, padx=6)
        self.btn_mark  = tk.Button(top, text="⏱ 插入时间戳(Ctrl+M)", width=20, command=self.mark, state=tk.DISABLED); self.btn_mark.pack(side=tk.LEFT, padx=6)
        self.btn_stop  = tk.Button(top, text="⏹ 停止并保存(Ctrl+S)", width=20, command=self.stop, state=tk.DISABLED); self.btn_stop.pack(side=tk.LEFT, padx=6)
        self.btn_export= tk.Button(top, text="🗂 另存会话", width=12, command=self.export, state=tk.DISABLED); self.btn_export.pack(side=tk.LEFT, padx=6)

        self.text = tk.Text(parent, wrap="word", font=("Segoe UI", 12))
        self.text.pack(expand=True, fill=tk.BOTH, padx=10, pady=(0,10))
        self.text.insert("1.0", "开始录音后在此输入笔记；可以不打时间戳，系统会自动生成“隐形锚点”。\n")

        self.status = tk.StringVar(value="准备就绪。")
        tk.Label(parent, textvariable=self.status, anchor="w").pack(side=tk.BOTTOM, fill=tk.X)

        self.autosaver = AutoSaver(
            get_text_fn=lambda: self.text.get("1.0", tk.END),
            save_fn=lambda t: save_text(os.path.join(self.session_dir, "_autosave.md"), t) if self.session_dir else None,
            interval_sec=20
        )

        parent.bind("<Control-s>", lambda e: self.stop())
        parent.bind("<Control-S>", lambda e: self.stop())
        parent.bind("<Control-m>", lambda e: self.mark())
        parent.bind("<Control-M>", lambda e: self.mark())

        self.refresh_devices()

    def refresh_devices(self):
        try:
            items = AudioRecorder.list_input_devices()
            labels = [label for _, label in items]
            self.device_box["values"] = labels
            if labels:
                self.device_box.current(0); self.device_var.set(labels[0])
                self.status.set(f"已加载 {len(labels)} 个输入设备。")
            else:
                self.status.set("未发现可用输入设备。请检查系统声音设置。")
        except Exception as e:
            self.status.set(f"加载设备失败：{e}")
            messagebox.showerror("加载设备失败",
                f"无法获取输入设备列表：\n{e}\n\n请检查：设置→隐私与安全性→麦克风、声音设置、是否有其他程序独占设备。")

    def _selected_device_index(self):
        txt = self.device_var.get().strip()
        if not txt or " - " not in txt: return None
        try: return int(txt.split(" - ", 1)[0])
        except: return None

    def set_state(self, recording: bool):
        if recording:
            self.btn_start.config(state=tk.DISABLED)
            self.btn_mark.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.NORMAL)
            self.btn_export.config(state=tk.DISABLED)
            self.device_box.config(state="disabled")
        else:
            self.btn_start.config(state=tk.NORMAL)
            self.btn_mark.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.DISABLED)
            self.btn_export.config(state=tk.NORMAL)
            self.device_box.config(state="readonly")

    def start(self):
        # 1) 创建会话目录
        self.session_dir = new_session_dir()
        audio_path = os.path.join(self.session_dir, "audio.wav")

        # 2) 开会话日志（可选）
        try:
            if self.file_handler:
                self.logger.removeHandler(self.file_handler); self.file_handler.close()
            fh = logging.FileHandler(os.path.join(self.session_dir, "app.log"), encoding="utf-8")
            fh.setLevel(logging.INFO); fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            self.logger.addHandler(fh); self.file_handler = fh
            self.logger.info("===== New session started =====")
        except Exception:
            pass

        # 3) 打开录音设备并开始
        try:
            self.rec.set_device(self._selected_device_index())
            self.rec.start(audio_path)
        except Exception as e:
            messagebox.showerror("设备错误", f"无法打开录音设备：\n{e}")
            return

        # 4) 元信息 + UI 状态
        self.meta = {
            "sample_rate": self.rec.sr, "channels": self.rec.channels, "sample_width": self.rec.sample_width,
            "device_index": self._selected_device_index(), "audio_path": audio_path, "duration_seconds": None,
        }
        self.autosaver.start()
        self.set_state(True); self.status.set("录音中… 你可以开始输入笔记。")

        # 5) 启动“隐形锚点”采集
        self.anchors = []
        self._start_anchor_timer()

    def _start_anchor_timer(self, interval_ms: int = 2000):
        try:
            t = float(self.rec.elapsed_seconds())
            text_len = len(self.text.get("1.0", "end-1c"))
            if not self.anchors or (t - self.anchors[-1][0] >= 1.0 or text_len != self.anchors[-1][1]):
                self.anchors.append((t, text_len))
        except Exception:
            pass
        finally:
            self._anchor_timer = self.root.after(interval_ms, self._start_anchor_timer, interval_ms)

    def _stop_anchor_timer(self):
        if self._anchor_timer:
            try: self.root.after_cancel(self._anchor_timer)
            except Exception: pass
            self._anchor_timer = None

    def mark(self):
        tag = f"[{self.rec.elapsed_hms()}]"
        idx = self.text.index(tk.INSERT)
        self.text.insert(idx, tag + " ")

    def stop(self):
        if not self.session_dir: return
        try:
            # 1) 停止录音
            duration = self.rec.stop()
            self.meta["duration_seconds"] = duration

            # 2) 保存 anchors / notes / meta
            self._stop_anchor_timer()
            save_json(os.path.join(self.session_dir, "anchors.json"),
                      [{"t": round(t,3), "len": ln} for (t, ln) in self.anchors])

            save_text(os.path.join(self.session_dir, "notes.md"),
                      "# 笔记\n\n" + self.text.get("1.0", tk.END))
            save_json(os.path.join(self.session_dir, "meta.json"), self.meta)

            # 3) 自动加入“会话库”
            add_recent(self.session_dir)

            self.autosaver.stop()
            self.set_state(False)
            self.status.set(f"已保存：{self.session_dir}")
            messagebox.showinfo("完成", f"音频与笔记已保存：\n{self.session_dir}\n可在“会话库”一键打开。")
            self.refresh_library()
        except Exception:
            messagebox.showerror("保存失败", traceback.format_exc())

    def export(self):
        if not self.session_dir: return
        dst = filedialog.askdirectory(title="选择导出位置")
        if not dst: return
        try:
            target = export_dir(self.session_dir, dst)
            messagebox.showinfo("导出成功", f"已导出到：\n{target}")
        except FileExistsError as e:
            messagebox.showwarning("已存在", str(e))
        except Exception:
            messagebox.showerror("导出失败", traceback.format_exc())

    # ================= 回放 =================
    def _build_review_tab(self, parent):
        top = tk.Frame(parent); top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        tk.Button(top, text="打开会话…", command=self.open_session_dialog).pack(side=tk.LEFT, padx=4)
        self.btn_play = tk.Button(top, text="▶ 播放", state=tk.DISABLED, command=self.toggle_play); self.btn_play.pack(side=tk.LEFT, padx=6)
        self.btn_stop2 = tk.Button(top, text="⏹ 停止", state=tk.DISABLED, command=self.stop_playback); self.btn_stop2.pack(side=tk.LEFT, padx=6)
        self.time_var = tk.StringVar(value="00:00 / 00:00")
        tk.Label(top, textvariable=self.time_var).pack(side=tk.LEFT, padx=10)

        self.progress = tk.Canvas(parent, height=26, bg="#F2F3F5", highlightthickness=0)
        self.progress.pack(fill=tk.X, padx=10, pady=4)
        self.progress.bind("<Button-1>", self.on_progress_click)

        self.review_text = tk.Text(parent, wrap="word", font=("Segoe UI", 12))
        self.review_text.pack(expand=True, fill=tk.BOTH, padx=10, pady=(0,10))
        self.review_text.tag_configure("hilite", background="#FFF3B0")
        self.review_text.bind("<Button-1>", self.on_text_click)

    def open_session_dialog(self):
        d = filedialog.askdirectory(title="选择 session_XXXX 目录")
        if not d: return
        self._open_session_path(d)

    def _open_session_path(self, d):
        audio = os.path.join(d, "audio.wav")
        if not os.path.exists(audio):  # 兼容扩展名被隐藏
            audio = os.path.join(d, "audio")
        notes = os.path.join(d, "notes.md")
        if not (os.path.exists(audio) and os.path.exists(notes)):
            messagebox.showwarning("缺少文件", "未找到 audio.wav 或 notes.md"); return

        if self.player: self.player.close()
        self.player = WavPlayer(audio)
        self.review_total = self.player.duration()

        raw = open(notes, "r", encoding="utf-8").read()
        times = []
        out_chars = []; i = 0
        for m in TIMESTAMP_RE.finditer(raw):
            h, m2, s = map(int, m.groups())
            sec = h*3600 + m2*60 + s
            out_chars.append(raw[i:m.start()])
            i = m.end()
            current_clean_len = len("".join(out_chars))
            times.append((sec, current_clean_len))
        out_chars.append(raw[i:])
        clean = "".join(out_chars)
        self.review_clean_text = clean
        self.review_markers = sorted(times, key=lambda x: x[0])

        if not self.review_markers:
            anchors_path = os.path.join(d, "anchors.json")
            if os.path.exists(anchors_path):
                anchors = json.load(open(anchors_path, "r", encoding="utf-8"))
                self.review_markers = [(float(a["t"]), int(a["len"])) for a in anchors]
                self.review_markers.sort(key=lambda x: x[0])
                dedup, last_off = [], -1
                for sec, off in self.review_markers:
                    if off != last_off:
                        dedup.append((sec, off)); last_off = off
                self.review_markers = dedup
            else:
                self.review_markers = [(0.0, 0)]

        self.review_text.delete("1.0", tk.END)
        self.review_text.insert("1.0", clean)
        self.btn_play.config(state=tk.NORMAL, text="▶ 播放")
        self.btn_stop2.config(state=tk.NORMAL)
        self.update_progress_bar(0.0)
        self.time_var.set(f"{self._fmt(0)} / {self._fmt(self.review_total)}")
        self._schedule_progress_updater(True)

    # —— 播放联动 —— #
    def _fmt(self, t):
        t = int(max(0, t)); h, r = divmod(t, 3600); m, s = divmod(r, 60); return f"{h:02d}:{m:02d}:{s:02d}"

    def toggle_play(self):
        if not self.player: return
        if self.btn_play["text"].startswith("▶"):
            self.player.play(); self.btn_play.config(text="⏸ 暂停")
        else:
            self.player.pause(); self.btn_play.config(text="▶ 播放")

    def stop_playback(self):
        if not self.player: return
        self.player.stop(); self.btn_play.config(text="▶ 播放")
        self.update_progress_bar(0.0); self._highlight_at_time(0.0)
        self.time_var.set(f"{self._fmt(0)} / {self._fmt(self.review_total)}")

    def on_progress_click(self, event):
        if not self.player: return
        width = self.progress.winfo_width()
        ratio = max(0.0, min(1.0, event.x / max(1, width)))
        t = ratio * self.review_total
        self.player.seek(t); self._highlight_at_time(t); self.update_progress_bar(t)

    def on_text_click(self, event):
        if not self.player: return
        index = self.review_text.index(f"@{event.x},{event.y}")
        line, col = map(int, index.split("."))
        char_offset = self._index_to_offset(line, col)
        sec = 0.0
        for i in range(len(self.review_markers)-1, -1, -1):
            ts, off = self.review_markers[i]
            if char_offset >= off: sec = float(ts); break
        self.player.seek(sec); self._highlight_at_time(sec); self.update_progress_bar(sec)
        self.btn_play.config(text="⏸ 暂停"); self.player.play()

    def _index_to_offset(self, line, col):
        total = 0
        for ln in range(1, line):
            total += len(self.review_text.get(f"{ln}.0", f"{ln}.end")) + 1
        total += col; return total

    def _offset_to_index(self, off):
        text = self.review_text.get("1.0", tk.END)
        off = max(0, min(off, len(text)))
        run = 0; line = 1
        for ch in text.splitlines(True):
            ln = len(ch)
            if run + ln > off:
                col = off - run; return f"{line}.{col}"
            run += ln; line += 1
        return f"{line}.0"

    def _highlight_at_time(self, t):
        self.review_text.tag_remove("hilite", "1.0", tk.END)
        if not self.review_markers: return
        current_idx = 0
        for i, (sec, _off) in enumerate(self.review_markers):
            if t >= sec: current_idx = i
            else: break
        start_off = self.review_markers[current_idx][1]
        end_off = len(self.review_clean_text)
        if current_idx + 1 < len(self.review_markers):
            end_off = self.review_markers[current_idx+1][1]
        start = self._offset_to_index(start_off)
        end = self._offset_to_index(end_off)
        self.review_text.tag_add("hilite", start, end)
        self.review_text.see(start)

    def update_progress_bar(self, t=None):
        if not self.player:
            self.progress.delete("all"); return
        if t is None: t = self.player.current_time()
        w = self.progress.winfo_width(); h = self.progress.winfo_height()
        self.progress.delete("all")
        self.progress.create_rectangle(2, h//3, w-2, h//3*2, fill="#E5E7EB", width=0)
        ratio = 0 if self.review_total <= 0 else t / self.review_total
        self.progress.create_rectangle(2, h//3, 2 + int((w-4)*ratio), h//3*2, fill="#3B82F6", width=0)
        for sec, _off in self.review_markers:
            x = 2 + int((w-4) * (sec / max(1e-6, self.review_total)))
            self.progress.create_line(x, 4, x, h-4, fill="#9CA3AF")

    def _schedule_progress_updater(self, enable):
        if enable:
            def _tick():
                if self.player:
                    t = self.player.current_time()
                    self.update_progress_bar(t)
                    self.time_var.set(f"{self._fmt(t)} / {self._fmt(self.review_total)}")
                    self._highlight_at_time(t)
                self._progress_updater = self.root.after(80, _tick)
            if self._progress_updater is None: _tick()
        else:
            if self._progress_updater:
                self.root.after_cancel(self._progress_updater); self._progress_updater = None

    # ================= 关于 =================
    def show_about(self):
        top = tk.Toplevel(self.root)
        top.title(f"关于 {APP_NAME}")
        top.resizable(False, False)
        top.transient(self.root)
        top.grab_set()
        padx, pady = 16, 14

        frm = tk.Frame(top); frm.pack(padx=padx, pady=pady)

        self._about_img = None
        for p in (os.path.join(ASSETS_DIR, "about.png"),
                  os.path.join(ASSETS_DIR, "icon.png"),
                  os.path.join(ASSETS_DIR, "icon.ico")):
            if os.path.exists(p):
                try:
                    self._about_img = tk.PhotoImage(file=p)
                    break
                except Exception:
                    self._about_img = None

        if self._about_img:
            tk.Label(frm, image=self._about_img).grid(row=0, column=0, rowspan=5, sticky="nw", padx=(0, 12))

        row = 0
        tk.Label(frm, text=f"{APP_NAME}  v{APP_VERSION}", font=("Segoe UI", 12, "bold")).grid(row=row, column=1, sticky="w"); row += 1
        tk.Label(frm, text=f"{APP_DESC}", font=("Segoe UI", 10)).grid(row=row, column=1, sticky="w"); row += 1
        tk.Label(frm, text=f"作者：{APP_AUTHOR}  |  组织：{APP_ORG}", font=("Segoe UI", 10)).grid(row=row, column=1, sticky="w"); row += 1
        tk.Label(frm, text=APP_COPYRIGHT, font=("Segoe UI", 9)).grid(row=row, column=1, sticky="w"); row += 1

        tk.Button(frm, text="确定", width=10, command=top.destroy)\
            .grid(row=row, column=1, sticky="e", pady=(8, 0))

        top.update_idletasks()
        w, h = top.winfo_width(), top.winfo_height()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        top.geometry(f"{w}x{h}+((sw-w)//2)+((sh-h)//2)")

    # ================= 退出 =================
    def on_close(self):
        try:
            if self.rec.is_recording:
                if messagebox.askyesno("退出确认", "正在录音，是否停止并保存后退出？"):
                    self.stop()
                else:
                    return
        finally:
            if self.player: self.player.close()
            try:
                if self.file_handler:
                    self.logger.removeHandler(self.file_handler); self.file_handler.close()
            except Exception:
                pass
            self.root.destroy()
