import os
import tkinter as tk
from tkinter import scrolledtext, messagebox

from config import save_config, ensure_cookie_file
from history import load_history, delete_history_entry
from utils import mask_key, check_folder_status
from ui_helpers import t, bind_hover, _rb_kw, _cb_kw, _bind_toggle


# ============================================================
# 历史记录对话框
# ============================================================

class HistoryDialog:
    def __init__(self, parent, font_family, colors, on_reprocess=None, on_continue=None):
        self.F = font_family
        self.C = colors
        self.sort_order = "desc"
        self.on_reprocess = on_reprocess
        self.on_continue = on_continue
        self._history_data = []
        self._selected_index = -1

        self.win = tk.Toplevel(parent)
        self.win.title("导出记录")
        self.win.geometry("860x560")
        self.win.minsize(800, 450)
        self.win.configure(bg=colors["bg"])
        self.win.transient(parent)
        self.win.grab_set()
        self.win.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 860) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 560) // 2
        self.win.geometry(f"+{max(0, x)}+{max(0, y)}")

        self.context_menu = tk.Menu(self.win, tearoff=0, font=(font_family, 10))
        self.context_menu.add_command(label="📂  打开文件夹", command=self._open_folder)
        self.context_menu.add_command(label="🔄  重新处理", command=self._reprocess)
        self.context_menu.add_command(label="▶  继续处理", command=self._continue_record_ctx)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="🗑️  删除记录", command=self._delete_record)

        self._build()

    def _build(self):
        c, f = self.C, self.F

        hdr = tk.Frame(self.win, bg=c["bg"])
        hdr.pack(fill="x", padx=24, pady=(16, 0))
        t(hdr, bg="bg")
        t(tk.Label(hdr, text="📋  导出记录", font=(f, 16, "bold"),
                   fg=c["accent"], bg=c["bg"]), bg="bg", fg="accent").pack(side="left")

        sort_bar = tk.Frame(self.win, bg=c["bg"])
        sort_bar.pack(fill="x", padx=24, pady=(12, 0))
        t(sort_bar, bg="bg")
        t(tk.Label(sort_bar, text="排序：", font=(f, 10),
                   fg=c["text_dim"], bg=c["bg"]), bg="bg", fg="text_dim").pack(side="left")

        self.btn_desc = tk.Button(
            sort_bar, text="时间从近到远 ↓", font=(f, 9),
            bg=c["accent"], fg="white", relief="flat", bd=0,
            activebackground=c["accent_dim"], cursor="hand2",
            command=lambda: self._set_sort("desc"))
        t(self.btn_desc, bg="accent").pack(side="left", padx=(8, 0), ipady=2, ipadx=8)

        self.btn_asc = tk.Button(
            sort_bar, text="时间从远到近 ↑", font=(f, 9),
            bg=c["surface2"], fg=c["text_dim"], relief="flat", bd=0,
            activebackground=c["surface3"], cursor="hand2",
            command=lambda: self._set_sort("asc"))
        t(self.btn_asc, bg="surface2", fg="text_dim").pack(side="left", padx=(6, 0), ipady=2, ipadx=8)

        self.count_label = tk.Label(sort_bar, text="", font=(f, 9),
                                    fg=c["text_muted"], bg=c["bg"])
        t(self.count_label, bg="bg", fg="text_muted").pack(side="right")

        tk.Label(sort_bar, text="双击标题打开文件夹 · 右键更多操作", font=(f, 9),
                 fg=c["text_muted"], bg=c["bg"]).pack(side="right", padx=(0, 12))

        content_frame = tk.Frame(self.win, bg=c["bg"])
        content_frame.pack(fill="both", expand=True, padx=24, pady=(12, 16))
        t(content_frame, bg="bg")

        self.canvas = tk.Canvas(content_frame, bg=c["bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(content_frame, orient="vertical", command=self.canvas.yview)
        self.table_frame = tk.Frame(self.canvas, bg=c["bg"])

        self.table_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.table_frame, anchor="nw", tags="inner")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig("inner", width=e.width))

        def _on_mousewheel(event):
            try:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except tk.TclError:
                pass
        self.canvas.bind("<MouseWheel>", _on_mousewheel)
        self.table_frame.bind("<MouseWheel>", _on_mousewheel)

        self._populate()

    def _set_sort(self, order):
        self.sort_order = order
        c = self.C
        if order == "desc":
            self.btn_desc.configure(bg=c["accent"], fg="white")
            self.btn_asc.configure(bg=c["surface2"], fg=c["text_dim"])
        else:
            self.btn_asc.configure(bg=c["accent"], fg="white")
            self.btn_desc.configure(bg=c["surface2"], fg=c["text_dim"])
        for w in self.table_frame.winfo_children():
            w.destroy()
        self._populate()

    def _populate(self):
        c, f = self.C, self.F
        history = load_history()
        history.sort(key=lambda e: e.get("time", ""), reverse=(self.sort_order == "desc"))
        self._history_data = history
        self.count_label.configure(text=f"共 {len(history)} 条记录")

        cols = [(0, 36), (1, 145), (2, 300), (3, 80), (4, 80), (5, 70)]
        for ci, minsize in cols:
            self.table_frame.grid_columnconfigure(ci, weight=0, minsize=minsize)

        headers = ["#", "时间", "标题", "格式", "状态", "操作"]
        for ci, text in enumerate(headers):
            tk.Label(self.table_frame, text=text, font=(f, 10, "bold"),
                     anchor="w", fg=c["text"], bg=c["surface2"]
                     ).grid(row=0, column=ci, sticky="ew", padx=6, pady=6)

        if not history:
            tk.Label(self.table_frame, text="暂无记录", font=(f, 11),
                     fg=c["text_muted"], bg=c["bg"]).grid(row=1, column=0, columnspan=6, pady=40)
            return

        for i, entry in enumerate(history):
            row = i + 1
            bg = c["surface"] if i % 2 == 0 else c["bg"]

            time_str = entry.get("time", "")[:19]
            title = entry.get("title", "")
            if len(title) > 25:
                title = title[:25] + "..."
            fmt = entry.get("format", "")
            status = entry.get("status", "")
            is_failed = "失败" in status
            fg_status = c["green"] if "成功" in status else (c["red"] if is_failed else c["text_dim"])

            cells = [
                (str(i + 1), (f, 9), "text_muted", "center"),
                (time_str, ("Consolas", 9), "text_dim", "w"),
                (title, (f, 9), "text", "w"),
                (fmt, (f, 9), "text_dim", "w"),
                (status, (f, 9), None, "w"),
            ]
            all_labels = []
            for ci, (text_val, font_cfg, fg_cfg, anchor_cfg) in enumerate(cells):
                fg_val = fg_status if ci == 4 else c[fg_cfg]
                cur = "hand2" if ci == 2 else ""
                lbl = tk.Label(self.table_frame, text=text_val, font=font_cfg,
                               anchor=anchor_cfg, fg=fg_val, bg=bg, cursor=cur)
                lbl.grid(row=row, column=ci, sticky="ew", padx=6, pady=5)
                all_labels.append(lbl)

            title_lbl = all_labels[2]
            title_lbl.bind("<Double-Button-1>", lambda e, idx=i: self._on_title_double_click(idx))

            for w in all_labels:
                w.bind("<Button-3>", lambda e, idx=i: self._on_right_click(e, idx))
                w.bind("<Enter>", lambda e, r=row: self._highlight_row(r, True))
                w.bind("<Leave>", lambda e, r=row, bg_orig=bg: self._highlight_row(r, False, bg_orig))

            if is_failed:
                cont_btn = tk.Button(
                    self.table_frame, text="继续", font=(f, 9, "bold"),
                    bg=c["accent"], fg="white", relief="flat", bd=0,
                    activebackground=c["accent_dim"], cursor="hand2",
                    command=lambda idx=i: self._continue_record(idx))
                cont_btn.grid(row=row, column=5, padx=6, pady=3, sticky="ew")
                cont_btn.bind("<Enter>", lambda e, r=row: self._highlight_row(r, True))
                cont_btn.bind("<Leave>", lambda e, r=row, bg_orig=bg: self._highlight_row(r, False, bg_orig))
            else:
                empty_lbl = tk.Label(self.table_frame, text="—", font=(f, 9),
                                     fg=c["text_muted"], bg=bg)
                empty_lbl.grid(row=row, column=5, padx=6, pady=5)
                empty_lbl.bind("<Enter>", lambda e, r=row: self._highlight_row(r, True))
                empty_lbl.bind("<Leave>", lambda e, r=row, bg_orig=bg: self._highlight_row(r, False, bg_orig))

    def _highlight_row(self, row, hover, bg_orig=None):
        c = self.C
        bg = c["surface3"] if hover else (bg_orig or c["bg"])
        for child in self.table_frame.grid_slaves(row=row):
            try:
                child.configure(bg=bg)
            except tk.TclError:
                pass

    def _on_title_double_click(self, index):
        if 0 <= index < len(self._history_data):
            folder = self._history_data[index].get("folder", "")
            if folder and os.path.exists(folder):
                os.startfile(folder)
            else:
                messagebox.showwarning("提示", "文件夹不存在或已被删除", parent=self.win)

    def _on_right_click(self, event, index):
        self._selected_index = index
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _open_folder(self):
        if 0 <= self._selected_index < len(self._history_data):
            folder = self._history_data[self._selected_index].get("folder", "")
            if folder and os.path.exists(folder):
                os.startfile(folder)
            else:
                messagebox.showwarning("提示", "文件夹不存在或已被删除", parent=self.win)

    def _reprocess(self):
        if 0 <= self._selected_index < len(self._history_data):
            entry = self._history_data[self._selected_index]
            url = entry.get("url", "")
            if url and self.on_reprocess:
                self.on_reprocess(url)
                self.win.destroy()
            else:
                messagebox.showinfo("提示", "该记录没有保存原始链接，无法重新处理", parent=self.win)

    def _continue_record(self, index):
        if 0 <= index < len(self._history_data):
            entry = self._history_data[index]
            folder = entry.get("folder", "")
            if folder and os.path.exists(folder) and self.on_continue:
                self.on_continue(folder)
                self.win.destroy()
            else:
                messagebox.showwarning("提示", "文件夹不存在或已被删除", parent=self.win)

    def _continue_record_ctx(self):
        self._continue_record(self._selected_index)

    def _delete_record(self):
        if 0 <= self._selected_index < len(self._history_data):
            if messagebox.askyesno("确认", "确定要删除这条记录吗？", parent=self.win):
                entry = self._history_data[self._selected_index]
                history = load_history()
                for i, h in enumerate(history):
                    if (h.get("time") == entry.get("time")
                            and h.get("title") == entry.get("title")
                            and h.get("folder") == entry.get("folder")):
                        delete_history_entry(i)
                        break
                for w in self.table_frame.winfo_children():
                    w.destroy()
                self._populate()


