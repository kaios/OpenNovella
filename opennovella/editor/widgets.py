"""Reusable tkinter widgets and helpers for the editor."""

from __future__ import annotations

import os
import shutil
import tkinter as tk
from tkinter import colorchooser, filedialog, simpledialog, ttk

from ..story import SCENE_NAME_RE, Story, StoryError

IMAGE_TYPES = [("Images", "*.png *.jpg *.jpeg *.gif *.webp *.bmp"), ("All files", "*.*")]
AUDIO_TYPES = [("Audio", "*.ogg *.mp3 *.wav *.flac"), ("All files", "*.*")]
FONT_TYPES = [("Fonts", "*.ttf *.otf"), ("All files", "*.*")]

NEW_SCENE = "+ New scene…"
HELP_FG = "#6b6880"

try:
    from PIL import Image, ImageTk
except ImportError:  # thumbnails fall back to tk's own PNG/GIF support
    Image = ImageTk = None


# --------------------------------------------------------------------------
# Assets
# --------------------------------------------------------------------------

def import_asset(story: Story, src: str, folder: str) -> str:
    """Return a project-relative path for ``src``, copying it into the project if needed."""
    if not src:
        return ""
    src = os.path.abspath(src)
    rel = story.relative(src)
    if not os.path.isabs(rel):
        return rel  # already inside the project
    dest_dir = os.path.join(story.path, folder)
    os.makedirs(dest_dir, exist_ok=True)
    base = os.path.basename(src.rstrip(os.sep))
    stem, ext = os.path.splitext(base)
    dest = os.path.join(dest_dir, base)
    n = 2
    while os.path.exists(dest):
        dest = os.path.join(dest_dir, f"{stem}_{n}{ext}")
        n += 1
    if os.path.isdir(src):
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)
    return story.relative(dest)


def load_thumbnail(path: str, max_size=(160, 160)):
    """A PhotoImage thumbnail for ``path`` (a file or a frame folder), or None."""
    if os.path.isdir(path):
        frames = sorted(f for f in os.listdir(path) if f.lower().endswith((".png", ".gif", ".jpg", ".jpeg")))
        if not frames:
            return None
        path = os.path.join(path, frames[0])
    if not os.path.isfile(path):
        return None
    try:
        if Image is not None:
            img = Image.open(path)
            img.thumbnail(max_size)
            return ImageTk.PhotoImage(img)
        img = tk.PhotoImage(file=path)
        factor = max(1, int(max(img.width() / max_size[0], img.height() / max_size[1]) + 0.999))
        return img.subsample(factor, factor)
    except Exception:
        return None


def ask_new_scene(parent, story: Story, suggestion: str = "") -> str | None:
    """Ask for a scene name and create it. Returns the name or None."""
    while True:
        name = simpledialog.askstring("New scene", "Name for the new scene\n(letters, numbers, spaces, - and _):",
                                      parent=parent, initialvalue=suggestion)
        if name is None:
            return None
        name = name.strip()
        try:
            return story.add_scene(name)
        except StoryError as exc:
            from tkinter import messagebox
            messagebox.showerror("New scene", str(exc), parent=parent)
            suggestion = name


def suggest_scene_name(story: Story, base: str = "scene") -> str:
    base = "".join(ch if SCENE_NAME_RE.match(ch) else "_" for ch in base.strip().lower()) or "scene"
    base = base.replace(" ", "_")[:24]
    name, n = base, 2
    while name in story.scenes:
        name = f"{base}_{n}"
        n += 1
    return name


# --------------------------------------------------------------------------
# Widgets
# --------------------------------------------------------------------------

