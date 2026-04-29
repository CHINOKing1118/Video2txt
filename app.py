import os
import re
import json
import time
import atexit
import threading
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from ui_helpers import detect_font, t, bind_hover, _rb_kw, _bind_toggle
import tkinter as tk
from tkinter import scrolledtext, messagebox

try:
    import windnd
    HAS_WINDND = True
except ImportError:
    HAS_WINDND = False

from config import (
    load_config, save_config, ensure_cookie_file,
    OUTPUT_DIR, COOKIE_FILE,
)
from utils import (
    extract_url, extract_all_urls, sanitize_filename,
    format_duration, get_user_friendly_error,
    is_douyin_url, clean_title_for_folder,
    find_matching_folders, check_folder_status,
    retry_operation, write_text_file, write_json_file,
)
from history import load_history, save_history_entry, write_log, flush_log
from themes import THEMES
from ui_helpers import detect_font, t, bind_hover, _rb_kw
from components import StepProgress, SplashScreen
from download import download_video, get_video_title_quick
from transcribe import video_to_mp3, transcribe
from export import format_subtitle, save_output
from ai_polish import polish, generate_short_title, rename_folder_safe
from dialogs import SettingsDialog, HistoryDialog


# ============================================================
# 一键修复命令表
# ============================================================

FIX_COMMANDS = {
    "install_ffmpeg": (
        "winget install --id Gyan.FFmpeg -e --accept-package-agreements",
        "请访问 https://ffmpeg.org/download.html 手动下载并添加到 PATH"
    ),
    "install_whisper": ("pip install openai-whisper", None),
    "install_f2": ("pip install f2", None),
    "install_fpdf": ("pip install fpdf2", None),
    "install_docx": ("pip install python-docx", None),
    "install_opencc": ("pip install opencc-python-reimplemented", None),
}

FIX_LABELS = {
    "install_ffmpeg": "🔧 一键安装 FFmpeg",
    "install_whisper": "🔧 一键安装 Whisper 语音模型",
    "install_f2": "🔧 一键安装 f2 下载工具",
    "install_fpdf": "🔧 一键安装 fpdf2 (PDF)",
    "install_docx": "🔧 一键安装 python-docx (Word)",
    "install_opencc": "🔧 一键安装 opencc (繁简转换)",
}