# ============================================================
# 设置对话框
# ============================================================

class SettingsDialog:
    def __init__(self, parent, config, font_family, colors, on_save):
        self.config = config
        self.F = font_family
        self.C = colors
        self.on_save = on_save
        self._actual_key = config.get("api_key", "")
        self._api_visible = False
        self._api_editing = False
        self._url_editing = False
        self._model_editing = False

        self.win = tk.Toplevel(parent)
        self.win.title("设置")
        self.win.geometry("700x920")
        self.win.configure(bg=colors["bg"])
        self.win.transient(parent)
        self.win.grab_set()
        self.win.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 700) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 920) // 2
        self.win.geometry(f"+{max(0, x)}+{max(0, y)}")
        self._build()

    def _build(self):
        c, f = self.C, self.F
        self._sf = self.win

        hdr = tk.Frame(self._sf, bg=c["bg"])
        hdr.pack(fill="x", padx=28, pady=(20, 0))
        t(hdr, bg="bg")
        t(tk.Label(hdr, text="⚙  设置", font=(f, 16, "bold"),
                   fg=c["accent"], bg=c["bg"]), bg="bg", fg="accent").pack(side="left")

        # ── 下载设置 ──
        self._section("下载设置")

        brow = tk.Frame(self._sf, bg=c["bg"])
        brow.pack(fill="x", padx=28, pady=4)
        t(brow, bg="bg")
        t(tk.Label(brow, text="浏览器", font=(f, 11), width=10, anchor="w",
                   fg=c["text_dim"], bg=c["bg"]), bg="bg", fg="text_dim").pack(side="left")
        self.browser_var = tk.StringVar(value=self.config.get("browser", "chrome"))
        for txt, val in [("Chrome", "chrome"), ("Edge", "edge"),
                         ("Firefox", "firefox"), ("360", "360")]:
            rb = tk.Radiobutton(brow, text=txt, variable=self.browser_var, value=val,
                                **_rb_kw(f, c))
            _bind_toggle(rb, self.browser_var, val, c, "bg")
            t(rb, bg="bg", fg="text").pack(side="left", padx=(0, 14))

        clf = tk.Frame(self._sf, bg=c["bg"])
        clf.pack(fill="x", padx=28, pady=(12, 2))
        t(clf, bg="bg")
        t(tk.Label(clf, text="Cookie", font=(f, 11),
                   anchor="w", fg=c["text_dim"], bg=c["bg"]),
          bg="bg", fg="text_dim").pack(side="left")
        t(tk.Label(clf, text="（浏览器 cookies 失效时手动填写，留空则自动读取）",
                   font=(f, 9), fg=c["text_muted"], bg=c["bg"]),
          bg="bg", fg="text_muted").pack(side="left", padx=(8, 0))

        self.cookie_text = scrolledtext.ScrolledText(
            self._sf, font=("Consolas", 9), height=4,
            bg=c["entry_bg"], fg=c["entry_fg"],
            insertbackground=c["text"], relief="flat", bd=0, wrap="word")
        t(self.cookie_text, bg="entry_bg", fg="entry_fg").pack(
            fill="x", padx=28, pady=(0, 4), ipadx=4, ipady=4)
        if self.config.get("cookies", ""):
            self.cookie_text.insert("1.0", self.config["cookies"])

        # ── AI 模型设置 ──
        self._section("AI 模型设置")
        self.url_entry = self._make_field("API 地址", self.config.get("base_url", ""), "_url_editing")
        self.model_entry = self._make_field("模型名称", self.config.get("model", ""), "_model_editing")
        self._make_api_field()

        # ── 输出设置 ──
        self._section("输出设置")

        # 输出格式 — 多选 Checkbutton
        fmt_row = tk.Frame(self._sf, bg=c["bg"])
        fmt_row.pack(fill="x", padx=28, pady=4)
        t(fmt_row, bg="bg")
        t(tk.Label(fmt_row, text="输出格式", font=(f, 11), width=10, anchor="w",
                   fg=c["text_dim"], bg=c["bg"]), bg="bg", fg="text_dim").pack(side="left")
        current_formats = self.config.get("output_formats", ["md"])
        self.md_var = tk.BooleanVar(value="md" in current_formats)
        self.docx_var = tk.BooleanVar(value="docx" in current_formats)
        self.pdf_var = tk.BooleanVar(value="pdf" in current_formats)
        for txt, var in [("Markdown (.md)", self.md_var),
                         ("Word (.docx)", self.docx_var),
                         ("PDF (.pdf)", self.pdf_var)]:
            cb = tk.Checkbutton(fmt_row, text=txt, variable=var, **_cb_kw(f, c, "bg"))
            _bind_toggle(cb, var, True, c, "bg")
            t(cb, bg="bg", fg="text").pack(side="left", padx=(0, 16))

        # 完成后操作 — 删除媒体
        del_row = tk.Frame(self._sf, bg=c["bg"])
        del_row.pack(fill="x", padx=28, pady=(12, 4))
        t(del_row, bg="bg")
        t(tk.Label(del_row, text="完成之后", font=(f, 11), width=10, anchor="w",
                   fg=c["text_dim"], bg=c["bg"]), bg="bg", fg="text_dim").pack(side="left")
        self.delete_var = tk.BooleanVar(value=self.config.get("delete_media", False))
        cb_del = tk.Checkbutton(del_row, text="自动删除 MP4 和 MP3 文件",
                                variable=self.delete_var, **_cb_kw(f, c, "bg"))
        _bind_toggle(cb_del, self.delete_var, True, c, "bg")
        t(cb_del, bg="bg", fg="text").pack(side="left", padx=(0, 14))

        # 完成后操作 — 自动打开 / 自动复制
        auto_row = tk.Frame(self._sf, bg=c["bg"])
        auto_row.pack(fill="x", padx=28, pady=4)
        t(auto_row, bg="bg")
        tk.Label(auto_row, text="", width=10, bg=c["bg"]).pack(side="left")
        self.auto_open_var = tk.BooleanVar(value=self.config.get("auto_open_folder", False))
        cb_open = tk.Checkbutton(auto_row, text="自动打开输出文件夹",
                                 variable=self.auto_open_var, **_cb_kw(f, c, "bg"))
        _bind_toggle(cb_open, self.auto_open_var, True, c, "bg")
        t(cb_open, bg="bg", fg="text").pack(side="left", padx=(0, 14))
        self.auto_copy_var = tk.BooleanVar(value=self.config.get("auto_copy_text", False))
        cb_copy = tk.Checkbutton(auto_row, text="自动复制文稿到剪贴板",
                                 variable=self.auto_copy_var, **_cb_kw(f, c, "bg"))
        _bind_toggle(cb_copy, self.auto_copy_var, True, c, "bg")
        t(cb_copy, bg="bg", fg="text").pack(side="left", padx=(0, 14))

        # ── 底部按钮 ──
        bf = tk.Frame(self._sf, bg=c["bg"])
        bf.pack(fill="x", padx=28, pady=(24, 20))
        t(bf, bg="bg")
        cancel_btn = tk.Button(bf, text="取消", font=(f, 11),
                               bg=c["surface2"], fg=c["text_dim"], relief="flat", bd=0,
                               activebackground=c["surface3"], cursor="hand2",
                               command=self.win.destroy)
        cancel_btn.pack(side="right", ipady=6, ipadx=14)
        bind_hover(cancel_btn, "surface3", "surface2", colors=c)
        save_btn = tk.Button(bf, text="保存并关闭", font=(f, 11, "bold"),
                             bg=c["accent"], fg="white", relief="flat", bd=0,
                             activebackground=c["accent_dim"], cursor="hand2",
                             command=self._save)
        save_btn.pack(side="right", padx=(0, 8), ipady=6, ipadx=18)
        bind_hover(save_btn, "accent_dim", "accent", colors=c)

    def _section(self, title):
        c, f = self.C, self.F
        frame = tk.Frame(self._sf, bg=c["bg"])
        frame.pack(fill="x", padx=28, pady=(16, 0))
        t(frame, bg="bg")
        t(tk.Label(frame, text=title, font=(f, 12, "bold"),
                   fg=c["text"], bg=c["bg"]), bg="bg", fg="text").pack(anchor="w")
        t(tk.Frame(frame, bg=c["border"], height=1), bg="border").pack(fill="x", pady=(4, 8))

    def _make_field(self, label, value, editing_attr):
        c, f = self.C, self.F
        row = tk.Frame(self._sf, bg=c["bg"])
        row.pack(fill="x", padx=28, pady=4)
        t(row, bg="bg")
        t(tk.Label(row, text=label, font=(f, 11), width=10, anchor="w",
                   fg=c["text_dim"], bg=c["bg"]), bg="bg", fg="text_dim").pack(side="left")
        entry = tk.Entry(row, font=(f, 10), bg=c["entry_bg"], fg=c["entry_fg"],
                         insertbackground=c["text"], relief="flat", bd=0)
        t(entry, bg="entry_bg", fg="entry_fg").pack(
            side="left", fill="x", expand=True, ipady=6, ipadx=8, padx=(8, 4))
        entry.insert(0, value)
        entry.configure(state="readonly", readonlybackground=c["entry_bg"])
        edit_btn = tk.Button(row, text="✏", font=(f, 10), bg=c["surface2"], fg=c["text_dim"],
                             relief="flat", bd=0, activebackground=c["surface3"],
                             cursor="hand2", width=3)
        t(edit_btn, bg="surface2", fg="text_dim").pack(side="right")
        bind_hover(edit_btn, "surface3", "surface2", colors=c)

        def toggle():
            if getattr(self, editing_attr):
                entry.configure(state="readonly", readonlybackground=c["entry_bg"])
                edit_btn.configure(text="✏")
                setattr(self, editing_attr, False)
            else:
                entry.configure(state="normal", bg=c["entry_bg"])
                entry.focus_set()
                entry.select_range(0, "end")
                edit_btn.configure(text="✓")
                setattr(self, editing_attr, True)
        edit_btn.configure(command=toggle)
        return entry

    def _make_api_field(self):
        c, f = self.C, self.F
        row = tk.Frame(self._sf, bg=c["bg"])
        row.pack(fill="x", padx=28, pady=4)
        t(row, bg="bg")
        t(tk.Label(row, text="API Key", font=(f, 11), width=10, anchor="w",
                   fg=c["text_dim"], bg=c["bg"]), bg="bg", fg="text_dim").pack(side="left")
        self.api_entry = tk.Entry(row, font=(f, 10), bg=c["entry_bg"], fg=c["entry_fg"],
                                  insertbackground=c["text"], relief="flat", bd=0)
        t(self.api_entry, bg="entry_bg", fg="entry_fg").pack(
            side="left", fill="x", expand=True, ipady=6, ipadx=8, padx=(8, 4))
        self._refresh_api_display()

        self.eye_btn = tk.Button(row, text="👁", font=(f, 10), bg=c["surface2"], fg=c["text_dim"],
                                 relief="flat", bd=0, activebackground=c["surface3"],
                                 cursor="hand2", width=3)
        t(self.eye_btn, bg="surface2", fg="text_dim").pack(side="right", padx=(0, 2))
        bind_hover(self.eye_btn, "surface3", "surface2", colors=c)

        def toggle_eye():
            self._api_visible = not self._api_visible
            self._refresh_api_display()
            self.eye_btn.configure(text="🔒" if self._api_visible else "👁")
        self.eye_btn.configure(command=toggle_eye)

        self.api_edit_btn = tk.Button(row, text="✏", font=(f, 10), bg=c["surface2"],
                                      fg=c["text_dim"], relief="flat", bd=0,
                                      activebackground=c["surface3"], cursor="hand2", width=3)
        t(self.api_edit_btn, bg="surface2", fg="text_dim").pack(side="right")
        bind_hover(self.api_edit_btn, "surface3", "surface2", colors=c)

        def toggle_edit():
            if self._api_editing:
                self._actual_key = self.api_entry.get()
                self._api_editing = False
                self._refresh_api_display()
                self.api_edit_btn.configure(text="✏")
            else:
                self._api_editing = True
                self.api_entry.configure(state="normal", bg=c["entry_bg"])
                self.api_entry.delete(0, "end")
                self.api_entry.insert(0, self._actual_key)
                self.api_entry.focus_set()
                self.api_entry.select_range(0, "end")
                self.api_edit_btn.configure(text="✓")
        self.api_edit_btn.configure(command=toggle_edit)

    def _refresh_api_display(self):
        c = self.C
        self.api_entry.configure(state="normal")
        self.api_entry.delete(0, "end")
        if self._api_visible or self._api_editing:
            self.api_entry.insert(0, self._actual_key)
        else:
            self.api_entry.insert(0, mask_key(self._actual_key))
        if not self._api_editing:
            self.api_entry.configure(state="readonly", readonlybackground=c["entry_bg"])

    def _save(self):
        self.config["browser"] = self.browser_var.get()
        self.config["base_url"] = self.url_entry.get().strip()
        self.config["model"] = self.model_entry.get().strip()
        self.config["api_key"] = self._actual_key.strip()
        formats = []
        if self.md_var.get():
            formats.append("md")
        if self.docx_var.get():
            formats.append("docx")
        if self.pdf_var.get():
            formats.append("pdf")
        self.config["output_formats"] = formats or ["md"]
        self.config["delete_media"] = self.delete_var.get()
        self.config["auto_open_folder"] = self.auto_open_var.get()
        self.config["auto_copy_text"] = self.auto_copy_var.get()
        self.config["cookies"] = self.cookie_text.get("1.0", "end").strip()
        ensure_cookie_file(self.config["cookies"])
        save_config(self.config)
        self.on_save(self.config)
        self.win.destroy()
