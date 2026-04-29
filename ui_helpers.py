import tkinter as tk
from tkinter import font as tkfont


def detect_font(root):
    available = tkfont.families(root)
    if "MiSans" in available:
        return "MiSans"
    return "Microsoft YaHei UI"


def t(widget, bg=None, fg=None, border=None):
    if bg:
        widget._tbg = bg
    if fg:
        widget._tfg = fg
    if border:
        widget._tborder = border
    return widget


def bind_hover(btn, hover_bg, normal_bg, hover_fg=None, normal_fg=None, colors=None):
    btn._hover_bg = hover_bg
    btn._hover_fg = hover_fg
    btn._normal_bg = normal_bg
    btn._normal_fg = normal_fg
    btn._hover_colors = colors

    def _apply(key_fg, key_bg):
        c = btn._hover_colors
        if not c:
            return
        try:
            kw = {'bg': c[key_bg]}
            if key_fg:
                kw['fg'] = c[key_fg]
            btn.configure(**kw)
        except (tk.TclError, KeyError):
            pass

    btn.bind("<Enter>", lambda e: _apply(btn._hover_fg, btn._hover_bg))
    btn.bind("<Leave>", lambda e: _apply(btn._normal_fg, btn._normal_bg))


def _rb_kw(f, c, parent_bg_key="bg"):
    """Radiobutton 关键字参数 — 固定宽度，未选中底色匹配父容器"""
    bg_val = c[parent_bg_key]
    return dict(
        font=(f, 10), bg=bg_val, fg=c["text"],
        selectcolor=c["accent"],
        activebackground=bg_val, activeforeground=c["text"],
        highlightthickness=0,
        indicatoron=False,
        width=12,
        padx=2,
    )


def _cb_kw(f, c, parent_bg_key="bg"):
    """Checkbutton 关键字参数 — 不限宽度，自适应文字长度"""
    bg_val = c[parent_bg_key]
    return dict(
        font=(f, 10), bg=bg_val, fg=c["text"],
        selectcolor=c["accent"],
        activebackground=bg_val, activeforeground=c["text"],
        highlightthickness=0,
        indicatoron=False,
        padx=2,
    )


def _bind_toggle(widget, variable, selected_value, c, parent_bg_key="bg"):
    """
    根据变量状态切换 widget 外观：
    - 选中 → accent 底色（橙色）+ 白字
    - 未选中 → 父容器底色（透明）+ 主题文字色
    """
    widget._ttoggle_var = variable
    widget._ttoggle_val = selected_value
    widget._ttoggle_bg_key = parent_bg_key
    widget._ttoggle_c = c

    def _update(*_args):
        colors = widget._ttoggle_c
        try:
            if variable.get() == selected_value:
                widget.configure(
                    bg=colors["accent"], fg="white",
                    activebackground=colors.get("accent_dim", colors["accent"]),
                    activeforeground="white")
            else:
                parent_bg = colors[parent_bg_key]
                widget.configure(
                    bg=parent_bg, fg=colors["text"],
                    activebackground=parent_bg,
                    activeforeground=colors["text"])
        except tk.TclError:
            pass

    variable.trace_add("write", _update)
    _update()