# ============================================================
# 主应用
# ============================================================

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()

        self.config = load_config()
        self.font_family = detect_font(self.root)
        self.current_theme = self.config.get("theme", "dark")
        self.colors = THEMES[self.current_theme]
        self.is_running = False
        self.step_states = ["reset"] * 4

        self.batch_urls = []
        self.batch_current = 0
        self.batch_total = 0

        self.failed_step = -1
        self.current_folder_path = None
        self.current_video_path = None
        self.current_mp3_path = None
        self.current_title = None

        self._process_start = 0
        self._step_start = 0
        self._step_times = []
        self._timer_id = None

        # 批量并发
        self._success_count = 0
        self._fail_count = 0
        self._last_error = None
        self._completed_count = 0
        self._batch_lock = threading.Lock()

        # 暂停 / 取消
        self._paused = threading.Event()
        self._paused.set()
        self._cancel_flag = False

        # 失败重试
        self._failed_urls = []

        # 文稿字体大小
        self._result_font_size = 11

        self.root.title("Video2Txt v2.2  ·  抖音视频转文稿")
        self.root.geometry("1200x1200")
        self.root.minsize(1100, 1100)
        self.root.configure(bg=self.colors["bg"])

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        atexit.register(flush_log)

        ensure_cookie_file(self.config.get("cookies", ""))
        write_log("程序启动")
        self._show_splash()

    def _on_close(self):
        self._cancel_flag = True
        self._paused.set()
        flush_log()
        self.root.destroy()

    # ─────────── 启动闪屏 ───────────

    def _show_splash(self):
        self.splash = SplashScreen(self.root, self.font_family, self.colors)
        self.root.update()

        def load():
            try:
                from transcribe import get_whisper_model
                result = get_whisper_model()
                if result is not None:
                    write_log("[启动] Whisper 模型预加载完成")
                else:
                    write_log("[启动] Whisper 模型预加载失败，将在首次使用时重试")
            except Exception as e:
                write_log(f"[启动] 模型预加载异常: {e}")
            self.root.after(0, self._on_splash_done)

        threading.Thread(target=load, daemon=True).start()

    def _on_splash_done(self):
        self.splash.destroy()
        self.root.update_idletasks()
        self._build_ui()
        self.root.deiconify()

    # ─────────── 构建 UI ───────────

    def _build_ui(self):
        self._build_header()
        self._build_input()
        self._build_progress()
        self._build_log()
        self._build_result()

    def _build_header(self):
        c, f = self.colors, self.font_family
        self.header = t(tk.Frame(self.root, bg=c["bg"]), bg="bg")
        self.header.pack(fill="x", padx=32, pady=(24, 0))

        left = t(tk.Frame(self.header, bg=c["bg"]), bg="bg")
        left.pack(side="left")
        self.title_lbl = t(tk.Label(left, text="Video2Txt v2.2", font=(f, 22, "bold"),
                                     fg=c["accent"], bg=c["bg"]), bg="bg", fg="accent")
        self.title_lbl.pack(side="left")
        self.sub_lbl = t(tk.Label(left, text="抖音视频 → 文字文稿", font=(f, 13),
                                   fg=c["text_dim"], bg=c["bg"]), bg="bg", fg="text_dim")
        self.sub_lbl.pack(side="left", padx=(12, 0), pady=(6, 0))
        self.author_lbl = t(tk.Label(left, text="by CHINOKing", font=(f, 10),
                                      fg=c["text_muted"], bg=c["bg"]), bg="bg", fg="text_muted")
        self.author_lbl.pack(side="left", padx=(12, 0), pady=(8, 0))

        right = t(tk.Frame(self.header, bg=c["bg"]), bg="bg")
        right.pack(side="right")

        theme_sym = "☀" if self.current_theme == "dark" else "☾"
        self.theme_btn = t(tk.Button(right, text=theme_sym, font=(f, 18), bg=c["bg"],
                                      fg=c["text_dim"], relief="flat", bd=0,
                                      activebackground=c["surface"], cursor="hand2",
                                      command=self._toggle_theme), bg="bg", fg="text_dim")
        self.theme_btn.pack(side="right", padx=(10, 0))
        bind_hover(self.theme_btn, "surface", "bg", "text", "text_dim", colors=c)

        self.settings_btn = t(tk.Button(right, text="⚙", font=(f, 18), bg=c["bg"],
                                         fg=c["text_dim"], relief="flat", bd=0,
                                         activebackground=c["surface"], cursor="hand2",
                                         command=self._open_settings), bg="bg", fg="text_dim")
        self.settings_btn.pack(side="right")
        bind_hover(self.settings_btn, "surface", "bg", "text", "text_dim", colors=c)

        self.history_btn = t(tk.Button(right, text="📋", font=(f, 18), bg=c["bg"],
                                        fg=c["text_dim"], relief="flat", bd=0,
                                        activebackground=c["surface"], cursor="hand2",
                                        command=self._open_history), bg="bg", fg="text_dim")
        self.history_btn.pack(side="right")
        bind_hover(self.history_btn, "surface", "bg", "text", "text_dim", colors=c)

    def _build_input(self):
        c, f = self.colors, self.font_family
        self.input_outer = t(tk.Frame(self.root, bg=c["surface"],
                                       highlightbackground=c["border"],
                                       highlightthickness=1), bg="surface", border="border")
        self.input_outer.pack(fill="x", padx=32, pady=(20, 0))

        inner = t(tk.Frame(self.input_outer, bg=c["surface"]), bg="surface")
        inner.pack(fill="x", padx=16, pady=12)

        t(tk.Label(inner, text="粘贴抖音分享内容（支持多个链接，每行一个）", font=(f, 11),
                   fg=c["text_dim"], bg=c["surface"]), bg="surface", fg="text_dim").pack(anchor="w")

        self.input_text = scrolledtext.ScrolledText(
            inner, font=("Consolas", 11), height=3,
            bg=c["entry_bg"], fg=c["entry_fg"],
            insertbackground=c["text"], relief="flat", bd=0, wrap="word")
        t(self.input_text, bg="entry_bg", fg="entry_fg").pack(fill="x", pady=(8, 0), ipady=4, ipadx=4)

        # 拖拽支持
        if HAS_WINDND:
            try:
                windnd.hook_dropfiles(self.input_text, func=self._on_drop)
                t(tk.Label(inner, text="💡 支持拖拽 TXT / 文件夹到此处", font=(f, 9),
                           fg=c["text_muted"], bg=c["surface"]),
                  bg="surface", fg="text_muted").pack(anchor="w", pady=(2, 0))
            except Exception:
                pass

        # 模板选择
        tpl_frame = t(tk.Frame(inner, bg=c["surface"]), bg="surface")
        tpl_frame.pack(fill="x", pady=(10, 0))
        t(tk.Label(tpl_frame, text="文稿模板：", font=(f, 10),
                   fg=c["text_dim"], bg=c["surface"]), bg="surface", fg="text_dim").pack(side="left")
        self.template_var = tk.StringVar(value=self.config.get("template", "notes"))
        for txt, val in [("简洁版", "concise"), ("笔记版", "notes"), ("字幕版", "subtitle")]:
            rb = tk.Radiobutton(tpl_frame, text=txt, variable=self.template_var, value=val,
                                **_rb_kw(f, c, parent_bg_key="surface"))
            _bind_toggle(rb, self.template_var, val, c, "surface")   # ← 新增
            t(rb, bg="surface", fg="text").pack(side="left", padx=(0, 16))

        # 批量控制栏
        batch_ctrl = t(tk.Frame(inner, bg=c["surface"]), bg="surface")
        batch_ctrl.pack(fill="x", pady=(8, 0))

        self.select_all_btn = tk.Button(batch_ctrl, text="☑ 全选", font=(f, 9),
                                         bg=c["surface2"], fg=c["text_dim"], relief="flat", bd=0,
                                         activebackground=c["surface3"], cursor="hand2",
                                         command=self._select_all_urls)
        t(self.select_all_btn, bg="surface2", fg="text_dim").pack(side="left", padx=(0, 4), ipady=3)
        bind_hover(self.select_all_btn, "surface3", "surface2", colors=c)

        self.pause_btn = tk.Button(batch_ctrl, text="⏸ 暂停全部", font=(f, 9),
                                    bg=c["surface2"], fg=c["text_dim"], relief="flat", bd=0,
                                    activebackground=c["surface3"], cursor="hand2",
                                    command=self._toggle_pause)
        t(self.pause_btn, bg="surface2", fg="text_dim").pack(side="left", padx=(0, 4), ipady=3)
        bind_hover(self.pause_btn, "surface3", "surface2", colors=c)

        self.clear_finished_btn = tk.Button(batch_ctrl, text="🗑 清空结果", font=(f, 9),
                                             bg=c["surface2"], fg=c["text_dim"], relief="flat", bd=0,
                                             activebackground=c["surface3"], cursor="hand2",
                                             command=self._clear_finished)
        t(self.clear_finished_btn, bg="surface2", fg="text_dim").pack(side="left", padx=(0, 4), ipady=3)
        bind_hover(self.clear_finished_btn, "surface3", "surface2", colors=c)

        # 操作按钮行
        btn_row = t(tk.Frame(inner, bg=c["surface"]), bg="surface")
        btn_row.pack(fill="x", pady=(10, 0))

        self.start_btn = tk.Button(btn_row, text="  开始处理  ", font=(f, 11, "bold"),
                                    bg=c["accent"], fg="white", relief="flat", bd=0,
                                    activebackground=c["accent_dim"], cursor="hand2",
                                    command=self._on_start)
        t(self.start_btn, bg="accent").pack(side="right", ipady=4)
        bind_hover(self.start_btn, "accent_dim", "accent", colors=c)

        self.paste_btn = tk.Button(btn_row, text="📋 粘贴", font=(f, 10),
                                    bg=c["surface2"], fg=c["text_dim"], relief="flat", bd=0,
                                    activebackground=c["surface3"], cursor="hand2",
                                    command=self._on_paste)
        t(self.paste_btn, bg="surface2", fg="text_dim").pack(side="right", padx=(4, 4), ipady=5)
        bind_hover(self.paste_btn, "surface3", "surface2", colors=c)

        self.batch_label = t(tk.Label(inner, text="", font=(f, 10),
                                       fg=c["accent"], bg=c["surface"]), bg="surface", fg="accent")
        self.batch_label.pack(anchor="w", pady=(8, 0))

    def _build_progress(self):
        c, f = self.colors, self.font_family
        self.steps_container = t(tk.Frame(self.root, bg=c["bg"]), bg="bg")
        self.steps_container.pack(fill="x", padx=32, pady=(16, 0))

        self.steps_frame = t(tk.Frame(self.steps_container, bg=c["bg"]), bg="bg")
        self.steps_frame.pack(fill="x")

        self.step_widgets = []
        for name in ["下载视频", "转换 MP3", "语音识别", "AI 整理"]:
            sp = StepProgress(self.steps_frame, name, f, c)
            sp.pack(fill="x", pady=3)
            self.step_widgets.append(sp)

        bottom_row = t(tk.Frame(self.steps_container, bg=c["bg"]), bg="bg")
        bottom_row.pack(fill="x", pady=(8, 0))

        self.timer_label = t(tk.Label(bottom_row, text="", font=("Consolas", 10),
                                       fg=c["text_muted"], bg=c["bg"]), bg="bg", fg="text_muted")
        self.timer_label.pack(side="left")

        # 重试失败按钮（默认隐藏）
        self.retry_failed_btn = tk.Button(bottom_row, text="🔄 重试全部失败", font=(f, 10, "bold"),
                                           bg=c["red"], fg="white", relief="flat", bd=0,
                                           activebackground="#d44", cursor="hand2",
                                           command=self._retry_all_failed)
        t(self.retry_failed_btn, bg="red")
        bind_hover(self.retry_failed_btn, "#d44", "red", colors=c)

        # 继续处理按钮（默认隐藏）
        self.continue_btn = tk.Button(bottom_row, text="▶ 继续处理", font=(f, 10, "bold"),
                                       bg=c["yellow"], fg="#1a1a1a", relief="flat", bd=0,
                                       activebackground="#d4a80e", cursor="hand2",
                                       command=self._on_continue)
        t(self.continue_btn, bg="yellow")
        bind_hover(self.continue_btn, "#d4a80e", "yellow", colors=c)

    def _build_log(self):
        c, f = self.colors, self.font_family
        t(tk.Label(self.root, text="运行日志", font=(f, 10),
                   fg=c["text_muted"], bg=c["bg"]), bg="bg", fg="text_muted").pack(
            anchor="w", padx=32, pady=(12, 4))
        self.log_text = t(scrolledtext.ScrolledText(
            self.root, font=("Consolas", 9), bg=c["surface"], fg=c["text_dim"],
            insertbackground=c["text"], relief="flat", bd=0, height=7, wrap="word",
            state="disabled"), bg="surface", fg="text_dim")
        self.log_text.pack(fill="x", padx=32, pady=(0, 8))

    def _build_result(self):
        c, f = self.colors, self.font_family
        self.result_outer = t(tk.Frame(self.root, bg=c["surface"],
                                        highlightbackground=c["border"],
                                        highlightthickness=1), bg="surface", border="border")
        self.result_outer.pack(fill="both", expand=True, padx=32, pady=(0, 24))

        rh = t(tk.Frame(self.result_outer, bg=c["surface"]), bg="surface")
        rh.pack(fill="x", padx=16, pady=(10, 0))
        t(tk.Label(rh, text="整理后的文稿", font=(f, 11, "bold"),
                   fg=c["text"], bg=c["surface"]), bg="surface", fg="text").pack(side="left")

        # 复制按钮
        self.copy_btn = tk.Button(rh, text="复制", font=(f, 9), bg=c["surface2"], fg=c["text_dim"],
                                   relief="flat", bd=0, activebackground=c["border"],
                                   cursor="hand2", command=self._copy_result)
        t(self.copy_btn, bg="surface2", fg="text_dim").pack(side="right")
        bind_hover(self.copy_btn, "border", "surface2", colors=c)

        # 缩放按钮
        self.zoom_in_btn = tk.Button(rh, text="A+", font=(f, 9, "bold"), bg=c["surface2"],
                                      fg=c["text_dim"], relief="flat", bd=0,
                                      activebackground=c["border"], cursor="hand2",
                                      command=self._zoom_in)
        t(self.zoom_in_btn, bg="surface2", fg="text_dim").pack(side="right", padx=(4, 0))
        bind_hover(self.zoom_in_btn, "border", "surface2", colors=c)

        self.zoom_out_btn = tk.Button(rh, text="A−", font=(f, 9, "bold"), bg=c["surface2"],
                                       fg=c["text_dim"], relief="flat", bd=0,
                                       activebackground=c["border"], cursor="hand2",
                                       command=self._zoom_out)
        t(self.zoom_out_btn, bg="surface2", fg="text_dim").pack(side="right", padx=(4, 0))
        bind_hover(self.zoom_out_btn, "border", "surface2", colors=c)

        # 文稿区（可编辑）
        self.result_text = t(scrolledtext.ScrolledText(
            self.result_outer, font=(self.font_family, self._result_font_size),
            bg=c["surface"], fg=c["text"],
            insertbackground=c["text"], relief="flat", bd=0, wrap="word"),
            bg="surface", fg="text")
        self.result_text.pack(fill="both", expand=True, padx=16, pady=(8, 12))

    # ─────────── 主题切换 ───────────

    def _toggle_theme(self):
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        self.colors = THEMES[self.current_theme]
        self.config["theme"] = self.current_theme
        save_config(self.config)
        self.theme_btn.configure(text="☀" if self.current_theme == "dark" else "☾")
        self._apply_theme()

    def _apply_theme(self):
        c = self.colors
        self.root.configure(bg=c["bg"])
        self._apply_recursive(self.root, c)
        for sp in self.step_widgets:
            sp.update_colors(c)

    def _apply_recursive(self, parent, c):
        for w in parent.winfo_children():
            try:
                bg_role = getattr(w, '_tbg', None)
                fg_role = getattr(w, '_tfg', None)
                bd_role = getattr(w, '_tborder', None)
                if bg_role:
                    kw = {'bg': c[bg_role]}
                    if isinstance(w, tk.Entry):
                        kw['insertbackground'] = c['text']
                        kw['readonlybackground'] = c[bg_role]
                    w.configure(**kw)
                if fg_role:
                    w.configure(fg=c[fg_role])
                if bd_role:
                    w.configure(highlightbackground=c[bd_role])
                if isinstance(w, tk.Text):
                    w.configure(insertbackground=c["text"])
                if hasattr(w, '_hover_colors'):
                    w._hover_colors = c
                # ── toggle 按钮主题刷新 ──
                if hasattr(w, '_ttoggle_c'):
                    w._ttoggle_c = c
                    var = w._ttoggle_var
                    val = w._ttoggle_val
                    bg_key = w._ttoggle_bg_key
                    try:
                        if var.get() == val:
                            w.configure(
                                bg=c["accent"], fg="white",
                                activebackground=c.get("accent_dim", c["accent"]),
                                activeforeground="white")
                        else:
                            w.configure(
                                bg=c[bg_key], fg=c["text"],
                                activebackground=c[bg_key],
                                activeforeground=c["text"])
                    except tk.TclError:
                        pass
            except tk.TclError:
                pass
            self._apply_recursive(w, c)

    # ─────────── 步骤控制 ───────────

    def _set_step(self, index, state, status_text=""):
        self.step_states[index] = state
        self.step_widgets[index].set_state(state, status_text)

    def _reset_steps(self):
        self.step_states = ["reset"] * 4
        for sp in self.step_widgets:
            sp.set_state("reset")

    def _step_ui(self, is_batch, index, state, status=""):
        """仅在单任务模式下更新步骤 UI"""
        if not is_batch:
            self.root.after(0, lambda: self._set_step(index, state, status))

    # ─────────── 计时器 ───────────

    def _start_timer(self):
        self._process_start = time.time()
        self._step_start = time.time()
        self._step_times = []
        self._update_timer()

    def _step_done_timer(self):
        elapsed = time.time() - self._step_start
        self._step_times.append(elapsed)
        self._step_start = time.time()

    def _update_timer(self):
        if not self.is_running:
            self.timer_label.configure(text="")
            return
        elapsed = time.time() - self._process_start
        if self._step_times:
            avg = sum(self._step_times) / len(self._step_times)
            remaining_steps = 4 - len(self._step_times)
            current_elapsed = time.time() - self._step_start
            remaining = max(0, avg - current_elapsed) + avg * max(0, remaining_steps - 1)
        else:
            remaining = 0
        if self.batch_total > 1 and self._step_times:
            video_time = sum(self._step_times) + remaining
            remaining_videos = self.batch_total - self.batch_current - 1
            remaining += video_time * remaining_videos
        self.timer_label.configure(
            text=f"⏱  已用时 {format_duration(elapsed)}  ·  预计剩余 {format_duration(remaining)}")
        self._timer_id = self.root.after(1000, self._update_timer)

    def _stop_timer(self):
        if self._timer_id:
            try:
                self.root.after_cancel(self._timer_id)
            except tk.TclError:
                pass
            self._timer_id = None

    # ─────────── 日志与结果 ───────────

    def _log(self, msg):
        def _u():
            self.log_text.config(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{ts}] {msg}\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.root.after(0, _u)

    def _set_result(self, text, append=False):
        def _u():
            self.result_text.config(state="normal")
            if append:
                existing = self.result_text.get("1.0", "end").strip()
                if existing:
                    self.result_text.insert("end", "\n\n" + "─" * 60 + "\n\n")
                self.result_text.insert("end", text)
                self.result_text.see("end")
            else:
                self.result_text.delete("1.0", "end")
                self.result_text.insert("1.0", text)
        self.root.after(0, _u)

    def _copy_result(self):
        content = self.result_text.get("1.0", "end").strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.copy_btn.config(text="已复制!")
            self.root.after(1500, lambda: self.copy_btn.config(text="复制"))

    def _on_paste(self):
        try:
            clip = self.root.clipboard_get()
            self.input_text.delete("1.0", "end")
            self.input_text.insert("1.0", clip)
        except tk.TclError:
            pass

    # ─────────── 字体缩放 ───────────

    def _zoom_in(self):
        self._result_font_size = min(32, self._result_font_size + 1)
        self.result_text.configure(font=(self.font_family, self._result_font_size))

    def _zoom_out(self):
        self._result_font_size = max(8, self._result_font_size - 1)
        self.result_text.configure(font=(self.font_family, self._result_font_size))

    # ─────────── 拖拽 ───────────

    def _on_drop(self, files):
        for f in files:
            try:
                path = f.decode('gbk') if isinstance(f, bytes) else str(f)
            except Exception:
                continue
            if os.path.isfile(path):
                self._load_file_to_input(path)
            elif os.path.isdir(path):
                count = 0
                for fname in sorted(os.listdir(path)):
                    if fname.lower().endswith(('.txt', '.md')):
                        self._load_file_to_input(os.path.join(path, fname))
                        count += 1
                if count == 0:
                    self._log(f"⚠️ 文件夹中没有 TXT/MD 文件: {os.path.basename(path)}")

    def _load_file_to_input(self, filepath):
        for encoding in ['utf-8', 'gbk', 'utf-16']:
            try:
                with open(filepath, 'r', encoding=encoding) as fh:
                    content = fh.read().strip()
                if content:
                    self.input_text.insert('end', content + '\n')
                    self._log(f"📂 已加载: {os.path.basename(filepath)}")
                return
            except (UnicodeDecodeError, UnicodeError):
                continue
        self._log(f"⚠️ 无法读取: {os.path.basename(filepath)}")

    # ─────────── 批量控制 ───────────

    def _select_all_urls(self):
        self.input_text.tag_add("sel", "1.0", "end-1c")
        self.input_text.focus_set()

    def _toggle_pause(self):
        if not self.is_running:
            return
        if self._paused.is_set():
            self._paused.clear()
            self.pause_btn.configure(text="▶ 继续全部")
            self.batch_label.configure(text="⏸ 已暂停")
            self._log("⏸ 已暂停全部任务")
        else:
            self._paused.set()
            self.pause_btn.configure(text="⏸ 暂停全部")
            self._log("▶ 已继续全部任务")

    def _clear_finished(self):
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")
        self.batch_label.configure(text="")
        self._reset_steps()
        self.retry_failed_btn.pack_forget()
        self._log("🗑️ 已清空结果")

    def _retry_all_failed(self):
        if not self._failed_urls:
            messagebox.showinfo("提示", "没有失败的任务需要重试")
            return
        urls_to_retry = self._failed_urls[:]
        self._failed_urls.clear()
        self.retry_failed_btn.pack_forget()
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", "\n".join(urls_to_retry))
        self._log(f"🔄 准备重试 {len(urls_to_retry)} 个失败任务")
        self._on_start()

    def _update_batch_progress(self):
        self.batch_label.configure(
            text=f"📦 已完成 {self._completed_count}/{self.batch_total} 个"
                 f"（✅ {self._success_count}  ❌ {self._fail_count}）")

    # ─────────── 设置与历史 ───────────

    def _open_settings(self):
        SettingsDialog(self.root, self.config, self.font_family, self.colors,
                       on_save=self._on_settings_saved)

    def _on_settings_saved(self, new_config):
        self.config = new_config

    def _open_history(self):
        HistoryDialog(self.root, self.font_family, self.colors,
                      on_reprocess=self._on_reprocess,
                      on_continue=self._on_continue_from_history)

    def _on_reprocess(self, url):
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", url)
        self._on_start()

    def _on_continue_from_history(self, folder_path):
        if self.is_running:
            messagebox.showwarning("提示", "正在处理中，请等待完成")
            return

        status, detail = check_folder_status(folder_path)
        if status == 'completed':
            messagebox.showinfo("提示", "已生成，正在帮您打开")
            os.startfile(detail)
            return
        if status == 'empty':
            messagebox.showwarning("提示", "该文件夹中没有可继续处理的文件")
            return

        self.current_folder_path = folder_path
        self.current_video_path = None
        self.current_mp3_path = None
        for f_name in os.listdir(folder_path):
            if f_name.endswith(('.mp4', '.webm')):
                self.current_video_path = os.path.join(folder_path, f_name)
            elif f_name == 'audio.mp3':
                self.current_mp3_path = os.path.join(folder_path, f_name)

        folder_name = os.path.basename(folder_path)
        parts = folder_name.rsplit(' ', 1)
        self.current_title = parts[0] if len(parts) == 2 and re.match(r'^\d{8}$', parts[1]) else folder_name

        step_map = {'need_convert': 1, 'need_transcribe': 2, 'need_polish': 3}
        self.failed_step = step_map.get(status, 1)

        self.batch_urls = []
        self.batch_total = 1
        self.batch_current = 0
        self.is_running = True
        self.continue_btn.pack_forget()
        self.retry_failed_btn.pack_forget()
        self.start_btn.config(state="disabled")
        self._reset_steps()
        for i in range(self.failed_step):
            self._set_step(i, "done")
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        self._set_result("")
        self._start_timer()
        self._step_start = time.time()

        threading.Thread(target=self._continue_pipeline, daemon=True).start()

    # ─────────── 保存多格式文稿 ───────────

    def _save_all_formats(self, pol_text, folder_path):
        """保存所有选中的输出格式，逐个处理错误"""
        formats = self.config.get("output_formats", ["md"])
        saved_paths = []
        for fmt in formats:
            try:
                p = save_output(pol_text, folder_path, fmt)
                saved_paths.append(p)
                self._log(f"📄 [{fmt.upper()}] 文稿已保存: {p}")
            except Exception as e:
                friendly, action = get_user_friendly_error(str(e))
                self._log(f"⚠️ [{fmt.upper()}] 导出失败: {friendly}")
                if action:
                    self.root.after(0, lambda a=action, m=friendly: self._show_fix_dialog(m, a))
        return saved_paths

    # ─────────── 流程控制 ───────────

    def _on_start(self):
        if self.is_running:
            return
        text = self.input_text.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("提示", "请先粘贴抖音分享内容")
            return

        urls = extract_all_urls(text)
        if not urls:
            messagebox.showwarning("提示", "未检测到有效链接")
            return

        valid_urls = [u for u in urls if is_douyin_url(u)]
        invalid_urls = [u for u in urls if not is_douyin_url(u)]

        if not valid_urls:
            messagebox.showwarning("提示", "未检测到有效的抖音链接")
            return

        if invalid_urls:
            self._log(f"⚠️ 已跳过 {len(invalid_urls)} 个非抖音链接")

        self.config["template"] = self.template_var.get()
        save_config(self.config)

        self.batch_urls = valid_urls
        self.batch_total = len(valid_urls)
        self.batch_current = 0
        self.is_running = True
        self.failed_step = -1
        self.continue_btn.pack_forget()
        self.retry_failed_btn.pack_forget()
        self.start_btn.config(state="disabled")
        self._reset_steps()
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        self._set_result("")
        self._start_timer()

        if self.batch_total > 1:
            self._log(f"📋 共检测到 {self.batch_total} 个链接，将并发处理")

        threading.Thread(target=self._run_batch, daemon=True).start()

    def _on_continue(self):
        if self.is_running:
            return
        if self.failed_step < 1 or self.failed_step > 3:
            return
        self.is_running = True
        self.continue_btn.pack_forget()
        self.start_btn.config(state="disabled")
        self._step_start = time.time()
        threading.Thread(target=self._continue_pipeline, daemon=True).start()

    # ─────────── 批量调度（线程池 + 暂停） ───────────

    def _run_batch(self):
        self._success_count = 0
        self._fail_count = 0
        self._last_error = None
        self._completed_count = 0
        self._failed_urls.clear()
        self._paused.set()
        self._cancel_flag = False
        self.root.after(0, lambda: self.pause_btn.configure(text="⏸ 暂停全部"))

        max_workers = min(3, max(1, self.batch_total))

        def _on_done(ok, result, url=None):
            with self._batch_lock:
                if ok:
                    self._success_count += 1
                else:
                    self._fail_count += 1
                    self._last_error = result
                    if url:
                        self._failed_urls.append(url)
                self._completed_count += 1
            if self.batch_total > 1:
                self.root.after(0, self._update_batch_progress)

        if max_workers <= 1:
            self._paused.wait()
            if not self._cancel_flag:
                ok, result = self._run_single(self.batch_urls[0])
                _on_done(ok, result, self.batch_urls[0])
        else:
            self.root.after(0, lambda: self.batch_label.configure(
                text=f"📦 {self.batch_total} 个链接，{max_workers} 线程并发"))

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for url in self.batch_urls:
                    if self._cancel_flag:
                        break
                    self._paused.wait()
                    if self._cancel_flag:
                        break
                    f = executor.submit(self._run_single, url)
                    futures[f] = url

                for future in as_completed(futures):
                    url = futures[future]
                    try:
                        ok, result = future.result()
                    except Exception as e:
                        ok, result = False, str(e)
                    _on_done(ok, result, url)

        if self.batch_total > 1:
            summary = (f"\n📊 批量处理完成：成功 {self._success_count} 个，"
                       f"失败 {self._fail_count} 个，共 {self.batch_total} 个")
            self._log(summary)

        if self._fail_count > 0 and self.batch_total == 1:
            self.root.after(0, lambda: messagebox.showerror(
                "处理失败", self._last_error or "未知错误"))

        if self._failed_urls and self.batch_total > 1:
            self.root.after(0, lambda: self.retry_failed_btn.pack(
                side="right", padx=(8, 0), ipady=4))

        if self.failed_step >= 1 and self.current_folder_path and self.batch_total == 1:
            self.root.after(0, lambda: self.continue_btn.pack(
                side="right", padx=(16, 0), ipady=4))

        self.root.after(0, self._finish)

    # ─────────── 核心流程 ───────────

    def _run_single(self, share_text):
        is_batch = self.batch_total > 1
        video_path = mp3_path = folder_path = None
        try:
            url = extract_url(share_text)
            self._log(f"🔗 提取到链接: {url}")

            # ── 重复检测：按 URL 匹配历史 ──
            history = load_history()
            for entry in history:
                if entry.get("url") == url and entry.get("status", "").startswith("成功"):
                    existing_folder = entry.get("folder", "")
                    if existing_folder and os.path.exists(existing_folder):
                        st, det = check_folder_status(existing_folder)
                        if st == 'completed':
                            self._log(f"📄 检测到已有文稿: {det}")
                            content = ""
                            try:
                                if det.endswith(('.md', '.txt')):
                                    with open(det, 'r', encoding='utf-8') as f:
                                        content = f.read()
                                else:
                                    content = f"文稿已存在于: {det}"
                            except Exception:
                                content = f"文稿已存在于: {det}"
                            self._set_result(content, append=is_batch)
                            for idx in range(4):
                                self.root.after(0, lambda i=idx: self._set_step(i, "done"))
                            if not is_batch:
                                self.root.after(200, lambda d=det: (
                                    messagebox.showinfo("提示", "已生成，正在帮您打开"),
                                    os.startfile(d)))
                            else:
                                self._log("📄 已有文稿，跳过")
                            return True, content

            # ── 重复检测：按标题匹配文件夹 ──
            quick_title = get_video_title_quick(url, self._log)
            if quick_title:
                clean = clean_title_for_folder(quick_title)
                matches = find_matching_folders(clean)
                if matches:
                    for match_name, match_path in matches:
                        status, detail = check_folder_status(match_path)
                        if status == 'completed':
                            self._log(f"📄 检测到已有文稿: {detail}")
                            content = ""
                            try:
                                if detail.endswith(('.md', '.txt')):
                                    with open(detail, 'r', encoding='utf-8') as f:
                                        content = f.read()
                                else:
                                    content = f"文稿已存在于: {detail}"
                            except Exception:
                                content = f"文稿已存在于: {detail}"
                            self._set_result(content, append=is_batch)
                            for idx in range(4):
                                self.root.after(0, lambda i=idx: self._set_step(i, "done"))
                            if not is_batch:
                                self.root.after(200, lambda d=detail: (
                                    messagebox.showinfo("提示", "已生成，正在帮您打开"),
                                    os.startfile(d)))
                            else:
                                self._log("📄 已有文稿，跳过")
                            return True, content

                        if status in ('need_convert', 'need_transcribe', 'need_polish'):
                            self._log("🔄 检测到已有内容，从断点继续处理")
                            return self._resume_from_folder(
                                match_path, quick_title, url, status, is_batch)

            # ── Step 1: 下载 ──
            self._step_ui(is_batch, 0, "running", "正在下载...")
            cookie_file = COOKIE_FILE if os.path.exists(COOKIE_FILE) else None
            video_path, title = download_video(
                share_text, self._log,
                self.config.get("browser", "chrome"), cookie_file)
            self._step_ui(is_batch, 0, "done")
            if not is_batch:
                self.root.after(0, self._step_done_timer)

            clean = clean_title_for_folder(title)
            date_str = datetime.now().strftime("%Y%m%d")
            folder_name = sanitize_filename(f"{clean} {date_str}")
            folder_path = os.path.join(OUTPUT_DIR, folder_name)
            os.makedirs(folder_path, exist_ok=True)

            ext = os.path.splitext(video_path)[1]
            new_video_path = os.path.join(folder_path, f"video{ext}")
            if os.path.abspath(video_path) != os.path.abspath(new_video_path):
                retry_operation(lambda: os.rename(video_path, new_video_path))
            video_path = new_video_path
            self._log(f"📁 文件夹: {folder_path}")

            self.current_folder_path = folder_path
            self.current_video_path = video_path
            self.current_title = title

            # ── Step 2: 转换 ──
            self._step_ui(is_batch, 1, "running", "正在转换...")
            mp3_path = os.path.join(folder_path, "audio.mp3")
            video_to_mp3(video_path, mp3_path, self._log)
            self._step_ui(is_batch, 1, "done")
            if not is_batch:
                self.root.after(0, self._step_done_timer)
            self.current_mp3_path = mp3_path

            # ── Step 3: 识别 ──
            self._step_ui(is_batch, 2, "running", "正在识别...")
            raw, segments = transcribe(mp3_path, self._log)
            self._step_ui(is_batch, 2, "done")
            if not is_batch:
                self.root.after(0, self._step_done_timer)

            raw_path = os.path.join(folder_path, "raw.txt")
            retry_operation(lambda: write_text_file(raw_path, raw))
            segments_path = os.path.join(folder_path, "segments.json")
            retry_operation(lambda: write_json_file(segments_path, segments))
            self._log(f"💾 原始识别文本已保存: {raw_path}")

            # ── Step 4: AI 整理 ──
            template = self.template_var.get()
            self._step_ui(is_batch, 3, "running", "正在整理...")
            if template == "subtitle" and segments:
                pol = format_subtitle(segments)
                pol_ai = polish(raw, self._log,
                                self.config.get("base_url"),
                                self.config.get("model"),
                                self.config.get("api_key"), template)
                pol = pol + "\n\n---\n\n" + pol_ai
            else:
                pol = polish(raw, self._log,
                             self.config.get("base_url"),
                             self.config.get("model"),
                             self.config.get("api_key"), template)
            self._step_ui(is_batch, 3, "done")
            if not is_batch:
                self.root.after(0, self._step_done_timer)

            # ── 短标题 & 重命名 ──
            display_title, folder_path, video_path, mp3_path = self._maybe_shorten_title(
                title, raw, folder_path, video_path, mp3_path, date_str)

            # ── 保存文稿（多格式） ──
            self._save_all_formats(pol, folder_path)

            if self.config.get("delete_media", False):
                for p in [video_path, mp3_path]:
                    if p and os.path.exists(p):
                        retry_operation(lambda path=p: os.remove(path), max_retries=2, delay=0.3)
                        self._log(f"🗑️  已删除: {os.path.basename(p)}")

            # ── 结果展示 ──
            if is_batch:
                self._set_result(f"━━━ {display_title} ━━━\n{pol}", append=True)
            else:
                self._set_result(pol)
            self._log("🎉 全部完成！")
            write_log(f"[完成] {display_title} | 文件夹: {folder_path}")

            # ── 自动操作 ──
            if not is_batch and self.config.get("auto_copy_text"):
                try:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(pol)
                    self._log("📋 文稿已自动复制到剪贴板")
                except Exception:
                    pass
            if not is_batch and self.config.get("auto_open_folder") and folder_path:
                try:
                    os.startfile(folder_path)
                except Exception:
                    pass

            formats = self.config.get("output_formats", ["md"])
            save_history_entry({
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "title": display_title,
                "url": url,
                "folder": folder_path,
                "format": ",".join(formats),
                "status": "成功"
            })
            return True, pol

        except Exception as e:
            err_msg = str(e)
            friendly, action = get_user_friendly_error(err_msg)
            self._log(f"❌ 出错了: {friendly}")
            write_log(f"[错误] {err_msg}")
            if action:
                self.root.after(0, lambda a=action, m=friendly: self._show_fix_dialog(m, a))

            for i, state in enumerate(self.step_states):
                if state == "running":
                    self._step_ui(is_batch, i, "error", "失败")
                    self.failed_step = i
                    break

            self._set_result(f"处理失败：{friendly}", append=is_batch)

            title_for_log = self.current_title or "未知"
            formats = self.config.get("output_formats", ["md"])
            save_history_entry({
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "title": title_for_log,
                "url": extract_url(share_text),
                "folder": self.current_folder_path or "",
                "format": ",".join(formats),
                "status": f"失败(步骤{self.failed_step + 1})"
            })
            return False, friendly

    def _resume_from_folder(self, folder_path, title, url, status, is_batch=False):
        video_path = mp3_path = None
        for f_name in os.listdir(folder_path):
            if f_name.endswith(('.mp4', '.webm')):
                video_path = os.path.join(folder_path, f_name)
            elif f_name == 'audio.mp3':
                mp3_path = os.path.join(folder_path, f_name)

        self.current_folder_path = folder_path
        self.current_video_path = video_path
        self.current_title = title
        self._step_ui(is_batch, 0, "done")
        if not is_batch:
            self.root.after(0, self._step_done_timer)

        # Step 2
        if status == 'need_convert':
            self._step_ui(is_batch, 1, "running", "正在转换...")
            mp3_path = os.path.join(folder_path, "audio.mp3")
            video_to_mp3(video_path, mp3_path, self._log)
            self._step_ui(is_batch, 1, "done")
            if not is_batch:
                self.root.after(0, self._step_done_timer)
            self.current_mp3_path = mp3_path
            status = 'need_transcribe'

        # Step 3
        raw = None
        segments = []
        if status == 'need_transcribe':
            self._step_ui(is_batch, 2, "running", "正在识别...")
            if not mp3_path or not os.path.exists(mp3_path):
                mp3_path = os.path.join(folder_path, "audio.mp3")
            raw, segments = transcribe(mp3_path, self._log)
            self._step_ui(is_batch, 2, "done")
            if not is_batch:
                self.root.after(0, self._step_done_timer)
            raw_path = os.path.join(folder_path, "raw.txt")
            retry_operation(lambda: write_text_file(raw_path, raw))
            segments_path = os.path.join(folder_path, "segments.json")
            retry_operation(lambda: write_json_file(segments_path, segments))
            self._log(f"💾 原始识别文本已保存: {raw_path}")
        else:
            raw_path = os.path.join(folder_path, "raw.txt")
            with open(raw_path, "r", encoding="utf-8") as f:
                raw = f.read()
            segments_path = os.path.join(folder_path, "segments.json")
            if os.path.exists(segments_path):
                with open(segments_path, "r", encoding="utf-8") as f:
                    segments = json.load(f)
            self._step_ui(is_batch, 2, "done")
            if not is_batch:
                self.root.after(0, self._step_done_timer)

        # Step 4
        template = self.template_var.get()
        self._step_ui(is_batch, 3, "running", "正在整理...")
        if template == "subtitle" and segments:
            pol = format_subtitle(segments)
            pol_ai = polish(raw, self._log,
                            self.config.get("base_url"),
                            self.config.get("model"),
                            self.config.get("api_key"), template)
            pol = pol + "\n\n---\n\n" + pol_ai
        else:
            pol = polish(raw, self._log,
                         self.config.get("base_url"),
                         self.config.get("model"),
                         self.config.get("api_key"), template)
        self._step_ui(is_batch, 3, "done")
        if not is_batch:
            self.root.after(0, self._step_done_timer)

        parts = os.path.basename(folder_path).rsplit(' ', 1)
        date_str = parts[1] if len(parts) == 2 and re.match(r'^\d{8}$', parts[1]) else datetime.now().strftime("%Y%m%d")
        display_title, folder_path, video_path, mp3_path = self._maybe_shorten_title(
            title, raw, folder_path, video_path, mp3_path, date_str)

        self._save_all_formats(pol, folder_path)

        if self.config.get("delete_media", False):
            for p in [video_path, mp3_path]:
                if p and os.path.exists(p):
                    retry_operation(lambda path=p: os.remove(path), max_retries=2, delay=0.3)
                    self._log(f"🗑️  已删除: {os.path.basename(p)}")

        if is_batch:
            self._set_result(f"━━━ {display_title} ━━━\n{pol}", append=True)
        else:
            self._set_result(pol)
        self._log("🎉 全部完成！")
        write_log(f"[完成] {display_title} | 文件夹: {folder_path}")

        # 自动操作
        if not is_batch and self.config.get("auto_copy_text"):
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(pol)
                self._log("📋 文稿已自动复制到剪贴板")
            except Exception:
                pass
        if not is_batch and self.config.get("auto_open_folder") and folder_path:
            try:
                os.startfile(folder_path)
            except Exception:
                pass

        formats = self.config.get("output_formats", ["md"])
        save_history_entry({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "title": display_title,
            "url": url,
            "folder": folder_path,
            "format": ",".join(formats),
            "status": "成功(续传)"
        })
        return True, pol

    def _maybe_shorten_title(self, title, raw, folder_path, video_path, mp3_path, date_str):
        display_title = title
        cleaned = clean_title_for_folder(title)
        if len(cleaned) > 25:
            short = generate_short_title(
                raw, self._log,
                self.config.get("base_url"),
                self.config.get("model"),
                self.config.get("api_key"))
            if short:
                display_title = short
                new_name = sanitize_filename(f"{short} {date_str}")
                new_path = rename_folder_safe(folder_path, new_name)
                if new_path != folder_path:
                    folder_path = new_path
                    self.current_folder_path = folder_path
                    if video_path:
                        video_path = os.path.join(folder_path, os.path.basename(video_path))
                        self.current_video_path = video_path
                    if mp3_path:
                        mp3_path = os.path.join(folder_path, os.path.basename(mp3_path))
                        self.current_mp3_path = mp3_path
                    self.current_title = short
                    self._log(f"📁 文件夹已重命名: {os.path.basename(folder_path)}")
            else:
                display_title = cleaned[:25]
        return display_title, folder_path, video_path, mp3_path

    def _continue_pipeline(self):
        try:
            folder = self.current_folder_path
            step = self.failed_step

            if step == 1:
                video_path = self.current_video_path
                if not video_path or not os.path.exists(video_path):
                    for f in os.listdir(folder):
                        if f.endswith((".mp4", ".webm")):
                            video_path = os.path.join(folder, f)
                            break
                    if not video_path or not os.path.exists(video_path):
                        raise Exception("未找到视频文件，无法继续")
                self.root.after(0, lambda: self._set_step(1, "running", "正在转换..."))
                mp3_path = os.path.join(folder, "audio.mp3")
                video_to_mp3(video_path, mp3_path, self._log)
                self.root.after(0, lambda: self._set_step(1, "done"))
                self.root.after(0, self._step_done_timer)
                self.current_mp3_path = mp3_path
                step = 2

            if step == 2:
                mp3_path = self.current_mp3_path
                if not mp3_path or not os.path.exists(mp3_path):
                    mp3_path = os.path.join(folder, "audio.mp3")
                if not os.path.exists(mp3_path):
                    raise Exception("未找到 MP3 文件，无法继续")
                self.root.after(0, lambda: self._set_step(2, "running", "正在识别..."))
                raw, segments = transcribe(mp3_path, self._log)
                self.root.after(0, lambda: self._set_step(2, "done"))
                self.root.after(0, self._step_done_timer)
                raw_path = os.path.join(folder, "raw.txt")
                retry_operation(lambda: write_text_file(raw_path, raw))
                segments_path = os.path.join(folder, "segments.json")
                retry_operation(lambda: write_json_file(segments_path, segments))
                self._log(f"💾 原始识别文本已保存: {raw_path}")
                step = 3

            if step == 3:
                raw_path = os.path.join(folder, "raw.txt")
                if not os.path.exists(raw_path):
                    raise Exception("未找到 raw.txt，无法继续")
                with open(raw_path, "r", encoding="utf-8") as f:
                    raw = f.read()
                segments_path = os.path.join(folder, "segments.json")
                segments = []
                if os.path.exists(segments_path):
                    with open(segments_path, "r", encoding="utf-8") as f:
                        segments = json.load(f)
                template = self.template_var.get()
                self.root.after(0, lambda: self._set_step(3, "running", "正在整理..."))
                if template == "subtitle" and segments:
                    pol = format_subtitle(segments)
                    pol_ai = polish(raw, self._log,
                                    self.config.get("base_url"),
                                    self.config.get("model"),
                                    self.config.get("api_key"), template)
                    pol = pol + "\n\n---\n\n" + pol_ai
                else:
                    pol = polish(raw, self._log,
                                 self.config.get("base_url"),
                                 self.config.get("model"),
                                 self.config.get("api_key"), template)
                self.root.after(0, lambda: self._set_step(3, "done"))
                self.root.after(0, self._step_done_timer)

                parts = os.path.basename(folder).rsplit(' ', 1)
                date_str = parts[1] if len(parts) == 2 and re.match(r'^\d{8}$', parts[1]) else datetime.now().strftime("%Y%m%d")
                display_title, folder, self.current_video_path, self.current_mp3_path = self._maybe_shorten_title(
                    self.current_title or "未知", raw, folder,
                    self.current_video_path, self.current_mp3_path, date_str)

                self._save_all_formats(pol, folder)

                if self.config.get("delete_media", False):
                    for p in [self.current_video_path, self.current_mp3_path]:
                        if p and os.path.exists(p):
                            retry_operation(lambda path=p: os.remove(path), max_retries=2, delay=0.3)
                            self._log(f"🗑️  已删除: {os.path.basename(p)}")

                self._set_result(pol)
                self._log("🎉 继续处理完成！")
                write_log(f"[继续完成] {display_title} | 文件夹: {folder}")

                # 自动操作
                if self.config.get("auto_copy_text"):
                    try:
                        self.root.clipboard_clear()
                        self.root.clipboard_append(pol)
                        self._log("📋 文稿已自动复制到剪贴板")
                    except Exception:
                        pass
                if self.config.get("auto_open_folder") and folder and os.path.exists(folder):
                    try:
                        os.startfile(folder)
                    except Exception:
                        pass

                formats = self.config.get("output_formats", ["md"])
                save_history_entry({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "title": display_title,
                    "url": "",
                    "folder": folder,
                    "format": ",".join(formats),
                    "status": "成功(继续)"
                })

            self.failed_step = -1

        except Exception as e:
            err_msg = str(e)
            friendly, action = get_user_friendly_error(err_msg)
            self._log(f"❌ 继续处理出错: {friendly}")
            write_log(f"[继续错误] {err_msg}")
            if action:
                self.root.after(0, lambda a=action, m=friendly: self._show_fix_dialog(m, a))

            for i, state in enumerate(self.step_states):
                if state == "running":
                    self.root.after(0, lambda idx=i: self._set_step(idx, "error", "失败"))
                    self.failed_step = i
                    break

            self.root.after(0, lambda m=friendly: self._set_result(f"处理失败：{m}"))
            self.root.after(0, lambda m=friendly: messagebox.showerror("处理失败", m))

            if self.failed_step >= 1:
                self.root.after(0, lambda: self.continue_btn.pack(
                    side="right", padx=(16, 0), ipady=4))
        finally:
            self.root.after(0, self._finish)

    # ─────────── 错误修复弹窗 ───────────

    def _show_fix_dialog(self, message, action):
        c, f = self.colors, self.font_family
        win = tk.Toplevel(self.root)
        win.title("出错了")
        win.geometry("500x230")
        win.configure(bg=c["surface"])
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 500) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 230) // 2
        win.geometry(f"+{max(0, x)}+{max(0, y)}")

        tk.Label(win, text="❌  处理失败", font=(f, 14, "bold"),
                 fg=c["red"], bg=c["surface"]).pack(anchor="w", padx=28, pady=(20, 4))
        tk.Label(win, text=message, font=(f, 11), fg=c["text"], bg=c["surface"],
                 wraplength=440, justify="left").pack(padx=28, anchor="w")

        btn_frame = tk.Frame(win, bg=c["surface"])
        btn_frame.pack(fill="x", padx=28, pady=(20, 20))

        if action and action in FIX_COMMANDS:
            label = FIX_LABELS.get(action, "🔧 一键修复")
            fix_btn = tk.Button(btn_frame, text=label, font=(f, 11, "bold"),
                                bg=c["accent"], fg="white", relief="flat", bd=0,
                                activebackground=c["accent_dim"], cursor="hand2",
                                command=lambda: self._run_fix(action, win))
            fix_btn.pack(side="left", ipady=5, ipadx=14)
            bind_hover(fix_btn, "accent_dim", "accent", colors=c)

        close_btn = tk.Button(btn_frame, text="关闭", font=(f, 10),
                              bg=c["surface2"], fg=c["text_dim"], relief="flat", bd=0,
                              activebackground=c["surface3"], cursor="hand2",
                              command=win.destroy)
        close_btn.pack(side="left", padx=(12, 0), ipady=5, ipadx=14)
        bind_hover(close_btn, "surface3", "surface2", colors=c)

    def _run_fix(self, action, dialog_win):
        if action not in FIX_COMMANDS:
            return
        cmd, fallback = FIX_COMMANDS[action]
        dialog_win.destroy()
        self._log(f"🔧 正在执行: {cmd}")

        def _do():
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True,
                                   text=True, timeout=300, encoding="utf-8", errors="replace")
                if r.returncode == 0:
                    self._log("✅ 安装成功！请重新执行操作")
                    self.root.after(0, lambda: messagebox.showinfo(
                        "安装完成", "依赖安装成功，请重新执行操作。"))
                else:
                    err_out = (r.stderr or r.stdout or "")[:300]
                    self._log(f"⚠️ 安装失败: {err_out}")
                    if fallback:
                        self._log(f"💡 备选方案: {fallback}")
                    msg = f"自动安装失败：\n{err_out}"
                    if fallback:
                        msg += f"\n\n💡 {fallback}"
                    self.root.after(0, lambda m=msg: messagebox.showwarning("安装失败", m))
            except subprocess.TimeoutExpired:
                self._log("⚠️ 安装超时")
                self.root.after(0, lambda: messagebox.showwarning(
                    "超时", "安装超时，请手动执行命令"))
            except Exception as e:
                self._log(f"⚠️ 安装异常: {e}")
                self.root.after(0, lambda: messagebox.showwarning(
                    "异常", f"安装异常: {e}"))

        threading.Thread(target=_do, daemon=True).start()

    # ─────────── 结束 ───────────

    def _finish(self):
        self.is_running = False
        self.start_btn.config(state="normal")
        self._stop_timer()
        self.batch_label.configure(text="")
        self._paused.set()
        self._cancel_flag = False
        self.pause_btn.configure(text="⏸ 暂停全部")

    def run(self):
        try:
            self.root.mainloop()
        finally:
            flush_log()