class ToolTip:
    def __init__(self, widget, text):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _e=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, background="#fffbe6", relief="solid", borderwidth=1,
                 padx=6, pady=3, justify="left", wraplength=320).pack()

    def hide(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class AssetField(ttk.Frame):
    """Entry + Browse button (+ optional Folder button) + thumbnail preview."""

    def __init__(self, master, story: Story, kind: str, value: str = "", preview=True):
        super().__init__(master)
        self.story, self.kind = story, kind
        self.var = tk.StringVar(value=value or "")
        self.entry = ttk.Entry(self, textvariable=self.var, width=36)
        self.entry.grid(row=0, column=0, sticky="ew")
        col = 1
        ttk.Button(self, text="Browse…", command=self.browse).grid(row=0, column=col, padx=(4, 0))
        col += 1
        if kind == "animation":
            b = ttk.Button(self, text="Frames folder…", command=self.browse_folder)
            b.grid(row=0, column=col, padx=(4, 0))
            ToolTip(b, "Pick a folder of numbered images (001.png, 002.png, …) to use as an animation.")
            col += 1
        ttk.Button(self, text="✕", width=3, command=lambda: self.var.set("")).grid(row=0, column=col, padx=(4, 0))
        self.columnconfigure(0, weight=1)
        self.preview = None
        if preview and kind in ("image", "animation"):
            self.preview = ttk.Label(self)
            self.preview.grid(row=1, column=0, columnspan=col + 1, sticky="w", pady=(4, 0))
            self.var.trace_add("write", lambda *_: self.update_preview())
            self.update_preview()

    @property
    def folder(self):
        return {"audio": "audio", "font": "fonts"}.get(self.kind, "images")

    def browse(self):
        types = {"audio": AUDIO_TYPES, "font": FONT_TYPES}.get(self.kind, IMAGE_TYPES)
        start = os.path.join(self.story.path or "", self.folder)
        path = filedialog.askopenfilename(parent=self, filetypes=types,
                                          initialdir=start if os.path.isdir(start) else None)
        if path:
            self.var.set(import_asset(self.story, path, self.folder))

    def browse_folder(self):
        start = os.path.join(self.story.path or "", "images")
        path = filedialog.askdirectory(parent=self, initialdir=start if os.path.isdir(start) else None,
                                       title="Choose a folder of animation frames")
        if path:
            self.var.set(import_asset(self.story, path, "images"))

    def update_preview(self):
        if not self.preview:
            return
        img = load_thumbnail(self.story.resolve(self.var.get())) if self.var.get() else None
        self.preview.configure(image=img or "", text="" if img or not self.var.get() else "(no preview)")
        self.preview.image = img  # keep a reference

    def get(self):
        return self.var.get().strip()


class ColorField(ttk.Frame):
    def __init__(self, master, value="#ffffff"):
        super().__init__(master)
        self.var = tk.StringVar(value=value or "")
        ttk.Entry(self, textvariable=self.var, width=12).pack(side="left")
        self.swatch = tk.Label(self, width=3, relief="groove")
        self.swatch.pack(side="left", padx=4)
        ttk.Button(self, text="Pick…", command=self.pick).pack(side="left")
        self.var.trace_add("write", lambda *_: self.refresh())
        self.refresh()

    def refresh(self):
        try:
            self.swatch.configure(background=self.var.get()[:7] or "#ffffff")
        except tk.TclError:
            self.swatch.configure(background="#ffffff")

    def pick(self):
        try:
            initial = self.var.get()[:7] or None
            _rgb, hexv = colorchooser.askcolor(color=initial, parent=self)
        except tk.TclError:
            _rgb, hexv = colorchooser.askcolor(parent=self)
        if hexv:
            self.var.set(hexv)

    def get(self):
        return self.var.get().strip()


class SceneField(ttk.Combobox):
    """Pick a scene, or create a new one on the spot."""

    def __init__(self, master, story: Story, value="", allow_blank=True, blank_label=""):
        self.story = story
        self.allow_blank = allow_blank
        self.blank_label = blank_label
        super().__init__(master, state="readonly", width=34)
        self.refresh_values()
        self.set(value or self.blank_label if value or allow_blank else "")
        self.bind("<<ComboboxSelected>>", self._selected)

    def refresh_values(self):
        values = list(self.story.scenes) + [NEW_SCENE]
        if self.allow_blank:
            values.insert(0, self.blank_label)
        self["values"] = values

    def _selected(self, _e=None):
        if self.get() == NEW_SCENE:
            name = ask_new_scene(self, self.story, suggest_scene_name(self.story))
            self.refresh_values()
            self.set(name or (self.blank_label if self.allow_blank else ""))
            self.event_generate("<<SceneCreated>>")

    def value(self):
        v = self.get()
        return "" if v in (self.blank_label, NEW_SCENE) else v


class ScrolledFrame(ttk.Frame):
    """A frame with a vertical scrollbar, for long forms."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
