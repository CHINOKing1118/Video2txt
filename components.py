import tkinter as tk


class StepProgress(tk.Frame):
    def __init__(self, parent, name, font_family, colors):
        super().__init__(parent, bg=colors["bg"])
        self.F = font_family
        self.C = colors
        self._state = "reset"
        self._anim_id = None
        self._build(name)

    def _build(self, name):
        c, f = self.C, self.F
        self.dot = tk.Label(self, text="○", font=(f, 11),
                            fg=c["text_muted"], bg=c["bg"], width=2)
        self.dot.pack(side="left")
        self.lbl = tk.Label(self, text=name, font=(f, 11),
                            fg=c["text_dim"], bg=c["bg"], width=8, anchor="w")
        self.lbl.pack(side="left")
        self.bar_canvas = tk.Canvas(self, width=100, height=6,
                                     bg=c["surface2"], highlightthickness=0)
        self.bar_canvas.pack(side="left", padx=(12, 4))
        self.pct_label = tk.Label(self, text="", font=("Consolas", 9),
                                   fg=c["text_muted"], bg=c["bg"], width=5)
        self.pct_label.pack(side="left")
        self.status = tk.Label(self, text="", font=(f, 10),
                               fg=c["text_muted"], bg=c["bg"])
        self.status.pack(side="right")

    def set_state(self, state, status_text=""):
        self._state = state
        c = self.C
        if state == "running":
            self.dot.configure(text="◉", fg=c["yellow"])
            self.lbl.configure(fg=c["text"])
            self.status.configure(text=status_text or "处理中...", fg=c["yellow"])
            self.pct_label.configure(text="")
            self._start_animation()
        elif state == "done":
            self._stop_animation()
            self.dot.configure(text="●", fg=c["green"])
            self.lbl.configure(fg=c["text"])
            self.status.configure(text=status_text or "完成", fg=c["green"])
            self._draw_bar(100, c["green"])
            self.pct_label.configure(text="100%")
        elif state == "error":
            self._stop_animation()
            self.dot.configure(text="●", fg=c["red"])
            self.lbl.configure(fg=c["text"])
            self.status.configure(text=status_text or "失败", fg=c["red"])
            self.pct_label.configure(text="")
        else:
            self._stop_animation()
            self.dot.configure(text="○", fg=c["text_muted"])
            self.lbl.configure(fg=c["text_dim"])
            self.status.configure(text="", fg=c["text_muted"])
            self.bar_canvas.delete("all")
            self.pct_label.configure(text="")

    def set_progress(self, percent, status_text=None):
        self._stop_animation()
        self._draw_bar(percent, self.C["accent"])
        self.pct_label.configure(text=f"{int(percent)}%")
        if status_text:
            self.status.configure(text=status_text)

    def update_colors(self, colors):
        self.C = colors
        c = colors
        self.configure(bg=c["bg"])
        self.dot.configure(bg=c["bg"])
        self.lbl.configure(bg=c["bg"])
        self.bar_canvas.configure(bg=c["surface2"])
        self.pct_label.configure(bg=c["bg"])
        self.status.configure(bg=c["bg"])
        self.set_state(self._state)

    def _draw_bar(self, percent, color):
        self.bar_canvas.delete("bar")
        try:
            w = self.bar_canvas.winfo_width()
            h = self.bar_canvas.winfo_height()
        except tk.TclError:
            return
        if w <= 1:
            w = 100
        if h <= 1:
            h = 6
        bar_w = w * (percent / 100)
        if bar_w > 0:
            self.bar_canvas.create_rectangle(0, 0, bar_w, h,
                                              fill=color, outline="", tags="bar")

    def _start_animation(self):
        self._anim_x = 0
        self._anim_dir = 1
        self.bar_canvas.delete("bar")
        self._animate()

    def _animate(self):
        if self._state != "running":
            return
        c = self.C
        try:
            w = self.bar_canvas.winfo_width()
            h = self.bar_canvas.winfo_height()
        except tk.TclError:
            return
        if w <= 1:
            w = 100
        if h <= 1:
            h = 6
        bar_w = w * 0.25
        self.bar_canvas.delete("bar")
        self.bar_canvas.create_rectangle(
            self._anim_x, 0, self._anim_x + bar_w, h,
            fill=c["accent"], outline="", tags="bar")
        self._anim_x += self._anim_dir * 2
        if self._anim_x + bar_w >= w:
            self._anim_dir = -1
        elif self._anim_x <= 0:
            self._anim_dir = 1
        self._anim_id = self.after(40, self._animate)

    def _stop_animation(self):
        if self._anim_id:
            try:
                self.after_cancel(self._anim_id)
            except tk.TclError:
                pass
            self._anim_id = None


class SplashScreen:
    def __init__(self, parent, font_family, colors):
        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.configure(bg=colors["bg"])
        self.win.attributes("-topmost", True)
        w, h = 420, 240
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        c, f = colors, font_family
        border_frame = tk.Frame(self.win, bg=c["accent"], padx=2, pady=2)
        border_frame.pack(fill="both", expand=True)
        inner = tk.Frame(border_frame, bg=c["surface"])
        inner.pack(fill="both", expand=True)
        tk.Label(inner, text="Video2Txt v2.2", font=(f, 22, "bold"),
                 fg=c["accent"], bg=c["surface"]).pack(pady=(36, 2))
        tk.Label(inner, text="抖音视频 → 文字文稿", font=(f, 11),
                 fg=c["text_dim"], bg=c["surface"]).pack()
        self.loading_lbl = tk.Label(inner, text="正在加载语音识别模型，请稍候",
                                     font=(f, 10), fg=c["text_muted"], bg=c["surface"])
        self.loading_lbl.pack(pady=(28, 8))
        self.bar = tk.Canvas(inner, width=300, height=4,
                              bg=c["surface3"], highlightthickness=0)
        self.bar.pack()
        self._anim_x = 0
        self._anim_dir = 1
        self._dot_count = 0
        self._running = True
        self._animate_bar()
        self._animate_dots()

    def _animate_bar(self):
        if not self._running:
            return
        try:
            w, h = 300, 4
            bar_w = 80
            self.bar.delete("bar")
            self.bar.create_rectangle(
                self._anim_x, 0, self._anim_x + bar_w, h,
                fill="#ff6b35", outline="", tags="bar")
            self._anim_x += self._anim_dir * 2
            if self._anim_x + bar_w >= w:
                self._anim_dir = -1
            elif self._anim_x <= 0:
                self._anim_dir = 1
            self._bar_id = self.win.after(30, self._animate_bar)
        except tk.TclError:
            pass

    def _animate_dots(self):
        if not self._running:
            return
        try:
            self._dot_count = (self._dot_count + 1) % 4
            self.loading_lbl.configure(text="正在加载语音识别模型，请稍候" + "." * self._dot_count)
            self._dots_id = self.win.after(500, self._animate_dots)
        except tk.TclError:
            pass

    def destroy(self):
        self._running = False
        for attr in ('_bar_id', '_dots_id'):
            try:
                self.win.after_cancel(getattr(self, attr, None))
            except Exception:
                pass
        self.win.destroy()
